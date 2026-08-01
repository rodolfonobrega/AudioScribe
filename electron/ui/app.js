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

    // --- 5. POST-PROCESSING PROFILES & DEDICATED HOTKEYS MANAGER ---
    const defaultProfiles = [
        {
            id: 'prof_std',
            name: '📝 Standard Grammar & Polish',
            enabled: true,
            shortcut: 'F9',
            prompt: 'Fix grammar, punctuation, and speech errors while preserving exact meaning. Output ONLY polished text.'
        },
        {
            id: 'prof_trans',
            name: '🌐 Translate to English',
            enabled: true,
            shortcut: 'Ctrl+Shift+E',
            prompt: 'Translate the transcribed audio into natural, professional English. Output ONLY the translated text.'
        },
        {
            id: 'prof_summary',
            name: '📋 Bullet Point Summary',
            enabled: true,
            shortcut: 'Ctrl+Shift+S',
            prompt: 'Summarize the spoken audio into clean, structured markdown bullet points.'
        },
        {
            id: 'prof_code',
            name: '💻 Code & Technical Formatter',
            enabled: true,
            shortcut: 'Ctrl+Shift+C',
            prompt: 'Format code snippets, technical explanations, and variable names cleanly in markdown.'
        }
    ];

    let profiles = JSON.parse(localStorage.getItem('audioscribe_profiles') || 'null') || defaultProfiles;
    const profilesListEl = document.getElementById('profiles-list');
    const addProfileBtn = document.getElementById('add-profile-btn');

    function saveProfiles() {
        localStorage.setItem('audioscribe_profiles', JSON.stringify(profiles));
        if (window.api && window.api.updateProfiles) {
            window.api.updateProfiles(profiles);
        }
    }

    saveProfiles();

    function renderProfiles() {
        if (!profilesListEl) return;
        profilesListEl.innerHTML = '';

        profiles.forEach(prof => {
            const card = document.createElement('div');
            card.className = 'profile-card';
            card.innerHTML = `
                <div class="profile-header-row">
                    <div class="profile-title-group">
                        <input type="checkbox" ${prof.enabled ? 'checked' : ''} data-id="${prof.id}" class="profile-enable-check">
                        <span class="profile-title">${prof.name}</span>
                    </div>
                    <button class="btn-danger-sm delete-prof-btn" data-id="${prof.id}">Delete</button>
                </div>
                <div class="form-group">
                    <label>System Prompt Rule</label>
                    <textarea class="profile-prompt-preview" data-id="${prof.id}" rows="2">${prof.prompt}</textarea>
                </div>
                <div class="profile-actions-row">
                    <div class="profile-hotkey-group">
                        <span>Dedicated Shortcut:</span>
                        <kbd class="hotkey-badge">${prof.shortcut || 'None'}</kbd>
                        <button class="btn-secondary record-prof-shortcut-btn" data-id="${prof.id}">Change Shortcut</button>
                    </div>
                    <button class="btn-primary-sm save-prof-btn" data-id="${prof.id}">Save & Apply</button>
                </div>
            `;
            profilesListEl.appendChild(card);
        });

        // Add Event Listeners for inline editing
        profilesListEl.querySelectorAll('.save-prof-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = e.target.getAttribute('data-id');
                const prof = profiles.find(p => p.id === id);
                if (prof) {
                    const card = e.target.closest('.profile-card');
                    const promptArea = card.querySelector('.profile-prompt-preview');
                    const check = card.querySelector('.profile-enable-check');
                    prof.prompt = promptArea.value.trim();
                    prof.enabled = check.checked;
                    saveProfiles();
                    alert(`Saved profile "${prof.name}"! Shortcut: ${prof.shortcut}`);
                }
            });
        });

        profilesListEl.querySelectorAll('.delete-prof-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = e.target.getAttribute('data-id');
                if (confirm('Are you sure you want to delete this post-processing profile?')) {
                    profiles = profiles.filter(p => p.id !== id);
                    saveProfiles();
                    renderProfiles();
                }
            });
        });

        profilesListEl.querySelectorAll('.record-prof-shortcut-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = e.target.getAttribute('data-id');
                const prof = profiles.find(p => p.id === id);
                if (!prof) return;

                const newKey = prompt(`Enter new hotkey combination for "${prof.name}":\n(e.g., Ctrl+Shift+E, Alt+R, F9)`, prof.shortcut);
                if (newKey && newKey.trim()) {
                    prof.shortcut = newKey.trim();
                    saveProfiles();
                    renderProfiles();
                }
            });
        });
    }

    renderProfiles();

    if (addProfileBtn) {
        addProfileBtn.addEventListener('click', () => {
            const name = prompt('Enter a name for your new Post-Processing Profile:', '✨ Custom Rule');
            if (!name) return;
            const promptText = prompt('Enter the System Prompt instruction for the AI:', 'Translate and clean up text...');
            if (!promptText) return;

            const newProf = {
                id: 'prof_' + Date.now(),
                name: name.trim(),
                enabled: true,
                shortcut: 'Ctrl+Alt+' + (profiles.length + 1),
                prompt: promptText.trim()
            };
            profiles.push(newProf);
            saveProfiles();
            renderProfiles();
        });
    }

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
