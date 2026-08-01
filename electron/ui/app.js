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
    const apiKeyInput = document.getElementById('api-key-input');

    // Load saved API Key
    const savedApiKey = localStorage.getItem('audioscribe_api_key') || '';
    apiKeyInput.value = savedApiKey;

    function runPreflightCheck() {
        const apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            statusBar.className = 'system-status-bar error';
            statusMsg.textContent = '🔴 Action Needed: Groq API Key Missing';
            warningText.textContent = 'Missing Groq API Key. Please enter your API Key in Settings to start dictating.';
            warningCard.classList.remove('hidden');
            return false;
        } else {
            statusBar.className = 'system-status-bar';
            statusMsg.textContent = '🟢 All Systems Operational • Press F9 to Dictate';
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
        localStorage.setItem('audioscribe_api_key', apiKeyInput.value.trim());
        runPreflightCheck();
        alert('Settings saved successfully!');
    });

    // --- 4. INTERACTIVE HOTKEY RECORDER ---
    const hotkeyInput = document.getElementById('hotkey-recorder-input');
    const recordHotkeyBtn = document.getElementById('record-hotkey-btn');
    const activeHotkeyBadge = document.getElementById('active-hotkey-badge');
    let isRecordingHotkey = false;

    const savedShortcut = localStorage.getItem('audioscribe_shortcut') || 'F9';
    hotkeyInput.value = savedShortcut;
    activeHotkeyBadge.textContent = savedShortcut;

    recordHotkeyBtn.addEventListener('click', () => {
        isRecordingHotkey = true;
        hotkeyInput.value = 'Press key combination...';
        recordHotkeyBtn.textContent = 'Listening...';
        recordHotkeyBtn.style.backgroundColor = '#ef4444';
    });

    document.addEventListener('keydown', async (e) => {
        if (!isRecordingHotkey) return;
        e.preventDefault();

        const keys = [];
        if (e.ctrlKey) keys.push('Control');
        if (e.shiftKey) keys.push('Shift');
        if (e.altKey) keys.push('Alt');
        if (e.metaKey) keys.push('Command');

        const key = e.key.toUpperCase();
        if (!['CONTROL', 'SHIFT', 'ALT', 'META'].includes(key)) {
            keys.push(key);
        }

        if (keys.length > 0) {
            const shortcutString = keys.join('+');
            isRecordingHotkey = false;
            hotkeyInput.value = shortcutString;
            activeHotkeyBadge.textContent = shortcutString;
            recordHotkeyBtn.textContent = 'Record Hotkey';
            recordHotkeyBtn.style.backgroundColor = '';

            localStorage.setItem('audioscribe_shortcut', shortcutString);
            if (window.api && window.api.registerShortcut) {
                const res = await window.api.registerShortcut(shortcutString);
                if (res && res.status === 'ok') {
                    console.log(`[Hotkey] Registered ${shortcutString}`);
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
