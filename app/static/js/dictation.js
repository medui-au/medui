/**
 * dictation.js — Reusable inline voice dictation for text areas.
 *
 * Any element with [data-dictate-for="<textarea-id>"] and
 * [data-dictate-url="<endpoint>"] is auto-wired as a push-to-talk mic button.
 *
 * On stop, the WAV is sent as a single POST; the returned transcription is
 * inserted at the cursor position in the target element.
 *
 * data-dictate-for="@focus" serves a whole page (or the element named by
 * data-dictate-within): the text goes to the text box last clicked into, at its cursor.
 *
 * Also expose window.initDictationButtons(root) for HTMX / dynamic content.
 */

(function () {
    'use strict';

    const MAX_MS = 180000; // 3-minute safety cutoff

    function attachDictation(btn) {
        const targetId = btn.dataset.dictateFor;
        const endpoint = btn.dataset.dictateUrl;
        const byFocus  = targetId === '@focus';
        const target   = byFocus ? null : document.getElementById(targetId);
        if ((!byFocus && !target) || !endpoint) return;
        if (btn._dictationAttached) return;
        btn._dictationAttached = true;

        const workletUrl = btn.dataset.workletUrl
            || (document.querySelector('[data-worklet-url]') || {}).dataset?.workletUrl
            || '/static/js/audio-processor.js';

        let isRecording      = false;
        let audioContext     = null;
        let mediaStream      = null;
        let audioWorkletNode = null;
        let audioDataBuffer  = [];
        let sampleRate       = 0;
        let safetyTimer      = null;
        let lastBox          = null;

        if (byFocus) {
            const scope = document.getElementById(btn.dataset.dictateWithin) || document;
            scope.addEventListener('focusin', (e) => {
                const el = e.target;
                if (el.tagName === 'TEXTAREA'
                    || (el.tagName === 'INPUT' && ['text', 'search', ''].includes(el.getAttribute('type') || ''))) {
                    lastBox = el;
                }
            });
        }

        function currentTarget() {
            if (!byFocus) return target;
            return lastBox && lastBox.isConnected && !lastBox.disabled && !lastBox.readOnly ? lastBox : null;
        }

        btn.addEventListener('click', async () => {
            if (!isRecording && byFocus && !currentTarget()) {
                alert('Click in a text box first; the dictation goes where the cursor is.');
                return;
            }
            if (isRecording) await stopAndSend(); else await startRecording();
        });

        async function startRecording() {
            try {
                if (!navigator.mediaDevices?.getUserMedia) {
                    throw new Error('getUserMedia not available — use HTTPS.');
                }
                mediaStream  = await navigator.mediaDevices.getUserMedia({ audio: true });
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                await audioContext.resume();
                sampleRate   = audioContext.sampleRate;

                const source   = audioContext.createMediaStreamSource(mediaStream);
                const gain     = audioContext.createGain();
                gain.gain.value = 2.0;
                source.connect(gain);

                await audioContext.audioWorklet.addModule(workletUrl);
                audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor');
                audioWorkletNode.port.onmessage = (e) => {
                    if (e.data?.length > 0) audioDataBuffer.push(new Float32Array(e.data));
                };
                gain.connect(audioWorkletNode);
                audioWorkletNode.connect(audioContext.destination);

                isRecording = true;
                audioDataBuffer = [];
                setState('recording');
                safetyTimer = setTimeout(() => stopAndSend(), MAX_MS);

            } catch (err) {
                console.error('Dictation: mic error', err);
                alert('Microphone access required. Ensure HTTPS and permission granted.');
                teardown();
            }
        }

        async function stopAndSend() {
            if (!isRecording) return;
            clearTimeout(safetyTimer);
            isRecording = false;
            // Immediately show the click was registered, but keep the mic active
            // for a short tail so in-flight AudioWorklet frames arrive in the buffer.
            setState('stopping');
            await new Promise(resolve => setTimeout(resolve, 750));
            setState('sending');

            const buffered = audioDataBuffer.splice(0);
            teardown();

            if (!buffered.length) { setState('idle'); return; }

            const wav = encodeWAV(mergeBuffers(buffered), sampleRate);
            const fd  = new FormData();
            fd.append('audio', wav, 'dictation.wav');
            fd.append('sample_rate', sampleRate);

            try {
                const resp = await fetch(endpoint, { method: 'POST', body: fd });
                const data = await resp.json();
                const into = currentTarget();
                if (data.transcription && into) {
                    insertAtCursor(into, data.transcription);
                    flashBtn('done');
                } else {
                    if (data.error) console.error('Dictation error:', data.error);
                    flashBtn('error');
                }
            } catch (err) {
                console.error('Dictation fetch error:', err);
                flashBtn('error');
            } finally {
                setState('idle');
            }
        }

        function teardown() {
            if (audioWorkletNode) { audioWorkletNode.disconnect(); audioWorkletNode = null; }
            if (audioContext)     { audioContext.close();          audioContext     = null; }
            if (mediaStream)      { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
        }

        // ── Button state ──────────────────────────────────────────────────────

        const origTitle = btn.title || btn.getAttribute('aria-label') || 'Dictate';

        function setState(state) {
            btn.classList.remove('dictation-btn--recording', 'dictation-btn--sending');
            btn.disabled = false;
            btn.setAttribute('aria-pressed', 'false');
            if (state === 'recording') {
                btn.classList.add('dictation-btn--recording');
                btn.title = 'Recording — click to stop';
                btn.setAttribute('aria-pressed', 'true');
            } else if (state === 'stopping') {
                // Pulse stops immediately; button dims while the 750ms tail flushes
                btn.classList.add('dictation-btn--sending');
                btn.title = 'Finishing…';
                btn.disabled = true;
            } else if (state === 'sending') {
                btn.classList.add('dictation-btn--sending');
                btn.title = 'Transcribing…';
                btn.disabled = true;
            } else {
                btn.title = origTitle;
            }
        }

        function flashBtn(type) {
            const cls = 'dictation-btn--' + type;
            btn.classList.add(cls);
            setTimeout(() => btn.classList.remove(cls), 1200);
        }

        // ── Audio helpers ─────────────────────────────────────────────────────

        function mergeBuffers(buffers) {
            const len = buffers.reduce((a, b) => a + b.length, 0);
            const out = new Float32Array(len);
            let off = 0;
            buffers.forEach(b => { out.set(b, off); off += b.length; });
            return out;
        }

        function encodeWAV(samples, rate) {
            const buf  = new ArrayBuffer(44 + samples.length * 2);
            const view = new DataView(buf);
            const ws   = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
            ws(0, 'RIFF');
            view.setUint32(4, 36 + samples.length * 2, true);
            ws(8, 'WAVE'); ws(12, 'fmt ');
            view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
            view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
            view.setUint16(32, 2, true);   view.setUint16(34, 16, true);
            ws(36, 'data');
            view.setUint32(40, samples.length * 2, true);
            let o = 44;
            for (let i = 0; i < samples.length; i++, o += 2) {
                let s = Math.max(-1, Math.min(1, samples[i]));
                view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
            }
            return new Blob([view], { type: 'audio/wav' });
        }

        // ── Insert at cursor ──────────────────────────────────────────────────

        function insertAtCursor(el, text) {
            const start  = el.selectionStart ?? el.value.length;
            const end    = el.selectionEnd   ?? el.value.length;
            const before = el.value.slice(0, start);
            const after  = el.value.slice(end);
            const pad    = (before.length && !/\s$/.test(before) ? ' ' : '')
                         + text
                         + (after.length  && !/^\s/.test(after)  ? ' ' : '');
            el.value = before + pad + after;
            const pos = start + pad.length;
            el.setSelectionRange(pos, pos);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.focus();
        }
    }

    // ── Auto-discover ─────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-dictate-for]').forEach(attachDictation);
    });

    window.initDictationButtons = function (root) {
        (root || document).querySelectorAll('[data-dictate-for]').forEach(attachDictation);
    };

}());
