const { app, BrowserWindow, Tray, Menu, ipcMain, globalShortcut } = require('electron');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let pythonProcess = null;
let socketClient = null;
let isRecording = false;

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
        width: 800,
        height: 620,
        minWidth: 600,
        minHeight: 500,
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

    mainWindow.on('close', (event) => {
        if (!app.isQuitting) {
            event.preventDefault();
            mainWindow.hide();
        }
        return false;
    });
}

function createTray() {
    // Basic tray setup
    tray = new Tray(path.join(__dirname, '..', 'assets', 'llm_transcriber.png'));
    
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
    socketClient = net.connect({ port: 8765, host: '127.0.0.1' }, () => {
        console.log('[Electron] Connected to AudioScribe Python Server.');
    });

    let buffer = '';
    socketClient.on('data', (data) => {
        buffer += data.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const eventData = JSON.parse(line.trim());
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
        console.log('[Electron] Waiting for Python engine to initialize...');
        setTimeout(connectToPythonServer, 2000);
    });
}

function launchPythonSidecar() {
    let executable;
    let args;

    if (app.isPackaged) {
        const binName = process.platform === 'win32' ? 'audioscribe_engine.exe' : 'audioscribe_engine';
        executable = path.join(process.resourcesPath, 'bin', binName);
        args = ['--server', '--port', '8765'];
        if (!require('fs').existsSync(executable)) {
            console.log('[Electron] Standalone mode: Running Native Node.js Engine (no sidecar binary required).');
            return;
        }
    } else {
        executable = process.platform === 'win32' ? 'python' : 'python3';
        const scriptPath = path.join(__dirname, '..', 'main.py');
        args = [scriptPath, '--server', '--port', '8765'];
    }

    try {
        pythonProcess = spawn(executable, args);
        pythonProcess.on('error', (err) => {
            console.log('[Electron] Running in Pure Native Node.js mode.');
        });
    } catch (e) {
        console.log('[Electron] Running in Pure Native Node.js mode.');
    }

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python Engine]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Engine Error]: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`[Python Engine] exited with code ${code}`);
    });

    setTimeout(connectToPythonServer, 1500);
}

function toggleRecording() {
    isRecording = !isRecording;
    const command = isRecording ? 'start_recording' : 'stop_recording';
    
    if (overlayWindow) {
        if (isRecording) {
            overlayWindow.showInactive();
            overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1, shortcut: currentShortcut });
        } else {
            overlayWindow.webContents.send('update-overlay-state', { status: 'processing', shortcut: currentShortcut });
        }
    }

    if (socketClient && !socketClient.destroyed) {
        socketClient.write(JSON.stringify({ command }) + '\n');
    }
}

let currentShortcut = 'F9';

function registerShortcut(newKey) {
    try {
        globalShortcut.unregisterAll();
        const success = globalShortcut.register(newKey, () => {
            toggleRecording();
        });
        if (success) {
            currentShortcut = newKey;
            return { status: 'ok', shortcut: newKey };
        } else {
            // Fallback to F9
            globalShortcut.register('F9', () => toggleRecording());
            currentShortcut = 'F9';
            return { status: 'error', error: `Could not register key '${newKey}'. Reverted to F9.` };
        }
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

ipcMain.handle('register-shortcut', async (event, key) => {
    return registerShortcut(key);
});

ipcMain.handle('engine-command', async (event, { command, params }) => {
    return new Promise((resolve) => {
        if (!socketClient || socketClient.destroyed) {
            return resolve({ status: 'error', error: 'Python engine offline' });
        }

        const id = Math.random().toString(36).substring(7);
        const onData = (data) => {
            const lines = data.toString().split('\n');
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const parsed = JSON.parse(line);
                    if (parsed.id === id) {
                        socketClient.removeListener('data', onData);
                        resolve(parsed);
                    }
                } catch (e) {}
            }
        };

        socketClient.on('data', onData);
        socketClient.write(JSON.stringify({ id, command, params }) + '\n');
    });
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
