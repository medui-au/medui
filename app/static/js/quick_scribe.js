/**
 * quick_scribe.js — Patient-free voice recording for Quick Scribe.
 *
 * Record → ASR chunks → transcript textarea → copy to clipboard.
 * No patient context, no DB saves, no recompose pipeline.
 */

document.addEventListener('DOMContentLoaded', function () {

    const root           = document.getElementById('quick-scribe-root');
    const recordBtn      = document.getElementById('qsRecordBtn');
    const copyBtn        = document.getElementById('qsCopyBtn');
    const clearBtn       = document.getElementById('qsClearBtn');
    const transcriptArea = document.getElementById('qsTranscriptTextarea');
    const chunkList      = document.getElementById('qsChunkList');
    const chunkSel       = document.getElementById('qsChunkDurationSelector');
    const statusLabel    = document.getElementById('qsStatusLabel');
    const charCount      = document.getElementById('qsCharCount');

    const CHUNK_URL   = root.dataset.chunkUrl;
    const WORKLET_URL = root.dataset.workletUrl;

    let chunkDurationMs   = parseInt(chunkSel?.value || '45000');
    let isRecording       = false;
    let audioContext      = null;
    let mediaStream       = null;
    let audioWorkletNode  = null;
    let audioDataBuffer   = [];
    let sampleRate        = 0;
    let sessionId         = null;
    let chunkIntervalId   = null;
    let currentChunkIndex = 0;

    function generateSessionId() {
        return 'qs-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);
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

    transcriptArea.addEventListener('input', updateCharCount);

    chunkSel?.addEventListener('change', function () {
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

    // ── Record ────────────────────────────────────────────────────────────────

    recordBtn.addEventListener('click', async () => {
        if (isRecording) stopRecording(); else await startRecording();
    });

    async function startRecording() {
        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                throw new Error('MediaDevices API not available. Use HTTPS.');
            }
            mediaStream  = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            await audioContext.resume();
            sampleRate   = audioContext.sampleRate;

            const source   = audioContext.createMediaStreamSource(mediaStream);
            const gainNode = audioContext.createGain();
            gainNode.gain.value = 2.0;
            source.connect(gainNode);

            await audioContext.audioWorklet.addModule(WORKLET_URL);
            audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor');
            audioWorkletNode.port.onmessage = (event) => {
                if (event.data?.length > 0) audioDataBuffer.push(new Float32Array(event.data));
            };
            gainNode.connect(audioWorkletNode);
            audioWorkletNode.connect(audioContext.destination);

            isRecording       = true;
            sessionId         = generateSessionId();
            currentChunkIndex = 0;
            recordBtn.classList.add('recording');
            recordBtn.textContent = '⏹ Stop';
            chunkList.innerHTML   = '';
            setStatus(`Recording — chunk every ${chunkDurationMs / 1000}s`);

            chunkIntervalId = setInterval(() => {
                if (isRecording) exportAndSendChunk(false);
            }, chunkDurationMs);

        } catch (err) {
            console.error('Microphone error:', err);
            alert('Microphone access required. Ensure HTTPS and permission granted.');
        }
    }

    function stopRecording() {
        if (!isRecording) return;
        isRecording = false;
        clearInterval(chunkIntervalId);
        recordBtn.classList.remove('recording');
        recordBtn.textContent = '● Record';
        setStatus('Finalizing…');
        exportAndSendChunk(true);
        if (audioWorkletNode) { audioWorkletNode.disconnect(); audioWorkletNode = null; }
        if (audioContext)     { audioContext.close(); audioContext = null; }
        if (mediaStream)      { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
        audioDataBuffer = [];
    }

    // ── Chunk encoding & sending ──────────────────────────────────────────────

    function exportAndSendChunk(final = false) {
        if (audioDataBuffer.length === 0) return;
        const merged  = mergeBuffers(audioDataBuffer);
        const wavBlob = encodeWAV(merged, sampleRate);
        audioDataBuffer = [];
        sendChunk(wavBlob, final, currentChunkIndex);
        currentChunkIndex++;
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
        view.setUint32(16, 16, true);
        view.setUint16(20, 1,  true);
        view.setUint16(22, 1,  true);
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

    async function sendChunk(blob, final, chunkIndex) {
        const li = document.createElement('li');
        li.id    = `qs-chunk-${chunkIndex}`;
        li.innerHTML = `<span class="spinner"></span> Chunk ${chunkIndex}${final ? ' (final)' : ''}`;
        chunkList.prepend(li);

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

            if (data.transcription) {
                li.innerHTML   = `✓ Chunk ${chunkIndex}`;
                li.style.color = 'var(--success)';
                const current  = transcriptArea.value;
                transcriptArea.value = (current ? current + '\n\n' : '') + data.transcription;
                transcriptArea.scrollTop = transcriptArea.scrollHeight;
                updateCharCount();
                if (final) setStatus('Done — copy transcript to clipboard');
            } else if (data.error) {
                li.innerHTML   = `✗ Chunk ${chunkIndex}: ${data.error.substring(0, 60)}`;
                li.style.color = 'var(--danger)';
                if (final) setStatus('Error on final chunk');
            } else {
                li.innerHTML   = `— Chunk ${chunkIndex} silent`;
                li.style.color = 'var(--text-muted)';
                if (final) setStatus('Recording complete');
            }
        } catch (err) {
            li.innerHTML   = `✗ Chunk ${chunkIndex} failed`;
            li.style.color = 'var(--danger)';
            console.error('Quick scribe chunk error:', err);
            if (final) setStatus('Network error on final chunk');
        }
    }

    // ── Copy to clipboard ─────────────────────────────────────────────────────

    copyBtn.addEventListener('click', function () {
        const text = transcriptArea.value.trim();
        if (!text) { setStatus('Nothing to copy.'); return; }
        navigator.clipboard.writeText(text).then(function () {
            const orig = copyBtn.textContent;
            copyBtn.textContent = '✓ Copied!';
            copyBtn.classList.add('copied');
            setTimeout(function () {
                copyBtn.textContent = orig;
                copyBtn.classList.remove('copied');
            }, 2000);
            setStatus('Transcript copied to clipboard');
        }).catch(function () {
            setStatus('Clipboard write failed — select all and copy manually (Ctrl+A, Ctrl+C).');
        });
    });

    // ── Clear ─────────────────────────────────────────────────────────────────

    clearBtn.addEventListener('click', function () {
        if (isRecording) return;
        if (transcriptArea.value.trim() && !confirm('Clear the transcript?')) return;
        transcriptArea.value = '';
        chunkList.innerHTML  = '<li style="color:var(--text-muted);font-family:inherit;font-size:0.7rem;padding:0.2rem 0;">Press Record to begin.</li>';
        sessionId            = null;
        currentChunkIndex    = 0;
        updateCharCount();
        setStatus('Cleared');
    });

    // ── Initial state ─────────────────────────────────────────────────────────
    updateCharCount();
    setStatus('Ready — press Record to begin');
});
