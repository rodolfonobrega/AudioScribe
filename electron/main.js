const { app, BrowserWindow, Tray, Menu, ipcMain, globalShortcut, safeStorage } = require('electron');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let pythonProcess = null;
let socketClient = null;
let socketBuffer = '';
const pendingRequests = new Map();
let reconnectTimer = null;
let isRecording = false;
let lastEngineEvent = { event: 'engine_starting', data: { code: 'engine_starting' } };

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

function loadProviderConfig() {
    try {
        const encrypted = require('fs').readFileSync(providerConfigPath(), 'utf8');
        if (safeStorage.isEncryptionAvailable()) {
            return JSON.parse(safeStorage.decryptString(Buffer.from(encrypted, 'base64')));
        }
        return JSON.parse(encrypted);
    } catch (error) {
        return null;
    }
}

function saveProviderConfig(config) {
    const fs = require('fs');
    fs.mkdirSync(path.dirname(providerConfigPath()), { recursive: true });
    const serialized = JSON.stringify(config);
    const value = safeStorage.isEncryptionAvailable()
        ? safeStorage.encryptString(serialized).toString('base64')
        : serialized;
    fs.writeFileSync(providerConfigPath(), value, { encoding: 'utf8', mode: 0o600 });
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
            contextIsolation: true
        }
    });

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
        width: 1180,
        height: 820,
        minWidth: 900,
        minHeight: 650,
        show: false,
        title: "AudioScribe Desktop",
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

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
        { label: 'Toggle Recording (F9)', click: () => toggleRecording() },
        { label: 'Open Settings', click: () => mainWindow.show() },
        { type: 'separator' },
        { label: 'Quit', click: () => {
            app.isQuitting = true;
            app.quit();
        }}
    ]);

    tray.setToolTip('AudioScribe - Press F9 to Record');
    tray.setContextMenu(contextMenu);

    tray.on('double-click', () => {
        mainWindow.show();
    });
}

function connectToPythonServer() {
    if (socketClient && !socketClient.destroyed) return;
    socketBuffer = '';
    socketClient = net.connect({ port: 8765, host: '127.0.0.1' }, () => {
        console.log('[Electron] Connected to AudioScribe Python Server.');
        publishEngineEvent('engine_status', { code: 'engine_connected', message: 'Engine connected' });
        sendStoredProviderConfig().then((result) => {
            if (result?.status === 'ok') {
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
                const eventData = JSON.parse(line.trim());
                if (eventData.id && pendingRequests.has(eventData.id)) {
                    const request = pendingRequests.get(eventData.id);
                    pendingRequests.delete(eventData.id);
                    clearTimeout(request.timer);
                    request.resolve(eventData);
                    continue;
                }
                if (mainWindow) {
                    mainWindow.webContents.send('engine-event', eventData);
                }

                // Update floating overlay
                if (overlayWindow) {
                    if (eventData.event === 'status_changed') {
                        const status = eventData.data.status;
                        if (status === 'recording') {
                            overlayWindow.showInactive();
                            overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1 });
                        } else if (status === 'processing') {
                            overlayWindow.webContents.send('update-overlay-state', { status: 'processing' });
                        }
                    } else if (eventData.event === 'transcription_result') {
                        const text = eventData.data.text;
                        overlayWindow.webContents.send('update-overlay-state', { status: 'done', text: text });
                        
                        // Auto-paste text into the user's currently focused window
                        const NativeOutputHandler = require('./src/output');
                        NativeOutputHandler.copyAndPaste(text);

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
                connectToPythonServer();
            }, 2000);
        }
    });
}

function sendEngineRequest(command, params = {}, timeoutMs = 10000) {
    return new Promise((resolve) => {
        if (!socketClient || socketClient.destroyed) {
            resolve({ status: 'error', code: 'engine_offline', error: 'Python engine offline' });
            return;
        }
        const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
        const timer = setTimeout(() => {
            pendingRequests.delete(id);
            resolve({ status: 'error', code: 'engine_timeout', error: `Engine timeout for ${command}` });
        }, timeoutMs);
        pendingRequests.set(id, { resolve, timer });
        socketClient.write(JSON.stringify({ id, command, params }) + '\n');
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
        args = ['--server', '--port', '8765'];
        if (!require('fs').existsSync(executable)) {
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
        args = [scriptPath, '--server', '--port', '8765'];
    }

    try {
        pythonProcess = spawn(executable, args, { cwd: app.isPackaged ? process.resourcesPath : path.join(__dirname, '..') });
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
        console.log(`[Python Engine]: ${data}`);
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

    setTimeout(connectToPythonServer, 1500);
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

async function toggleRecording(profile = null) {
    const command = isRecording ? 'stop_recording' : 'start_recording';
    const result = await sendEngineRequest(command);
    if (result?.status !== 'ok') {
        console.error('[Electron] Recording command failed:', result?.error || result?.code);
        return result;
    }
    isRecording = command === 'start_recording';
    if (overlayWindow) {
        if (isRecording) {
            overlayWindow.showInactive();
            overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1, shortcut: profile?.shortcut || currentShortcut });
        } else {
            overlayWindow.webContents.send('update-overlay-state', { status: 'processing', shortcut: profile?.shortcut || currentShortcut });
        }
    }
    return result;
}

let currentShortcut = 'F9';

function registerAllShortcuts() {
    globalShortcut.unregisterAll();
    const registered = [];
    const candidates = [{ shortcut: currentShortcut, callback: () => toggleRecording() }];
    activeProfiles.forEach((profile) => {
        if (profile.enabled && profile.shortcut) candidates.push({ shortcut: profile.shortcut, callback: () => toggleRecording(profile) });
    });
    candidates.forEach(({ shortcut, callback }) => {
        try {
            if (globalShortcut.register(shortcut, callback)) registered.push(shortcut);
        } catch (error) {
            console.error(`[Electron] Failed to register ${shortcut}:`, error.message);
        }
    });
    if (!registered.length && currentShortcut !== 'F9') {
        currentShortcut = 'F9';
        globalShortcut.register('F9', () => toggleRecording());
        registered.push('F9');
    }
    return registered;
}

function registerShortcut(newKey) {
    try {
        const previous = currentShortcut;
        currentShortcut = newKey;
        const registered = registerAllShortcuts();
        if (registered.includes(newKey)) return { status: 'ok', shortcut: newKey };
        currentShortcut = previous;
        registerAllShortcuts();
        return { status: 'error', error: `Could not register key '${newKey}'. Reverted to ${previous}.` };
    } catch (err) {
        return { status: 'error', error: err.message };
    }
}

app.whenReady().then(() => {
    createMainWindow();
    createOverlayWindow();
    createTray();
    launchPythonSidecar();

    registerShortcut('F9');

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
});

let activeProfiles = [];

function registerProfileShortcuts(profiles) {
    activeProfiles = profiles || [];
    const registered = registerAllShortcuts();
    return { status: 'ok', count: registered.length, registered };
}

ipcMain.handle('update-profiles', async (event, profiles) => {
    return registerProfileShortcuts(profiles);
});

ipcMain.handle('register-shortcut', async (event, key) => {
    return registerShortcut(key);
});

ipcMain.handle('get-provider-config', async () => {
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
    if (!Object.prototype.hasOwnProperty.call(config.llm || {}, 'api_key')) {
        next.llm.api_key = current.llm?.api_key || current.api_key || null;
    }
    if (config.api_key === 'configured' || !Object.prototype.hasOwnProperty.call(config, 'api_key')) {
        next.api_key = current.api_key || null;
    }
    saveProviderConfig(next);
    const result = await sendEngineRequest('configure_provider', next);
    return { ...result, config: {
        ...next,
        api_key: next.api_key ? 'configured' : '',
        transcription: { ...next.transcription, api_key: next.transcription?.api_key ? 'configured' : '' },
        llm: { ...next.llm, api_key: next.llm?.api_key ? 'configured' : '' },
    } };
});

ipcMain.handle('engine-command', async (event, { command, params }) => {
    return sendEngineRequest(command, params);
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (pythonProcess) {
        pythonProcess.kill();
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        // App stays in tray
    }
});
