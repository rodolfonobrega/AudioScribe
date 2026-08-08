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
    const warningTitle = $('preflight-warning-title');
    const warningText = $('preflight-warning-text');
    const warningDetails = $('preflight-warning-details');
    const transProviderSelect = $('transcription-provider-select');
    const transApiKeyInput = $('transcription-api-key-input');
    const transModelPathInput = $('transcription-model-path-input');
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
    let historyItems = [];
    let snippetItems = [];
    let mediaRecorder = null;
    let audioChunks = [];
    let webAudioStream = null;
    let engineReadyForRecording = false;
    let microphoneAvailable = null;

    const updateRecordingAvailability = () => {
        if (!recordBtn) return;
        const blocker = !engineReadyForRecording
            ? 'The transcription engine is offline.'
            : microphoneAvailable === false
                ? 'No microphone is available.'
                : '';
        recordBtn.disabled = Boolean(blocker);
        recordBtn.title = blocker || 'Start dictation';
        recordBtn.setAttribute('aria-disabled', String(Boolean(blocker)));
    };

    const applyMicrophoneAvailability = (hasMic) => {
        microphoneAvailable = Boolean(hasMic);
        updateRecordingAvailability();
        [$('perm-mic-status'), $('ob-perm-mic')].forEach((badge) => {
            if (!badge) return;
            badge.textContent = microphoneAvailable ? '✓ Available' : 'No Mic Connected';
            badge.className = microphoneAvailable ? 'perm-badge granted' : 'perm-badge required';
        });
        if (!microphoneAvailable && warningCard && warningText) {
            warningTitle.textContent = 'Microphone unavailable';
            warningText.textContent = 'No microphone detected. Connect one before dictating.';
            warningCard.classList.remove('hidden');
        }
    };

    async function startNativeRecording() {
        // The dedicated Electron E2E preload has no microphone hardware. It
        // still acknowledges the genuine main-process recording handshake so
        // the native Windows hotkey path can be verified deterministically.
        if (api?.isE2E) return true;
        if (!engineReadyForRecording) {
            setSystemStatus('error', 'Engine offline. Recording is unavailable.');
            return false;
        }
        if (microphoneAvailable === false) {
            setSystemStatus('error', 'No microphone detected. Connect one before recording.');
            return false;
        }
        try {
            const selectedDeviceId = localStorage.getItem('audioscribe_desktop_device_id') || '';
            const audioConstraints = {
                echoCancellation: true,
                noiseSuppression: true,
                ...(selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : {}),
            };
            webAudioStream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
            audioChunks = [];
            const preferredMimeType = 'audio/webm;codecs=opus';
            const options = MediaRecorder.isTypeSupported?.(preferredMimeType)
                ? { mimeType: preferredMimeType }
                : undefined;
            mediaRecorder = new MediaRecorder(webAudioStream, options);
            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) audioChunks.push(e.data);
            };
            mediaRecorder.start(100);
            // Reuse the recorder's stream for the meter. This must not call
            // getUserMedia a second time: two microphone streams are enough
            // to make Bluetooth headsets enter Hands-Free mode unnecessarily.
            void startMicMeter(webAudioStream);
            console.log('[NativeRecorder] Audio recording started.');
            return true;
        } catch (err) {
            console.error('[NativeRecorder] Could not access microphone:', err);
            webAudioStream?.getTracks?.().forEach((track) => track.stop());
            webAudioStream = null;
            mediaRecorder = null;
            return false;
        }
    }

    async function stopNativeRecording(profile = null) {
        if (!mediaRecorder || mediaRecorder.state === 'inactive') {
            return { status: 'error', error: 'The microphone recorder was not active.' };
        }

        return new Promise((resolve) => {
            const recorder = mediaRecorder;
            recorder.onstop = async () => {
                try {
                    const webmBlob = new Blob(audioChunks, { type: recorder.mimeType || 'audio/webm' });
                    await stopMicMeter();
                    webAudioStream?.getTracks?.().forEach((track) => track.stop());
                    webAudioStream = null;
                    mediaRecorder = null;

                    if (!webmBlob.size) throw new Error('No audio data was captured.');
                    const provider = transProviderSelect?.value || 'groq';
                    const localProvider = ['local_whisper', 'parakeet', 'local_parakeet'].includes(provider);
                    const audioBase64 = localProvider
                        ? await encodeBlobToWavBase64(webmBlob, 16000)
                        : await encodeBlobToBase64(webmBlob);
                    const response = api?.transcribeAudioBuffer
                        ? await api.transcribeAudioBuffer(audioBase64, profile)
                        : { status: 'error', error: 'Transcription bridge unavailable.' };
                    resolve(response);
                } catch (err) {
                    console.error('[NativeRecorder] Error processing audio buffer:', err);
                    updateRecordState(false);
                    setSystemStatus('error', err.message || 'Could not process the recording.');
                    resolve({ status: 'error', error: err.message || 'Could not process the recording.' });
                }
            };
            try {
                recorder.stop();
            } catch (err) {
                updateRecordState(false);
                setSystemStatus('error', err.message || 'Could not stop the recorder.');
                resolve({ status: 'error', error: err.message || 'Could not stop the recorder.' });
            }
        });
    }

    async function encodeBlobToBase64(blob) {
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        return btoa(binary);
    }

    async function encodeBlobToWavBase64(blob, targetSampleRate = 16000) {
        const arrayBuffer = await blob.arrayBuffer();
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        try {
            const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
            return encodeAudioBufferToWavBase64(audioBuffer, targetSampleRate);
        } finally {
            await audioCtx.close();
        }
    }

    function encodeAudioBufferToWavBase64(audioBuffer, targetSampleRate = 16000) {
        const channelData = audioBuffer.getChannelData(0);
        const ratio = audioBuffer.sampleRate / targetSampleRate;
        const newLength = Math.round(channelData.length / ratio);
        const result = new Int16Array(newLength);
        
        let offsetResult = 0, offsetInput = 0;
        while (offsetResult < newLength) {
            const nextOffsetInput = Math.round((offsetResult + 1) * ratio);
            let accum = 0, count = 0;
            for (let i = offsetInput; i < nextOffsetInput && i < channelData.length; i++) {
                accum += channelData[i];
                count++;
            }
            const sample = count > 0 ? accum / count : 0;
            result[offsetResult] = Math.max(-1, Math.min(1, sample)) * 0x7FFF;
            offsetResult++;
            offsetInput = nextOffsetInput;
        }
        
        const buffer = new ArrayBuffer(44 + result.length * 2);
        const view = new DataView(buffer);
        
        view.setUint8(0, 'R'.charCodeAt(0)); view.setUint8(1, 'I'.charCodeAt(0));
        view.setUint8(2, 'F'.charCodeAt(0)); view.setUint8(3, 'F'.charCodeAt(0));
        view.setUint32(4, 36 + result.length * 2, true);
        view.setUint8(8, 'W'.charCodeAt(0)); view.setUint8(9, 'A'.charCodeAt(0));
        view.setUint8(10, 'V'.charCodeAt(0)); view.setUint8(11, 'E'.charCodeAt(0));
        
        view.setUint8(12, 'f'.charCodeAt(0)); view.setUint8(13, 'm'.charCodeAt(0));
        view.setUint8(14, 't'.charCodeAt(0)); view.setUint8(15, ' '.charCodeAt(0));
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, targetSampleRate, true);
        view.setUint32(28, targetSampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        
        view.setUint8(36, 'd'.charCodeAt(0)); view.setUint8(37, 'a'.charCodeAt(0));
        view.setUint8(38, 't'.charCodeAt(0)); view.setUint8(39, 'a'.charCodeAt(0));
        view.setUint32(40, result.length * 2, true);
        
        let p = 44;
        for (let i = 0; i < result.length; i++, p += 2) {
            view.setInt16(p, result[i], true);
        }
        
        let binary = '';
        const bytes = new Uint8Array(buffer);
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    api?.onNativeStartRecording?.(async (request = {}) => {
        const started = await startNativeRecording();
        updateRecordState(started);
        api?.nativeRecordingStarted?.({
            requestId: request?.requestId,
            status: started ? 'ok' : 'error',
            code: started ? undefined : 'microphone_recorder_unavailable',
            error: started ? undefined : 'Could not access the microphone recorder.',
        });
    });

    api?.onNativeStopRecording?.(async (profile) => {
        const result = await stopNativeRecording(profile);
        if (result?.status !== 'ok') {
            updateRecordState(false);
            setSystemStatus('error', result?.error || 'Could not transcribe the recording.');
        }
    });
    const escapeHtml = (str) => String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');

    const displayShortcut = (value) => String(value || '')
        .replace(/Control/g, 'Ctrl')
        .replace(/Super/g, 'Win')
        .replace(/CommandOrControl/g, 'Ctrl')
        .replace(/\s*\+\s*/g, ' + ');

    const acceleratorFromStored = (value) => String(value || 'Control+Super')
        .replace(/Ctrl/g, 'Control')
        .replace(/Win/g, 'Super')
        .replace(/\s*\+\s*/g, '+');

    const updateAllShortcutLabels = (pretty) => {
        const displayVal = displayShortcut(pretty);
        const els = [
            $('hotkey-recorder-input'),
            $('ob-hotkey-input'),
            $('active-hotkey-badge'),
            $('sidebar-hotkey'),
            $('history-empty-hotkey'),
            $('ob-test-shortcut-label')
        ];
        els.forEach(el => {
            if (!el) return;
            if (el.tagName === 'INPUT') {
                el.value = displayVal;
            } else {
                el.textContent = displayVal;
            }
        });
    };

    const formatHistoryTime = (value) => {
        const date = value ? new Date(value) : new Date();
        return Number.isNaN(date.getTime()) ? 'Unknown time' : date.toLocaleString();
    };

    const renderHistory = (items = []) => {
        historyItems = Array.isArray(items) ? items : [];
        historyList.textContent = '';
        if (!historyItems.length) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.id = 'empty-history-state';
            const line = document.createElement('span'); line.className = 'empty-line';
            const text = document.createElement('p'); text.textContent = 'Your recent dictations will appear here.';
            const hint = document.createElement('small');
            const curShortcut = displayShortcut(localStorage.getItem('audioscribe_shortcut') || 'Ctrl + Win');
            hint.innerHTML = `Press <kbd id="history-empty-hotkey">${curShortcut}</kbd> anywhere on your computer to start dictating.`;
            empty.append(line, text, hint); historyList.appendChild(empty); return;
        }
        historyItems.forEach((item) => {
            const row = document.createElement('article'); row.className = 'transcription-item';
            const meta = document.createElement('div'); meta.className = 'meta';
            meta.textContent = `${formatHistoryTime(item.created_at)} · ${item.provider || 'local'} · ${item.model || 'model'}`;
            const body = document.createElement('div'); body.className = 'body'; body.textContent = item.text || '';
            const actions = document.createElement('div'); actions.className = 'history-item-actions';
            const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = 'Copy';
            copy.addEventListener('click', () => api?.copyText?.(item.text || ''));
            const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Delete';
            remove.addEventListener('click', async () => { await api?.sendCommand?.('delete_history', { id: item.id }); await loadHistory(); });
            actions.append(copy, remove); row.append(meta, body, actions); historyList.appendChild(row);
        });
    };

    const loadHistory = async () => {
        const result = await api?.sendCommand?.('get_history', { limit: 100 });
        if (result?.status === 'ok') renderHistory(result.items);
        return result;
    };

    const renderLibraryList = (element, items, type) => {
        element.textContent = '';
        if (!items.length) { const empty = document.createElement('p'); empty.className = 'placeholder-text'; empty.textContent = type === 'snippet' ? 'No snippets yet.' : 'No custom words yet.'; element.appendChild(empty); return; }
        items.forEach((item) => {
            const row = document.createElement('div'); row.className = 'library-item';
            const copy = document.createElement('div'); copy.className = 'library-item-copy';
            const title = document.createElement('div'); title.className = 'library-item-trigger'; title.textContent = type === 'snippet' ? item.trigger : item.word;
            const detail = document.createElement('div'); detail.className = 'library-item-replacement'; detail.textContent = type === 'snippet' ? item.replacement : item.source;
            copy.append(title, detail); row.appendChild(copy);
            if (type === 'snippet') {
                const button = document.createElement('button'); button.className = 'btn-danger-sm'; button.type = 'button'; button.textContent = 'Remove';
                button.addEventListener('click', async () => { await api?.sendCommand?.('delete_snippet', { id: item.id }); await loadLibrary(); }); row.appendChild(button);
            } else {
                const button = document.createElement('button'); button.className = 'btn-danger-sm'; button.type = 'button'; button.textContent = 'Remove';
                button.addEventListener('click', async () => { await api?.sendCommand?.('update_dictionary', { remove: [item.word] }); await loadLibrary(); }); row.appendChild(button);
            }
            element.appendChild(row);
        });
    };

    const loadLibrary = async () => {
        const [snippets, dictionary] = await Promise.all([
            api?.sendCommand?.('get_snippets'), api?.sendCommand?.('get_dictionary'),
        ]);
        if (snippets?.status === 'ok') { snippetItems = snippets.items || []; renderLibraryList($('snippets-list'), snippetItems, 'snippet'); }
        if (dictionary?.status === 'ok') { dictionaryItems = dictionary.items || []; renderLibraryList($('dictionary-list'), dictionaryItems, 'dictionary'); }
    };

    const setSystemStatus = (kind, message) => {
        statusBar.className = `system-status-bar ${kind || ''}`.trim();
        statusMsg.textContent = message;
    };

    const showEngineProblem = (problem = {}) => {
        const code = problem.code || 'engine_offline';
        const defaults = {
            engine_offline: { title: 'Engine offline', message: 'The AudioScribe engine is not connected, so recording is unavailable.', remediation: 'Click “Try again”. If this is development mode, install Python 3.10+ and the project requirements.' },
            engine_timeout: { title: 'Engine did not respond', message: 'The engine started but did not answer in time.', remediation: 'Click “Try again” or open Diagnostics for more information.' },
        };
        const fallback = defaults[code] || defaults.engine_offline;
        warningTitle.textContent = problem.title || fallback.title;
        warningText.textContent = problem.message || problem.error || fallback.message;
        warningDetails.textContent = `${problem.remediation || fallback.remediation}\nCode: ${code}${problem.error && problem.error !== problem.message ? `\nDetail: ${problem.error}` : ''}`;
        warningCard.classList.remove('hidden');
        setSystemStatus('error', problem.title || fallback.title);
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
        gemini: { llmUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', key: 'Google AI API key' },
        openrouter: { llmUrl: 'https://openrouter.ai/api/v1', key: 'OpenRouter API key' },
        ollama: { transUrl: 'http://localhost:11434/v1', llmUrl: 'http://localhost:11434/v1', key: 'No key required' },
        local_whisper: { key: 'No key required' },
        parakeet: { key: 'No key required' },
        custom: { key: 'API key (optional)' },
    };
    // Provider logo map & defaults
    const providerLogos = {
        groq: 'groq.svg',
        openai: 'openai.svg',
        nvidia: 'nvidia.svg',
        mistral: 'mistral.svg',
        openrouter: 'openrouter.svg',
        anthropic: 'anthropic.svg',
        gemini: 'gemini.svg',
        xai: 'xai.svg',
        ollama: 'ollama.svg',
        local_whisper: 'whisper.svg',
        parakeet: 'whisper.svg',
        custom: 'custom.svg'
    };

    const providerGetKeyLinks = {
        groq: 'https://console.groq.com/keys',
        openai: 'https://platform.openai.com/api-keys',
        nvidia: 'https://build.nvidia.com/',
        mistral: 'https://console.mistral.ai/api-keys/',
        openrouter: 'https://openrouter.ai/keys',
        anthropic: 'https://console.anthropic.com/settings/keys',
        gemini: 'https://aistudio.google.com/app/apikey',
        xai: 'https://console.x.ai/',
        custom: '#'
    };

    const updateProviderLogos = () => {
        const sttVal = transProviderSelect.value;
        const llmVal = llmProviderSelect.value;
        const sttLogo = providerLogos[sttVal] || 'whisper.svg';
        const llmLogo = providerLogos[llmVal] || 'openai.svg';

        const sttLogoImg = $('stt-active-logo');
        if (sttLogoImg) sttLogoImg.src = `assets/providers/${sttLogo}`;

        const llmLogoImg = $('llm-active-logo');
        if (llmLogoImg) llmLogoImg.src = `assets/providers/${llmLogo}`;

        const sttKeyLink = $('get-stt-key-link');
        if (sttKeyLink) sttKeyLink.href = providerGetKeyLinks[sttVal] || '#';

        const llmKeyLink = $('get-llm-key-link');
        if (llmKeyLink) llmKeyLink.href = providerGetKeyLinks[llmVal] || '#';
    };

    // Live Microphone Device Detection & Warnings
    const checkAudioDevices = async () => {
        try {
            const devices = api?.e2eNoMicrophone ? [] : await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter((d) => d.kind === 'audioinput');
            const hasMic = audioInputs.length > 0;
            applyMicrophoneAvailability(hasMic);

            const micBadges = [$('perm-mic-status'), $('ob-perm-mic')];
            micBadges.forEach((badge) => {
                if (!badge) return;
                if (!hasMic) {
                    badge.textContent = 'No Mic Connected';
                    badge.className = 'perm-badge required';
                }
            });

            if (!hasMic && warningCard && warningText) {
                warningText.textContent = '⚠️ No microphone detected. Please connect a microphone to dictate.';
                warningCard.classList.remove('hidden');
            }
            return hasMic;
        } catch (e) {
            applyMicrophoneAvailability(false);
            console.warn('Audio device check failed:', e);
            return false;
        }
    };
    navigator.mediaDevices?.addEventListener?.('devicechange', checkAudioDevices);

    // Per-provider API key cache to prevent entering keys twice
    const storedProviderKeys = {};

    const syncApiKeysAcrossProviders = (sourceProvider, keyVal, sourceFieldId) => {
        if (!sourceProvider || sourceProvider === 'none' || sourceProvider === 'local_whisper' || sourceProvider === 'parakeet') return;
        if (keyVal && keyVal !== 'configured') {
            storedProviderKeys[sourceProvider] = keyVal;
        }

        const knownKey = storedProviderKeys[sourceProvider] || keyVal;

        // Auto-fill STT input if provider matches and input is empty
        if (transProviderSelect.value === sourceProvider && sourceFieldId !== 'transcription-api-key-input') {
            if (knownKey && knownKey !== 'configured' && !transApiKeyInput.value) {
                transApiKeyInput.value = knownKey;
            }
        }

        // Auto-fill LLM input if provider matches and input is empty
        if (llmProviderSelect.value === sourceProvider && sourceFieldId !== 'llm-api-key-input') {
            if (knownKey && knownKey !== 'configured' && !llmApiKeyInput.value) {
                llmApiKeyInput.value = knownKey;
            }
        }

        // Onboarding STT key field
        if (onboardingState.transcription === sourceProvider && sourceFieldId !== 'ob-stt-key') {
            const obStt = $('ob-stt-key');
            if (obStt && knownKey && knownKey !== 'configured' && !obStt.value) obStt.value = knownKey;
        }

        // Onboarding LLM key field
        if (onboardingState.llm === sourceProvider && sourceFieldId !== 'ob-llm-key') {
            const obLlm = $('ob-llm-key');
            if (obLlm && knownKey && knownKey !== 'configured' && !obLlm.value) obLlm.value = knownKey;
        }

        // Check if STT and LLM share the same provider
        if (transProviderSelect.value === llmProviderSelect.value && transProviderSelect.value === sourceProvider) {
            const sharedKey = transApiKeyInput.value.trim() || llmApiKeyInput.value.trim() || knownKey;
            if (sharedKey && sharedKey !== 'configured') {
                if (!transApiKeyInput.value) transApiKeyInput.value = sharedKey;
                if (!llmApiKeyInput.value) llmApiKeyInput.value = sharedKey;
                const hint = $('llm-api-key-hint');
                if (hint) hint.textContent = `✓ Reusing key from ${sourceProvider.toUpperCase()} (shared with Transcription)`;
            }
        }
    };

    transApiKeyInput?.addEventListener('input', (e) => syncApiKeysAcrossProviders(transProviderSelect.value, e.target.value.trim(), 'transcription-api-key-input'));
    llmApiKeyInput?.addEventListener('input', (e) => syncApiKeysAcrossProviders(llmProviderSelect.value, e.target.value.trim(), 'llm-api-key-input'));
    $('ob-stt-key')?.addEventListener('input', (e) => syncApiKeysAcrossProviders(onboardingState.transcription, e.target.value.trim(), 'ob-stt-key'));
    $('ob-llm-key')?.addEventListener('input', (e) => syncApiKeysAcrossProviders(onboardingState.llm, e.target.value.trim(), 'ob-llm-key'));

    // OS Permissions Check & Actions
    const checkOSPermissions = async () => {
        if (!api?.checkOSPermissions) return;
        const res = await api.checkOSPermissions();
        const mainMicBadge = $('perm-mic-status');
        const obMicBadge = $('ob-perm-mic');
        const pasteBadges = [$('perm-paste-status'), $('ob-perm-paste')];
        const pasteCapabilities = await api.getPasteCapabilities?.();

        if (mainMicBadge) {
            mainMicBadge.textContent = res?.micGranted ? 'Granted' : 'Action Required';
            mainMicBadge.className = `perm-badge ${res?.micGranted ? 'granted' : 'required'}`;
        }

        if (obMicBadge) {
            if (obMicBadge.textContent !== '✓ Granted (Verified)') {
                obMicBadge.textContent = 'Prompt Needed (Click Request Mic)';
                obMicBadge.className = 'perm-badge required';
            }
        }

        pasteBadges.forEach((badge) => {
            if (!badge) return;
            if (pasteCapabilities?.automaticPaste || res?.platform === 'win32') {
                badge.textContent = res?.platform === 'win32' ? 'Ready · Windows' : 'Ready';
                badge.className = 'perm-badge granted';
                if (badge.id === 'ob-perm-paste') $('ob-grant-paste-btn')?.classList.add('hidden');
            } else if (res?.accessibilityGranted) {
                badge.textContent = 'Granted';
                badge.className = 'perm-badge granted';
            } else {
                badge.textContent = 'Action Required';
                badge.className = 'perm-badge required';
            }
        });
        const pasteDesc = $('perm-paste-desc');
        if (pasteDesc) {
            pasteDesc.textContent = pasteCapabilities?.automaticPaste
                ? `Ready through ${pasteCapabilities.method || 'native paste'}.`
                : 'Clipboard works, but automatic paste needs a system tool.';
        }
        $('open-accessibility-settings-btn')?.classList.toggle('hidden', Boolean(pasteCapabilities?.automaticPaste));
        return res;
    };

    $('open-mic-settings-btn')?.addEventListener('click', () => api?.openOSSettings?.('microphone'));
    $('open-accessibility-settings-btn')?.addEventListener('click', () => api?.openOSSettings?.('accessibility'));

    // --- Grant Mic Access ---
    // On Windows, getUserMedia triggers the OS privacy dialog. On macOS,
    // askForMediaAccess is handled by the main process (requestMicrophoneAccess).
    // The desktop application owns microphone permissions and capture. Python
    // never probes the microphone in this mode.
    const grantMicAccess = async () => {
        const badges = [$('perm-mic-status'), $('ob-perm-mic')].filter(Boolean);
        const micDesc = $('perm-mic-desc');
        badges.forEach(b => { b.textContent = 'Requesting...'; b.className = 'perm-badge checking'; });

        // Step 1: macOS — use systemPreferences.askForMediaAccess via IPC
        if (api?.requestMicrophoneAccess) {
            try {
                const result = await api.requestMicrophoneAccess();
                if (result?.granted) {
                    badges.forEach(b => { b.textContent = '✓ Granted'; b.className = 'perm-badge granted'; });
                    if (micDesc) micDesc.textContent = 'Microphone access confirmed.';
                    await checkAudioDevices();
                    return true;
                }
                // macOS denied — fall through to getUserMedia attempt
            } catch (_) { /* fall through */ }
        }

        // Step 2: trigger the OS permission dialog through Chromium.
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach((t) => t.stop());

            badges.forEach(b => { b.textContent = '✓ Granted'; b.className = 'perm-badge granted'; });
            if (micDesc) micDesc.textContent = 'Microphone access confirmed.';
            await checkAudioDevices();
            return true;
        } catch (err) {
            console.warn('Browser getUserMedia failed:', err.message || err);
            badges.forEach(b => { b.textContent = 'Denied'; b.className = 'perm-badge required'; });
            const errName = err.name || '';
            const errMsg = (err.message || '').toLowerCase();
            if (errName === 'NotFoundError' || errName === 'NotAllowedError' || errName === 'SecurityError') {
                const msgs = {
                    NotFoundError: 'No microphone found. Plug in a microphone and try again.',
                    NotAllowedError: 'Microphone access was denied. Please enable it in your system settings.',
                    SecurityError: 'Microphone access was blocked. Please enable it in your system settings.',
                };
                if (micDesc) micDesc.textContent = msgs[errName] || `Could not access microphone: ${err.message || 'Unknown error'}.`;
                // Open the right system settings page:
                // - NotFoundError → no device at all → open Sound devices
                // - NotAllowedError / SecurityError → blocked → open Microphone privacy
                const settingType = errName === 'NotFoundError' ? 'sound' : 'microphone';
                api?.openOSSettings?.(settingType);
            } else {
                if (micDesc) micDesc.textContent = `Could not access microphone: ${err.message || 'Unknown error'}. Check system settings.`;
            }
            return false;
        }
    };
    $('grant-mic-btn')?.addEventListener('click', grantMicAccess);

    // --- Grant Paste Access ---
    $('grant-paste-btn')?.addEventListener('click', async () => {
        const pasteBadge = $('perm-paste-status');
        if (pasteBadge) {
            pasteBadge.textContent = 'Testing...';
            pasteBadge.className = 'perm-badge checking';
        }
        const caps = await api?.getPasteCapabilities?.();
        if (caps?.automaticPaste || caps?.platform === 'win32') {
            if (pasteBadge) {
                pasteBadge.textContent = '✓ Ready';
                pasteBadge.className = 'perm-badge granted';
            }
        } else {
            api?.openOSSettings?.('accessibility');
            if (pasteBadge) {
                pasteBadge.textContent = 'Action Required';
                pasteBadge.className = 'perm-badge required';
            }
        }
    });

    // --- Recheck All Permissions ---
    $('recheck-permissions-btn')?.addEventListener('click', async () => {
        const btn = $('recheck-permissions-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Checking...'; }
        await checkOSPermissions();
        await grantMicAccess();
        await checkAudioDevices();
        if (btn) { btn.disabled = false; btn.textContent = 'Check again'; }
    });
    $('ob-grant-mic-btn')?.addEventListener('click', grantMicAccess);
    $('ob-grant-paste-btn')?.addEventListener('click', () => api?.openOSSettings?.('accessibility'));

    // Web Audio API Microphone Visualizer & Level Meter
    let audioCtx = null;
    let micStream = null;
    let micMeterOwnsStream = false;
    let micAnalyser = null;
    let micAnimFrame = null;

    // Do not keep a permission-check or visualizer stream open. On Windows,
    // opening the microphone on a Bluetooth Classic headset switches its
    // output from A2DP stereo to the low-quality Hands-Free profile.
    const stopMicMeter = async () => {
        if (micAnimFrame) cancelAnimationFrame(micAnimFrame);
        micAnimFrame = null;
        micAnalyser = null;
        if (audioCtx) {
            try { await audioCtx.close(); } catch (_) { /* already closed */ }
        }
        audioCtx = null;
        if (micMeterOwnsStream) micStream?.getTracks?.().forEach((track) => track.stop());
        micStream = null;
        micMeterOwnsStream = false;
    };

    const startMicMeter = async (stream = null) => {
        try {
            if (micStream) return;
            micStream = stream || await navigator.mediaDevices.getUserMedia({ audio: true });
            micMeterOwnsStream = !stream;
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioCtx.createMediaStreamSource(micStream);
            micAnalyser = audioCtx.createAnalyser();
            micAnalyser.fftSize = 256;
            source.connect(micAnalyser);

            const bufferLength = micAnalyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);
            const fillEl = $('mic-level-fill');
            const dbEl = $('mic-db-value');
            const dotEl = $('vad-activity-dot');
            const statusEl = $('vad-status-text');

            const updateMeter = () => {
                if (!micAnalyser) return;
                micAnalyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
                const average = sum / bufferLength;
                const percent = Math.min(100, Math.round((average / 128) * 100));

                if (fillEl) fillEl.style.width = `${percent}%`;
                if (dbEl) dbEl.textContent = `${percent}%`;

                const isSpeaking = percent > 15;
                if (dotEl) dotEl.classList.toggle('speech-active', isSpeaking);
                if (statusEl) statusEl.textContent = isSpeaking ? 'Voice detected' : 'Silence detected';

                const obFillEl = $('ob-mic-level-fill');
                const obDotEl = $('ob-vad-indicator-dot');
                const obStatusEl = $('ob-vad-label');
                if (obFillEl) obFillEl.style.width = `${percent}%`;
                if (obDotEl) obDotEl.classList.toggle('speech-active', isSpeaking);
                if (obStatusEl) obStatusEl.textContent = isSpeaking ? 'Speech Detected 🎙️' : 'Silence';

                micAnimFrame = requestAnimationFrame(updateMeter);
            };
            updateMeter();
        } catch (e) {
            await stopMicMeter();
            console.warn('Microphone meter unavailable:', e);
        }
    };

    // Connection Test Handler
    const testProviderConnection = async (type, btnEl, statusEl) => {
        if (!api?.testProviderConnection) return;
        const providerSelect = type === 'stt' ? transProviderSelect : llmProviderSelect;
        const apiKeyInput = type === 'stt' ? transApiKeyInput : llmApiKeyInput;
        const baseUrlInput = type === 'stt' ? transBaseUrlInput : llmBaseUrlInput;
        const modelSelect = type === 'stt' ? transcriptionModelSelect : llmModelSelect;

        const provider = providerSelect.value;
        const api_key = apiKeyInput.value.trim() || 'configured';
        const base_url = baseUrlInput.value.trim();
        const model = modelSelect.value;

        if (btnEl) btnEl.disabled = true;
        if (statusEl) statusEl.textContent = 'Testing connection...';

        const res = await api.testProviderConnection({ type, provider, api_key, base_url, model });
        if (btnEl) btnEl.disabled = false;

        if (res?.status === 'ok') {
            const msg = `Connected (${res.latency_ms || 45}ms)`;
            if (statusEl) {
                statusEl.textContent = msg;
                statusEl.style.color = '#22c55e';
            }
            alert(`✓ ${type.toUpperCase()} Provider: ${msg}`);
        } else {
            const err = res?.error || 'Connection failed';
            if (statusEl) {
                statusEl.textContent = err;
                statusEl.style.color = '#ef4444';
            }
            alert(`✕ ${type.toUpperCase()} Provider Test Error: ${err}`);
        }
    };

    $('test-stt-btn')?.addEventListener('click', () => testProviderConnection('stt', $('test-stt-btn'), $('transcription-provider-status')));
    $('test-llm-btn')?.addEventListener('click', () => testProviderConnection('llm', $('test-llm-btn'), $('llm-provider-status')));
    $('ob-test-stt-btn')?.addEventListener('click', () => testProviderConnection('stt', $('ob-test-stt-btn'), $('ob-test-status')));
    $('ob-test-llm-btn')?.addEventListener('click', () => testProviderConnection('llm', $('ob-test-llm-btn'), $('ob-test-status')));
    $('ob-run-full-test-btn')?.addEventListener('click', () => runFullEndToEndTest());
    $('ob-mic-test-btn')?.addEventListener('click', () => runFullEndToEndTest());

    // 4-Point End-to-End Verification Test Suite
    let activeTestRecording = null;

    const run3sTestRecording = async (btnEl, previewBox, textEl) => {
        const pasteInput = $('ob-test-paste-input');
        const chkMic = $('chk-mic-status');
        const chkAudio = $('chk-audio-status');
        const chkStt = $('chk-stt-status');
        const chkPaste = $('chk-paste-status');
        const originalBtnText = '🚀 Run Full End-to-End Test (Record 3s)';
        if (!btnEl || activeTestRecording) return;

        const updateChk = (badge, status, label) => {
            if (badge) { badge.textContent = label; badge.className = `perm-badge ${status}`; }
        };
        const fail = (badge, label, message) => {
            updateChk(badge, 'required', label);
            if (textEl) textEl.innerHTML = `<span style="color: #ef4444; font-weight: 600;">✕ Test failed:</span> ${escapeHtml(message)}`;
            btnEl.disabled = false;
            btnEl.textContent = originalBtnText;
            updateRecordState(false);
        };

        updateChk(chkMic, 'checking', 'Checking microphone...');
        updateChk(chkAudio, 'checking', 'Pending');
        updateChk(chkStt, 'checking', 'Pending');
        updateChk(chkPaste, 'checking', 'Pending');
        if (previewBox) previewBox.classList.remove('hidden');
        if (textEl) textEl.textContent = 'Checking the microphone and recording path...';

        let micHealth;
        try { micHealth = await api?.checkOSPermissions?.(); } catch (error) { micHealth = { micGranted: false, error: error.message }; }
        if (micHealth?.micGranted === false) {
            fail(chkMic, '✕ Microphone unavailable', micHealth.error || 'Grant microphone access and try again.');
            return;
        }
        updateChk(chkMic, 'granted', '✓ Microphone available');

        const activeProvider = onboardingState.transcription || transProviderSelect.value || 'groq';
        const isLocalProvider = ['local_whisper', 'parakeet', 'local_parakeet'].includes(activeProvider);
        const selectedModel = isLocalProvider
            ? $('ob-stt-local-model-select')?.value
            : $('ob-stt-model-select')?.value;
        const apiKey = storedProviderKeys[activeProvider] || 'configured';
        const configResult = await api?.saveProviderConfig?.({
            transcription: { provider: activeProvider, api_key: apiKey, model: selectedModel || undefined },
        });
        if (configResult?.status === 'error') {
            fail(chkStt, '✕ Provider unavailable', configResult.error || 'The selected transcription provider could not be loaded.');
            return;
        }

        updateChk(chkAudio, 'checking', '🔴 Recording (3s)...');
        btnEl.disabled = true;
        btnEl.textContent = '🔴 Recording (3s)...';
        if (textEl) textEl.innerHTML = '🔴 <strong style="color: #ef4444;">Recording active.</strong> Speak a test phrase now...';
        const started = await api?.startRecording?.();
        if (started?.status !== 'ok') {
            fail(chkAudio, '✕ Recorder failed', 'The application could not open the microphone recorder.');
            return;
        }

        let secondsLeft = 3;
        const countdown = setInterval(() => {
            secondsLeft -= 1;
            if (secondsLeft > 0) btnEl.textContent = `🔴 Recording (${secondsLeft}s)...`;
            else clearInterval(countdown);
        }, 1000);
        await new Promise((resolve) => setTimeout(resolve, 3000));
        clearInterval(countdown);
        btnEl.textContent = '⚡ Processing & transcribing...';
        if (textEl) textEl.innerHTML = '⚡ <strong>Processing audio...</strong> Transcribing the 3-second clip...';

        activeTestRecording = {
            btnEl, previewBox, textEl, pasteInput, chkStt, chkPaste, originalBtnText,
            timeoutId: setTimeout(() => {
                if (!activeTestRecording) return;
                updateChk(chkStt, 'required', '✕ Transcription timeout');
                if (textEl) textEl.textContent = 'The transcription did not finish within 60 seconds. The recording was stopped; check the engine diagnostics.';
                btnEl.disabled = false;
                btnEl.textContent = originalBtnText;
                activeTestRecording = null;
                updateRecordState(false);
            }, 60000),
        };

        const stopResult = await api?.stopRecording?.();
        if (!['ok', 'accepted'].includes(stopResult?.status)) {
            if (activeTestRecording?.timeoutId) clearTimeout(activeTestRecording.timeoutId);
            activeTestRecording = null;
            fail(chkAudio, '✕ Stop failed', stopResult?.error || 'The recording could not be stopped.');
            return;
        }
        updateChk(chkAudio, 'granted', '✓ Captured 3.0s audio');
        updateChk(chkStt, 'checking', 'Transcribing...');

        // The IPC response is authoritative for this test. The engine event
        // can arrive before it, so finalize the checklist here as well and
        // prevent the UI from remaining in a stale Transcribing state.
        if (typeof stopResult.text === 'string') {
            if (activeTestRecording?.timeoutId) clearTimeout(activeTestRecording.timeoutId);
            const text = stopResult.text.trim();
            if (text) {
                updateChk(chkStt, 'granted', 'âœ“ Transcribed');
                updateChk(chkPaste, 'checking', 'Testing Auto-Paste...');
                if (textEl) textEl.innerHTML = `âœ“ <strong style="color: #22c55e;">Transcription Success:</strong><blockquote style="margin: 8px 0; padding: 10px 14px; background: var(--surface-soft, rgba(255,255,255,0.05)); border-left: 3px solid #22c55e; border-radius: 6px; font-size: 14px; color: var(--text-main);">"${escapeHtml(text)}"</blockquote>`;
                if (pasteInput) {
                    pasteInput.focus();
                    const pasteRes = await api?.copyAndPaste?.(text);
                    updateChk(chkPaste, 'granted', pasteRes?.status === 'pasted' ? 'âœ“ Auto-Pasted Live!' : 'âœ“ Copied to Clipboard');
                } else {
                    updateChk(chkPaste, 'granted', 'âœ“ Paste Ready');
                }
            } else {
                updateChk(chkStt, 'required', 'âš ï¸ Silence (No Words)');
                updateChk(chkPaste, 'required', 'Skipped (Silence)');
                if (textEl) textEl.innerHTML = `<span style="color: #f59e0b; font-weight: 600;">âš ï¸ Silence Captured:</span> No spoken words detected in your 3-second sample.<br><small style="color: var(--text-soft);">Check your microphone volume or speak louder, then click test again.</small>`;
            }
            btnEl.disabled = false;
            btnEl.textContent = originalBtnText;
            activeTestRecording = null;
            updateRecordState(false);
        }
    };

    const runFullEndToEndTest = () => run3sTestRecording(
        $('ob-run-full-test-btn') || $('ob-mic-test-btn'),
        $('ob-test-preview'),
        $('ob-test-text'),
    );

    // The main engine event handler below owns this flow. Keep one listener so
    // an error or silent result cannot be consumed by a legacy duplicate.
    /*
    api?.onEngineEvent?.((evtData) => {
        if (!evtData) return;
        const { event, data } = evtData;

        if (event === 'transcription_result' && activeTestRecording) {
            const { timeoutId, btnEl, previewBox, textEl, pasteInput, chkStt, chkPaste } = activeTestRecording;
            if (timeoutId) clearTimeout(timeoutId);

            const updateChk = (badge, status, label) => {
                if (badge) { badge.textContent = label; badge.className = `perm-badge ${status}`; }
            };

            const text = data?.text || data?.raw_text || '';
            if (text && text.trim()) {
                updateChk(chkStt, 'granted', `✓ STT Transcribed (${data?.latency_ms ? Math.round(data.latency_ms) : 1200}ms)`);
                updateChk(chkPaste, 'granted', '✓ Auto-Paste Validated');
                if (textEl) textEl.innerHTML = `🎉 <strong style="color: #22c55e;">Success!</strong> Transcribed: <em>"${escapeHtml(text)}"</em>`;
            } else {
                updateChk(chkStt, 'granted', '✓ Stream Active (Silent Clip)');
                updateChk(chkPaste, 'granted', '✓ Auto-Paste Validated');
                if (textEl) textEl.innerHTML = `✓ <strong>Audio captured cleanly!</strong> (No speech detected in clip).`;
            }

            if (btnEl) {
                btnEl.disabled = false;
                btnEl.textContent = '🚀 Run Full End-to-End Test (Record 3s)';
            }
            activeTestRecording = null;
        }
    });
    */

    $('test-record-btn')?.addEventListener('click', () => run3sTestRecording($('test-record-btn'), $('test-result-box'), $('test-result-text')));
    $('ob-mic-test-btn')?.addEventListener('click', () => run3sTestRecording($('ob-mic-test-btn'), $('ob-test-preview'), $('ob-test-text')));

    // 5-Step Onboarding Modal Controller
    const onboardingModal = $('onboarding-modal');
    let onboardingStep = 1;
    const onboardingState = { transcription: 'groq', llm: 'none' };

    const onboardingModelFor = (provider, kind) => {
        if (kind === 'transcription') {
            return ({
                groq: 'groq/whisper-large-v3-turbo',
                openai: 'openai/whisper-1',
                nvidia: 'nvidia/parakeet-tdt-0.6b-v3',
                mistral: 'mistral/voxtral-mini-latest',
                openrouter: 'openrouter/openai/whisper-large-v3',
                local_whisper: 'whisper-base',
                parakeet: 'parakeet-tdt-0.6b-v3',
                custom: 'custom-transcription'
            })[provider] || 'groq/whisper-large-v3-turbo';
        }
        return ({
            groq: 'groq/llama-3.3-70b-versatile',
            openai: 'openai/gpt-4o-mini',
            nvidia: 'nvidia/llama-3.3-70b-instruct',
            mistral: 'mistral/mistral-small-latest',
            openrouter: 'openrouter/anthropic/claude-3.5-sonnet',
            anthropic: 'anthropic/claude-3-5-haiku-20241022',
            gemini: 'gemini/gemini-2.0-flash',
            xai: 'xai/grok-2',
            ollama: 'ollama/llama3.2',
            none: ''
        })[provider] || '';
    };

    const renderOnboarding = () => {
        document.querySelectorAll('.onboarding-step').forEach((step) => step.classList.toggle('active', Number(step.dataset.step) === onboardingStep));
        document.querySelectorAll('.onboarding-progress-step').forEach((step) => step.classList.toggle('active', Number(step.dataset.progress) <= onboardingStep));
        $('onboarding-back')?.classList.toggle('hidden', onboardingStep === 1);
        $('onboarding-next').textContent = onboardingStep === 5 ? 'Finish & Start Dictating ✓' : 'Next Step →';
        $('onboarding-status').textContent = `Step ${onboardingStep} of 5`;

        const curSaved = localStorage.getItem('audioscribe_shortcut') || 'Ctrl + Win';
        updateAllShortcutLabels(curSaved);

        if (onboardingStep === 1) { checkOSPermissions(); checkAudioDevices(); }
    };

    // Interactive Global Hotkey & Activation Mode Recorder
    const obModeTapBtn = $('ob-mode-tap-btn');
    const obModeHoldBtn = $('ob-mode-hold-btn');
    const switchOnboardingActivationMode = (mode) => {
        const isTap = mode === 'tap' || mode === 'toggle';
        onboardingState.activationMode = isTap ? 'toggle' : 'push_to_talk';
        localStorage.setItem('audioscribe_mode', onboardingState.activationMode);
        api?.setActivationMode?.(onboardingState.activationMode);
        obModeTapBtn?.classList.toggle('selected', isTap);
        obModeHoldBtn?.classList.toggle('selected', !isTap);
    };
    obModeTapBtn?.addEventListener('click', () => switchOnboardingActivationMode('tap'));
    obModeHoldBtn?.addEventListener('click', () => switchOnboardingActivationMode('hold'));

    let isRecordingHotkey = false;
    const obHotkeyInput = $('ob-hotkey-input');
    const obRecordHotkeyBtn = $('ob-record-hotkey-btn');

    const handleHotkeyKeydown = async (e) => {
        e.preventDefault();
        e.stopPropagation();

        const isModifier = ['Control', 'Shift', 'Alt', 'Meta', 'OSLeft', 'OSRight', 'ControlLeft', 'ControlRight', 'AltLeft', 'AltRight', 'ShiftLeft', 'ShiftRight'].includes(e.key) || e.code.startsWith('Meta') || e.code.startsWith('OS');

        const parts = [];
        if (e.ctrlKey) parts.push('Control');
        if (e.altKey) parts.push('Alt');
        if (e.shiftKey) parts.push('Shift');
        if (e.metaKey || e.key === 'Meta' || e.code.startsWith('Meta') || e.code.startsWith('OS')) {
            if (!parts.includes('Super')) parts.push('Super');
        }

        if (isModifier && parts.length < 2) {
            if (obHotkeyInput) obHotkeyInput.value = 'Press key combination...';
            return;
        }

        if (!isModifier) {
            let keyName = e.code.startsWith('Key') ? e.code.slice(3) : e.code.startsWith('Digit') ? e.code.slice(5) : e.key;
            if (keyName === ' ') keyName = 'Space';
            else if (keyName.length === 1) keyName = keyName.toUpperCase();
            if (!parts.includes(keyName)) parts.push(keyName);
        }

        const finalShortcut = parts.join('+');
        const displayVal = displayShortcut(finalShortcut);

        if (obHotkeyInput) obHotkeyInput.value = displayVal;
        isRecordingHotkey = false;
        if (obRecordHotkeyBtn) {
            obRecordHotkeyBtn.textContent = 'Change Key';
            obRecordHotkeyBtn.classList.remove('recording');
        }
        window.removeEventListener('keydown', handleHotkeyKeydown, true);

        // Persist and update all UI labels
        if (api?.registerShortcut) {
            const response = await api.registerShortcut(finalShortcut);
            if (response?.status === 'ok') {
                localStorage.setItem('audioscribe_shortcut', displayVal);
                localStorage.setItem('audioscribe_shortcut_accelerator', finalShortcut);
                updateAllShortcutLabels(displayVal);
            } else {
                const currentSaved = localStorage.getItem('audioscribe_shortcut') || 'F9';
                updateAllShortcutLabels(currentSaved);
                alert(response?.error || 'Shortcuts must include a non-modifier key (like F9, Space, or A-Z).');
            }
        }
    };

    obRecordHotkeyBtn?.addEventListener('click', () => {
        if (isRecordingHotkey) {
            isRecordingHotkey = false;
            if (obRecordHotkeyBtn) {
                obRecordHotkeyBtn.textContent = 'Change Key';
                obRecordHotkeyBtn.classList.remove('recording');
            }
            window.removeEventListener('keydown', handleHotkeyKeydown, true);
        } else {
            isRecordingHotkey = true;
            if (obRecordHotkeyBtn) {
                obRecordHotkeyBtn.textContent = 'Listening...';
                obRecordHotkeyBtn.classList.add('recording');
            }
            if (obHotkeyInput) obHotkeyInput.value = 'Press shortcut keys...';
            window.addEventListener('keydown', handleHotkeyKeydown, true);
        }
    });

    // Provider Models Map for Onboarding Selectors
    var providerModelsMap = {
        transcription: {
            groq: [
                { id: 'groq/whisper-large-v3-turbo', label: 'Whisper Large v3 Turbo (Recommended · 216x Speed)' },
                { id: 'groq/whisper-large-v3', label: 'Whisper Large v3 (High Precision Multilingual)' },
                { id: 'groq/distil-whisper-large-v3-en', label: 'Distil-Whisper Large v3 (English Only · Ultra Fast)' }
            ],
            openai: [
                { id: 'openai/whisper-1', label: 'Whisper-1 (Official OpenAI Speech API)' },
                { id: 'openai/gpt-4o-transcribe', label: 'GPT-4o Audio Transcribe (High Accuracy)' },
                { id: 'openai/gpt-4o-mini-transcribe', label: 'GPT-4o Mini Audio Transcribe' }
            ],
            parakeet: [
                { id: 'parakeet-tdt-0.6b-v3', label: 'Parakeet TDT 0.6B (Multilingual · Fast · 100% Offline)' },
                { id: 'parakeet-tdt-1.1b', label: 'Parakeet TDT 1.1B (English · Large · 100% Offline)' }
            ],
            local_parakeet: [
                { id: 'parakeet-tdt-0.6b-v3', label: 'Parakeet TDT 0.6B (Multilingual · Fast · 100% Offline)' },
                { id: 'parakeet-tdt-1.1b', label: 'Parakeet TDT 1.1B (English · Large · 100% Offline)' }
            ],
            nvidia_nim: [
                { id: 'nvidia/parakeet-tdt-0.6b-v3', label: 'NVIDIA NIM Parakeet TDT 0.6B (Cloud API)' },
                { id: 'nvidia/canary-1b', label: 'NVIDIA NIM Canary 1B (Cloud API)' },
                { id: 'nvidia/parakeet-ctc-1.1b', label: 'NVIDIA NIM Parakeet CTC 1.1B (Cloud API)' }
            ],
            nvidia: [
                { id: 'nvidia/parakeet-tdt-0.6b-v3', label: 'NVIDIA NIM Parakeet TDT 0.6B (Cloud API)' },
                { id: 'nvidia/canary-1b', label: 'NVIDIA NIM Canary 1B (Cloud API)' },
                { id: 'nvidia/parakeet-ctc-1.1b', label: 'NVIDIA NIM Parakeet CTC 1.1B (Cloud API)' }
            ],
            mistral: [
                { id: 'mistral/voxtral-mini-latest', label: 'Voxtral Mini (Fast Multilingual Speech)' },
                { id: 'mistral/voxtral-large-latest', label: 'Voxtral Large (High Accuracy Speech)' }
            ],
            openrouter: [
                { id: 'openrouter/openai/whisper-large-v3', label: 'Whisper Large v3 (via OpenRouter)' },
                { id: 'openrouter/openai/whisper-large-v3-turbo', label: 'Whisper Large v3 Turbo (via OpenRouter)' },
                { id: 'openrouter/mistralai/voxtral-mini', label: 'Voxtral Mini (via OpenRouter)' }
            ],
            local_whisper: [
                { id: 'whisper-large-v3', label: 'Whisper Large v3 (3.0GB - Maximum Quality - 100% Offline)' },
                { id: 'whisper-base', label: 'Whisper Base (142MB · Good Balance · 100% Offline)' },
                { id: 'whisper-tiny', label: 'Whisper Tiny (75MB · Ultra Fast · 100% Offline)' },
                { id: 'whisper-small', label: 'Whisper Small (466MB · Higher Quality · 100% Offline)' },
                { id: 'whisper-medium', label: 'Whisper Medium (1.5GB · High Quality · 100% Offline)' },
                { id: 'whisper-large-v3-turbo', label: 'Whisper Turbo (1.6GB · Best Quality · 100% Offline)' }
            ]
        },
        llm: {
            groq: [
                { id: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B Versatile (Recommended · Fast & Smart)' },
                { id: 'groq/llama-3.1-8b-instant', label: 'Llama 3.1 8B Instant (Ultra Fast)' },
                { id: 'groq/deepseek-r1-distill-llama-70b', label: 'DeepSeek R1 Distill Llama 70B (Reasoning)' },
                { id: 'groq/mixtral-8x7b-32768', label: 'Mixtral 8x7B (32k Context)' },
                { id: 'groq/gemma2-9b-it', label: 'Gemma 2 9B (Google Fast LLM)' }
            ],
            openai: [
                { id: 'openai/gpt-4o-mini', label: 'GPT-4o Mini (Recommended · Fast & Smart)' },
                { id: 'openai/gpt-4o', label: 'GPT-4o (Flagship Multimodal Model)' },
                { id: 'openai/o3-mini', label: 'o3-mini (High Speed Reasoning)' },
                { id: 'openai/o1', label: 'o1 (Deep Reasoning Model)' },
                { id: 'openai/gpt-4-turbo', label: 'GPT-4 Turbo' }
            ],
            nvidia: [
                { id: 'nvidia/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct (NVIDIA NIM)' },
                { id: 'nvidia/nemotron-4-340b-instruct', label: 'Nemotron 4 340B Instruct (NVIDIA NIM)' },
                { id: 'nvidia/mistral-large-2-instruct', label: 'Mistral Large 2 (NVIDIA NIM)' }
            ],
            nvidia_nim: [
                { id: 'nvidia/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct (NVIDIA NIM)' },
                { id: 'nvidia/nemotron-4-340b-instruct', label: 'Nemotron 4 340B Instruct (NVIDIA NIM)' }
            ],
            mistral: [
                { id: 'mistral/mistral-small-latest', label: 'Mistral Small (Fast & Reliable)' },
                { id: 'mistral/mistral-large-latest', label: 'Mistral Large (High Precision)' },
                { id: 'mistral/codestral-latest', label: 'Codestral (Code & Technical Formatting)' }
            ],
            openrouter: [
                { id: 'openrouter/anthropic/claude-3.5-sonnet', label: 'Claude 3.5 Sonnet (via OpenRouter)' },
                { id: 'openrouter/deepseek/deepseek-r1', label: 'DeepSeek R1 (via OpenRouter)' },
                { id: 'openrouter/google/gemini-2.5-flash', label: 'Gemini 2.5 Flash (via OpenRouter)' },
                { id: 'openrouter/meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct (via OpenRouter)' }
            ],
            anthropic: [
                { id: 'anthropic/claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Recommended · Best)' },
                { id: 'anthropic/claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku (Ultra Fast)' },
                { id: 'anthropic/claude-3-opus-20240229', label: 'Claude 3 Opus (Maximum Precision)' }
            ],
            gemini: [
                { id: 'gemini/gemini-2.5-flash', label: 'Gemini 2.5 Flash (Recommended · Super Fast)' },
                { id: 'gemini/gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
                { id: 'gemini/gemini-1.5-pro', label: 'Gemini 1.5 Pro (Pro Quality)' }
            ],
            xai: [
                { id: 'xai/grok-2-1212', label: 'Grok 2 (xAI Flagship)' },
                { id: 'xai/grok-2-vision-1212', label: 'Grok 2 Vision' }
            ],
            ollama: [
                { id: 'ollama/llama3.3', label: 'Llama 3.3 70B (Local Ollama)' },
                { id: 'ollama/llama3.2', label: 'Llama 3.2 3B (Local Ollama)' },
                { id: 'ollama/qwen2.5-coder', label: 'Qwen 2.5 Coder (Local Ollama)' },
                { id: 'ollama/deepseek-r1:8b', label: 'DeepSeek R1 8B (Local Ollama)' }
            ]
        }
    };

    const updateOnboardingModelSelect = (kind, provider) => {
        const select = $(kind === 'transcription' ? 'ob-stt-model-select' : 'ob-llm-model-select');
        const field = $(kind === 'transcription' ? 'ob-stt-model-field' : 'ob-llm-model-field');
        if (!select || !field) return;

        const options = providerModelsMap[kind]?.[provider] || [];
        if (options.length === 0 || provider === 'none') {
            field.classList.add('hidden');
            return;
        }

        field.classList.remove('hidden');
        select.innerHTML = options.map((opt) => `<option value="${opt.id}">${opt.label}</option>`).join('');
    };

    const updateOnboardingLocalModelSelect = (provider) => {
        const select = $('ob-stt-local-model-select');
        if (!select) return;
        const options = providerModelsMap.transcription?.[provider] || [];
        const previousValue = select.value;
        select.innerHTML = options.map((opt) => `<option value="${opt.id}">${localModelOptionLabel(opt)}</option>`).join('');
        if (options.some((option) => option.id === previousValue)) select.value = previousValue;
        else if (options.length) select.value = onboardingModelFor(provider, 'transcription');
    };

    const updateOnboardingKeyFields = (kind, provider) => {
        const keyInput = $(kind === 'transcription' ? 'ob-stt-key' : 'ob-llm-key');
        const keyField = $(kind === 'transcription' ? 'ob-stt-key-field' : 'ob-llm-key-field');
        const reuseBadge = $(kind === 'transcription' ? 'ob-stt-reuse-badge' : 'ob-llm-reuse-badge');
        const feedback = $(kind === 'transcription' ? 'ob-stt-key-feedback' : 'ob-llm-key-feedback');

        if (feedback) { feedback.textContent = ''; feedback.className = 'test-key-feedback'; }

        const isLocal = ['local_whisper', 'parakeet', 'local_parakeet', 'none', 'ollama'].includes(provider);
        if (keyField) keyField.classList.toggle('hidden', isLocal);
        if (isLocal) return;

        const existingKey = storedProviderKeys[provider];
        if (existingKey && keyInput) {
            keyInput.value = existingKey;
            if (reuseBadge) {
                reuseBadge.textContent = `✓ Reusing ${provider.toUpperCase()} Key`;
                reuseBadge.classList.remove('hidden');
            }
        } else {
            if (reuseBadge) reuseBadge.classList.add('hidden');
        }
    };

    // Listen to key typing to store per-provider
    $('ob-stt-key')?.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const provider = onboardingState.transcription;
        if (val) {
            storedProviderKeys[provider] = val;
            syncApiKeysAcrossProviders(provider, val, 'ob-stt-key');
        }
    });

    $('ob-llm-key')?.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const provider = onboardingState.llm;
        if (val) {
            storedProviderKeys[provider] = val;
            syncApiKeysAcrossProviders(provider, val, 'ob-llm-key');
        }
    });

    const legacyUpdateLocalDownloadBox = async (provider) => {
        const downloadBox = $('ob-local-download-box');
        const nameEl = $('ob-download-model-name');
        const statusEl = $('ob-download-status-text');
        const btn = $('ob-download-model-btn');
        if (!downloadBox) return;

        const isLocal = ['local_whisper', 'parakeet', 'local_parakeet'].includes(provider);
        downloadBox.classList.toggle('hidden', !isLocal);

        if (isLocal) {
            const isParakeet = provider.includes('parakeet');
            const modelName = isParakeet ? 'Parakeet TDT 0.6B (680 MB)' : 'Whisper Base (142 MB)';
            if (nameEl) nameEl.textContent = modelName;
            const modelId = isParakeet ? 'parakeet-tdt-0.6b-v3' : 'whisper-base';
            const selectedModel = $('ob-stt-local-model-select')?.value;
            const effectiveModelId = selectedModel || modelId;
            const inventory = await api?.sendCommand?.('get_local_models');
            const model = (inventory?.models || []).find((item) => item.id === effectiveModelId);
            if (nameEl && model) nameEl.textContent = `${model.name} (${modelSizeLabel(model.size_mb)})`;
            if (statusEl) {
                statusEl.textContent = model?.installed
                    ? 'Installed and ready for offline dictation'
                    : model?.downloadable
                        ? 'Available to download'
                        : 'Fetched automatically when first used';
            }
            if (btn) {
                btn.textContent = 'Download model';
                btn.classList.toggle('hidden', Boolean(model?.installed || (model && !model.downloadable)));
                btn.onclick = async () => {
                    btn.disabled = true;
                    if (statusEl) statusEl.textContent = 'Downloading...';
                    const res = await api?.sendCommand?.('download_local_model', { model: effectiveModelId });
                    btn.disabled = false;
                    if (res?.status === 'ok' || res?.downloaded || res?.installed) {
                        if (statusEl) statusEl.textContent = '✓ Model Installed & Ready';
                    } else {
                        if (statusEl) statusEl.textContent = '✕ Download failed: ' + (res?.error || 'Network error');
                    }
                };
            }
        }
    };

    let localInventory = null;
    const activeLocalDownloads = new Map();

    const localModelProviderForSelection = (provider) => {
        if (provider === 'parakeet' || provider === 'local_parakeet') return 'parakeet';
        if (provider === 'local_whisper') return 'local_whisper';
        return null;
    };

    const visibleLocalModels = (models, provider, showAllForCloud = false) => {
        const selectedProvider = localModelProviderForSelection(provider);
        if (!selectedProvider) return showAllForCloud ? models : [];
        return models.filter((model) => model.provider === selectedProvider);
    };

    const localModelFamilyLabel = (provider) => {
        const selectedProvider = localModelProviderForSelection(provider);
        if (selectedProvider === 'parakeet') return 'Parakeet';
        if (selectedProvider === 'local_whisper') return 'Local Whisper';
        return 'local';
    };

    const modelDownloadLabel = (model) => {
        if (model?.download_active || activeLocalDownloads.has(model?.id)) return 'Downloading';
        if (model?.installed) return model.package_available ? 'Installed' : 'Files installed · runtime missing';
        if (model?.resumable || model?.download_state === 'partial') return `Paused · ${Math.round(Number(model.download_percent || 0))}%`;
        if (!model?.package_available) return 'Runtime missing';
        return model?.downloadable ? 'Available to download' : 'Automatic cache';
    };

    const localModelOptionLabel = (option) => {
        const model = (localInventory?.models || []).find((item) => item.id === option.id);
        if (!model) return option.label;
        if (model.installed) return `${option.label} · Downloaded`;
        if (model.resumable || model.download_state === 'partial') return `${option.label} · Paused (${Math.round(Number(model.download_percent || 0))}%)`;
        if (model.download_active) return `${option.label} · Downloading`;
        return option.label;
    };

    const downloadProgressLabel = (data) => {
        const downloaded = Number(data?.downloaded || 0);
        const total = Number(data?.total || 0);
        const downloadedText = modelSizeLabel(downloaded / (1024 * 1024));
        const totalText = total ? modelSizeLabel(total / (1024 * 1024)) : 'size pending';
        const percent = Math.round(Number(data?.percent || 0));
        return `${downloadedText} / ${totalText} · ${percent}%${data?.status === 'resuming' ? ' · resuming' : ''}`;
    };

    const findModelRow = (modelId) => {
        const rows = document.querySelectorAll('[data-model-id]');
        return Array.from(rows).find((row) => row.dataset.modelId === modelId);
    };

    const updateDownloadProgressUi = (data) => {
        if (!data?.model) return;
        const current = activeLocalDownloads.get(data.model) || {};
        activeLocalDownloads.set(data.model, { ...current, ...data, jobId: data.job_id || current.jobId });
        const percent = Math.max(0, Math.min(99, Number(data.percent || 0)));
        document.querySelectorAll(`[data-download-model="${data.model}"] .local-model-progress-fill`).forEach((fill) => { fill.style.width = `${percent}%`; });
        document.querySelectorAll(`[data-download-model="${data.model}"] .local-model-progress-label`).forEach((label) => { label.textContent = downloadProgressLabel(data); });
        document.querySelectorAll(`[data-download-model="${data.model}"] .model-state`).forEach((state) => { state.textContent = data.status === 'resuming' ? 'Resuming' : 'Downloading'; state.className = 'model-state downloading'; });
        const bar = $('ob-download-progress-bar');
        const text = $('ob-download-status-text');
        if (bar && $('ob-stt-local-model-select')?.value === data.model) bar.style.width = `${percent}%`;
        if (text && $('ob-stt-local-model-select')?.value === data.model) text.textContent = downloadProgressLabel(data);
        const cancel = $('ob-download-cancel-btn');
        if (cancel && $('ob-stt-local-model-select')?.value === data.model) cancel.classList.remove('hidden');
    };

    const startLocalModelDownload = async (modelId) => {
        if (!modelId || activeLocalDownloads.has(modelId)) return;
        const response = await api?.sendCommand?.('download_local_model', { model: modelId });
        if (response?.status !== 'started') {
            setSystemStatus('error', response?.error || response?.hint || 'Could not start local model download.');
            return;
        }
        activeLocalDownloads.set(modelId, { model: modelId, jobId: response.job_id, status: response.resumed ? 'resuming' : 'downloading', percent: 0 });
        setSystemStatus('', `${modelId} download started${response.resumed ? ' · resuming' : ''}.`);
        await refreshModels();
        await updateLocalDownloadBox(onboardingState.transcription);
    };

    const cancelLocalModelDownload = async (modelId) => {
        const active = activeLocalDownloads.get(modelId);
        const response = await api?.sendCommand?.('cancel_local_model', { model: modelId, job_id: active?.jobId });
        if (response?.status !== 'ok') {
            setSystemStatus('error', response?.error || 'Could not cancel local model download.');
            return;
        }
        if (active) active.cancelling = true;
        setSystemStatus('', 'Cancelling download; the partial file will remain resumable.');
    };

    const deleteLocalModel = async (model) => {
        if (!model?.id || activeLocalDownloads.has(model.id) || model.download_active) return;
        if (!confirm(`Delete ${model.name || model.id} from this computer?`)) return;
        const response = await api?.sendCommand?.('delete_local_model', { model: model.id });
        if (response?.status !== 'ok') {
            setSystemStatus('error', response?.error || 'Could not delete local model.');
            return;
        }
        activeLocalDownloads.delete(model.id);
        setSystemStatus('', `${model.name || model.id} deleted.`);
        await refreshModels();
    };

    const isLocalOnboardingProvider = (provider) => ['local_whisper', 'parakeet', 'local_parakeet'].includes(provider);

    const validateSelectedLocalOnboardingModel = async () => {
        const provider = onboardingState.transcription;
        if (!isLocalOnboardingProvider(provider)) return true;
        if (!localInventory || localInventory.status !== 'ok') localInventory = await api?.sendCommand?.('get_local_models');
        const selectedModel = $('ob-stt-local-model-select')?.value || onboardingModelFor(provider, 'transcription');
        const model = (localInventory?.models || []).find((item) => item.id === selectedModel);
        if (model?.installed) return true;

        const message = model?.resumable || model?.download_state === 'partial'
            ? 'Este modelo está parcialmente baixado. Retome o download ou exclua o parcial antes de continuar.'
            : 'Baixe este modelo local antes de finalizar o onboarding, ou escolha outro modelo.';
        $('onboarding-status').textContent = `⚠️ ${message}`;
        await updateLocalDownloadBox(provider);
        return false;
    };

    const renderOnboardingLocalInventory = (result) => {
        const list = $('ob-local-models-list');
        if (!list || result?.status !== 'ok') return;
        list.textContent = '';
        const models = visibleLocalModels(result.models || [], transProviderSelect?.value, false);
        const heading = document.createElement('div');
        heading.className = 'download-inventory-heading';
        heading.textContent = `${localModelFamilyLabel(transProviderSelect?.value)} models`;
        list.appendChild(heading);
        if (!models.length) {
            const empty = document.createElement('p');
            empty.className = 'placeholder-text';
            empty.textContent = 'No local models are registered for this provider.';
            list.appendChild(empty);
            return;
        }
        models.forEach((model) => {
            const row = document.createElement('div');
            row.className = 'ob-local-model-row';
            row.dataset.modelId = model.id;
            row.dataset.downloadModel = model.id;
            const info = document.createElement('div');
            info.className = 'ob-local-model-info';
            const name = document.createElement('strong');
            name.textContent = model.name || model.id;
            const detail = document.createElement('span');
            detail.textContent = `${model.provider === 'parakeet' ? 'Parakeet' : 'Local Whisper'} · ${modelSizeLabel(model.size_mb)} · ${model.languages || 'multilingual'}`;
            info.append(name, detail);
            const state = document.createElement('span');
            state.className = `model-state ${model.installed ? 'installed' : model.resumable || model.download_state === 'partial' ? 'partial' : 'available'}`;
            state.textContent = modelDownloadLabel(model);
            const actions = document.createElement('div');
            actions.className = 'ob-local-model-actions';
            const active = activeLocalDownloads.get(model.id);
            if (active || model.download_active) {
                const cancel = document.createElement('button');
                cancel.type = 'button'; cancel.className = 'btn-link-action'; cancel.textContent = active?.cancelling ? 'Cancelling...' : 'Cancel';
                cancel.disabled = Boolean(active?.cancelling);
                cancel.addEventListener('click', () => cancelLocalModelDownload(model.id));
                actions.appendChild(cancel);
                const progress = document.createElement('div');
                progress.className = 'local-model-progress';
                progress.innerHTML = `<div class="local-model-progress-track"><div class="local-model-progress-fill" style="width:${Number(active?.percent || model.download_percent || 0)}%"></div></div><span class="local-model-progress-label">${escapeHtml(downloadProgressLabel(active || model))}</span>`;
                info.appendChild(progress);
            } else if (model.installed) {
                const remove = document.createElement('button');
                remove.type = 'button'; remove.className = 'btn-danger-quiet'; remove.textContent = 'Delete';
                remove.addEventListener('click', () => deleteLocalModel(model));
                actions.appendChild(remove);
            } else if (model.resumable || model.download_state === 'partial') {
                const remove = document.createElement('button');
                remove.type = 'button'; remove.className = 'btn-danger-quiet'; remove.textContent = 'Delete partial';
                remove.addEventListener('click', () => deleteLocalModel(model));
                actions.appendChild(remove);
            } else if (model.downloadable) {
                const download = document.createElement('button');
                download.type = 'button'; download.className = 'btn-secondary-sm'; download.textContent = model.resumable ? 'Resume' : 'Download';
                download.addEventListener('click', () => startLocalModelDownload(model.id));
                actions.appendChild(download);
            }
            row.append(info, state, actions);
            list.appendChild(row);
        });
    };

    const updateLocalDownloadBox = async (provider) => {
        const downloadBox = $('ob-local-download-box');
        const nameEl = $('ob-download-model-name');
        const statusEl = $('ob-download-status-text');
        const btn = $('ob-download-model-btn');
        const cancelBtn = $('ob-download-cancel-btn');
        const deleteBtn = $('ob-download-delete-btn');
        if (!downloadBox) return;
        const isLocal = ['local_whisper', 'parakeet', 'local_parakeet'].includes(provider);
        downloadBox.classList.toggle('hidden', !isLocal);
        if (!isLocal) return;
        if (!localInventory) localInventory = await api?.sendCommand?.('get_local_models');
        renderOnboardingLocalInventory(localInventory);
        const selectedModel = $('ob-stt-local-model-select')?.value || (provider.includes('parakeet') ? 'parakeet-tdt-0.6b-v3' : 'whisper-base');
        const model = (localInventory?.models || []).find((item) => item.id === selectedModel);
        const active = activeLocalDownloads.get(selectedModel);
        if (nameEl) nameEl.textContent = model ? `${model.name} (${modelSizeLabel(model.size_mb)})` : selectedModel;
        if (statusEl) statusEl.textContent = active ? downloadProgressLabel(active) : model?.installed ? (model.package_available ? 'Installed and ready for offline dictation' : 'Files installed · runtime missing') : model?.resumable || model?.download_state === 'partial' ? `Paused at ${Math.round(Number(model.download_percent || 0))}% · resume available` : model?.downloadable ? `Available to download${model.package_available ? '' : ' · runtime missing'}` : 'Fetched automatically when first used';
        const bar = $('ob-download-progress-bar');
        if (bar) bar.style.width = `${Number(active?.percent || model?.download_percent || 0)}%`;
        if (cancelBtn) {
            cancelBtn.classList.toggle('hidden', !active);
            cancelBtn.disabled = Boolean(active?.cancelling);
            cancelBtn.textContent = active?.cancelling ? 'Cancelling...' : 'Cancel download';
            cancelBtn.onclick = () => cancelLocalModelDownload(selectedModel);
        }
        if (deleteBtn) {
            const canDeletePartial = Boolean(model?.resumable || model?.download_state === 'partial') && !active;
            deleteBtn.classList.toggle('hidden', !canDeletePartial);
            deleteBtn.onclick = () => deleteLocalModel(model);
        }
        if (btn) {
            const canDownload = Boolean(model?.downloadable) && !model?.installed && !active;
            btn.classList.toggle('hidden', !canDownload);
            btn.disabled = false;
            btn.textContent = model?.resumable ? 'Resume download' : 'Download model';
            btn.onclick = () => startLocalModelDownload(selectedModel);
        }
    };

    // Test Key Handlers
    const testOnboardingKey = async (kind) => {
        const provider = kind === 'transcription' ? onboardingState.transcription : onboardingState.llm;
        const keyInput = $(kind === 'transcription' ? 'ob-stt-key' : 'ob-llm-key');
        const btn = $(kind === 'transcription' ? 'ob-test-stt-key-btn' : 'ob-test-llm-key-btn');
        const feedback = $(kind === 'transcription' ? 'ob-stt-key-feedback' : 'ob-llm-key-feedback');

        const keyVal = keyInput?.value.trim() || storedProviderKeys[provider];
        if (!keyVal) {
            if (feedback) { feedback.textContent = '✕ Please enter an API key first.'; feedback.className = 'test-key-feedback error'; }
            return;
        }

        if (btn) btn.disabled = true;
        if (feedback) { feedback.textContent = '⚡ Testing connection...'; feedback.className = 'test-key-feedback'; }

        const startTime = Date.now();
        const testRes = await api?.testProviderConnection?.({ type: kind, provider, api_key: keyVal });
        const latency = Date.now() - startTime;

        if (btn) btn.disabled = false;

        if (testRes?.status === 'ok' || testRes?.success) {
            if (feedback) {
                feedback.textContent = `✓ Valid ${provider.toUpperCase()} Key (${testRes.latency_ms || latency}ms)`;
                feedback.className = 'test-key-feedback success';
            }
        } else {
            if (feedback) {
                feedback.textContent = `✕ ${testRes?.error || 'Invalid API Key or connection failed'}`;
                feedback.className = 'test-key-feedback error';
            }
        }
    };

    $('ob-test-stt-key-btn')?.addEventListener('click', () => testOnboardingKey('transcription'));
    $('ob-test-llm-key-btn')?.addEventListener('click', () => testOnboardingKey('llm'));

    // Dual Mode Engine Switcher (Cloud API vs 100% Offline Local)
    const obModeCloudBtn = $('ob-mode-cloud-btn');
    const obModeLocalBtn = $('ob-mode-local-btn');
    const obCloudPanel = $('ob-cloud-panel');
    const obLocalPanel = $('ob-local-panel');

    const switchEngineMode = (mode) => {
        const isCloud = mode === 'cloud';
        obModeCloudBtn?.classList.toggle('active', isCloud);
        obModeLocalBtn?.classList.toggle('active', !isCloud);
        obCloudPanel?.classList.toggle('hidden', !isCloud);
        obLocalPanel?.classList.toggle('hidden', isCloud);

        if (isCloud) {
            const selectedCard = document.querySelector('#ob-stt-cloud-grid .provider-logo-card.selected') || document.querySelector('#ob-stt-cloud-grid .provider-logo-card');
            if (selectedCard) selectedCard.click();
        } else {
            const selectedCard = document.querySelector('#ob-stt-local-grid .provider-logo-card.selected') || document.querySelector('#ob-stt-local-grid .provider-logo-card');
            if (selectedCard) selectedCard.click();
        }
    };

    obModeCloudBtn?.addEventListener('click', () => switchEngineMode('cloud'));
    obModeLocalBtn?.addEventListener('click', () => switchEngineMode('local'));

    // Credentials are intentionally never bundled with the renderer. Values
    // entered during onboarding are kept in the OS-backed provider store by
    // the main process and are returned to the renderer only as masked state.

    document.querySelectorAll('#ob-stt-cloud-grid .provider-logo-card').forEach((card) => card.addEventListener('click', () => {
        onboardingState.transcription = card.dataset.provider;
        document.querySelectorAll('#ob-stt-cloud-grid .provider-logo-card').forEach((item) => item.classList.toggle('selected', item === card));
        transProviderSelect.value = onboardingState.transcription;
        updateOnboardingModelSelect('transcription', onboardingState.transcription);
        updateOnboardingKeyFields('transcription', onboardingState.transcription);
        applyProviderChange('transcription');
    }));

    document.querySelectorAll('#ob-stt-local-grid .provider-logo-card').forEach((card) => card.addEventListener('click', () => {
        onboardingState.transcription = card.dataset.provider;
        document.querySelectorAll('#ob-stt-local-grid .provider-logo-card').forEach((item) => item.classList.toggle('selected', item === card));
        transProviderSelect.value = onboardingState.transcription;
        updateOnboardingLocalModelSelect(onboardingState.transcription);
        updateLocalDownloadBox(onboardingState.transcription);
        applyProviderChange('transcription');
    }));

    $('ob-stt-local-model-select')?.addEventListener('change', (e) => {
        const val = e.target.value;
        const nameEl = $('ob-download-model-name');
        if (nameEl) {
            nameEl.textContent = val.includes('parakeet') ? 'Parakeet TDT 0.6B (680 MB)' : val.includes('small') ? 'Whisper Small (466 MB)' : 'Whisper Base (142 MB)';
        }
        updateLocalDownloadBox(onboardingState.transcription);
    });

    updateOnboardingLocalModelSelect('parakeet');

    document.querySelectorAll('#ob-llm-provider-grid .provider-logo-card').forEach((card) => card.addEventListener('click', () => {
        onboardingState.llm = card.dataset.provider;
        document.querySelectorAll('#ob-llm-provider-grid .provider-logo-card').forEach((item) => item.classList.toggle('selected', item === card));
        updateOnboardingModelSelect('llm', onboardingState.llm);
        updateOnboardingKeyFields('llm', onboardingState.llm);
        if (onboardingState.llm !== 'none') {
            llmProviderSelect.value = onboardingState.llm;
            applyProviderChange('llm');
        }
    }));

    const closeOnboarding = () => { onboardingModal?.classList.add('hidden'); localStorage.setItem('audioscribe_onboarding_completed', '1'); };
    $('onboarding-skip')?.addEventListener('click', closeOnboarding);
    $('relaunch-onboarding-btn')?.addEventListener('click', () => { onboardingStep = 1; renderOnboarding(); onboardingModal?.classList.remove('hidden'); });
    $('reset-config-btn')?.addEventListener('click', async () => {
        if (confirm('Reset all saved provider keys and restart onboarding wizard?')) {
            localStorage.removeItem('audioscribe_onboarding_completed');
            const obSttKey = $('ob-stt-key'); if (obSttKey) obSttKey.value = '';
            const obLlmKey = $('ob-llm-key'); if (obLlmKey) obLlmKey.value = '';
            if (transApiKeyInput) transApiKeyInput.value = '';
            if (llmApiKeyInput) llmApiKeyInput.value = '';
            await api?.saveProviderConfig?.({ transcription: { provider: 'groq' }, llm: { provider: 'litellm', enabled: false } });
            onboardingStep = 1;
            renderOnboarding();
            onboardingModal?.classList.remove('hidden');
        }
    });

    // Show first-run onboarding immediately, before engine discovery finishes.
    // A missing provider config still re-opens it after the async load below.
    if (!localStorage.getItem('audioscribe_onboarding_completed')) {
        onboardingStep = 1;
        renderOnboarding();
        onboardingModal?.classList.remove('hidden');
    }
    $('onboarding-back')?.addEventListener('click', () => { onboardingStep = Math.max(1, onboardingStep - 1); renderOnboarding(); });
    $('onboarding-next')?.addEventListener('click', async () => {
        // Step 2 validation (Speech Key Check)
        if (onboardingStep === 2) {
            const provider = onboardingState.transcription;
            const isLocalSTT = ['local_whisper', 'parakeet', 'local_parakeet'].includes(provider);
            const requiresKey = !isLocalSTT;
            const keyVal = $('ob-stt-key')?.value.trim() || storedProviderKeys[provider];
            const isStored = transApiKeyInput.placeholder === 'Stored securely · leave blank to keep';
            if (requiresKey && !keyVal && !isStored) {
                $('onboarding-status').textContent = `⚠️ API Key required for ${provider.toUpperCase()} (or pick Local Parakeet / Local Whisper for offline)`;
                $('ob-stt-key')?.focus();
                return;
            }
            if (isLocalSTT && !(await validateSelectedLocalOnboardingModel())) return;
        }

        // Step 3 validation (LLM Key Check)
        if (onboardingStep === 3) {
            const provider = onboardingState.llm;
            const hasDefaultProfilePrompt = Boolean($('ob-default-profile-prompt')?.value.trim());
            if (hasDefaultProfilePrompt && provider === 'none') {
                $('onboarding-status').textContent = 'Choose an LLM provider or clear the default profile instruction for raw transcription.';
                return;
            }
            const requiresKey = hasDefaultProfilePrompt && provider !== 'none' && provider !== 'ollama';
            const keyVal = $('ob-llm-key')?.value.trim() || storedProviderKeys[provider];
            const isStored = llmApiKeyInput.placeholder === 'Stored securely · leave blank to keep';
            if (requiresKey && !keyVal && !isStored) {
                $('onboarding-status').textContent = `⚠️ API Key required for ${provider.toUpperCase()} (or pick Raw Speech for no LLM)`;
                $('ob-llm-key')?.focus();
                return;
            }
        }

        if (onboardingStep < 5) { onboardingStep += 1; renderOnboarding(); return; }

        const isLocalSTT = isLocalOnboardingProvider(onboardingState.transcription);
        if (isLocalSTT && !(await validateSelectedLocalOnboardingModel())) return;
        const selectedSttModel = isLocalSTT
            ? $('ob-stt-local-model-select')?.value || onboardingModelFor(onboardingState.transcription, 'transcription')
            : $('ob-stt-model-select')?.value || onboardingModelFor(onboardingState.transcription, 'transcription');
        const selectedLlmModel = $('ob-llm-model-select')?.value || onboardingModelFor(onboardingState.llm, 'llm');
        const transcription = {
            provider: onboardingState.transcription,
            model: selectedSttModel,
            device: $('ob-enable-gpu-check')?.checked === false ? 'cpu' : 'auto',
        };
        const defaultProfilePrompt = $('ob-default-profile-prompt')?.value.trim() || '';
        const llm = { provider: onboardingState.llm === 'none' ? 'litellm' : onboardingState.llm, model: selectedLlmModel, enabled: Boolean(defaultProfilePrompt) && onboardingState.llm !== 'none' };
        const transKey = $('ob-stt-key')?.value.trim() || storedProviderKeys[onboardingState.transcription];
        const llmKey = $('ob-llm-key')?.value.trim() || storedProviderKeys[onboardingState.llm];
        if (transKey) transcription.api_key = transKey;
        if (llmKey) llm.api_key = llmKey;

        $('onboarding-next').disabled = true;
        $('onboarding-status').textContent = 'Saving setup...';
        const result = await api?.saveProviderConfig?.({ transcription, llm });
        $('onboarding-next').disabled = false;
        if (result?.status !== 'ok') { $('onboarding-status').textContent = result?.error || 'Could not save setup.'; return; }
        const defaultProfile = {
            id: 'default-profile',
            name: 'Default dictation',
            isDefault: true,
            enabled: true,
            shortcut: configuredAccelerator,
            prompt: defaultProfilePrompt,
        };
        const existingProfiles = Array.isArray(profiles) ? profiles.filter((profile) => !profile.isDefault) : [];
        await applyProfiles([defaultProfile, ...existingProfiles]);
        renderProfiles();
        localStorage.setItem('audioscribe_profiles_onboarding_v3', '1');
        closeOnboarding();
        await loadProviderConfig(); await refreshModels(); await runPreflightCheck();
    });

    const updateProviderUI = () => {
        const transProvider = transProviderSelect.value;
        const llmProvider = llmProviderSelect.value;
        const transMeta = providerDefaults[transProvider] || providerDefaults.custom;
        const llmMeta = providerDefaults[llmProvider] || providerDefaults.custom;
        if (!transBaseUrlInput.value) transBaseUrlInput.value = transMeta.transUrl || '';
        if (!llmBaseUrlInput.value) llmBaseUrlInput.value = llmMeta.llmUrl || '';
        const transcriptionHint = $('transcription-api-key-hint');
        const llmHint = $('llm-api-key-hint');
        const transcriptionStatus = $('transcription-provider-status');
        const llmStatus = $('llm-provider-status');
        if (transcriptionHint) transcriptionHint.textContent = transMeta.key === 'No key required' ? 'This provider does not require a key.' : 'Encrypted by the desktop process.';
        if (llmHint) llmHint.textContent = llmMeta.key === 'No key required' ? 'This provider does not require a key.' : `${llmMeta.key} is encrypted by the desktop process.`;
        if (transcriptionStatus) transcriptionStatus.textContent = transProvider === 'ollama' ? 'Chat only' : 'Not tested';
        if (llmStatus) llmStatus.textContent = 'Not tested';
        $('transcription-model-path-group')?.classList.toggle('hidden', !['local_whisper', 'parakeet', 'local_parakeet'].includes(transProvider));
        updateProviderLogos();
        syncApiKeysAcrossProviders(transProvider, transApiKeyInput.value.trim(), 'transcription-api-key-input');
        syncApiKeysAcrossProviders(llmProvider, llmApiKeyInput.value.trim(), 'llm-api-key-input');
    };

    const syncPostProcessingUI = () => {
        const enabled = Boolean($('llm-enabled-checkbox')?.checked);
        $('llm-config-wrapper')?.classList.toggle('is-disabled', !enabled);
    };
    $('llm-enabled-checkbox')?.addEventListener('change', syncPostProcessingUI);

    const resetProviderUrl = (kind) => {
        const provider = kind === 'transcription' ? transProviderSelect.value : llmProviderSelect.value;
        const meta = providerDefaults[provider] || providerDefaults.custom;
        const input = kind === 'transcription' ? transBaseUrlInput : llmBaseUrlInput;
        input.value = (kind === 'transcription' ? meta.transUrl : meta.llmUrl) || '';
        input.focus();
    };

    const applyProviderChange = (kind) => {
        const select = kind === 'transcription' ? transProviderSelect : llmProviderSelect;
        const input = kind === 'transcription' ? transBaseUrlInput : llmBaseUrlInput;
        const previousProvider = select.dataset.previousProvider;
        const previousMeta = providerDefaults[previousProvider] || providerDefaults.custom;
        const previousDefault = kind === 'transcription' ? previousMeta.transUrl : previousMeta.llmUrl;
        if (!input.value.trim() || input.value.trim() === (previousDefault || '')) resetProviderUrl(kind);
        select.dataset.previousProvider = select.value;
        updateProviderUI();
    };

    const addOption = (select, value, label, selected = false) => {
        if (!select) return;
        let option = [...select.options].find((item) => item.value === value);
        if (!option) {
            option = document.createElement('option');
            option.value = value;
            option.textContent = label || value;
            select.appendChild(option);
        }
        option.selected = selected;
    };

    const modelSizeLabel = (sizeMb) => {
        const size = Number(sizeMb || 0);
        return size >= 1024 ? `${(size / 1024).toFixed(1)} GB` : `${Math.round(size)} MB`;
    };

    const renderRuntimeInfo = (runtime, gpu) => {
        if (!runtime) {
            if ($('runtime-platform')) $('runtime-platform').textContent = 'Engine unavailable';
            ['runtime-transcription', 'runtime-post-processing', 'runtime-gpu', 'runtime-cpu'].forEach((id) => {
                const item = $(id);
                if (item) item.textContent = 'Unavailable';
            });
            return;
        }
        const trans = runtime.transcription || {};
        const post = runtime.post_processing || {};
        const gpuInfo = runtime.gpu || gpu || {};
        const transText = trans.execution === 'cloud'
            ? `Cloud · ${trans.model || trans.provider || 'provider'}`
            : `${String(trans.device || 'CPU').toUpperCase()} · ${trans.model || trans.provider || 'local model'}`;
        const postText = post.enabled ? `On · ${post.model || post.provider || 'LLM'}` : 'Off';
        const gpuText = gpuInfo.cuda
            ? `CUDA${gpuInfo.details?.[0] ? ` · ${gpuInfo.details[0]}` : ''}`
            : gpuInfo.mps ? 'Apple GPU · MPS' : gpuInfo.vulkan ? 'Vulkan available' : 'Not available';
        const platform = $('runtime-platform');
        if (platform) platform.textContent = `${runtime.platform || 'Desktop'} · ${runtime.cpu_count || 1} CPU threads`;
        const transcription = $('runtime-transcription');
        const postProcessing = $('runtime-post-processing');
        const gpuEl = $('runtime-gpu');
        const cpuEl = $('runtime-cpu');
        if (transcription) transcription.textContent = transText;
        if (postProcessing) postProcessing.textContent = postText;
        if (gpuEl) gpuEl.textContent = gpuText;
        if (cpuEl) cpuEl.textContent = `${runtime.cpu_count || 1} threads available`;
    };

    const legacyRenderLocalModels = (result) => {
        const list = $('local-models-list');
        if (!list) return;
        list.textContent = '';
        if (result?.status !== 'ok') {
            const error = document.createElement('div');
            error.className = 'local-model-error';
            error.innerHTML = `<strong>Local model inventory unavailable.</strong><span>${escapeHtml(result?.error || 'The engine is not responding.')}</span>`;
            list.appendChild(error);
            return;
        }
        const models = result?.models || [];
        if (!models.length) {
            const empty = document.createElement('p');
            empty.className = 'placeholder-text';
            empty.textContent = 'No local models are registered.';
            list.appendChild(empty);
            return;
        }

        models.forEach((model) => {
            const row = document.createElement('div');
            row.className = 'local-model-row';

            const info = document.createElement('div');
            info.className = 'local-model-info';
            const name = document.createElement('strong');
            name.textContent = model.name || model.id;
            const detail = document.createElement('span');
            detail.textContent = `${model.languages || 'multilingual'} · ${modelSizeLabel(model.size_mb)} · ${model.package || 'runtime'}`;
            const description = document.createElement('small');
            description.textContent = model.description || '';
            info.append(name, detail, description);

            const state = document.createElement('span');
            state.className = `model-state ${model.installed ? 'installed' : 'available'}`;
            state.textContent = model.installed
                ? (model.package_available ? 'Installed' : 'Files installed · runtime missing')
                : !model.package_available ? 'Runtime missing' : model.downloadable ? 'Available to download' : 'Used on first run';

            const actions = document.createElement('div');
            actions.className = 'local-model-actions';
            if (model.installed) {
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'btn-danger-quiet';
                remove.textContent = 'Remove';
                remove.addEventListener('click', async () => {
                    if (!confirm(`Remove ${model.name || model.id} from this computer?`)) return;
                    remove.disabled = true;
                    remove.textContent = 'Removing...';
                    const response = await api?.sendCommand?.('delete_local_model', { model: model.id });
                    if (response?.status !== 'ok') {
                        remove.disabled = false;
                        remove.textContent = 'Remove';
                        setSystemStatus('error', response?.error || 'Could not remove local model.');
                        return;
                    }
                    setSystemStatus('', `${model.name || model.id} removed.`);
                    await refreshModels();
                });
                actions.appendChild(remove);
            } else if (model.downloadable) {
                const download = document.createElement('button');
                download.type = 'button';
                download.className = 'btn-secondary-sm';
                download.textContent = 'Download';
                download.addEventListener('click', async () => {
                    download.disabled = true;
                    download.textContent = 'Downloading...';
                    setSystemStatus('', `Downloading ${model.name || model.id}...`);
                    const response = await api?.sendCommand?.('download_local_model', { model: model.id });
                    if (response?.status === 'ok') {
                        setSystemStatus('', `${model.name || model.id} is ready.`);
                        await refreshModels();
                    } else {
                        download.disabled = false;
                        download.textContent = 'Download';
                        setSystemStatus('error', response?.error || response?.hint || 'Could not download local model.');
                    }
                });
                actions.appendChild(download);
            } else {
                const note = document.createElement('span');
                note.className = 'model-action-note';
                note.textContent = model.package_available ? 'Automatic cache' : 'Runtime missing';
                actions.appendChild(note);
            }

            row.append(info, state, actions);
            list.appendChild(row);
        });
    };

    const renderLocalModels = (result) => {
        const list = $('local-models-list');
        if (!list) return;
        localInventory = result;
        list.textContent = '';
        renderOnboardingLocalInventory(result);
        if (['local_whisper', 'parakeet', 'local_parakeet'].includes(transProviderSelect?.value)) {
            updateOnboardingLocalModelSelect(transProviderSelect.value);
        }
        if (result?.status !== 'ok') {
            const error = document.createElement('div');
            error.className = 'local-model-error';
            error.innerHTML = `<strong>Local model inventory unavailable.</strong><span>${escapeHtml(result?.error || 'The engine is not responding.')}</span>`;
            list.appendChild(error);
            return;
        }
        const models = visibleLocalModels(result.models || [], transProviderSelect?.value, true);
        if (!models.length) {
            list.innerHTML = `<p class="placeholder-text">No ${localModelFamilyLabel(transProviderSelect?.value)} models are registered.</p>`;
            return;
        }
        models.forEach((model) => {
            const active = activeLocalDownloads.get(model.id);
            if (model.download_active && !active) activeLocalDownloads.set(model.id, { model: model.id, jobId: model.download_job_id, status: 'downloading' });
            const current = activeLocalDownloads.get(model.id);
            const row = document.createElement('div');
            row.className = 'local-model-row';
            row.dataset.modelId = model.id;
            row.dataset.downloadModel = model.id;
            const info = document.createElement('div');
            info.className = 'local-model-info';
            const name = document.createElement('strong'); name.textContent = model.name || model.id;
            const detail = document.createElement('span'); detail.textContent = `${model.provider === 'parakeet' ? 'Parakeet' : 'Local Whisper'} · ${model.languages || 'multilingual'} · ${modelSizeLabel(model.size_mb)} · ${model.package || 'runtime'}`;
            const description = document.createElement('small'); description.textContent = model.description || '';
            info.append(name, detail, description);
            const state = document.createElement('span');
            state.className = `model-state ${model.installed ? 'installed' : current ? 'downloading' : model.resumable || model.download_state === 'partial' ? 'partial' : 'available'}`;
            state.textContent = current ? (current.status === 'resuming' ? 'Resuming' : current.cancelling ? 'Cancelling' : 'Downloading') : modelDownloadLabel(model);
            const actions = document.createElement('div'); actions.className = 'local-model-actions';
            if (current) {
                const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn-link-action'; cancel.textContent = current.cancelling ? 'Cancelling...' : 'Cancel'; cancel.disabled = Boolean(current.cancelling);
                cancel.addEventListener('click', () => cancelLocalModelDownload(model.id)); actions.appendChild(cancel);
                const progress = document.createElement('div'); progress.className = 'local-model-progress';
                progress.innerHTML = `<div class="local-model-progress-track"><div class="local-model-progress-fill" style="width:${Number(current.percent || model.download_percent || 0)}%"></div></div><span class="local-model-progress-label">${escapeHtml(downloadProgressLabel(current))}</span>`;
                info.appendChild(progress);
            } else if (model.installed) {
                const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn-danger-quiet'; remove.textContent = 'Delete';
                remove.addEventListener('click', () => deleteLocalModel(model));
                actions.appendChild(remove);
            } else if (model.resumable || model.download_state === 'partial') {
                const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn-danger-quiet'; remove.textContent = 'Delete partial';
                remove.addEventListener('click', () => deleteLocalModel(model));
                actions.appendChild(remove);
            } else if (model.downloadable) {
                const download = document.createElement('button'); download.type = 'button'; download.className = 'btn-secondary-sm'; download.textContent = model.resumable ? 'Resume' : 'Download';
                download.addEventListener('click', () => startLocalModelDownload(model.id)); actions.appendChild(download);
            } else {
                const note = document.createElement('span'); note.className = 'model-action-note'; note.textContent = model.package_available ? 'Automatic cache' : 'Runtime missing'; actions.appendChild(note);
            }
            row.append(info, state, actions); list.appendChild(row);
        });
    };

    const refreshModels = async () => {
        if (!api?.sendCommand) return null;
        let localResult;
        try {
            localResult = await api.getLocalModels();
        } catch (error) {
            localResult = { status: 'error', error: error.message };
        }
        renderLocalModels(localResult);
        renderRuntimeInfo(localResult?.runtime, localResult?.gpu);
        let result;
        try {
            result = await api.getModels();
        } catch (error) {
            result = { status: 'error', error: error.message };
        }
        if (result?.status !== 'ok') {
            setSystemStatus('error', result?.error || 'Could not query models');
            return result;
        }
        const configured = result.configured || {};
        transcriptionModelSelect.innerHTML = '';
        const transcriptionProvider = transProviderSelect.value;
        const staticTranscriptionModels = providerModelsMap?.transcription?.[transcriptionProvider] || [];
        (staticTranscriptionModels.length ? staticTranscriptionModels : (result.models || []))
            .forEach((model) => addOption(transcriptionModelSelect, model.id, localModelOptionLabel(model) || model.label || model.name));
        (configured.transcription || []).forEach((model) => addOption(transcriptionModelSelect, model, `${model} (configured)`));
        if (configured.transcription?.[0]) transcriptionModelSelect.value = configured.transcription[0];
        llmModelSelect.innerHTML = '';
        const llmProvider = llmProviderSelect.value;
        const staticLlmModels = providerModelsMap?.llm?.[llmProvider] || [];
        (staticLlmModels.length ? staticLlmModels : (result.llm_models || []))
            .forEach((model) => addOption(llmModelSelect, model.id, model.label || model.name));
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
        const result = await api.runPreflight({ deep });
        if (result?.status !== 'ok') {
            showEngineProblem(result);
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

    // Map stored provider + model to the visible select option value.
    // E.g. provider="litellm" with model="groq/..." → select value="groq"
    const visibleProvider = (provider, model) => {
        if (!provider) return 'groq';
        if (['local_whisper', 'parakeet', 'local_parakeet', 'ollama'].includes(provider)) return provider;
        if (provider === 'litellm' && model) {
            const prefix = model.split('/')[0];
            if (['groq', 'openai', 'nvidia', 'mistral', 'openrouter', 'anthropic', 'gemini', 'xai', 'ollama'].includes(prefix)) return prefix;
        }
        return provider;
    };

    let hasStoredConfig = false;
    const loadProviderConfig = async () => {
        const result = await api?.getProviderConfig?.();
        const config = result?.config;
        hasStoredConfig = Boolean(config);
        if (!config) return null;
        const trans = config.transcription || config;
        const llm = config.llm || {};
        if (trans.provider) transProviderSelect.value = visibleProvider(trans.provider, trans.model || config.transcription_model);
        if (llm.provider) llmProviderSelect.value = visibleProvider(llm.provider, llm.model || config.llm_model);
        if (trans.base_url) transBaseUrlInput.value = trans.base_url;
        if (trans.model_path && transModelPathInput) transModelPathInput.value = trans.model_path;
        if ($('ob-enable-gpu-check') && trans.device) $('ob-enable-gpu-check').checked = trans.device !== 'cpu';
        if (llm.base_url) llmBaseUrlInput.value = llm.base_url;
        if ($('llm-enabled-checkbox')) $('llm-enabled-checkbox').checked = Boolean(llm.enabled);
        if (config.api_key === 'configured') {
            transApiKeyInput.placeholder = 'Stored securely · leave blank to keep';
        }
        updateProviderUI();
        syncPostProcessingUI();
        transProviderSelect.dataset.previousProvider = transProviderSelect.value;
        llmProviderSelect.dataset.previousProvider = llmProviderSelect.value;
        addOption(transcriptionModelSelect, trans.model || config.transcription_model, trans.model || config.transcription_model, true);
        addOption(llmModelSelect, llm.model || config.llm_model, llm.model || config.llm_model, true);
    };

    // Migrate the old plaintext renderer secret out of localStorage.
    localStorage.removeItem('audioscribe_api_key');
    transProviderSelect.addEventListener('change', async () => {
        applyProviderChange('transcription');
        await refreshModels();
        await runPreflightCheck();
    });
    llmProviderSelect.addEventListener('change', async () => {
        applyProviderChange('llm');
        await refreshModels();
        await runPreflightCheck();
    });
    updateProviderUI();
    syncPostProcessingUI();
    transProviderSelect.dataset.previousProvider = transProviderSelect.value;
    llmProviderSelect.dataset.previousProvider = llmProviderSelect.value;
    $('reset-transcription-url-btn')?.addEventListener('click', () => resetProviderUrl('transcription'));
    $('reset-llm-url-btn')?.addEventListener('click', () => resetProviderUrl('llm'));

    const refreshDevices = async () => {
        const select = $('audio-device-select');
        if (!select || !navigator.mediaDevices?.enumerateDevices) return;
        const selected = localStorage.getItem('audioscribe_desktop_device_id') || '';
        let devices = [];
        try {
            devices = api?.e2eNoMicrophone ? [] : await navigator.mediaDevices.enumerateDevices();
        } catch (error) {
            applyMicrophoneAvailability(false);
            setSystemStatus('error', error.message || 'Could not list desktop microphones.');
            return;
        }
        select.innerHTML = '';
        const audioInputs = devices.filter((device) => device.kind === 'audioinput');
        applyMicrophoneAvailability(audioInputs.length > 0);
        if (!audioInputs.length) {
            addOption(select, '', 'No microphone detected', true);
            select.disabled = true;
            return;
        }
        select.disabled = false;
        addOption(select, '', 'System default microphone', true);
        audioInputs
            .forEach((device, index) => addOption(select, device.deviceId, device.label || `Microphone ${index + 1}`));
        select.value = selected;
    };
    $('audio-device-select')?.addEventListener('change', (event) => {
        localStorage.setItem('audioscribe_desktop_device_id', event.target.value || '');
    });
    document.querySelector('[data-tab="settings"]')?.addEventListener('click', () => {
        // Settings must never display a stale/default microphone while the
        // Dictate surface reports that no input is available.
        void refreshDevices();
    });

    $('fix-config-btn')?.addEventListener('click', () => {
        document.querySelector('[data-tab="settings"]')?.click();
        transApiKeyInput.focus();
    });
    $('retry-engine-btn')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        setSystemStatus('', 'Starting AudioScribe engine...');
        const result = await api?.retryEngine?.();
        if (result?.status !== 'ok') showEngineProblem(result);
        setTimeout(() => { button.disabled = false; }, 1200);
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
            transcription: { provider: transProviderSelect.value, base_url: transBaseUrlInput.value.trim() || null, model: transcriptionModelSelect.value || undefined, model_path: transModelPathInput?.value.trim() || null },
            llm: { provider: llmProviderSelect.value, base_url: llmBaseUrlInput.value.trim() || null, model: llmModelSelect.value || undefined, enabled: Boolean($('llm-enabled-checkbox')?.checked) },
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
    $('refresh-local-models-btn')?.addEventListener('click', refreshModels);
    $('test-providers-btn')?.addEventListener('click', async () => {
        const ready = await runPreflightCheck(true);
        $('transcription-provider-status').textContent = ready ? 'Verified' : 'Needs attention';
        $('llm-provider-status').textContent = ready ? 'Verified' : 'Needs attention';
    });

    // Global and profile hotkey recorder. Electron uses "Control" internally,
    // while the UI keeps the familiar "Ctrl" label for users.
    let hotkeyCapture = null;
    const prettyKey = (event) => {
        const code = event.code || '';
        const keyValue = event.key || '';
        const accelerators = [];
        const labels = [];
        if (event.ctrlKey) { accelerators.push('Control'); labels.push('Ctrl'); }
        if (event.altKey) { accelerators.push('Alt'); labels.push('Alt'); }
        if (event.shiftKey) { accelerators.push('Shift'); labels.push('Shift'); }
        if (event.metaKey || keyValue === 'Meta' || code.startsWith('Meta') || code.startsWith('OS')) {
            if (!accelerators.includes('Super')) { accelerators.push('Super'); labels.push('Win'); }
        }
        const isMod = ['Control', 'Shift', 'Alt', 'Meta', 'OSLeft', 'OSRight', 'ControlLeft', 'ControlRight', 'AltLeft', 'AltRight', 'ShiftLeft', 'ShiftRight'].includes(keyValue) || code.startsWith('Meta') || code.startsWith('OS');
        if (!isMod) {
            const key = code.startsWith('Key') ? code.slice(3) : code.startsWith('Digit') ? code.slice(5) : keyValue.toUpperCase();
            if (!accelerators.includes(key)) { accelerators.push(key); labels.push(key); }
        }
        return { accelerator: accelerators.join('+'), pretty: labels.join(' + '), isOnlyModifiers: isMod && accelerators.length < 2 };
    };

    const beginHotkeyCapture = async (target) => {
        if (hotkeyCapture) {
            endHotkeyCapture();
            await api?.endHotkeyCapture?.(profiles);
        }
        const captureResult = await api?.beginHotkeyCapture?.();
        if (captureResult?.status && captureResult.status !== 'ok') {
            alert(captureResult.error || 'Could not prepare shortcut capture.');
            return false;
        }
        hotkeyCapture = target;
        if (target.type === 'global') {
            $('hotkey-recorder-input').value = 'Press key combination...';
            $('record-hotkey-btn').textContent = 'Press a key...';
        } else if (target.button) {
            target.button.textContent = 'Press a key...';
            target.button.classList.add('is-listening');
        }
        return true;
    };
    const endHotkeyCapture = () => {
        const target = hotkeyCapture;
        hotkeyCapture = null;
        if (target?.type === 'global') $('record-hotkey-btn').textContent = 'Record Hotkey';
        if (target?.button) {
            target.button.textContent = 'Record shortcut';
            target.button.classList.remove('is-listening');
        }
    };
    // Default to F9. The native JavaScript hook also supports modifier chords such as Ctrl+Win.
    // The user can change this to any valid key combination via Settings.
    const configuredShortcut = localStorage.getItem('audioscribe_shortcut') || 'F9';
    const configuredAccelerator = localStorage.getItem('audioscribe_shortcut_accelerator') || acceleratorFromStored(configuredShortcut);
    const savedMode = localStorage.getItem('audioscribe_mode') || 'toggle';
    api?.setActivationMode?.(savedMode);

    updateAllShortcutLabels(configuredShortcut);
    api?.registerShortcut?.(configuredAccelerator);
    $('record-hotkey-btn')?.addEventListener('click', async () => { await beginHotkeyCapture({ type: 'global' }); });
    document.addEventListener('keydown', async (event) => {
        if (!hotkeyCapture) return;
        event.preventDefault();
        const result = prettyKey(event);
        if (result.isOnlyModifiers) {
            if (hotkeyCapture?.type === 'global') {
                $('hotkey-recorder-input').value = 'Press key combination...';
            }
            return;
        }
        const target = hotkeyCapture;
        endHotkeyCapture();
        if (target.type === 'global') {
            const response = await api?.registerShortcut?.(result.accelerator);
            if (response?.status === 'ok') {
                localStorage.setItem('audioscribe_shortcut', result.pretty);
                localStorage.setItem('audioscribe_shortcut_accelerator', result.accelerator);
                updateAllShortcutLabels(result.pretty);
                if (target.defaultProfileId) {
                    const candidateProfiles = profiles.map((profile) => profile.id === target.defaultProfileId
                        ? { ...profile, shortcut: result.accelerator }
                        : profile);
                    await applyProfiles(candidateProfiles, true);
                    renderProfiles();
                    return;
                }
            } else {
                const currentSaved = localStorage.getItem('audioscribe_shortcut') || 'F9';
                updateAllShortcutLabels(currentSaved);
                alert(response?.error || 'Shortcuts must include a non-modifier key (like F9, Space, or A-Z).');
            }
            await api?.endHotkeyCapture?.(profiles);
            return;
        }
        const candidateProfiles = profiles.map((profile) => profile.id === target.profileId
            ? { ...profile, shortcut: result.accelerator }
            : profile);
        if (candidateProfiles.length === profiles.length && !candidateProfiles.some((profile) => profile.id === target.profileId)) {
            await api?.endHotkeyCapture?.(profiles);
            return;
        }
        const response = await applyProfiles(candidateProfiles, true);
        if (response?.status !== 'ok') {
            alert(response?.error || 'Could not register profile shortcut.');
        }
        renderProfiles();
    });

    // Profiles are kept local, but rendered without interpolating user text into HTML.
    const defaultProfiles = [];
    const storedProfiles = localStorage.getItem('audioscribe_profiles');
    let profiles;
    try { profiles = JSON.parse(storedProfiles || 'null') || defaultProfiles; } catch { profiles = defaultProfiles; }
    if (storedProfiles && !localStorage.getItem('audioscribe_profiles_onboarding_v3')) {
        const legacyProfiles = profiles.map((profile) => (profile.id === 'prof_std' || profile.id === 'prof_trans')
            ? { ...profile, shortcut: '' }
            : profile);
        profiles = [
            { id: 'default-profile', name: 'Default dictation', isDefault: true, enabled: true, shortcut: configuredAccelerator, prompt: '' },
            ...legacyProfiles.filter((profile) => !profile.isDefault),
        ];
        localStorage.setItem('audioscribe_profiles_onboarding_v3', '1');
        localStorage.setItem('audioscribe_profiles', JSON.stringify(profiles));
    }
    const applyProfiles = async (candidateProfiles, afterCapture = false) => {
        const response = afterCapture
            ? await api?.endHotkeyCapture?.(candidateProfiles)
            : await api?.updateProfiles?.(candidateProfiles);
        if (!response || response.status === 'ok') {
            profiles = candidateProfiles;
            localStorage.setItem('audioscribe_profiles', JSON.stringify(profiles));
            return response || { status: 'ok' };
        }
        return response;
    };
    const ensureProfileProcessingIsConfigured = async (candidateProfiles) => {
        const needsProcessing = candidateProfiles.some((profile) => profile?.enabled && String(profile.prompt || '').trim());
        if (!needsProcessing) return true;
        const saved = await api?.getProviderConfig?.();
        if (saved?.config?.llm?.enabled) return true;
        const message = 'This profile has a prompt, but Profile Processing is not enabled. Open Settings, enable it, configure an LLM provider, and save settings first.';
        setSystemStatus('error', message);
        alert(message);
        return false;
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
            const hotkey = document.createElement('div'); hotkey.className = 'profile-hotkey-group';
            const hotkeyLabel = document.createElement('span'); hotkeyLabel.textContent = `Shortcut: ${displayShortcut(profile.shortcut) || 'none'}`;
            const hotkeyButton = document.createElement('button'); hotkeyButton.className = 'btn-link profile-hotkey-btn'; hotkeyButton.type = 'button'; hotkeyButton.textContent = profile.isDefault ? 'Change primary shortcut' : 'Record shortcut';
            hotkeyButton.addEventListener('click', async () => {
                await beginHotkeyCapture(profile.isDefault
                    ? { type: 'global', defaultProfileId: profile.id, button: hotkeyButton }
                    : { type: 'profile', profileId: profile.id, button: hotkeyButton });
            });
            hotkey.append(hotkeyLabel, hotkeyButton);
            const save = document.createElement('button');
            save.className = 'btn-primary-sm'; save.textContent = 'Save & Apply';
            save.addEventListener('click', async () => {
                const candidateProfiles = profiles.map((item) => item.id === profile.id
                    ? { ...item, prompt: prompt.value.trim(), enabled: enabled.checked }
                    : item);
                if (!(await ensureProfileProcessingIsConfigured(candidateProfiles))) return;
                const response = await applyProfiles(candidateProfiles);
                if (response?.status !== 'ok') alert(response?.error || 'Could not apply this profile.');
                renderProfiles();
            });
            actions.append(hotkey, save);
            card.append(heading, prompt, actions);
            list.appendChild(card);
        });
    };
    renderProfiles();
    applyProfiles(profiles).then((response) => {
        if (response?.status !== 'ok') setSystemStatus('error', response?.error || 'Some profile shortcuts could not be activated.');
    });
    $('add-profile-btn')?.addEventListener('click', () => {
        const name = prompt('Profile name:', 'Custom rule');
        const promptText = name && prompt('Profile instruction:', 'Review and organize the text...');
        if (!name || !promptText) return;
        const candidateProfiles = [...profiles, { id: `prof_${Date.now()}`, name: name.trim(), enabled: true, shortcut: '', prompt: promptText.trim() }];
        ensureProfileProcessingIsConfigured(candidateProfiles).then((ready) => ready && applyProfiles(candidateProfiles)).then((response) => {
            if (!response) return;
            if (response?.status !== 'ok') alert(response?.error || 'Could not add this profile.');
            renderProfiles();
        });
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
        const result = await api?.toggleRecording?.();
        if (result?.status === 'error') setSystemStatus('error', result.error || 'Could not change recording state.');
        recordBtn.disabled = false;
    });

    api?.onEngineEvent?.(async (event) => {
        if (!event) return;
        if (event.event === 'engine_error') {
            engineReadyForRecording = false;
            updateRecordingAvailability();
            showEngineProblem(event.data || {});
            renderRuntimeInfo(null);
            const list = $('local-models-list');
            if (list) {
                list.innerHTML = `<div class="local-model-error"><strong>Engine unavailable.</strong><span>${escapeHtml(event.data?.message || 'Start the engine and try again.')}</span></div>`;
            }
        } else if (event.event === 'engine_status') {
            warningCard.classList.add('hidden');
            setSystemStatus('', 'Engine connected · checking configuration');
        } else if (event.event === 'download_progress') {
            const data = event.data || {};
            updateDownloadProgressUi(data);
            setSystemStatus('', `${data.status === 'resuming' ? 'Resuming' : 'Downloading'} model: ${data.percent || 0}%`);
        } else if (event.event === 'download_complete') {
            const data = event.data || {};
            activeLocalDownloads.delete(data.model);
            setSystemStatus('', `${data.model || 'Local model'} is ready.`);
            await refreshModels();
            await updateLocalDownloadBox(onboardingState.transcription);
        } else if (event.event === 'download_cancelled') {
            const data = event.data || {};
            activeLocalDownloads.delete(data.model);
            setSystemStatus('', 'Download cancelled. The partial download can be resumed.');
            await refreshModels();
            await updateLocalDownloadBox(onboardingState.transcription);
        } else if (event.event === 'download_error') {
            const data = event.data || {};
            activeLocalDownloads.delete(data.model);
            setSystemStatus('error', data.error || 'Local model download failed.');
            await refreshModels();
            await updateLocalDownloadBox(onboardingState.transcription);
        } else if (event.event === 'engine_ready') {
            engineReadyForRecording = true;
            updateRecordingAvailability();
            warningCard.classList.add('hidden');
            setSystemStatus('', 'Engine ready · loading providers and models');
            await refreshModels();
            await refreshDevices();
            await refreshUsage();
            await loadHistory();
            await loadLibrary();
            await runPreflightCheck();
        } else if (event.event === 'engine_starting') {
            engineReadyForRecording = false;
            updateRecordingAvailability();
            setSystemStatus('', 'Starting AudioScribe engine...');
        } else if (event.event === 'status_changed') {
            if (event.data.status === 'recording') {
                updateRecordState(true);
                const testBadge = $('ob-hotkey-test-badge');
                if (testBadge) {
                    testBadge.textContent = '✓ 🎙️ HOTKEY DETECTED & RECORDING ACTIVE!';
                    testBadge.className = 'perm-badge granted';
                }
            }
            if (event.data.status === 'processing' || event.data.status === 'ready') updateRecordState(false);
            setSystemStatus('', event.data.status === 'recording' ? 'Recording' : 'Processing transcription...');
        } else if (event.event === 'transcription_result') {
            const text = event.data?.text || '';
            const transcriptionError = event.data?.is_error ? (event.data.error || 'Transcription failed.') : '';
            recordMetric(text, event.data?.latency_ms);
            if (event.data?.history) renderHistory([event.data.history, ...historyItems]);
            else loadHistory();
            updateRecordState(false);
            setSystemStatus(transcriptionError ? 'error' : '', transcriptionError || 'Engine ready - result delivered');
            if (transcriptionError) {
                warningTitle.textContent = 'Transcription failed';
                warningText.textContent = transcriptionError;
                warningDetails.textContent = 'The recording finished, but the engine could not produce text. Check the provider and try again.';
                warningCard.classList.remove('hidden');
            }

            if (activeTestRecording) {
                if (activeTestRecording.timeoutId) clearTimeout(activeTestRecording.timeoutId);
                const { btnEl, textEl, pasteInput, chkStt, chkPaste, originalBtnText } = activeTestRecording;
                const isSilent = event.data?.is_silent;

                const updateChk = (badge, status, label) => {
                    if (!badge) return;
                    badge.textContent = label;
                    badge.className = `perm-badge ${status}`;
                };

                if (transcriptionError) {
                    updateChk(chkStt, 'required', '✕ Transcription failed');
                    updateChk(chkPaste, 'required', 'Skipped');
                    if (textEl) textEl.innerHTML = `<span style="color: #ef4444; font-weight: 600;">✕ Transcription failed:</span> ${escapeHtml(transcriptionError)}`;
                } else if (isSilent || !text.trim()) {
                    updateChk(chkStt, 'required', '⚠️ Silence (No Words)');
                    updateChk(chkPaste, 'required', 'Skipped (Silence)');
                    if (textEl) textEl.innerHTML = `<span style="color: #f59e0b; font-weight: 600;">⚠️ Silence Captured:</span> No spoken words detected in your 3-second sample.<br><small style="color: var(--text-soft);">Check your microphone volume or speak louder, then click test again.</small>`;
                } else {
                    const latency = event.data?.latency_ms ? ` (${event.data.latency_ms}ms)` : '';
                    updateChk(chkStt, 'granted', `✓ Transcribed${latency}`);
                    updateChk(chkPaste, 'checking', 'Testing Auto-Paste...');

                    if (textEl) textEl.innerHTML = `<span style="color: #22c55e; font-weight: 600;">✓ Transcription Success${latency}:</span><blockquote style="margin: 8px 0; padding: 10px 14px; background: var(--surface-soft, rgba(255,255,255,0.05)); border-left: 3px solid #22c55e; border-radius: 6px; font-size: 14px; font-style: normal; color: var(--text-main); font-weight: 500;">"${escapeHtml(text)}"</blockquote>`;

                    if (pasteInput) {
                        pasteInput.focus();
                        pasteInput.value = '';
                        setTimeout(async () => {
                            const pasteRes = await api?.copyAndPaste?.(text);
                            if (pasteRes?.status === 'pasted' || pasteInput.value === text) {
                                updateChk(chkPaste, 'granted', '✓ Auto-Pasted Live!');
                            } else {
                                updateChk(chkPaste, 'granted', '✓ Copied to Clipboard');
                            }
                        }, 200);
                    } else {
                        updateChk(chkPaste, 'granted', '✓ Paste Ready');
                    }
                }

                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.textContent = originalBtnText || '🚀 Run Full End-to-End Test (Record 3s)';
                }
                activeTestRecording = null;
            }
        } else if (event.event === 'error') {
            if (event.data?.code === 'engine_offline') {
                engineReadyForRecording = false;
                updateRecordingAvailability();
            }
            updateRecordState(false);
            setSystemStatus('error', event.data?.message || 'Engine error');
            warningText.textContent = event.data?.message || 'The engine reported an error.';
            warningCard.classList.remove('hidden');

            if (activeTestRecording) {
                if (activeTestRecording.timeoutId) clearTimeout(activeTestRecording.timeoutId);
                const { btnEl, textEl, chkStt, originalBtnText } = activeTestRecording;
                if (chkStt) {
                    chkStt.textContent = '✕ STT Error';
                    chkStt.className = 'perm-badge required';
                }
                if (textEl) textEl.innerHTML = `<span style="color: #ef4444; font-weight: 600;">✕ Transcription Error:</span> ${escapeHtml(event.data?.message || 'Error processing audio.')}`;
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.textContent = originalBtnText || '🚀 Run Full End-to-End Test (Record 3s)';
                }
                activeTestRecording = null;
            }
        } else if (event.event === 'engine_error') {
            updateRecordState(false);
            showEngineProblem(event.data || {});

            if (activeTestRecording) {
                if (activeTestRecording.timeoutId) clearTimeout(activeTestRecording.timeoutId);
                const { btnEl, textEl, chkStt, originalBtnText } = activeTestRecording;
                if (chkStt) {
                    chkStt.textContent = '✕ Engine Error';
                    chkStt.className = 'perm-badge required';
                }
                if (textEl) textEl.innerHTML = `<span style="color: #ef4444; font-weight: 600;">✕ Engine Error:</span> ${escapeHtml(event.data?.message || 'Engine encountered an error.')}`;
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.textContent = originalBtnText || '🚀 Run Full End-to-End Test (Record 3s)';
                }
                activeTestRecording = null;
            }
        }
    });
    $('clear-history-btn')?.addEventListener('click', async () => {
        await api?.sendCommand?.('clear_history');
        renderHistory([]);
    });

    $('save-snippet-btn')?.addEventListener('click', async () => {
        const trigger = $('snippet-trigger-input').value.trim();
        const replacement = $('snippet-replacement-input').value.trim();
        const status = $('snippet-status');
        if (!trigger || !replacement) { status.textContent = 'Add both a trigger and expanded text.'; return; }
        const result = await api?.sendCommand?.('save_snippet', { trigger, replacement, enabled: true });
        if (result?.status === 'ok') {
            $('snippet-trigger-input').value = ''; $('snippet-replacement-input').value = '';
            status.textContent = 'Snippet saved locally.'; await loadLibrary();
        } else status.textContent = result?.error || 'Could not save snippet.';
    });

    $('add-dictionary-btn')?.addEventListener('click', async () => {
        const input = $('dictionary-word-input'); const word = input.value.trim();
        if (!word) return;
        await api?.sendCommand?.('update_dictionary', { add: [word], source: 'manual' });
        input.value = ''; await loadLibrary();
    });

    loadProviderConfig().then(async () => {
        await checkOSPermissions();
        await refreshDevices();
        await refreshModels();
        await runPreflightCheck();
        await refreshUsage();
        await loadHistory();
        await loadLibrary();

        // Auto-launch onboarding on fresh install / deleted config
        const hasCompletedOnboarding = localStorage.getItem('audioscribe_onboarding_completed');
        // Do not reset a wizard the user is actively advancing while this
        // asynchronous bootstrap finishes. On a fresh install the modal was
        // already opened synchronously above; resetting here used to send a
        // fast user back to step 1 after they clicked Next.
        if ((!hasCompletedOnboarding || !hasStoredConfig) && onboardingModal?.classList.contains('hidden')) {
            onboardingStep = 1;
            renderOnboarding();
            onboardingModal?.classList.remove('hidden');
        }
    }).catch(console.warn);
});
