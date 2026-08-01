document.addEventListener('DOMContentLoaded', () => {
    // Navigation Tabs
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

    const recordBtn = document.getElementById('record-toggle-btn');
    const recordLabel = document.getElementById('record-btn-label');
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    const historyList = document.getElementById('transcription-list');
    const audioSelect = document.getElementById('audio-device-select');
    const runDiagBtn = document.getElementById('run-preflight-btn');
    const diagBox = document.getElementById('diag-results');

    let isRecording = false;

    // Toggle Recording Button
    recordBtn.addEventListener('click', async () => {
        isRecording = !isRecording;
        const command = isRecording ? 'start_recording' : 'stop_recording';
        
        if (window.api) {
            const res = await window.api.sendCommand(command);
            updateRecordState(isRecording);
        }
    });

    function updateRecordState(recording) {
        isRecording = recording;
        if (recording) {
            recordBtn.classList.add('recording');
            recordLabel.textContent = 'Recording... Press F9 to Stop';
            statusDot.className = 'status-dot yellow';
            statusText.textContent = 'Recording';
        } else {
            recordBtn.classList.remove('recording');
            recordLabel.textContent = 'Start Recording (F9)';
            statusDot.className = 'status-dot green';
            statusText.textContent = 'Engine Ready';
        }
    }

    // Populate Audio Devices
    async function loadAudioDevices() {
        if (!window.api) return;
        try {
            const res = await window.api.sendCommand('get_devices');
            if (res && res.status === 'ok' && res.devices) {
                audioSelect.innerHTML = '<option value="">Auto / Default Microphone</option>';
                res.devices.forEach(dev => {
                    const opt = document.createElement('option');
                    opt.value = dev.index;
                    opt.textContent = `${dev.name} (Index ${dev.index})`;
                    audioSelect.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('Error fetching audio devices:', e);
        }
    }

    loadAudioDevices();

    // Listen to Engine Events
    if (window.api) {
        window.api.onEngineEvent((eventData) => {
            if (eventData.event === 'status_changed') {
                const status = eventData.data.status;
                if (status === 'recording') updateRecordState(true);
                else if (status === 'ready') updateRecordState(false);
            } else if (eventData.event === 'transcription_result') {
                addHistoryItem(eventData.data.text, eventData.data.latency_ms);
            }
        });
    }

    function addHistoryItem(text, latencyMs) {
        const emptyState = historyList.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const item = document.createElement('div');
        item.className = 'history-item';
        item.innerHTML = `
            <div class="history-text">${text}</div>
            <div class="history-meta">
                ${latencyMs ? `<span class="pill">⚡ ${Math.round(latencyMs)}ms</span>` : ''}
                <button class="copy-btn" onclick="navigator.clipboard.writeText('${text.replace(/'/g, "\\'")}')">Copy</button>
            </div>
        `;
        historyList.prepend(item);
    }

    // Check for Updates Button
    const checkUpdatesBtn = document.getElementById('check-updates-btn');
    const updateMsg = document.getElementById('update-status-msg');

    if (checkUpdatesBtn) {
        checkUpdatesBtn.addEventListener('click', async () => {
            if (updateMsg) updateMsg.textContent = 'Checking GitHub for updates...';
            if (window.api) {
                const res = await window.api.sendCommand('check_updates');
                if (res && res.status === 'ok') {
                    if (res.update_available && res.update_info) {
                        const info = res.update_info;
                        updateMsg.innerHTML = `🚀 <strong style="color:#10b981">Update Available! (v${info.latest_version})</strong><br>` +
                            `<a href="${info.release_url}" target="_blank" style="color:#6366f1">Click here to download release</a>`;
                    } else {
                        updateMsg.textContent = '✅ You are on the latest version of AudioScribe (v1.0.0).';
                    }
                }
            }
        });
    }

    // Preflight Diagnostics Button
    if (runDiagBtn) {
        runDiagBtn.addEventListener('click', async () => {
            diagBox.textContent = 'Running system diagnostic check...';
            if (window.api) {
                const res = await window.api.sendCommand('preflight');
                if (res && res.status === 'ok') {
                    if (res.ready) {
                        diagBox.textContent = '✅ [OK] Pre-flight Check: All systems ready!\nNo critical errors or warnings detected.';
                    } else {
                        let report = `[PRE-FLIGHT REPORT]\n\nErrors (${res.errors.length}):\n`;
                        res.errors.forEach((err, idx) => {
                            report += ` [${idx + 1}] ${err.component}: ${err.issue}\n     Remediation: ${err.remediation}\n\n`;
                        });
                        report += `Warnings (${res.warnings.length}):\n`;
                        res.warnings.forEach((warn, idx) => {
                            report += ` [${idx + 1}] ${warn.component}: ${warn.issue}\n     Remediation: ${warn.remediation}\n\n`;
                        });
                        diagBox.textContent = report;
                    }
                }
            }
        });
    }
});
