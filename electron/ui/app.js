document.addEventListener('DOMContentLoaded', () => {
    // --- 1. THEME SWITCHER (DARK / LIGHT) ---
    const themeBtn = document.getElementById('theme-toggle-btn');
    const themeIcon = document.getElementById('theme-icon');
    const themeLabel = document.getElementById('theme-label');
    const rootEl = document.documentElement;

    const savedTheme = localStorage.getItem('audioscribe_theme') || 'dark';
    setTheme(savedTheme);

    themeBtn.addEventListener('click', () => {
        const currentTheme = rootEl.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    });

    function setTheme(theme) {
        rootEl.setAttribute('data-theme', theme);
        localStorage.setItem('audioscribe_theme', theme);
        if (theme === 'light') {
            themeIcon.textContent = '☀️';
            themeLabel.textContent = 'Light';
        } else {
            themeIcon.textContent = '🌙';
            themeLabel.textContent = 'Dark';
        }
    }

    // --- 2. NAVIGATION TABS ---
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            navButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(t => t.classList.remove('active'));

            btn.classList.add('active');
            const tabId = `tab-${btn.dataset.tab}`;
            document.getElementById(tabId).classList.add('active');
        });
    });

    // --- 3. SYSTEM HEALTH PRE-FLIGHT CHECK ---
    const statusBar = document.getElementById('system-status-bar');
    const statusMsg = document.getElementById('status-msg');
    const warningCard = document.getElementById('preflight-warning-card');
    const warningText = document.getElementById('preflight-warning-text');
    const fixConfigBtn = document.getElementById('fix-config-btn');
    
    const providerSelect = document.getElementById('provider-select');
    const apiKeyGroup = document.getElementById('api-key-group');
    const apiKeyInput = document.getElementById('api-key-input');
    const apiKeyLabel = document.getElementById('api-key-label');
    const apiKeyHint = document.getElementById('api-key-hint');
    const baseUrlGroup = document.getElementById('base-url-group');
    const baseUrlInput = document.getElementById('base-url-input');

    // Load saved Provider settings
    const savedProvider = localStorage.getItem('audioscribe_provider') || 'groq';
    const savedApiKey = localStorage.getItem('audioscribe_api_key') || '';
    const savedBaseUrl = localStorage.getItem('audioscribe_base_url') || 'http://localhost:11434/v1';

    providerSelect.value = savedProvider;
    apiKeyInput.value = savedApiKey;
    baseUrlInput.value = savedBaseUrl;

    function handleProviderUIChange() {
        const val = providerSelect.value;
        if (val === 'ollama') {
            apiKeyGroup.classList.add('hidden');
            baseUrlGroup.classList.remove('hidden');
            baseUrlInput.value = 'http://localhost:11434/v1';
        } else if (val === 'custom') {
            apiKeyGroup.classList.remove('hidden');
            baseUrlGroup.classList.remove('hidden');
            apiKeyLabel.textContent = 'API Key (Optional for Local)';
            apiKeyHint.textContent = 'Optional if your local custom endpoint does not require authentication.';
        } else if (val === 'openai') {
            apiKeyGroup.classList.remove('hidden');
            baseUrlGroup.classList.add('hidden');
            apiKeyLabel.textContent = 'OpenAI API Key';
            apiKeyHint.textContent = 'Get key at platform.openai.com/api-keys';
        } else { // groq
            apiKeyGroup.classList.remove('hidden');
            baseUrlGroup.classList.add('hidden');
            apiKeyLabel.textContent = 'Groq API Key (Free)';
            apiKeyHint.textContent = 'Get a free instant key at console.groq.com/keys';
        }
    }

    providerSelect.addEventListener('change', () => {
        handleProviderUIChange();
        runPreflightCheck();
    });

    handleProviderUIChange();

    function runPreflightCheck() {
        const provider = providerSelect.value;
        const apiKey = apiKeyInput.value.trim();
        const baseUrl = baseUrlInput.value.trim();

        const isLocal = provider === 'ollama' || baseUrl.includes('localhost') || baseUrl.includes('127.0.0.1');

        if (!isLocal && !apiKey) {
            const providerName = provider === 'openai' ? 'OpenAI' : 'Groq';
            statusBar.className = 'system-status-bar error';
            statusMsg.textContent = `🔴 Action Needed: ${providerName} API Key Missing`;
            warningText.textContent = `Missing ${providerName} API Key. Please enter your key in Settings or switch to Localhost Ollama.`;
            warningCard.classList.remove('hidden');
            return false;
        } else {
            statusBar.className = 'system-status-bar';
            const label = isLocal ? 'Localhost Ollama' : (provider === 'openai' ? 'OpenAI API' : 'Groq API');
            statusMsg.textContent = `🟢 ${label} Operational • Press F9 to Dictate`;
            warningCard.classList.add('hidden');
            return true;
        }
    }

    runPreflightCheck();

    fixConfigBtn.addEventListener('click', () => {
        document.querySelector('[data-tab="settings"]').click();
        apiKeyInput.focus();
    });

    // Save Settings
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    saveSettingsBtn.addEventListener('click', () => {
        localStorage.setItem('audioscribe_provider', providerSelect.value);
        localStorage.setItem('audioscribe_api_key', apiKeyInput.value.trim());
        localStorage.setItem('audioscribe_base_url', baseUrlInput.value.trim());
        runPreflightCheck();
        alert('Settings saved successfully!');
    });

    // --- 4. INTERACTIVE MULTI-KEY HOTKEY RECORDER ---
    const hotkeyInput = document.getElementById('hotkey-recorder-input');
    const recordHotkeyBtn = document.getElementById('record-hotkey-btn');
    const activeHotkeyBadge = document.getElementById('active-hotkey-badge');
    let isRecordingHotkey = false;

    const savedShortcut = localStorage.getItem('audioscribe_shortcut') || 'F9';
    hotkeyInput.value = savedShortcut;
    activeHotkeyBadge.textContent = savedShortcut;

    recordHotkeyBtn.addEventListener('click', () => {
        isRecordingHotkey = true;
        hotkeyInput.value = 'Press key combination (e.g. Ctrl+Shift+R)...';
        recordHotkeyBtn.textContent = 'Listening...';
        recordHotkeyBtn.style.backgroundColor = '#ef4444';
    });

    function formatElectronKey(e) {
        const isModifierKey = ['Control', 'Shift', 'Alt', 'Meta', 'AltGraph'].includes(e.key);

        const modifiers = [];
        if (e.ctrlKey) modifiers.push('CommandOrControl');
        if (e.altKey) modifiers.push('Alt');
        if (e.shiftKey) modifiers.push('Shift');
        if (e.metaKey) modifiers.push('Super');

        const uniqueModifiers = [...new Set(modifiers)];

        if (isModifierKey) {
            const prettyMods = uniqueModifiers.map(m => m === 'CommandOrControl' ? 'Ctrl' : m);
            return {
                isComplete: false,
                preview: prettyMods.length > 0 ? prettyMods.join(' + ') + ' + ...' : 'Listening...'
            };
        }

        let keyName = '';
        if (e.code.startsWith('Key')) {
            keyName = e.code.replace('Key', '').toUpperCase();
        } else if (e.code.startsWith('Digit')) {
            keyName = e.code.replace('Digit', '');
        } else if (e.code.startsWith('F') && e.code.length <= 3) {
            keyName = e.code;
        } else if (e.code === 'Space' || e.key === ' ') {
            keyName = 'Space';
        } else if (e.code === 'Tab') {
            keyName = 'Tab';
        } else if (e.code === 'Escape') {
            keyName = 'Escape';
        } else if (e.code === 'Enter' || e.code === 'NumpadEnter') {
            keyName = 'Return';
        } else if (e.code === 'Backspace') {
            keyName = 'Backspace';
        } else if (e.code === 'Delete') {
            keyName = 'Delete';
        } else {
            keyName = e.key.toUpperCase();
        }

        const acceleratorParts = [...uniqueModifiers, keyName];
        const prettyParts = uniqueModifiers.map(m => m === 'CommandOrControl' ? 'Ctrl' : m).concat(keyName);

        return {
            isComplete: true,
            accelerator: acceleratorParts.join('+'),
            pretty: prettyParts.join('+')
        };
    }

    document.addEventListener('keydown', async (e) => {
        if (!isRecordingHotkey) return;
        e.preventDefault();
        e.stopPropagation();

        const result = formatElectronKey(e);
        if (!result.isComplete) {
            hotkeyInput.value = result.preview;
        } else {
            isRecordingHotkey = false;
            hotkeyInput.value = result.pretty;
            recordHotkeyBtn.textContent = 'Record Hotkey';
            recordHotkeyBtn.style.backgroundColor = '';

            if (window.api && window.api.registerShortcut) {
                const res = await window.api.registerShortcut(result.accelerator);
                if (res && res.status === 'ok') {
                    activeHotkeyBadge.textContent = result.pretty;
                    localStorage.setItem('audioscribe_shortcut', result.pretty);
                    console.log(`[Hotkey] Successfully registered ${result.accelerator}`);
                } else {
                    const err = (res && res.error) || 'Invalid key combination';
                    alert(`Failed to register shortcut '${result.pretty}': ${err}`);
                    hotkeyInput.value = savedShortcut;
                    activeHotkeyBadge.textContent = savedShortcut;
                }
            }
        }
    });

    // --- 5. PRODUCTIVITY STATS TRACKING ---
    const metricWordsEl = document.getElementById('metric-words');
    const metricTimeSavedEl = document.getElementById('metric-time-saved');
    const metricLatencyEl = document.getElementById('metric-latency');

    let totalWords = parseInt(localStorage.getItem('audioscribe_total_words') || '0', 10);
    let totalLatencyMs = parseInt(localStorage.getItem('audioscribe_total_latency') || '320', 10);
    let totalTranscriptions = parseInt(localStorage.getItem('audioscribe_count') || '1', 10);

    function updateMetricCards() {
        metricWordsEl.textContent = totalWords.toLocaleString();
        
        // Time saved formula: (Words / 40 WPM typing) - (Words / 150 WPM speaking)
        const typingMinutes = totalWords / 40;
        const speechMinutes = totalWords / 150;
        const minutesSaved = Math.max(0, Math.round(typingMinutes - speechMinutes));
        
        if (minutesSaved >= 60) {
            const hours = (minutesSaved / 60).toFixed(1);
            metricTimeSavedEl.textContent = `${hours} hrs`;
        } else {
            metricTimeSavedEl.textContent = `${minutesSaved} min`;
        }

        const avgLatency = Math.round(totalLatencyMs / totalTranscriptions);
        metricLatencyEl.textContent = `${avgLatency} ms`;
    }

    updateMetricCards();

    function recordNewTranscription(text, latencyMs = 320) {
        if (!text) return;
        const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
        
        totalWords += wordCount;
        totalLatencyMs += latencyMs;
        totalTranscriptions += 1;

        localStorage.setItem('audioscribe_total_words', totalWords.toString());
        localStorage.setItem('audioscribe_total_latency', totalLatencyMs.toString());
        localStorage.setItem('audioscribe_count', totalTranscriptions.toString());

        updateMetricCards();
    }

    // --- 6. RECORDING CONTROL WITH PRE-FLIGHT VALIDATION ---
    const recordBtn = document.getElementById('record-toggle-btn');
    const recordLabel = document.getElementById('record-btn-label');
    const historyList = document.getElementById('transcription-list');
    let isRecording = false;

    recordBtn.addEventListener('click', async () => {
        // Run Pre-flight Check First!
        const isReady = runPreflightCheck();
        if (!isReady) {
            return; // Abort recording if pre-flight fails!
        }

        isRecording = !isRecording;
        updateRecordState(isRecording);

        if (window.api) {
            const command = isRecording ? 'start_recording' : 'stop_recording';
            await window.api.sendCommand(command);
        }
    });

    function updateRecordState(recording) {
        isRecording = recording;
        if (recording) {
            recordBtn.classList.add('recording');
            recordLabel.textContent = 'Recording... Click or press hotkey to stop';
        } else {
            recordBtn.classList.remove('recording');
            recordLabel.textContent = 'Start Recording';
        }
    }

    // Listen to Engine Events from Main process
    if (window.api && window.api.onEngineEvent) {
        window.api.onEngineEvent((eventData) => {
            if (eventData.event === 'transcription_result') {
                const text = eventData.data.text;
                const latency = eventData.data.latency_ms || 320;
                
                recordNewTranscription(text, latency);

                // Add to UI history list
                const item = document.createElement('div');
                item.className = 'transcription-item';
                const timeStr = new Date().toLocaleTimeString();
                item.innerHTML = `<div class="meta">${timeStr} • ⚡ ${latency}ms</div><div class="body">${text}</div>`;
                
                const emptyState = document.getElementById('empty-history-state');
                if (emptyState) emptyState.remove();

                historyList.prepend(item);
            }
        });
    }

    // Clear History
    const clearHistoryBtn = document.getElementById('clear-history-btn');
    clearHistoryBtn.addEventListener('click', () => {
        historyList.innerHTML = '<div class="empty-state" id="empty-history-state"><p>Press hotkey anywhere on your computer to start dictating.</p></div>';
    });
});
