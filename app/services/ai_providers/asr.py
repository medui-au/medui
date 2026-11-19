"""ASR providers: WhisperProvider (local HTTP) and DeepgramProvider (cloud API)."""

from __future__ import annotations
import time
from urllib.parse import urlsplit
from .base import BaseProvider, GenerateResult, TranscribeResult

DEEPGRAM_DEFAULT_URL = 'https://api.deepgram.com'
DEEPGRAM_SPEAKER_VERSIONS = ('latest', 'v2', 'v1')


def _form_value(value) -> str:
    """A parameter as a query-string or form value: booleans as true/false."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def deepgram_root(base_url: str | None) -> str:
    """Scheme and host of a Deepgram provider's Base URL (ADR-151).

    The field may hold just the host (https://api.au.deepgram.com) or a full endpoint
    (https://api.deepgram.com/v1/listen, as older installs saved it); blank is the global
    endpoint.
    """
    parts = urlsplit((base_url or '').strip())
    if parts.scheme in ('http', 'https') and parts.netloc:
        return f'{parts.scheme}://{parts.netloc}'
    return DEEPGRAM_DEFAULT_URL


def deepgram_turns(body: dict) -> str | None:
    """The reply's text as speaker turns, or None when Deepgram did not separate speakers.

    Speakers are numbered from 1 within the chunk ("[Speaker 1] …"); the numbers restart in
    every chunk. Consecutive paragraphs of one speaker are joined.
    """
    if not (body.get('metadata') or {}).get('diarize_info'):
        return None
    alt = (((body.get('results') or {}).get('channels') or [{}])[0]
           .get('alternatives') or [{}])[0]
    paragraphs = ((alt.get('paragraphs') or {}).get('paragraphs')) or []
    turns: list[list] = []
    for para in paragraphs:
        speaker = para.get('speaker')
        if not isinstance(speaker, int):
            return None
        text = ' '.join((s.get('text') or '').strip() for s in para.get('sentences') or []).strip()
        if not text:
            continue
        if turns and turns[-1][0] == speaker:
            turns[-1][1] += ' ' + text
        else:
            turns.append([speaker, text])
    if not turns:
        return None
    return '\n'.join(f'[Speaker {speaker + 1}] {text}' for speaker, text in turns)


class WhisperProvider(BaseProvider):
    """Posts audio bytes to a local Whisper-compatible HTTP server (e.g. faster-whisper-server).

    Expected endpoint: POST <base_url>/asr
    Body: multipart/form-data with field 'audio_file'
    Response JSON: {'text': '...', 'language': '...'}
    """
    is_cloud: bool = False
    is_asr: bool = True

    def generate(self, *args, **kwargs) -> GenerateResult:
        raise NotImplementedError('WhisperProvider is ASR-only; use transcribe()')

    def transcribe(self, audio_bytes: bytes, language: str = 'en',
                   model: str | None = None, params: dict | None = None,
                   speaker_turns: str | None = None) -> TranscribeResult:
        import requests

        url = (self.base_url or 'http://localhost:9000').rstrip('/') + '/asr'
        files = {'audio_file': ('audio.wav', audio_bytes, 'audio/wav')}
        # The WhisperX server uses whatever model it was started with.
        # model_id in our DB is an internal name, not a server model selector.
        # Only pass 'model' if an explicit override was provided by the caller
        # AND it differs from our stored model_id (i.e. it's an actual server model name).
        # The model's extra parameters (ADR-151) go as form fields; MedUI's own come last.
        data = {k: _form_value(v) for k, v in (params or {}).items()}
        data['language'] = language
        if model and model != self.model_id:
            data['model'] = model

        t0 = time.monotonic()
        resp = requests.post(url, files=files, data=data, timeout=120)
        if not resp.ok:
            body = resp.text[:500] if resp.text else '(empty)'
            raise RuntimeError(
                f'WhisperX {resp.status_code}: {body}'
            )
        duration = time.monotonic() - t0

        body = resp.json()
        # Some WhisperX servers return text as a list of segment dicts; flatten to a string.
        raw = body.get('text', '')
        if isinstance(raw, list):
            raw = ' '.join(
                seg.get('text', '') if isinstance(seg, dict) else str(seg)
                for seg in raw
            )
        return TranscribeResult(
            text=raw,
            language=body.get('language', language),
            duration_seconds=duration,
            model_used=model or self.model_id,
        )

    def health_check(self) -> bool:
        import requests
        url = (self.base_url or 'http://localhost:9000').rstrip('/') + '/health'
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return True


class DeepgramProvider(BaseProvider):
    """Deepgram cloud ASR. Recommends nova-3-medical for clinical audio."""
    is_cloud: bool = True
    is_asr: bool = True

    def generate(self, *args, **kwargs) -> GenerateResult:
        raise NotImplementedError('DeepgramProvider is ASR-only; use transcribe()')

    def transcribe(self, audio_bytes: bytes, language: str = 'en',
                   model: str | None = None, params: dict | None = None,
                   speaker_turns: str | None = None) -> TranscribeResult:
        """One chunk to Deepgram's pre-recorded endpoint, at the provider's Base URL.

        params: the model's extra parameters, sent as query parameters; MedUI's own (model,
        language, speaker separation) are set last. speaker_turns: 'latest', 'v2' or 'v1'
        asks Deepgram to separate speakers (diarize_model) and the reply is read as turns.
        """
        import requests

        model_id = model or self.model_id or 'nova-3-medical'
        url = deepgram_root(self.base_url) + '/v1/listen'
        query = {'smart_format': 'true'}
        query.update({k: _form_value(v) for k, v in (params or {}).items()})
        query.update({'model': model_id, 'language': language})
        if speaker_turns in DEEPGRAM_SPEAKER_VERSIONS:
            query.update({'diarize_model': speaker_turns, 'paragraphs': 'true'})
        headers = {
            'Authorization': f'Token {self.api_key}',
            'Content-Type': 'audio/wav',
        }

        t0 = time.monotonic()
        resp = requests.post(url, params=query, headers=headers, data=audio_bytes, timeout=120)
        if not resp.ok:
            # Deepgram's reply names the problem (a parameter it refuses, a bad key); it
            # holds no audio or transcript.
            raise RuntimeError(f'Deepgram {resp.status_code}: {(resp.text or "")[:300]}')
        duration = time.monotonic() - t0

        body = resp.json()
        transcript = (body.get('results', {})
                         .get('channels', [{}])[0]
                         .get('alternatives', [{}])[0]
                         .get('transcript', ''))
        turns = deepgram_turns(body) if speaker_turns in DEEPGRAM_SPEAKER_VERSIONS else None
        return TranscribeResult(
            text=turns if turns is not None else transcript,
            language=language,
            duration_seconds=duration,
            model_used=model_id,
            speaker_turns=turns is not None,
        )

    def health_check(self) -> bool:
        import requests
        resp = requests.get(
            # /v1/auth/token checks the key on the global and the regional endpoints;
            # /v1/projects is not served at api.au.deepgram.com (ADR-151).
            deepgram_root(self.base_url) + '/v1/auth/token',
            headers={'Authorization': f'Token {self.api_key}'},
            timeout=8,
        )
        resp.raise_for_status()
        return True
