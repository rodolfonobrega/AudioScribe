document.addEventListener('DOMContentLoaded', () => {
    const $ = (id) => document.getElementById(id);
    const root = document.documentElement;
    const api = window.api;

    // Theme and navigation
    const savedTheme = localStorage.getItem('audioscribe_theme') || 'dark';
    const setTheme = (theme) => {
        root.setAttribute('data-theme', theme);
        localStorage.setItem('audioscribe_theme', theme);
        $('theme-label').textContent = theme === 'light' ? 'Light mode' : 'Dark mode';
        $('theme-icon').innerHTML = theme === 'light'
            ? '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path></svg>'
            : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.5A8.5 8.5 0 0 1 8.5 3.5 8.5 8.5 0 1 0 20.5 15.5Z"></path></svg>';
    };
    setTheme(savedTheme);
    $('theme-toggle-btn')?.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));
    document.querySelectorAll('.nav-btn').forEach((button) => button.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach((item) => item.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        $(`tab-${button.dataset.tab}`)?.classList.add('active');
    }));

    const statusBar = $('system-status-bar');
    const statusMsg = $('status-msg');
    const warningCard = $('preflight-warning-card');
    const warningText = $('preflight-warning-text');
    const transProviderSelect = $('transcription-provider-select');
    const transApiKeyInput = $('transcription-api-key-input');
    const transBaseUrlInput = $('transcription-base-url-input');
    const llmProviderSelect = $('llm-provider-select');
    const llmApiKeyInput = $('llm-api-key-input');
    const llmBaseUrlInput = $('llm-base-url-input');
    const transcriptionModelSelect = $('transcription-model-select');
    const llmModelSelect = $('llm-model-select');
    const recordBtn = $('record-toggle-btn');
    const recordLabel = $('record-btn-label');
    const recordActionLabel = $('record-action-label');
    const historyList = $('transcription-list');
    let isRecording = false;

    const setSystemStatus = (kind, message) => {
        statusBar.className = `system-status-bar ${kind || ''}`.trim();
        statusMsg.textContent = message;
    };

    const updateRecordState = (recording) => {
        isRecording = Boolean(recording);
        recordBtn.classList.toggle('recording', isRecording);
        recordBtn.closest('.record-card')?.classList.toggle('recording', isRecording);
        recordLabel.textContent = isRecording ? 'Recording now' : 'Start recording';
        recordActionLabel.textContent = isRecording ? 'Stop recording' : 'Start dictating';
    };

    const providerDefaults = {
        groq: { transUrl: 'https://api.groq.com/openai/v1', llmUrl: 'https://api.groq.com/openai/v1', key: 'Provider API key' },
        openai: { transUrl: 'https://api.openai.com/v1', llmUrl: 'https://api.openai.com/v1', key: 'OpenAI API key' },
        openrouter: { llmUrl: 'https://openrouter.ai/api/v1', key: 'OpenRouter API key' },
        ollama: { transUrl: 'http://localhost:11434/v1', llmUrl: 'http://localhost:11434/v1', key: 'No key required' },
        custom: { key: 'API key (optional)' },
    };
    const visibleProvider = (provider, model) => {
        if (provider && provider !== 'litellm') return provider;
        const prefix = String(model || '').split('/')[0];
        return ['groq', 'openai', 'ollama', 'openrouter'].includes(prefix) ? prefix : 'custom';
    };

    const updateProviderUI = () => {
        const transProvider = transProviderSelect.value;
        const llmProvider = llmProviderSelect.value;
        const transMeta = providerDefaults[transProvider] || providerDefaults.custom;
        const llmMeta = providerDefaults[llmProvider] || providerDefaults.custom;
        if (transProvider === 'ollama' && !transBaseUrlInput.value) transBaseUrlInput.value = transMeta.transUrl;
        if (llmProvider === 'ollama' && !llmBaseUrlInput.value) llmBaseUrlInput.value = llmMeta.llmUrl;
        if (llmProvider === 'openrouter' && !llmBaseUrlInput.value) llmBaseUrlInput.value = llmMeta.llmUrl;
        $('transcription-api-key-hint').textContent = transMeta.key === 'No key required' ? 'This provider does not require a key.' : 'Encrypted by the desktop process.';
        $('llm-api-key-hint').textContent = llmMeta.key === 'No key required' ? 'This provider does not require a key.' : `${llmMeta.key} is encrypted by the desktop process.`;
        $('transcription-provider-status').textContent = transProvider === 'ollama' ? 'Chat only' : 'Not tested';
        $('llm-provider-status').textContent = 'Not tested';
    };

    const addOption = (select, value, label, selected = false) => {
        if (!select || !value) return;
        let option = [...select.options].find((item) => item.value === value);
        if (!option) {
            option = document.createElement('option');
            option.value = value;
            option.textContent = label || value;
            select.appendChild(option);
        }
        option.selected = selected;
    };

    const refreshModels = async () => {
        if (!api?.sendCommand) return null;
        const result = await api.sendCommand('get_models');
        if (result?.status !== 'ok') {
            setSystemStatus('error', result?.error || 'Could not query models');
            return result;
        }
        const configured = result.configured || {};
        transcriptionModelSelect.innerHTML = '';
        (result.models || []).forEach((model) => addOption(transcriptionModelSelect, model.id, model.name));
        (configured.transcription || []).forEach((model) => addOption(transcriptionModelSelect, model, `${model} (configured)`));
        if (configured.transcription?.[0]) transcriptionModelSelect.value = configured.transcription[0];
        llmModelSelect.innerHTML = '';
        (result.llm_models || []).forEach((model) => addOption(llmModelSelect, model.id, model.name));
        (configured.llm || []).forEach((model) => addOption(llmModelSelect, model));
        if (configured.llm?.[0]) llmModelSelect.value = configured.llm[0];
        $('provider-discovery-note').textContent = result.capability_warning || `Transcription: ${result.sources?.transcription || 'configured'} · LLM: ${result.sources?.llm || 'configured'}`;
        return result;
    };

    const runPreflightCheck = async (deep = false) => {
        if (!api?.sendCommand) {
            setSystemStatus('error', 'Engine bridge unavailable');
            return false;
        }
        setSystemStatus('', 'Checking engine, microphone, provider and models...');
        const result = await api.sendCommand('preflight', { deep });
        if (result?.status !== 'ok') {
            setSystemStatus('error', result?.error || 'Engine is offline');
            warningText.textContent = result?.error || 'The engine did not respond.';
            warningCard.classList.remove('hidden');
            return false;
        }
        const failedCheck = result.checks?.find((check) => check.status === 'error');
        if (!result.ready) {
            setSystemStatus('error', 'Action required before recording');
            warningText.textContent = result.errors?.[0]?.issue || failedCheck?.error || 'Review Diagnostics for the repair action.';
            warningCard.classList.remove('hidden');
            return false;
        }
        const live = result.checks?.some((check) => check.verified);
        setSystemStatus('', live ? 'Engine ready · checks passed' : 'Configuration loaded · live test runs on recording');
        warningCard.classList.add('hidden');
        return true;
    };

    const loadProviderConfig = async () => {
        const result = await api?.getProviderConfig?.();
        const config = result?.config;
        if (!config) return;
        const trans = config.transcription || config;
        const llm = config.llm || {};
        if (trans.provider) transProviderSelect.value = visibleProvider(trans.provider, trans.model || config.transcription_model);
        if (llm.provider) llmProviderSelect.value = visibleProvider(llm.provider, llm.model || config.llm_model);
        if (trans.base_url) transBaseUrlInput.value = trans.base_url;
        if (llm.base_url) llmBaseUrlInput.value = llm.base_url;
        if (config.api_key === 'configured') {
            transApiKeyInput.placeholder = 'Stored securely · leave blank to keep';
        }
        updateProviderUI();
        addOption(transcriptionModelSelect, trans.model || config.transcription_model, trans.model || config.transcription_model, true);
        addOption(llmModelSelect, llm.model || config.llm_model, llm.model || config.llm_model, true);
    };

    // Migrate the old plaintext renderer secret out of localStorage.
    localStorage.removeItem('audioscribe_api_key');
    transProviderSelect.addEventListener('change', async () => {
        updateProviderUI();
        await refreshModels();
        await runPreflightCheck();
    });
    llmProviderSelect.addEventListener('change', async () => {
        updateProviderUI();
        await refreshModels();
        await runPreflightCheck();
    });
    updateProviderUI();

    const refreshDevices = async () => {
        const select = $('audio-device-select');
        if (!select || !api?.sendCommand) return;
        const result = await api.sendCommand('get_devices');
        select.innerHTML = '';
        addOption(select, '', 'System default microphone', true);
        if (result?.status === 'ok') {
            (result.devices || []).forEach((device) => addOption(select, String(device.index), `${device.name} (${device.channels} ch)`));
        }
    };
    $('audio-device-select')?.addEventListener('change', async (event) => {
        const result = await api?.sendCommand?.('set_device', { device_index: event.target.value });
        if (result?.status !== 'ok') setSystemStatus('error', result?.error || 'Could not change microphone');
    });

    $('fix-config-btn')?.addEventListener('click', () => {
        document.querySelector('[data-tab="settings"]')?.click();
        transApiKeyInput.focus();
    });
    $('run-preflight-btn')?.addEventListener('click', async () => {
        const ready = await runPreflightCheck();
        const output = $('diag-results');
        output.textContent = ready ? 'System ready. All required engine checks passed.' : 'A blocking issue was found. See the warning above.';
        output.className = `diag-output-box ${ready ? 'diag-ok' : 'diag-error'}`;
    });

    $('save-settings-btn')?.addEventListener('click', async () => {
        const button = $('save-settings-btn');
        button.disabled = true;
        const config = {
            transcription: { provider: transProviderSelect.value, base_url: transBaseUrlInput.value.trim() || null, model: transcriptionModelSelect.value || undefined },
            llm: { provider: llmProviderSelect.value, base_url: llmBaseUrlInput.value.trim() || null, model: llmModelSelect.value || undefined },
        };
        if (transApiKeyInput.value.trim()) config.transcription.api_key = transApiKeyInput.value.trim();
        if (llmApiKeyInput.value.trim()) config.llm.api_key = llmApiKeyInput.value.trim();
        const result = await api?.saveProviderConfig?.(config);
        if (result?.status === 'ok') {
            await refreshModels();
            await runPreflightCheck();
            alert('Settings saved and applied to the engine.');
        } else {
            alert(result?.error || 'Could not apply settings to the engine.');
        }
        button.disabled = false;
    });

    $('refresh-models-btn')?.addEventListener('click', refreshModels);
    $('test-providers-btn')?.addEventListener('click', async () => {
        const ready = await runPreflightCheck(true);
        $('transcription-provider-status').textContent = ready ? 'Verified' : 'Needs attention';
        $('llm-provider-status').textContent = ready ? 'Verified' : 'Needs attention';
    });

    // Global hotkey recorder
    let listeningForHotkey = false;
    const prettyKey = (event) => {
        const modifiers = [];
        if (event.ctrlKey) modifiers.push('Ctrl');
        if (event.altKey) modifiers.push('Alt');
        if (event.shiftKey) modifiers.push('Shift');
        if (event.metaKey) modifiers.push('Super');
        const key = event.code.startsWith('Key') ? event.code.slice(3) : event.code.startsWith('Digit') ? event.code.slice(5) : event.code;
        return { accelerator: [...modifiers, key].join('+'), pretty: [...modifiers, key].join(' + ') };
    };
    const shortcut = localStorage.getItem('audioscribe_shortcut') || 'F9';
    $('hotkey-recorder-input').value = shortcut;
    $('active-hotkey-badge').textContent = shortcut;
    $('sidebar-hotkey').textContent = shortcut;
    $('record-hotkey-btn')?.addEventListener('click', () => {
        listeningForHotkey = true;
        $('hotkey-recorder-input').value = 'Press a key combination...';
    });
    document.addEventListener('keydown', async (event) => {
        if (!listeningForHotkey) return;
        event.preventDefault();
        const result = prettyKey(event);
        if (['Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) return;
        listeningForHotkey = false;
        const response = await api?.registerShortcut?.(result.accelerator);
        if (response?.status === 'ok') {
            $('hotkey-recorder-input').value = result.pretty;
            $('active-hotkey-badge').textContent = result.pretty;
            $('sidebar-hotkey').textContent = result.pretty;
            localStorage.setItem('audioscribe_shortcut', result.pretty);
        } else {
            $('hotkey-recorder-input').value = shortcut;
            alert(response?.error || 'Could not register shortcut.');
        }
    });

    // Profiles are kept local, but rendered without interpolating user text into HTML.
    const defaultProfiles = [
        { id: 'prof_std', name: 'Review and clarity', enabled: true, shortcut: 'F9', prompt: 'Fix grammar, punctuation and filler words while preserving meaning. Return only the revised text.' },
        { id: 'prof_trans', name: 'Translate to English', enabled: true, shortcut: 'Ctrl+Shift+E', prompt: 'Translate the transcription into natural professional English. Return only the translation.' },
    ];
    let profiles;
    try { profiles = JSON.parse(localStorage.getItem('audioscribe_profiles') || 'null') || defaultProfiles; } catch { profiles = defaultProfiles; }
    const saveProfiles = () => {
        localStorage.setItem('audioscribe_profiles', JSON.stringify(profiles));
        api?.updateProfiles?.(profiles);
    };
    const renderProfiles = () => {
        const list = $('profiles-list');
        if (!list) return;
        list.textContent = '';
        profiles.forEach((profile) => {
            const card = document.createElement('div');
            card.className = 'profile-card';
            const heading = document.createElement('div');
            heading.className = 'profile-header-row';
            const title = document.createElement('span');
            title.className = 'profile-title';
            title.textContent = profile.name;
            const enabled = document.createElement('input');
            enabled.type = 'checkbox'; enabled.checked = Boolean(profile.enabled); enabled.className = 'profile-enable-check';
            heading.append(enabled, title);
            const prompt = document.createElement('textarea');
            prompt.className = 'profile-prompt-preview'; prompt.rows = 2; prompt.value = profile.prompt;
            const actions = document.createElement('div'); actions.className = 'profile-actions-row';
            const hotkey = document.createElement('span'); hotkey.className = 'profile-hotkey-group'; hotkey.textContent = `Shortcut: ${profile.shortcut || 'none'}`;
            const save = document.createElement('button');
            save.className = 'btn-primary-sm'; save.textContent = 'Save & Apply';
            save.addEventListener('click', () => { profile.prompt = prompt.value.trim(); profile.enabled = enabled.checked; saveProfiles(); });
            actions.append(hotkey, save);
            card.append(heading, prompt, actions);
            list.appendChild(card);
        });
    };
    renderProfiles();
    $('add-profile-btn')?.addEventListener('click', () => {
        const name = prompt('Profile name:', 'Custom rule');
        const promptText = name && prompt('Profile instruction:', 'Review and organize the text...');
        if (!name || !promptText) return;
        profiles.push({ id: `prof_${Date.now()}`, name: name.trim(), enabled: true, shortcut: `Ctrl+Alt+${profiles.length + 1}`, prompt: promptText.trim() });
        saveProfiles(); renderProfiles();
    });

    // Productivity and cost metrics
    let totalWords = Number(localStorage.getItem('audioscribe_total_words') || 0);
    let totalLatency = 0;
    let totalTranscriptions = 0;
    const updateMetrics = () => {
        $('metric-words').textContent = totalWords.toLocaleString();
        const saved = Math.max(0, Math.round(totalWords / 40 - totalWords / 150));
        $('metric-time-saved').textContent = saved >= 60 ? `${(saved / 60).toFixed(1)} hrs` : `${saved} min`;
        $('metric-latency').textContent = totalTranscriptions ? `${Math.round(totalLatency / totalTranscriptions)} ms` : '—';
    };
    const refreshUsage = async () => {
        const result = await api?.sendCommand?.('get_usage');
        const summary = result?.summary;
        if (!summary) return;
        $('metric-cost').textContent = summary.cost_known ? `$${Number(summary.estimated_cost_usd).toFixed(4)}` : 'Unknown';
        const periods = result.periods || {};
        const formatCost = (item) => item?.cost_known ? `$${Number(item.estimated_cost_usd).toFixed(4)}` : 'Unknown';
        $('metric-cost-today').textContent = formatCost(periods.today);
        $('metric-cost-month').textContent = formatCost(periods.month);
        $('metric-cost-unknown').textContent = String(summary.unknown_cost_records || 0);
    };
    const recordMetric = (text, latency) => {
        if (!text) return;
        totalWords += text.trim().split(/\s+/).filter(Boolean).length;
        totalLatency += Number(latency) || 0;
        totalTranscriptions += 1;
        localStorage.setItem('audioscribe_total_words', String(totalWords));
        updateMetrics(); refreshUsage();
    };
    updateMetrics();

    recordBtn?.addEventListener('click', async () => {
        recordBtn.disabled = true;
        if (!isRecording) {
            const ready = await runPreflightCheck(true);
            if (ready) {
                const result = await api?.sendCommand?.('start_recording');
                if (result?.status !== 'ok') setSystemStatus('error', result?.error || 'Could not start recording');
                else updateRecordState(true);
            }
        } else {
            const result = await api?.sendCommand?.('stop_recording');
            if (result?.status !== 'ok') setSystemStatus('error', result?.error || 'Could not stop recording');
            else updateRecordState(false);
        }
        recordBtn.disabled = false;
    });

    api?.onEngineEvent?.((event) => {
        if (!event) return;
        if (event.event === 'status_changed') {
            if (event.data.status === 'recording') updateRecordState(true);
            if (event.data.status === 'processing' || event.data.status === 'ready') updateRecordState(false);
            setSystemStatus('', event.data.status === 'recording' ? 'Recording' : 'Processing transcription...');
        } else if (event.event === 'transcription_result') {
            const text = event.data.text || '';
            recordMetric(text, event.data.latency_ms);
            const empty = $('empty-history-state');
            empty?.remove();
            const item = document.createElement('div'); item.className = 'transcription-item';
            const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = `${new Date().toLocaleTimeString()} · ${Math.round(event.data.latency_ms || 0)} ms · ${event.data.model || 'model'}`;
            const body = document.createElement('div'); body.className = 'body'; body.textContent = text;
            item.append(meta, body); historyList.prepend(item);
            updateRecordState(false); setSystemStatus('', 'Engine ready · result delivered');
        } else if (event.event === 'error' || event.event === 'engine_error') {
            updateRecordState(false);
            setSystemStatus('error', event.data?.message || 'Engine error');
            warningText.textContent = event.data?.message || 'The engine reported an error.';
            warningCard.classList.remove('hidden');
        }
    });
    $('clear-history-btn')?.addEventListener('click', () => {
        historyList.textContent = '';
        const empty = document.createElement('div'); empty.className = 'empty-state'; empty.id = 'empty-history-state';
        empty.textContent = 'Your recent dictations will appear here.'; historyList.appendChild(empty);
    });

    loadProviderConfig().then(async () => { await refreshDevices(); await refreshModels(); await runPreflightCheck(); await refreshUsage(); });
});
