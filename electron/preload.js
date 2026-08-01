const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    sendCommand: (command, params) => ipcRenderer.invoke('engine-command', { command, params }),
    registerShortcut: (key) => ipcRenderer.invoke('register-shortcut', key),
    onEngineEvent: (callback) => {
        ipcRenderer.on('engine-event', (event, data) => callback(data));
    },
    onStatusChange: (callback) => {
        ipcRenderer.on('status-change', (event, status) => callback(status));
    }
});
