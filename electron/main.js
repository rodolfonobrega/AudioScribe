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
        y: Math.round(height - 100),
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        show: false,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
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
                        overlayWindow.webContents.send('update-overlay-state', { status: 'done', text: eventData.data.text });
                        setTimeout(() => {
                            overlayWindow.hide();
                        }, 1800);
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
    } else {
        executable = process.platform === 'win32' ? 'python' : 'python3';
        const scriptPath = path.join(__dirname, '..', 'main.py');
        args = [scriptPath, '--server', '--port', '8765'];
    }

    pythonProcess = spawn(executable, args);

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
            overlayWindow.webContents.send('update-overlay-state', { status: 'recording', rms: 0.1 });
        } else {
            overlayWindow.webContents.send('update-overlay-state', { status: 'processing' });
        }
    }

    if (socketClient && !socketClient.destroyed) {
        socketClient.write(JSON.stringify({ command }) + '\n');
    }
}

app.whenReady().then(() => {
    createMainWindow();
    createOverlayWindow();
    createTray();
    launchPythonSidecar();

    // Register F9 global hotkey
    globalShortcut.register('F9', () => {
        toggleRecording();
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
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
