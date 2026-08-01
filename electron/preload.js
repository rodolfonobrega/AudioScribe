const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    sendCommand: (command, params) => ipcRenderer.invoke('engine-command', { command, params }),
    registerShortcut: (key) => ipcRenderer.invoke('register-shortcut', key),
    updateProfiles: (profiles) => ipcRenderer.invoke('update-profiles', profiles),
    getProviderConfig: () => ipcRenderer.invoke('get-provider-config'),
    saveProviderConfig: (config) => ipcRenderer.invoke('save-provider-config', config),
    onEngineEvent: (callback) => {
        ipcRenderer.on('engine-event', (event, data) => callback(data));
    },
    onOverlayState: (callback) => {
        ipcRenderer.on('update-overlay-state', (event, data) => callback(data));
    },
    onStatusChange: (callback) => {
        ipcRenderer.on('status-change', (event, status) => callback(status));
    }
});
