/**
 * scribe.js — Voice Scribe Frontend Logic (MedUI Gen3)
 *
 * Layout: Left (controls) / Centre (Transcript + Output tabs) / Right (chunk list)
 *
 * Stage 1 (per chunk):
 *   getUserMedia → AudioWorklet → encodeWAV → POST chunk → append labelled text
 *
 * Stage 2 (recompose):
 *   POST {pipeline_id, transcript, verbosity} → {run_id, stream_url} → EventSource SSE
 *   Result displays in Output tab.
 *
 * All endpoint URLs are read from data-* attributes on <div id="scribe-root">.
 */

document.addEventListener('DOMContentLoaded', function () {

    // ── Element references ────────────────────────────────────────────────────
    const root             = document.getElementById('scribe-root');
    const recordBtn        = document.getElementById('recordBtn');
    const recomposeBtn     = document.getElementById('recomposeBtn');
    const saveBtn          = document.getElementById('saveBtn');
    const transcriptArea   = document.getElementById('transcriptTextarea');
    const outputArea       = document.getElementById('outputTextarea');
    const chunkStatusList  = document.getElementById('chunkStatusList');
    const chunkDurationSel = document.getElementById('chunkDurationSelector');
    const pipelineSelect   = document.getElementById('pipelineSelect');
    const verbositySlider  = document.getElementById('verbositySlider');
    const verbosityValue   = document.getElementById('verbosityValue');
    const charCount        = document.getElementById('charCount');
    const statusLabel      = document.getElementById('scribeStatusLabel');
    const sseSteps         = document.getElementById('sse-steps');
    const sseError         = document.getElementById('sseError');

    // ── Configuration from data-* attributes ─────────────────────────────────
    const CHUNK_URL     = root.dataset.chunkUrl;
    const SYNC_URL      = root.dataset.syncUrl;
    const CONTENT_URL   = root.dataset.contentUrl;
    const CLEAR_URL     = root.dataset.clearUrl;
    const SAVE_URL      = root.dataset.saveUrl;
    const RECOMPOSE_URL = root.dataset.recomposeUrl;
    const WORKLET_URL   = root.dataset.workletUrl;
    const CSRF_TOKEN    = document.querySelector('meta[name="csrf-token"]')?.content || '';

    // The selector is the source of truth (server-rendered from the user's saved preference)
    let chunkDurationMs = parseInt(chunkDurationSel?.value || root.dataset.chunkInterval || '45000');

    // ── State ─────────────────────────────────────────────────────────────────
    let isRecording       = false;
    let audioContext      = null;
    let mediaStream       = null;
    let audioWorkletNode  = null;
    let audioDataBuffer   = [];
    let sampleRate        = 0;
    let sessionId         = null;
    let chunkIntervalId   = null;
    let currentChunkIndex = 0;
    // Speech-to-text model(s) used this session, saved with the transcript:
    // first chunk's model, chunks per model, and whether each is local.
    let asrFirst = null;
    let asrTally = {};
    let asrLocal = {};
    let activeEventSource = null;
    let lastSyncedContent = '';
    let _finalChunkPromise = null; // tracks the in-flight final chunk so startRecompose can wait for it
    let recomposeBusy = false;     // a Recompose is stopping, waiting or running; keeps the button off

    // ── Verbosity labels ──────────────────────────────────────────────────────
    const VERBOSITY_LABELS = { '1': 'Brief', '2': 'Normal', '3': 'Detailed' };

    function getVerbosity() {
        return verbositySlider ? VERBOSITY_LABELS[verbositySlider.value] || 'Normal' : 'Normal';
    }

    if (verbositySlider) {
        verbositySlider.addEventListener('input', function () {
            if (verbosityValue) verbosityValue.textContent = getVerbosity();
        });
        // Set initial label
        if (verbosityValue) verbosityValue.textContent = getVerbosity();
    }

    // ── Pipeline selector ─────────────────────────────────────────────────────
    if (pipelineSelect) {
        pipelineSelect.addEventListener('change', function () {
            updateRecomposeBtn();
        });
    }

    function getSelectedPipelineId() {
        return pipelineSelect ? pipelineSelect.value || null : null;
    }

    function updateRecomposeBtn() {
        if (recomposeBtn) {
            if (recomposeBusy) { recomposeBtn.disabled = true; return; }
            // Live while recording (or while the final chunk is in flight) even before any
            // text has come back: Recompose then stops, waits for the last chunk, and runs.
            const hasText = !!transcriptArea.value.trim();
            const pending = isRecording || !!_finalChunkPromise;
            recomposeBtn.disabled = !(getSelectedPipelineId() && (hasText || pending));
        }
    }

    // ── Utility ───────────────────────────────────────────────────────────────
    function generateSessionId() {
        return 'session-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
    }

    function setStatus(text) {
        if (statusLabel) statusLabel.textContent = text;
    }

    function updateCharCount() {
        if (!charCount) return;
        const n = transcriptArea.value.length;
        const w = transcriptArea.value.trim() ? transcriptArea.value.trim().split(/\s+/).length : 0;
        charCount.textContent = `${w} words · ${n} chars`;
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    transcriptArea.addEventListener('input', () => {
        updateCharCount();
        updateRecomposeBtn();
        debouncedSync();
        debouncedDbSave();
    });

    // ── Recording ─────────────────────────────────────────────────────────────
    recordBtn.addEventListener('click', async () => {
        if (isRecording) stopRecording(); else await startRecording();
    });

    async function startRecording() {
        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                throw new Error('MediaDevices API not available. Use HTTPS.');
            }
            mediaStream    = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioContext   = new (window.AudioContext || window.webkitAudioContext)();
            await audioContext.resume();
            sampleRate     = audioContext.sampleRate;

            const source   = audioContext.createMediaStreamSource(mediaStream);
            const gainNode = audioContext.createGain();
            gainNode.gain.value = 2.0;  // 6 dB boost
            source.connect(gainNode);

            await audioContext.audioWorklet.addModule(WORKLET_URL);
            audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor');

            audioWorkletNode.port.onmessage = (event) => {
                if (event.data?.length > 0) {
                    audioDataBuffer.push(new Float32Array(event.data));
                }
            };

            gainNode.connect(audioWorkletNode);
            audioWorkletNode.connect(audioContext.destination);

            isRecording       = true;
            updateRecomposeBtn();
            recordBtn.classList.add('recording');
            recordBtn.textContent = '⏹ Stop';
            chunkStatusList.innerHTML = '';
            setStatus(`Recording — chunk every ${chunkDurationMs / 1000}s`);
            window.switchScribeTab('transcript');

            if (!sessionId) sessionId = generateSessionId();
            currentChunkIndex = 0;

            chunkIntervalId = setInterval(() => {
                if (isRecording) exportAndSendChunk(false);
            }, chunkDurationMs);

        } catch (err) {
            console.error('Microphone error:', err);
            alert('Microphone access is required. Ensure HTTPS and permission granted.');
        }
    }

    function stopRecording() {
        if (!isRecording) return;
        isRecording = false;
        clearInterval(chunkIntervalId);

        recordBtn.classList.remove('recording');
        recordBtn.textContent = '● Record';
        setStatus('Finalizing…');

        const finalChunk = exportAndSendChunk(true);
        _finalChunkPromise = finalChunk;
        finalChunk.finally(() => {
            if (_finalChunkPromise === finalChunk) _finalChunkPromise = null;
            updateRecomposeBtn();
        });
        updateRecomposeBtn();

        if (audioWorkletNode) { audioWorkletNode.disconnect(); audioWorkletNode = null; }
        if (audioContext)     { audioContext.close(); audioContext = null; }
        if (mediaStream)      { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
        audioDataBuffer = [];

        setTimeout(() => syncTranscript(true), 1500);
    }

    // Resolves when the final chunk has come back (text, silent, error or failed) and,
    // when it had text, its DB save has committed; or straight away when there was no
    // audio left to send. The timeout is only a safety escape.
    function stopRecordingAndWait(timeoutMs = 15000) {
        stopRecording();
        const finalChunk = _finalChunkPromise || Promise.resolve();
        return new Promise(resolve => {
            const timer = setTimeout(resolve, timeoutMs);
            finalChunk.finally(() => { clearTimeout(timer); resolve(); });
        });
    }

    // ── Chunk encoding & sending ──────────────────────────────────────────────
    function exportAndSendChunk(final = false) {
        if (audioDataBuffer.length === 0) return Promise.resolve();
        const merged  = mergeBuffers(audioDataBuffer);
        const wavBlob = encodeWAV(merged, sampleRate);
        audioDataBuffer = [];
        const p = sendAudioChunk(wavBlob, final, currentChunkIndex);
        currentChunkIndex++;
        return p;
    }

    function mergeBuffers(buffers) {
        const length = buffers.reduce((acc, b) => acc + b.length, 0);
        const result = new Float32Array(length);
        let offset = 0;
        buffers.forEach(b => { result.set(b, offset); offset += b.length; });
        return result;
    }

    function encodeWAV(samples, rate) {
        const buffer = new ArrayBuffer(44 + samples.length * 2);
        const view   = new DataView(buffer);

        function ws(offset, str) {
            for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
        }

        ws(0, 'RIFF');
        view.setUint32(4, 36 + samples.length * 2, true);
        ws(8, 'WAVE'); ws(12, 'fmt ');
        view.setUint32(16, 16,       true);
        view.setUint16(20, 1,        true);
        view.setUint16(22, 1,        true);
        view.setUint32(24, rate,     true);
        view.setUint32(28, rate * 2, true);
        view.setUint16(32, 2,        true);
        view.setUint16(34, 16,       true);
        ws(36, 'data');
        view.setUint32(40, samples.length * 2, true);

        let off = 44;
        for (let i = 0; i < samples.length; i++, off += 2) {
            let s = Math.max(-1, Math.min(1, samples[i]));
            s = s < 0 ? s * 0x8000 : s * 0x7FFF;
            view.setInt16(off, s, true);
        }
        return new Blob([view], { type: 'audio/wav' });
    }

    async function sendAudioChunk(blob, final, chunkIndex) {
        const li = document.createElement('li');
        li.id    = `chunk-${chunkIndex}`;
        li.innerHTML = `<span class="spinner"></span> Chunk ${chunkIndex}${final ? ' (final)' : ''}`;
        chunkStatusList.prepend(li);

        const fd = new FormData();
        fd.append('audio',       blob, `chunk_${chunkIndex}.wav`);
        fd.append('session_id',  sessionId);
        fd.append('chunk_index', chunkIndex);
        fd.append('final',       final ? 'true' : 'false');
        fd.append('sample_rate', sampleRate);
        const asrModelId = (typeof window.getAsrModelId === 'function') ? window.getAsrModelId() : null;
        if (asrModelId) fd.append('model_id', asrModelId);

        try {
            const resp = await fetch(CHUNK_URL, { method: 'POST', body: fd });
            const data = await resp.json();

            if (data.asr_model) {
                if (!asrFirst) asrFirst = data.asr_model;
                asrTally[data.asr_model] = (asrTally[data.asr_model] || 0) + 1;
                asrLocal[data.asr_model] = !!data.asr_is_local;
            }
            if (data.transcription) {
                li.innerHTML   = `✓ Chunk ${chunkIndex}`;
                li.style.color = 'var(--success)';

                const current = transcriptArea.value;
                transcriptArea.value = (current ? current + '\n\n' : '') + data.transcription;
                transcriptArea.scrollTop = transcriptArea.scrollHeight;
                updateCharCount();
                updateRecomposeBtn();

                if (final) {
                    setStatus('Ready — select pipeline and Recompose');
                    // Await the save before resolving so startRecompose (if waiting) sees the
                    // record already in the DB and upserts rather than racing to INSERT.
                    await saveTranscriptToDb(false);
                }
            } else if (data.error) {
                li.innerHTML   = `✗ Chunk ${chunkIndex}: ${data.error.substring(0, 60)}`;
                li.style.color = 'var(--danger)';
                if (final) {
                    setStatus('Error on final chunk');
                }
            } else {
                li.innerHTML   = `— Chunk ${chunkIndex} silent`;
                li.style.color = 'var(--text-muted)';
                if (final) {
                    setStatus('Recording complete');
                    await saveTranscriptToDb(false);
                }
            }
        } catch (err) {
            li.innerHTML   = `✗ Chunk ${chunkIndex} failed`;
            li.style.color = 'var(--danger)';
            console.error('Chunk send error:', err);
        }
    }

    // ── DB save (auto on stop + debounced on edit) ────────────────────────────
    let currentTranscriptId = null;

    async function saveTranscriptToDb(isFinal = false) {
        const transcript = transcriptArea.value.trim();
        if (!transcript) return;
        if (!sessionId) sessionId = generateSessionId();

        try {
            const resp = await fetch(SAVE_URL, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                body:    JSON.stringify({
                    transcript: transcript,
                    session_id: sessionId,
                    is_final:   isFinal,
                    extra_data: Object.assign(
                        { char_count: transcript.length, chunks: currentChunkIndex },
                        asrFirst ? { asr_model_first: asrFirst, asr_models: asrTally,
                                     asr_local: asrLocal } : {}),
                }),
            });
            const data = await resp.json();
            if (data.transcript_id) {
                currentTranscriptId = data.transcript_id;
            }
        } catch (err) {
            console.error('Auto-save error:', err);
        }
    }

    let dbSaveTimeout = null;
    function debouncedDbSave() {
        clearTimeout(dbSaveTimeout);
        dbSaveTimeout = setTimeout(() => saveTranscriptToDb(false), 5000);
    }

    // ── Recompose (Stage 2 — SSE pipeline) ───────────────────────────────────
    recomposeBtn?.addEventListener('click', startRecompose);

    async function startRecompose() {
        const pipeline_id = getSelectedPipelineId();
        if (!pipeline_id) return;

        recomposeBusy            = true;
        recomposeBtn.disabled    = true;
        recomposeBtn.textContent = 'Starting…';

        // Stop recording and wait for the final chunk (+ its DB save) to complete.
        // If the user already clicked Stop manually, _finalChunkPromise tracks the
        // in-flight chunk so we still wait rather than racing its DB save.
        if (isRecording) {
            setStatus('Stopping recording…');
            recomposeBtn.textContent = 'Stopping…';
            await stopRecordingAndWait();
        } else if (_finalChunkPromise) {
            setStatus('Waiting for final chunk…');
            recomposeBtn.textContent = 'Finalizing…';
            await _finalChunkPromise;
        }

        // Save current textarea content to DB before recomposing (safe: any chunk
        // save has already committed above, so this will upsert, not duplicate).
        await saveTranscriptToDb(false);

        const transcript = transcriptArea.value.trim();
        const verbosity  = getVerbosity();
        if (!transcript) {
            setStatus('Nothing to recompose — no speech was transcribed');
            resetRecomposeBtn();
            return;
        }

        recomposeBtn.textContent = 'Starting…';
        setStatus('Starting recompose pipeline…');

        if (sseSteps)  { sseSteps.innerHTML  = ''; sseSteps.style.display  = 'none'; }
        if (sseError)  { sseError.innerHTML  = ''; sseError.style.display  = 'none'; }
        if (outputArea) outputArea.value = '';

        // Switch to Output tab so user sees progress
        window.switchScribeTab('output');

        try {
            const resp = await fetch(RECOMPOSE_URL, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                // review_capable: this page can show the pre-send review (ADR-094)
                body:    JSON.stringify({ pipeline_id, transcript, verbosity, review_capable: true }),
            });
            const data = await resp.json();

            if (data.error) {
                showError(data.error);
                if (typeof window.debugLogError === 'function') window.debugLogError(data.error);
                resetRecomposeBtn();
                return;
            }
            // Log run to debug tab (pipeline name from select option label)
            if (typeof window.debugLogRun === 'function') {
                const sel  = document.getElementById('pipelineSelect');
                const name = sel ? (sel.options[sel.selectedIndex]?.text || pipeline_id) : pipeline_id;
                window.debugLogRun(data.run_id, name);
            }
            openSSE(data.run_id, data.stream_url);
        } catch (err) {
            showError('Could not start recompose: ' + err);
            resetRecomposeBtn();
        }
    }

    function resetRecomposeBtn() {
        recomposeBusy = false;
        if (recomposeBtn) {
            recomposeBtn.textContent = '✦ Recompose';
            updateRecomposeBtn();
        }
    }

    function openSSE(runId, streamUrl) {
        if (activeEventSource) activeEventSource.close();
        if (recomposeBtn) recomposeBtn.textContent = 'Running…';
        clearPrivacyBadges();

        const src = new EventSource(streamUrl);
        activeEventSource = src;

        // step_start — show spinner dot immediately
        src.addEventListener('step_start', (e) => {
            const d = JSON.parse(e.data);
            d.status = 'run';
            updateStep(d);
            if (typeof window.debugLogStep === 'function') window.debugLogStep(d);
        });

        // step_done — update dot to green with timing
        src.addEventListener('step_done', (e) => {
            const d = JSON.parse(e.data);
            updateStep(d);
            if (typeof window.debugLogStep === 'function') window.debugLogStep(d);
        });

        // step_error — update dot to red
        src.addEventListener('step_error', (e) => {
            const d = JSON.parse(e.data);
            d.status = 'error';
            updateStep(d);
            if (typeof window.debugLogStep === 'function') window.debugLogStep(d);
            showError(d.error || d.message || 'Step error');
            if (typeof window.debugLogError === 'function') window.debugLogError(d.message || d.error || 'Step failed');
        });

        // review — held before the cloud call: the Sending tab (ADR-094)
        src.addEventListener('review', (e) => {
            const d = JSON.parse(e.data);
            const btn = document.getElementById('tab-btn-sent');
            const pane = document.getElementById('tab-pane-sent');
            if (!btn || !pane || !window.PresendReview) return;
            btn.style.display = '';
            setStatus(d.blocking ? 'Stopped before sending — an identifier was found'
                                 : 'Review what will be sent');
            window.PresendReview.mountReviewPanel(pane, btn, { runId, data: d, csrf: CSRF_TOKEN });
            window.switchScribeTab('sent');
        });

        // cancelled — nothing was sent
        src.addEventListener('cancelled', (e) => {
            const d = JSON.parse(e.data);
            const btn = document.getElementById('tab-btn-sent');
            const pane = document.getElementById('tab-pane-sent');
            if (btn) { btn.textContent = 'Sent'; btn.style.display = 'none'; }
            if (pane) pane.innerHTML = '';
            setStatus('Cancelled — nothing was sent');
            showError(d.message || 'Cancelled at review — nothing was sent to the AI.');
            window.switchScribeTab('output');
        });

        // complete — show output and privacy badges
        src.addEventListener('complete', (e) => {
            const d = JSON.parse(e.data);
            setStatus('Recompose complete');
            if (typeof window.debugLogComplete === 'function') window.debugLogComplete(d);
            showOutput(d.output || '');
            showPrivacyBadges(d);
            // What went to the AI, read-only (ADR-094)
            const sentBtn = document.getElementById('tab-btn-sent');
            const sentPane = document.getElementById('tab-pane-sent');
            if (sentBtn && sentPane && window.PresendReview && !d.model_is_local
                    && d.ai_debug && d.ai_debug.current_prompt) {
                sentBtn.textContent = 'Sent';
                sentBtn.style.display = '';
                window.PresendReview.showSent(sentPane, d.ai_debug.current_prompt, d.review, d.ai_debug.system_prompt);
            }
            if (document.getElementById('tab-pane-sent')?.classList.contains('active')) {
                window.switchScribeTab('output');
            }
        });

        // done — stream finished, clean up
        src.addEventListener('done', () => {
            src.close();
            activeEventSource = null;
            resetRecomposeBtn();
            if (typeof window.debugFetchContext === 'function') window.debugFetchContext();
        });

        // error — named SSE error event from engine
        src.addEventListener('error', (e) => {
            let d = {};
            try { d = JSON.parse(e.data); } catch (_) {}
            const msg = d.message || d.error || 'Pipeline error';
            src.close();
            activeEventSource = null;
            setStatus('Error');
            showError(msg);
            if (typeof window.debugLogError === 'function') window.debugLogError(msg);
            resetRecomposeBtn();
        });

        // onerror — connection-level failure (not a named SSE event)
        src.onerror = () => {
            if (src.readyState === EventSource.CLOSED) return;
            src.close();
            activeEventSource = null;
            const msg = 'Pipeline stream disconnected — check the Debug tab for details.';
            showError(msg);
            if (typeof window.debugLogError === 'function') window.debugLogError(msg);
            resetRecomposeBtn();
        };
    }

    function updateStep(d) {
        if (!sseSteps) return;
        sseSteps.style.display = '';
        let row = document.getElementById(`sse-step-${d.step}`);
        if (!row) {
            row = document.createElement('div');
            row.id        = `sse-step-${d.step}`;
            row.className = 'step-row-inline';
            sseSteps.appendChild(row);
        }
        const cls  = d.status === 'ok' ? 'ok' : d.status === 'error' ? 'error' : 'run';
        const icon = d.status === 'ok' ? '✓' : d.status === 'error' ? '✗' : '…';
        const dur  = d.duration_ms
            ? ` <span style="color:var(--text-muted);font-size:0.65rem">${d.duration_ms}ms</span>`
            : '';
        row.innerHTML =
            `<span class="step-dot ${cls}">${icon}</span>` +
            `<span style="flex:1;font-size:0.7rem">${escapeHtml(d.node || 'Step ' + d.step)}</span>${dur}`;
    }

    // ── Privacy badges ────────────────────────────────────────────────────────
    function clearPrivacyBadges() {
        const bar = document.getElementById('privacy-badge-bar');
        if (bar) bar.innerHTML = '';
    }

    function showPrivacyBadges(d) {
        const bar = document.getElementById('privacy-badge-bar');
        if (!bar) return;

        const badges = [];

        // Model locality badge
        if (d.model_is_local === true) {
            badges.push({ label: '💻 Local', cls: 'badge-local', title: 'Inference ran on a local model — no data sent to cloud' });
        } else if (d.model_is_local === false) {
            badges.push({ label: '☁️ Cloud', cls: 'badge-cloud', title: 'Inference used a cloud provider' });
        }

        // Redaction badge
        if (d.is_redacted === true && d.is_hcp_redacted === true) {
            badges.push({ label: '🔒 Fully Redacted', cls: 'badge-redacted', title: 'Patient PII and HCP identifiers redacted before sending' });
        } else if (d.is_redacted === true) {
            badges.push({ label: '🔒 PII Redacted', cls: 'badge-redacted', title: 'Patient PII redacted; HCP identifiers may be present' });
        } else if (d.is_redacted === false) {
            badges.push({ label: '⚠️ Not Redacted', cls: 'badge-unredacted', title: 'Data was sent without redaction — local model only' });
        }

        bar.innerHTML = badges.map(b =>
            `<span class="pipeline-badge ${b.cls}" title="${escapeHtml(b.title)}">${escapeHtml(b.label)}</span>`
        ).join('');
    }

    function showOutput(text) {
        if (!outputArea) return;
        outputArea.value = text;
        outputArea.scrollTop = 0;
        // Reset rendered view to editable
        const rendered = document.getElementById('outputRendered');
        const btn      = document.getElementById('outPrintVersionBtn');
        if (rendered) rendered.style.display = 'none';
        outputArea.style.display = 'block';
        if (btn) { btn.classList.remove('active'); btn.textContent = 'Print Version'; }
        window._outputIsRendered = false;
    }

    function showError(msg) {
        if (!sseError) return;
        sseError.innerHTML    = escapeHtml(msg);
        sseError.style.display = '';
    }

    // ── Save to chart (marks is_final=true) ──────────────────────────────────
    saveBtn?.addEventListener('click', async () => {
        const transcript = transcriptArea.value.trim();
        if (!transcript) { alert('No transcript to save.'); return; }

        saveBtn.disabled    = true;
        saveBtn.textContent = 'Saving…';
        try {
            await saveTranscriptToDb(true);
            saveBtn.textContent = 'Saved ✓';
            setTimeout(() => {
                saveBtn.textContent = '💾 Save to Chart';
                saveBtn.disabled    = false;
            }, 2000);
        } catch (err) {
            saveBtn.textContent = 'Save failed';
            saveBtn.disabled    = false;
        }
    });

    // ── Periodic sync (cache) ─────────────────────────────────────────────────
    async function syncTranscript(force = false) {
        const content = transcriptArea.value;
        if (!force && content === lastSyncedContent) return;
        try {
            await fetch(SYNC_URL, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                body:    JSON.stringify({ content }),
            });
            lastSyncedContent = content;
        } catch (err) {
            console.error('Sync error:', err);
        }
    }

    let syncTimeout = null;
    function debouncedSync() {
        clearTimeout(syncTimeout);
        syncTimeout = setTimeout(() => syncTranscript(false), 2000);
    }

    setInterval(() => syncTranscript(false), 10000);

    // ── Chunk duration change ─────────────────────────────────────────────────
    chunkDurationSel?.addEventListener('change', function () {
        chunkDurationMs = parseInt(this.value);
        // Apply mid-recording: restart the timer; buffered audio goes out on the next tick
        if (isRecording) {
            clearInterval(chunkIntervalId);
            chunkIntervalId = setInterval(() => {
                if (isRecording) exportAndSendChunk(false);
            }, chunkDurationMs);
            setStatus(`Recording — chunk every ${chunkDurationMs / 1000}s`);
        }
    });

    // ── Restore cached transcript on load ────────────────────────────────────
    (async () => {
        try {
            const resp = await fetch(CONTENT_URL);
            const data = await resp.json();
            if (data.has_content && !transcriptArea.value.trim()) {
                transcriptArea.value = data.content;
                updateCharCount();
                updateRecomposeBtn();
                setStatus('Transcript restored from session cache');
            }
        } catch (_) {}
    })();

    // ── Initial state ─────────────────────────────────────────────────────────
    updateCharCount();
    updateRecomposeBtn();
});
