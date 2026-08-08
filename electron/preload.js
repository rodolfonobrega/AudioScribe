const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    // Temporary compatibility bridge. The main process enforces a narrow
    // allowlist while the renderer migrates to the named methods below.
    sendCommand: (command, params) => ipcRenderer.invoke('engine-command', { command, params }),
    getLocalModels: () => ipcRenderer.invoke('get-local-models'),
    getModels: () => ipcRenderer.invoke('get-models'),
    runPreflight: (params) => ipcRenderer.invoke('run-preflight', params || {}),
    retryEngine: () => ipcRenderer.invoke('retry-engine'),
    startRecording: (profile) => ipcRenderer.invoke('start-recording', profile || null),
    stopRecording: (profile) => ipcRenderer.invoke('stop-recording', profile || null),
    toggleRecording: (profile) => ipcRenderer.invoke('toggle-recording', profile || null),
    registerShortcut: (key) => ipcRenderer.invoke('register-shortcut', key),
    updateProfiles: (profiles) => ipcRenderer.invoke('update-profiles', profiles),
    beginHotkeyCapture: () => ipcRenderer.invoke('begin-hotkey-capture'),
    endHotkeyCapture: (profiles) => ipcRenderer.invoke('end-hotkey-capture', profiles),
    getProviderConfig: () => ipcRenderer.invoke('get-provider-config'),
    saveProviderConfig: (config) => ipcRenderer.invoke('save-provider-config', config),
    getPasteCapabilities: () => ipcRenderer.invoke('get-paste-capabilities'),
    copyText: (text) => ipcRenderer.invoke('copy-text', text),
    transcribeAudioBuffer: (audioBase64, profile) => ipcRenderer.invoke('transcribe-audio-buffer', { audioBase64, profile }),
    checkOSPermissions: () => ipcRenderer.invoke('check-os-permissions'),
    requestMicrophoneAccess: () => ipcRenderer.invoke('request-microphone-access'),
    openOSSettings: (settingType) => ipcRenderer.invoke('open-os-settings', settingType),
    testProviderConnection: (params) => ipcRenderer.invoke('test-provider-connection', params),
    onEngineEvent: (callback) => {
        ipcRenderer.on('engine-event', (event, data) => callback(data));
    },
    onOverlayState: (callback) => {
        ipcRenderer.on('update-overlay-state', (event, data) => callback(data));
    },
    onStatusChange: (callback) => {
        ipcRenderer.on('status-change', (event, status) => callback(status));
    },
    setActivationMode: (mode) => ipcRenderer.invoke('set-activation-mode', mode),
    copyAndPaste: (text) => ipcRenderer.invoke('copy-text', text),
    onNativeStartRecording: (callback) => {
        ipcRenderer.on('native-start-recording', (event, data) => callback(data));
    },
    nativeRecordingStarted: (result) => {
        ipcRenderer.send('native-recording-started', result || {});
    },
    onNativeStopRecording: (callback) => {
        ipcRenderer.on('native-stop-recording', (event, data) => callback(data));
    }
});
