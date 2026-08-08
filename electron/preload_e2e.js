const { contextBridge, ipcRenderer } = require('electron');

// In-memory desktop bridge used only when AUDIOSCRIBE_E2E=1. The renderer is
// still loaded by Electron with context isolation enabled; the fake merely
// makes its external dependencies deterministic.
const state = {
    snippets: [],
    dictionary: [],
    profiles: [],
    listeners: [],
};

const ok = (extra = {}) => ({ status: 'ok', ...extra });
const localModels = [
    { id: 'parakeet-tdt-0.6b-v3', name: 'Parakeet TDT 0.6B', size_mb: 680, installed: true },
    { id: 'whisper-base', name: 'Whisper Base', size_mb: 142, installed: true },
];

function command(name, params = {}) {
    switch (name) {
    case 'get_snippets': return ok({ items: state.snippets });
    case 'save_snippet': {
        const item = { id: `snippet-${state.snippets.length + 1}`, ...params };
        state.snippets.push(item);
        return ok({ item });
    }
    case 'delete_snippet':
        state.snippets = state.snippets.filter((item) => item.id !== params.id);
        return ok();
    case 'get_dictionary': return ok({ items: state.dictionary });
    case 'update_dictionary':
        state.dictionary = state.dictionary
            .filter((item) => !(params.remove || []).includes(item.word));
        for (const word of params.add || []) {
            if (!state.dictionary.some((item) => item.word === word)) state.dictionary.push({ word, source: params.source || 'manual' });
        }
        return ok({ items: state.dictionary });
    case 'get_local_models': return ok({ models: localModels });
    case 'get_models': return ok({ transcription: [], llm: [] });
    case 'get_usage': return ok({ summary: { cost_known: true, estimated_cost_usd: 0, unknown_cost_records: 0 }, periods: {} });
    case 'get_history': return ok({ items: [] });
    case 'clear_history':
    case 'delete_history': return ok();
    case 'configure_provider': return ok();
    case 'preflight': return ok({ checks: [] });
    default: return ok();
    }
}

const api = {
    isE2E: true,
    e2eNoMicrophone: true,
    sendCommand: command,
    getLocalModels: () => command('get_local_models'),
    getModels: () => command('get_models'),
    runPreflight: () => command('preflight'),
    retryEngine: async () => ok(),
    startRecording: async () => ok({ recording: true }),
    stopRecording: async () => ok({ recording: false }),
    toggleRecording: () => ipcRenderer.invoke('toggle-recording', null),
    registerShortcut: async (shortcut) => ok({ shortcut }),
    updateProfiles: async (profiles) => { state.profiles = profiles; return ok({ count: profiles.length }); },
    beginHotkeyCapture: async () => ok(),
    endHotkeyCapture: async (profiles) => { state.profiles = profiles; return ok({ count: profiles.length }); },
    getProviderConfig: async () => ok({ config: null }),
    saveProviderConfig: async () => ok(),
    getPasteCapabilities: async () => ({ available: true }),
    copyText: async () => ok(),
    copyAndPaste: async () => ok(),
    transcribeAudioBuffer: async () => ok({ text: 'E2E transcription' }),
    checkOSPermissions: async () => ({ platform: process.platform, micGranted: true, accessibilityGranted: true }),
    requestMicrophoneAccess: async () => ({ granted: true }),
    openOSSettings: async () => ok(),
    testProviderConnection: async () => ok(),
    setActivationMode: async (mode) => ok({ mode }),
    onEngineEvent: (callback) => {
        state.listeners.push(callback);
        setTimeout(() => callback({ event: 'engine_ready', data: {} }), 0);
    },
    onOverlayState: () => {},
    onStatusChange: () => {},
    onNativeStartRecording: (callback) => ipcRenderer.on('native-start-recording', (_event, data) => callback(data)),
    // This preserves the real IPC acknowledgement in the physical-hotkey
    // test while avoiding any microphone permission or hardware dependency.
    nativeRecordingStarted: (result) => ipcRenderer.send('native-recording-started', result || {}),
    onNativeStopRecording: (callback) => ipcRenderer.on('native-stop-recording', (_event, data) => callback(data)),
};

contextBridge.exposeInMainWorld('api', api);
