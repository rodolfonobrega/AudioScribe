const { app, BrowserWindow, Tray, Menu, ipcMain, globalShortcut, safeStorage } = require('electron');
const path = require('path');
const net = require('net');
const crypto = require('crypto');
const fs = require('fs');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const { registerProfileShortcuts: attemptProfileShortcutRegistration } = require('./src/profile_shortcuts');

// E2E tests launch the real Electron shell but deliberately replace operating
// system integration and the Python sidecar with deterministic fakes. This
// keeps UI tests hermetic: no microphone prompt, global shortcut, API key, or
// user configuration is touched.
const IS_E2E = process.env.AUDIOSCRIBE_E2E === '1';
const IS_PHYSICAL_HOTKEY_E2E = process.env.AUDIOSCRIBE_E2E_PHYSICAL_HOTKEY === '1';

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let pythonProcess = null;
let socketClient = null;
let socketBuffer = '';
let sidecarStdoutBuffer = '';
let engineSession = null;
let enginePort = null;
let engineRequestSequence = 0;
let engineInboundSequence = 0;
let engineReady = false;
const pendingRequests = new Map();
let reconnectTimer = null;
let isRecording = false;
let lastEngineEvent = { event: 'engine_starting', data: { code: 'engine_starting' } };
let nativeHotkeys = null;
let pendingRendererStart = null;
let rendererStartSequence = 0;
let pushToTalkSafetyTimer = null;
let activeProfiles = [];
let shortcutCaptureActive = false;
const validatedProfileProcessors = new Set();
// Default to F9. The native JS hook also supports modifier-only chords such as Ctrl+Win.
let currentShortcut = 'F9';
// Activation mode: 'toggle' (tap once to start, tap again to stop) or 'push_to_talk' (hold)
let activationMode = 'toggle';

function stableJson(value) {
    if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
    if (value && typeof value === 'object') {
        return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
    }
    return JSON.stringify(value);
}

function requestSignature(message) {
    const material = [
        'request',
        String(message.protocol_version),
        String(message.sequence),
        String(message.id || ''),
        String(message.command || ''),
        stableJson(message.params || {}),
    ].join(':');
    return crypto.createHmac('sha256', engineSession).update(material, 'utf8').digest('hex');
}

function verifyEngineMessage(message, direction) {
    if (!engineSession || message?.protocol_version !== 3 || !Number.isInteger(message.sequence) || message.sequence <= engineInboundSequence) return false;
    const auth = message.auth;
    if (typeof auth !== 'string' || typeof message.payload !== 'string') return false;
    const material = `${direction}:${message.protocol_version}:${message.sequence}:${message.payload}`;
    const expected = crypto.createHmac('sha256', engineSession).update(material, 'utf8').digest('hex');
    if (auth.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(auth), Buffer.from(expected))) return false;
    engineInboundSequence = message.sequence;
    return true;
}

function getOverlayShortcut() {
    const sc = currentShortcut || 'F9';
    return String(sc).replace(/Control/g, 'Ctrl').replace(/Super/g, 'Win').replace(/windows/gi, 'Win').replace(/\s*\+\s*/g, ' + ');
}

function configureNativeHotkey() {
    try {
        // The native hook owns the main shortcut in both modes. Electron's
        // globalShortcut rejects modifier-only chords such as Control+Super,
        // while uIOhook can observe the Windows key and its key-up edge.
        if (!nativeHotkeys) nativeHotkeys = require('./src/native_hotkeys');
        const defaultProfile = activeProfiles.find((profile) => profile?.isDefault && profile.enabled) || null;
        return nativeHotkeys.configure(currentShortcut, {
            onPress: () => {
                if (shortcutCaptureActive) return;
                if (activationMode === 'push_to_talk') startRecording(defaultProfile);
                else toggleRecording(defaultProfile);
            },
            onRelease: () => {
                if (shortcutCaptureActive) return;
                if (activationMode === 'push_to_talk') stopRecording(defaultProfile);
            },
        });
    } catch (error) {
        console.error('[Electron] Native hotkey hook unavailable:', error);
        return { status: 'error', code: 'native_hotkey_unavailable', error: error.message };
    }
}

function assetPath(name) {
    return app.isPackaged
        ? path.join(process.resourcesPath, 'assets', name)
        : path.join(__dirname, '..', 'assets', name);
}

function publishEngineEvent(event, data) {
    lastEngineEvent = { event, data };
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('engine-event', lastEngineEvent);
}

function providerConfigPath() {
    return path.join(app.getPath('userData'), 'provider-config.json.enc');
}

function secureStorageAvailable() {
    if (!safeStorage.isEncryptionAvailable()) return false;
    // Linux can report encryption available while using Electron's basic_text
    // backend. Provider credentials must never silently fall back to plaintext.
    return typeof safeStorage.getSelectedStorageBackend !== 'function'
        || safeStorage.getSelectedStorageBackend() !== 'basic_text';
}

function loadProviderConfig() {
    try {
        if (!secureStorageAvailable()) return null;
        const encrypted = fs.readFileSync(providerConfigPath(), 'utf8');
        return JSON.parse(safeStorage.decryptString(Buffer.from(encrypted, 'base64')));
    } catch (error) {
        return null;
    }
}

function saveProviderConfig(config) {
    if (!secureStorageAvailable()) {
        throw new Error('Secure system credential storage is unavailable. Configure a supported keychain before saving provider credentials.');
    }
    fs.mkdirSync(path.dirname(providerConfigPath()), { recursive: true });
    const serialized = JSON.stringify(config);
    const value = safeStorage.encryptString(serialized).toString('base64');
    fs.writeFileSync(providerConfigPath(), value, { encoding: 'utf8', mode: 0o600 });
}

function profilePrompt(profile) {
    return String(profile?.prompt || '').trim();
}

function llmValidationRequest(config) {
    const llm = config?.llm;
    if (!llm?.enabled) {
        return {
            status: 'error',
            code: 'profile_llm_not_configured',
            error: 'This profile requires post-processing, but no post-processing model is enabled in Settings.',
        };
    }
    if (!String(llm.provider || '').trim() || !String(llm.model || '').trim()) {
        return {
            status: 'error',
            code: 'profile_llm_not_configured',
            error: 'This profile requires a configured post-processing provider and model.',
        };
    }
    const params = {
        type: 'llm',
        provider: String(llm.provider).trim(),
        model: String(llm.model).trim(),
        api_key: llm.api_key || 'configured',
        base_url: llm.base_url || '',
        allow_local: String(llm.provider).trim().toLowerCase() === 'ollama',
    };
    // Do not retain or log credentials. The fingerprint exists only for this
    // process so a validated configuration is not charged on every hotkey.
    const fingerprint = crypto.createHash('sha256').update(stableJson({
        provider: params.provider,
        model: params.model,
        api_key: params.api_key,
        base_url: params.base_url,
    })).digest('hex');
    return { status: 'ok', params, fingerprint };
}

async function ensureProfileProcessingReady(profile) {
    if (!profilePrompt(profile)) return { status: 'ok' };
    const request = llmValidationRequest(loadProviderConfig());
    if (request.status !== 'ok') return request;
    if (validatedProfileProcessors.has(request.fingerprint)) return { status: 'ok' };

    const result = await sendEngineRequest('test_connection', request.params, 15000);
    if (result?.status === 'ok') {
        validatedProfileProcessors.add(request.fingerprint);
        return { status: 'ok' };
    }
    return {
        status: 'error',
        code: 'profile_llm_unavailable',
        error: result?.error || 'The post-processing model could not complete its validation request.',
    };
}

function hardenRenderer(webContents) {
    webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    webContents.on('will-navigate', (event) => event.preventDefault());
    webContents.on('will-attach-webview', (event) => event.preventDefault());
    webContents.session.setPermissionRequestHandler((contents, permission, callback) => {
        callback(permission === 'media' && contents.getURL().startsWith('file://'));
    });
}

function trustedMainSender(event) {
    return Boolean(mainWindow && !mainWindow.isDestroyed() && event?.sender === mainWindow.webContents);
}

function untrustedSenderResult(event) {
    return trustedMainSender(event) ? null : { status: 'error', code: 'untrusted_renderer', error: 'Request rejected from an untrusted renderer.' };
}

function createOverlayWindow() {
    const { screen } = require('electron');
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width, height } = primaryDisplay.workAreaSize;

    overlayWindow = new BrowserWindow({
        width: 380,
        height: 80,
        x: Math.round((width - 380) / 2),
        y: Math.round((height - 80) / 2),
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        focusable: false,
        skipTaskbar: true,
        resizable: false,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
        }
    });

    hardenRenderer(overlayWindow.webContents);
    overlayWindow.loadFile(path.join(__dirname, 'ui', 'overlay.html'));
}

function setupAutoUpdater() {
    autoUpdater.autoDownload = false;

    autoUpdater.on('update-available', (info) => {
        if (mainWindow) {
            mainWindow.webContents.send('engine-event', {
                event: 'update_status',
                data: { available: true, info }
            });
        }
    });

    autoUpdater.on('update-not-available', () => {
        if (mainWindow) {
            mainWindow.webContents.send('engine-event', {
                event: 'update_status',
                data: { available: false }
            });
        }
    });

    autoUpdater.on('error', (err) => {
        console.error('[AutoUpdater Error]:', err);
    });
}

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 920,
        minWidth: 760,
        minHeight: 600,
        show: false,
        title: "AudioScribe Desktop",
        webPreferences: {
            preload: path.join(__dirname, IS_E2E ? 'preload_e2e.js' : 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
        }
    });

    hardenRenderer(mainWindow.webContents);
    mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });
    mainWindow.webContents.on('did-finish-load', () => {
        if (lastEngineEvent) mainWindow.webContents.send('engine-event', lastEngineEvent);
    });

    let hasShownTrayNotification = false;

    mainWindow.on('close', (event) => {
        if (!app.isQuitting) {
            event.preventDefault();
            mainWindow.hide();

            if (!hasShownTrayNotification) {
                hasShownTrayNotification = true;
                const { Notification } = require('electron');
                if (tray && tray.displayBalloon) {
                    tray.displayBalloon({
                        title: 'AudioScribe is running in background',
                        content: 'AudioScribe is still active! Press your shortcut (e.g. F9) anytime to dictate. Right-click tray icon to quit.'
                    });
                } else if (Notification.isSupported()) {
                    new Notification({
                        title: 'AudioScribe Active in Tray 🎙️',
                        body: 'AudioScribe is running in the background. Press your shortcut to dictate anytime or right-click tray icon to quit.'
                    }).show();
                }
            }
        }
        return false;
    });
}

function createTray() {
    // Basic tray setup
    tray = new Tray(assetPath('audioscribe-icon.png'));
    
    const contextMenu = Menu.buildFromTemplate([
        { label: 'AudioScribe Active', enabled: false },
        { type: 'separator' },
        { label: 'Toggle Recording (Ctrl + Win)', click: () => toggleRecording() },
        { label: 'Open Settings', click: () => mainWindow.show() },
        { type: 'separator' },
        { label: 'Quit', click: () => {
            app.isQuitting = true;
            app.quit();
        }}
    ]);

    tray.setToolTip('AudioScribe - Press Ctrl + Win to Record');
    tray.setContextMenu(contextMenu);

    tray.on('double-click', () => {
        mainWindow.show();
    });
}

function createApplicationMenu() {
    const menu = Menu.buildFromTemplate([
        {
            label: 'File',
            submenu: [
                {
                    label: 'Exit',
                    accelerator: process.platform === 'darwin' ? 'Command+Q' : 'Alt+F4',
                    click: () => {
                        app.isQuitting = true;
                        app.quit();
                    },
                },
            ],
        },
        ...(!app.isPackaged ? [{
            label: 'View',
            submenu: [{ role: 'reload' }, { role: 'toggledevtools' }],
        }] : []),
    ]);
    Menu.setApplicationMenu(menu);
}

function connectToPythonServer(port = enginePort) {
    if (!Number.isInteger(port) || port < 1 || port > 65535) return;
    if (socketClient && !socketClient.destroyed) return;
    socketBuffer = '';
    socketClient = net.connect({ port, host: '127.0.0.1' }, () => {
        console.log('[Electron] Connected to AudioScribe Python Server.');
        publishEngineEvent('engine_status', { code: 'engine_connected', message: 'Engine connected' });
        sendStoredProviderConfig().then((result) => {
            if (result?.status === 'ok') {
                engineReady = true;
                registerAllShortcuts();
                publishEngineEvent('engine_ready', { code: 'engine_ready', message: 'Engine ready for commands' });
            } else {
                publishEngineEvent('engine_error', {
                    code: 'provider_config_failed',
                    title: 'Provider configuration could not be applied',
                    message: result?.error || 'The engine connected, but the saved provider configuration was rejected.',
                    remediation: 'Open Settings, review the providers and click Save Settings.',
                });
            }
        });
    });

    socketClient.on('data', (data) => {
        socketBuffer += data.toString();
        const lines = socketBuffer.split('\n');
        socketBuffer = lines.pop();

        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const envelope = JSON.parse(line.trim());
                const eventData = JSON.parse(envelope.payload);
                const direction = eventData.event ? 'event' : 'response';
                if (!verifyEngineMessage(envelope, direction)) {
                    console.error('[Electron] Rejected unauthenticated engine message.');
                    socketClient?.destroy();
                    return;
                }
                if (eventData.id && pendingRequests.has(eventData.id)) {
                    const request = pendingRequests.get(eventData.id);
                    pendingRequests.delete(eventData.id);
                    clearTimeout(request.timer);
                    request.resolve(eventData);
                    continue;
                }

                if (mainWindow) {
                    mainWindow.webContents.send('engine-event', { event: eventData.event, data: eventData.data });
                }

                // Update the overlay based on engine state. MediaRecorder itself is
                // started/stopped only by the Electron recording functions above.
                if (overlayWindow) {
                    if (eventData.event === 'status_changed') {
                        const status = eventData.data?.status;
                        if (status === 'recording') {
                            overlayWindow.showInactive();
                            overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1, shortcut: getOverlayShortcut() });
                        } else if (status === 'processing') {
                            overlayWindow.webContents.send('update-overlay-state', { status: 'processing', shortcut: getOverlayShortcut() });
                        } else if (status === 'ready') {
                            overlayWindow.webContents.send('update-overlay-state', { status: 'ready', shortcut: getOverlayShortcut() });
                        }
                    } else if (eventData.event === 'transcription_result') {
                        const text = eventData.data?.text || '';
                        overlayWindow.webContents.send('update-overlay-state', {
                            status: 'done',
                            text: eventData.data?.is_error ? (eventData.data.error || 'Transcription failed.') : text,
                            isError: Boolean(eventData.data?.is_error),
                            isSilent: Boolean(eventData.data?.is_silent),
                            shortcut: getOverlayShortcut(),
                        });
                        
                        if (text && text.trim()) {
                            const NativeOutputHandler = require('./src/output');
                            NativeOutputHandler.copyAndPaste(text).then((result) => {
                                if (result?.status === 'copied' && result?.error) {
                                    console.warn('[AudioScribe] Automatic paste failed; text remains in clipboard:', result.error);
                                }
                            });
                        }

                        setTimeout(() => {
                            overlayWindow.hide();
                        }, 1500);
                    }
                }
            } catch (err) {
                console.error('[Electron] Error parsing JSON event:', err);
            }
        }
    });

    socketClient.on('error', (err) => {
        console.log('[Electron] Engine connection error:', err.message);
    });

    socketClient.on('close', () => {
        engineReady = false;
        publishEngineEvent('engine_error', {
            code: 'engine_offline',
            title: 'Engine disconnected',
            message: 'The AudioScribe engine is not running. Recording is unavailable until it reconnects.',
            remediation: 'Click “Try again”. In development, make sure Python 3.10+ and the project dependencies are installed.',
        });
        for (const [id, request] of pendingRequests) {
            clearTimeout(request.timer);
            request.resolve({ status: 'error', code: 'engine_offline', error: 'Python engine offline' });
            pendingRequests.delete(id);
        }
        socketClient = null;
        if (!reconnectTimer) {
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                connectToPythonServer(enginePort);
            }, 2000);
        }
    });
}

function sendEngineRequest(command, params = {}, timeoutMs = 10000) {
    return new Promise((resolve) => {
        if (!engineSession || !socketClient || socketClient.destroyed) {
            resolve({ status: 'error', code: 'engine_offline', error: 'Python engine offline' });
            return;
        }
        const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
        const timer = setTimeout(() => {
            pendingRequests.delete(id);
            resolve({ status: 'error', code: 'engine_timeout', error: `Engine timeout for ${command}` });
        }, timeoutMs);
        pendingRequests.set(id, { resolve, timer });
        const request = {
        protocol_version: 3,
            id,
            sequence: ++engineRequestSequence,
            command,
            params,
        };
        request.auth = requestSignature(request);
        socketClient.write(JSON.stringify(request) + '\n');
    });
}

async function sendStoredProviderConfig() {
    const config = loadProviderConfig();
    if (config) return sendEngineRequest('configure_provider', config);
    return { status: 'ok' };
}

function launchPythonSidecar() {
    let executable;
    let args;

    if (app.isPackaged) {
        const binName = process.platform === 'win32' ? 'audioscribe_engine.exe' : 'audioscribe_engine';
        executable = path.join(process.resourcesPath, 'bin', binName);
        args = ['--server', '--port', '0', '--session-token-stdin'];
        if (!fs.existsSync(executable)) {
            console.error('[Electron] Packaged engine binary is missing. Desktop app will remain offline.');
            publishEngineEvent('engine_error', {
                code: 'engine_binary_missing',
                title: 'Engine missing from this installation',
                message: 'The desktop engine was not included in this installation.',
                remediation: 'Install a complete AudioScribe release or rebuild the installer so the Python sidecar is included.',
            });
            return;
        }
    } else {
        executable = process.platform === 'win32' ? 'python' : 'python3';
        const scriptPath = path.join(__dirname, '..', 'main.py');
        args = [scriptPath, '--server', '--port', '0', '--session-token-stdin'];
    }

    try {
        engineSession = crypto.randomBytes(32).toString('base64url');
        engineReady = false;
        enginePort = null;
        engineRequestSequence = 0;
        engineInboundSequence = 0;
        sidecarStdoutBuffer = '';
        pythonProcess = spawn(executable, args, {
            cwd: app.isPackaged ? process.resourcesPath : path.join(__dirname, '..'),
            stdio: ['pipe', 'pipe', 'pipe'],
        });
        pythonProcess.stdin.write(`${engineSession}\n`);
        pythonProcess.stdin.end();
        pythonProcess.on('error', (err) => {
            console.error('[Electron] Python engine failed to start:', err.message);
            const missingPython = err.code === 'ENOENT';
            publishEngineEvent('engine_error', {
                code: missingPython ? 'python_missing' : 'engine_spawn_failed',
                title: missingPython ? 'Python is not installed' : 'Engine could not start',
                message: missingPython ? 'AudioScribe could not find Python on this computer.' : `The engine could not start: ${err.message}`,
                remediation: missingPython
                    ? 'Install Python 3.10 or newer, then run “pip install -r requirements.txt” in the project folder and click “Try again”.'
                    : 'Open Diagnostics for the technical error, fix the reported issue, and click “Try again”.',
            });
        });
    } catch (e) {
        console.error('[Electron] Python engine failed to start:', e.message);
    }

    pythonProcess.stdout.on('data', (data) => {
        sidecarStdoutBuffer += data.toString('utf8');
        const lines = sidecarStdoutBuffer.split(/\r?\n/);
        sidecarStdoutBuffer = lines.pop();
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const ready = JSON.parse(line);
                if (ready.event === 'desktop_ipc_ready' && ready.protocol_version === 3 && Number.isInteger(ready.port)) {
                    enginePort = ready.port;
                    connectToPythonServer(enginePort);
                    continue;
                }
            } catch (_) {
                // The sidecar stdout is a protocol channel. Ignore incidental
                // library output instead of treating it as desktop diagnostics.
            }
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Engine Error]: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`[Python Engine] exited with code ${code}`);
        if (code !== 0) publishEngineEvent('engine_error', {
            code: 'engine_exited',
            title: 'Engine stopped unexpectedly',
            message: `The engine stopped before AudioScribe could connect (exit code ${code}).`,
            remediation: 'Open Diagnostics, check the technical details, then click “Try again”.',
        });
    });

}

ipcMain.handle('retry-engine', async () => {
    if (pythonProcess && pythonProcess.exitCode === null && !pythonProcess.killed) {
        connectToPythonServer();
        return { status: 'ok', message: 'Trying to reconnect to the engine.' };
    }
    publishEngineEvent('engine_starting', { code: 'engine_starting', message: 'Starting the AudioScribe engine...' });
    launchPythonSidecar();
    return { status: 'ok', message: 'Starting the AudioScribe engine.' };
});

ipcMain.handle('transcribe-audio-buffer', async (event, { audioBase64, profile }) => {
    if (!audioBase64) return { status: 'error', error: 'No audio data' };
    if (overlayWindow) {
        overlayWindow.webContents.send('update-overlay-state', { status: 'processing', shortcut: getOverlayShortcut() });
    }
    // Use a 120s timeout: STT + LLM post-processing can take significantly longer than the
    // default 10s engine request timeout, especially for local models or slow connections.
    const response = await sendEngineRequest('transcribe_audio', { audio_base64: audioBase64, profile }, 120000);
    
    // Successful requests already produce a transcription_result from the
    // Python orchestrator. Only synthesize an event for failures that happen
    // before the orchestrator can emit one (invalid payload, timeout, etc.).
    if (response?.status !== 'ok') {
        publishEngineEvent('transcription_result', {
            text: '',
            latency_ms: response?.latency_ms || 0,
            is_silent: false,
            is_error: true,
            error: response?.error || 'Transcription failed.',
        });
    }
    return response;
});

ipcMain.handle('start-recording', async (event, profile) => {
    const rejected = untrustedSenderResult(event);
    return rejected || startRecording(profile || null);
});

ipcMain.handle('stop-recording', async (event, profile) => {
    const rejected = untrustedSenderResult(event);
    return rejected || stopRecording(profile || null);
});

ipcMain.handle('toggle-recording', async (event, profile) => {
    const rejected = untrustedSenderResult(event);
    return rejected || toggleRecording(profile || null);
});

ipcMain.on('native-recording-started', (event, result = {}) => {
    if (!trustedMainSender(event)) return;
    if (!pendingRendererStart) return;
    if (result.requestId && result.requestId !== pendingRendererStart.requestId) return;
    const pending = pendingRendererStart;
    pendingRendererStart = null;
    pending.resolve(result);
});

async function startRecording(profile = null) {
    if (isRecording) return pendingRendererStart?.promise || { status: 'ok', recording: true, already_recording: true };
    if (!engineReady) {
        const error = 'The AudioScribe engine is offline. Recording is unavailable until it reconnects.';
        publishEngineEvent('error', { code: 'engine_offline', stage: 'recording', message: error });
        return { status: 'error', code: 'engine_offline', error };
    }
    const processingReady = await ensureProfileProcessingReady(profile);
    if (processingReady.status !== 'ok') {
        publishEngineEvent('error', {
            code: processingReady.code,
            stage: 'post_processing',
            message: processingReady.error,
        });
        return processingReady;
    }
    isRecording = true;
    const requestId = `recording-${Date.now()}-${++rendererStartSequence}`;
    let resolveStart;
    const promise = new Promise((resolve) => { resolveStart = resolve; });
    const timer = setTimeout(() => {
        if (pendingRendererStart?.requestId !== requestId) return;
        pendingRendererStart = null;
        resolveStart({ status: 'error', code: 'renderer_recording_timeout', error: 'The microphone recorder did not start in time.' });
    }, 10000);
    pendingRendererStart = { requestId, promise, resolve: (result) => { clearTimeout(timer); resolveStart(result); } };

    if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('native-start-recording', { requestId });
    } else {
        pendingRendererStart = null;
        clearTimeout(timer);
        resolveStart({ status: 'error', code: 'renderer_unavailable', error: 'The desktop window is not ready to record.' });
    }

    const started = await promise;
    if (pendingRendererStart?.requestId === requestId) pendingRendererStart = null;
    if (started?.status !== 'ok') {
        isRecording = false;
        if (pushToTalkSafetyTimer) clearTimeout(pushToTalkSafetyTimer);
        pushToTalkSafetyTimer = null;
        publishEngineEvent('status_changed', { status: 'ready' });
        publishEngineEvent('error', {
            code: started?.code || 'recording_start_failed',
            stage: 'recording',
            message: started?.error || 'Could not start the microphone recorder.',
        });
        return started;
    }

    publishEngineEvent('status_changed', { status: 'recording' });
    if (activationMode === 'push_to_talk') {
        if (pushToTalkSafetyTimer) clearTimeout(pushToTalkSafetyTimer);
        // Match OpenWhispr's defensive maximum: a lost key-up cannot leave the
        // microphone recording forever.
        pushToTalkSafetyTimer = setTimeout(() => {
            pushToTalkSafetyTimer = null;
            if (isRecording) stopRecording(profile);
        }, 5 * 60 * 1000);
    }
    if (overlayWindow) {
        overlayWindow.showInactive();
        overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1, shortcut: profile?.shortcut || currentShortcut });
    }
    return { status: 'ok', recording: true };
}

async function stopRecording(profile = null) {
    if (pushToTalkSafetyTimer) clearTimeout(pushToTalkSafetyTimer);
    pushToTalkSafetyTimer = null;
    if (!isRecording && !pendingRendererStart) return { status: 'ok', recording: false, already_stopped: true };
    if (pendingRendererStart) {
        const started = await pendingRendererStart.promise;
        if (started?.status !== 'ok') {
            isRecording = false;
            pendingRendererStart = null;
            return started;
        }
    }
    if (!isRecording) return { status: 'ok', recording: false, already_stopped: true };
    isRecording = false;
    if (mainWindow && mainWindow.webContents) mainWindow.webContents.send('native-stop-recording', profile);
    publishEngineEvent('status_changed', { status: 'processing' });
    if (overlayWindow) {
        overlayWindow.webContents.send('update-overlay-state', { status: 'processing', shortcut: profile?.shortcut || currentShortcut });
    }
    return { status: 'accepted', recording: false };
}

async function toggleRecording(profile = null) {
    let result;
    if (activationMode === 'push_to_talk') {
        // Press/release edges are delivered by the native JavaScript hook.
        // Keep this tray/menu action useful as a safe one-shot start/stop.
        if (isRecording) result = await stopRecording(profile);
        else result = await startRecording(profile);
    } else {
        // Toggle mode: tap once to start, tap again to stop.
        if (isRecording) {
            result = await stopRecording(profile);
        } else {
            result = await startRecording(profile);
        }
    }
    if (result?.status === 'error') return result;
    return { status: 'ok', recording: isRecording };
}

function registerAllShortcuts() {
    globalShortcut.unregisterAll();
    return attemptProfileShortcutRegistration({
        globalShortcut,
        profiles: activeProfiles,
        currentShortcut,
        onProfileShortcut: (profile) => toggleRecording(profile),
    });
}

async function registerShortcut(newKey) {
    try {
        const previous = currentShortcut;
        currentShortcut = newKey;
        const res = registerAllShortcuts();
        const nativeResult = configureNativeHotkey();
        if (nativeResult?.status !== 'ok' || res.status !== 'ok') {
            currentShortcut = previous;
            registerAllShortcuts();
            configureNativeHotkey();
            return { status: 'error', error: nativeResult?.error || res.failed?.[0]?.error || `Could not register key '${newKey}'. It may already be in use by another application.` };
        }
        return { status: 'ok', shortcut: newKey, registered: res.registered };
    } catch (err) {
        return { status: 'error', error: err.message };
    }
}

app.whenReady().then(() => {
    createApplicationMenu();
    createMainWindow();
    if (IS_E2E) {
        // Keep the E2E shell hermetic, except for the dedicated Windows test
        // that verifies the OS -> native listener -> Electron -> renderer path.
        if (IS_PHYSICAL_HOTKEY_E2E) {
            engineReady = true;
            configureNativeHotkey();
        }
        return;
    }
    createOverlayWindow();
    createTray();
    const hotkeyResult = configureNativeHotkey();
    if (hotkeyResult?.status !== 'ok') {
        publishEngineEvent('engine_error', {
            code: hotkeyResult?.code || 'native_hotkey_unavailable',
            title: 'Global hotkeys unavailable',
            message: hotkeyResult?.error || 'AudioScribe could not initialize the native keyboard listener.',
            remediation: 'Choose another shortcut or reinstall the desktop application.',
        });
    }
    launchPythonSidecar();

    // Register profile shortcuts immediately. The main dictation shortcut is
    // installed by the native JavaScript hook above.
    registerAllShortcuts();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
});

function registerProfileShortcuts(profiles) {
    const previousProfiles = activeProfiles;
    const candidateProfiles = Array.isArray(profiles) ? profiles : [];
    activeProfiles = candidateProfiles;
    const result = registerAllShortcuts();
    if (result.status !== 'ok') {
        // Registering is all-or-nothing. A rejected change must not silently
        // deactivate the shortcuts that worked before the edit.
        activeProfiles = previousProfiles;
        registerAllShortcuts();
    }
    return {
        status: result.status,
        count: result.registered.length,
        registered: result.registered,
        failed: result.failed,
        error: result.status !== 'ok'
            ? result.failed.map((item) => item.error || `Could not register ${item.shortcut}.`).join(' ')
            : undefined,
    };
}

ipcMain.handle('update-profiles', async (event, profiles) => {
    return registerProfileShortcuts(profiles);
});

ipcMain.handle('begin-hotkey-capture', async () => {
    shortcutCaptureActive = true;
    // A registered global shortcut is consumed before the renderer receives
    // keydown, so temporarily release profile accelerators while recording.
    globalShortcut.unregisterAll();
    return { status: 'ok' };
});

ipcMain.handle('end-hotkey-capture', async (event, profiles) => {
    shortcutCaptureActive = false;
    return registerProfileShortcuts(profiles);
});

ipcMain.handle('set-activation-mode', async (event, mode) => {
    const previousMode = activationMode;
    activationMode = mode === 'push_to_talk' ? 'push_to_talk' : 'toggle';
    const shortcutResult = registerAllShortcuts();
    const nativeResult = configureNativeHotkey();
    if (nativeResult?.status !== 'ok' || shortcutResult.status !== 'ok') {
        activationMode = previousMode;
        registerAllShortcuts();
        configureNativeHotkey();
        return { status: 'error', error: nativeResult?.error || shortcutResult.failed?.[0]?.error || 'Could not register the desktop shortcut in toggle mode.' };
    }
    return { ...nativeResult, mode: activationMode };
});

ipcMain.handle('register-shortcut', async (event, key) => {
    return registerShortcut(key);
});

ipcMain.handle('get-provider-config', async (event) => {
    const rejected = untrustedSenderResult(event);
    if (rejected) return rejected;
    const config = loadProviderConfig();
    if (!config) return { status: 'ok', config: null };
    const safeConfig = {
        ...config,
        api_key: config.api_key ? 'configured' : '',
        transcription: config.transcription ? { ...config.transcription, api_key: config.transcription.api_key ? 'configured' : '' } : undefined,
        llm: config.llm ? { ...config.llm, api_key: config.llm.api_key ? 'configured' : '' } : undefined,
    };
    return {
        status: 'ok',
        config: safeConfig,
    };
});

ipcMain.handle('save-provider-config', async (event, config) => {
    const rejected = untrustedSenderResult(event);
    if (rejected) return rejected;
    const current = loadProviderConfig() || {};
    const next = {
        ...current,
        ...config,
        transcription: { ...(current.transcription || {}), ...(config.transcription || {}) },
        llm: { ...(current.llm || {}), ...(config.llm || {}) },
    };
    if (!Object.prototype.hasOwnProperty.call(config.transcription || {}, 'api_key')) {
        next.transcription.api_key = current.transcription?.api_key || current.api_key || null;
    }
    if (next.transcription.api_key === 'configured') {
        next.transcription.api_key = current.transcription?.api_key || current.api_key || null;
    }
    if (!Object.prototype.hasOwnProperty.call(config.llm || {}, 'api_key')) {
        next.llm.api_key = current.llm?.api_key || current.api_key || null;
    }
    if (next.llm.api_key === 'configured') {
        next.llm.api_key = current.llm?.api_key || current.api_key || null;
    }
    if (config.api_key === 'configured' || !Object.prototype.hasOwnProperty.call(config, 'api_key')) {
        next.api_key = current.api_key || null;
    }

    // Saving an enabled post-processing provider is a fail-fast operation.
    // Do this before applying it to the engine or secure store so a bad key or
    // unavailable model never becomes a configuration that can accept audio.
    let llmValidation = null;
    if (next.llm?.enabled) {
        llmValidation = llmValidationRequest(next);
        if (llmValidation.status !== 'ok') return llmValidation;
        const check = await sendEngineRequest('test_connection', llmValidation.params, 15000);
        if (check?.status !== 'ok') {
            return {
                status: 'error',
                code: 'llm_validation_failed',
                error: check?.error || 'The post-processing model could not complete its validation request.',
            };
        }
    }
    const result = await sendEngineRequest('configure_provider', next);
    if (result?.status !== 'ok') return result;
    try {
        saveProviderConfig(next);
    } catch (error) {
        // Keep the previous persisted configuration authoritative if the OS
        // keychain cannot store the candidate. Best-effort rollback prevents
        // an engine-only configuration from surprising the next app launch.
        if (Object.keys(current).length) await sendEngineRequest('configure_provider', current);
        return { status: 'error', code: 'credential_storage_unavailable', error: error.message };
    }
    if (llmValidation?.fingerprint) validatedProfileProcessors.add(llmValidation.fingerprint);
    return { ...result, config: {
        ...next,
        api_key: next.api_key ? 'configured' : '',
        transcription: { ...next.transcription, api_key: next.transcription?.api_key ? 'configured' : '' },
        llm: { ...next.llm, api_key: next.llm?.api_key ? 'configured' : '' },
    } };
});

async function engineReadCommand(event, command, params = {}) {
    const rejected = untrustedSenderResult(event);
    return rejected || sendEngineRequest(command, params);
}

ipcMain.handle('get-local-models', (event) => engineReadCommand(event, 'get_local_models'));
ipcMain.handle('get-models', (event) => engineReadCommand(event, 'get_models'));
ipcMain.handle('run-preflight', (event, params) => engineReadCommand(event, 'preflight', params || {}));

const RENDERER_ENGINE_COMMANDS = new Set([
    'get_history', 'delete_history', 'clear_history', 'get_snippets',
    'save_snippet', 'delete_snippet', 'get_dictionary', 'update_dictionary',
    'get_local_models', 'download_local_model', 'cancel_local_model',
    'delete_local_model', 'get_usage', 'configure_provider',
]);

// Compatibility bridge while the large renderer is migrated to explicit
// methods. Arbitrary engine commands are no longer reachable from the page.
ipcMain.handle('engine-command', async (event, { command, params } = {}) => {
    const rejected = untrustedSenderResult(event);
    if (rejected) return rejected;
    if (!RENDERER_ENGINE_COMMANDS.has(command)) {
        return { status: 'error', code: 'command_not_exposed', error: 'This engine command is not available to the renderer.' };
    }
    return sendEngineRequest(command, params || {});
});

ipcMain.handle('test-provider-connection', async (event, params) => {
    const rejected = untrustedSenderResult(event);
    return rejected || sendEngineRequest('test_connection', params);
});

ipcMain.handle('get-paste-capabilities', () => require('./src/output').capabilities());
ipcMain.handle('copy-text', (_event, text) => require('./src/output').copyAndPaste(String(text || ''), { automatic: false }));

// Mirror Electron's systemPreferences.askForMediaAccess for macOS.
// On Windows/Linux, getUserMedia in the renderer handles permission prompts
// natively — the main process has no equivalent API.
ipcMain.handle('request-microphone-access', async () => {
    if (process.platform !== 'darwin') {
        return { granted: true };
    }
    try {
        const { systemPreferences } = require('electron');
        const granted = await systemPreferences.askForMediaAccess('microphone');
        return { granted };
    } catch (_) {
        return { granted: false };
    }
});

ipcMain.handle('check-os-permissions', async () => {
    const platform = process.platform;
    let micGranted = true;
    let accessibilityGranted = true;

    if (platform === 'darwin') {
        const { systemPreferences } = require('electron');
        try {
            micGranted = systemPreferences.getMediaAccessStatus('microphone') === 'granted';
            accessibilityGranted = systemPreferences.isTrustedAccessibilityClient(false);
        } catch (e) {
            safeErr('Failed checking macOS permissions:', e);
        }
    } else if (platform === 'win32') {
        // On Windows we cannot query OS-level mic permission from the main
        // process.  getUserMedia in the renderer is the canonical test.
        micGranted = true;
        accessibilityGranted = true;
    } else if (platform === 'linux') {
        const pasteInfo = require('./src/output').capabilities();
        accessibilityGranted = pasteInfo.available !== false;
        micGranted = true;
    }

    return { platform, micGranted, accessibilityGranted };
});

ipcMain.handle('open-os-settings', async (_event, settingType) => {
    const { shell } = require('electron');
    const platform = process.platform;
    try {
        if (settingType === 'microphone') {
            if (platform === 'win32') {
                await shell.openExternal('ms-settings:privacy-microphone');
                return { status: 'ok' };
            } else if (platform === 'darwin') {
                await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone');
                return { status: 'ok' };
            } else {
                return { status: 'error', error: 'Platform not supported for microphone settings shortcut' };
            }
        }
        if (settingType === 'sound') {
            if (platform === 'win32') {
                await shell.openExternal('ms-settings:sound');
                return { status: 'ok' };
            } else if (platform === 'darwin') {
                await shell.openExternal('x-apple.systempreferences:com.apple.preference.sound');
                return { status: 'ok' };
            } else {
                return { status: 'error', error: 'Platform not supported for sound settings shortcut' };
            }
        }
        if (settingType === 'accessibility') {
            if (platform === 'win32') {
                await shell.openExternal('ms-settings:easeofaccess-keyboard');
                return { status: 'ok' };
            } else if (platform === 'darwin') {
                await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility');
                return { status: 'ok' };
            } else {
                return { status: 'error', error: 'Platform not supported for accessibility settings shortcut' };
            }
        }
        return { status: 'error', error: `Unknown setting type: ${settingType}` };
    } catch (err) {
        return { status: 'error', error: err.message };
    }
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (nativeHotkeys) nativeHotkeys.stop();
    if (pythonProcess) {
        pythonProcess.kill();
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        // App stays in tray
    }
});
