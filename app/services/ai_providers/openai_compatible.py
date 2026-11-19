"""OpenAI-compatible provider — covers Ollama, OpenAI, OpenRouter, Groq, DeepSeek, LM Studio."""

from __future__ import annotations
import time
from .base import BaseProvider, GenerateResult, TranscribeResult


def _describe_empty_response(resp) -> str:
    """Best-effort extraction of whatever a response with no choices still
    carries (e.g. an inline error from a proxy), for the raised error message.
    Returns '' (never raises) if resp can't be introspected."""
    try:
        dump = resp.model_dump(exclude_none=True)
    except Exception:
        return ''
    dump.pop('choices', None)
    if not dump:
        return ''
    return f' ({dump})'


class OpenAICompatibleProvider(BaseProvider):
    """Uses the openai Python SDK with a configurable base_url.
    Set is_cloud=False for local providers (Ollama, LM Studio) via the factory."""

    def generate(self, prompt: str, system_prompt: str | None = None,
                 temperature: float | None = None,
                 max_tokens: int | None = None,
                 keep_alive: str | int | None = None,
                 request_params: dict | None = None,
                 **kwargs) -> GenerateResult:
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key or 'not-needed')
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        create_kwargs: dict = {'model': self.model_id, 'messages': messages}
        if temperature is not None:
            create_kwargs['temperature'] = temperature
        if max_tokens is not None:
            create_kwargs['max_tokens'] = max_tokens
        if keep_alive is not None:
            # Ollama-specific: how long to keep this model resident in VRAM
            # after this request (e.g. "30m", or -1 for indefinite). Not part
            # of the OpenAI schema — sent via extra_body so the openai SDK
            # passes it straight through in the raw JSON body. Harmless no-op
            # against any backend that doesn't recognise it.
            create_kwargs['extra_body'] = {'keep_alive': keep_alive}
        if request_params:
            # Extra request parameters (ADR-119), e.g. {"reasoning_effort": "none"}: checked
            # on save never to name what is set above, and sent in the raw JSON body.
            create_kwargs['extra_body'] = {**request_params, **create_kwargs.get('extra_body', {})}

        t0 = time.monotonic()
        resp = client.chat.completions.create(**create_kwargs)
        latency = int((time.monotonic() - t0) * 1000)

        if not resp.choices:
            # Some OpenAI-compatible proxies/aggregators occasionally return a
            # 200 with an empty/null `choices` (safety filtering, upstream
            # rate-limiting, truncated responses, etc.) instead of raising.
            # Surface whatever diagnostic detail the response still carries
            # rather than crashing with an opaque 'NoneType' subscript error.
            raise RuntimeError(
                f'{self.model_id}: provider returned no choices in its response'
                f'{_describe_empty_response(resp)}'
            )
        choice = resp.choices[0]
        usage = resp.usage or type('U', (), {'prompt_tokens': 0, 'completion_tokens': 0})()

        # OpenRouter (and some other aggregators) report cache/cost detail under
        # usage.prompt_tokens_details / usage.cost — not part of the base OpenAI
        # response shape, so every access here is defensive (plain OpenAI/Ollama/
        # etc. simply won't have these attributes, and getattr falls through).
        details = getattr(usage, 'prompt_tokens_details', None)
        # Reasoning (ADR-119): Ollama and OpenRouter return the thinking as message.reasoning,
        # DeepSeek-style backends as reasoning_content; only its length is kept. OpenAI and
        # OpenRouter count reasoning tokens in completion_tokens_details; Ollama does not.
        reasoning = (getattr(choice.message, 'reasoning', None)
                     or getattr(choice.message, 'reasoning_content', None) or '')
        out_details = getattr(usage, 'completion_tokens_details', None)
        reasoning_tokens = getattr(out_details, 'reasoning_tokens', None)

        return GenerateResult(
            content=choice.message.content or '',
            model_used=resp.model or self.model_id,
            tokens_input=getattr(usage, 'prompt_tokens', 0),
            tokens_output=getattr(usage, 'completion_tokens', 0),
            latency_ms=latency,
            cached_tokens=getattr(details, 'cached_tokens', 0) or 0,
            cache_write_tokens=getattr(details, 'cache_write_tokens', 0) or 0,
            cost=getattr(usage, 'cost', None),
            reasoning_chars=len(reasoning) if isinstance(reasoning, str) else 0,
            reasoning_tokens=reasoning_tokens if isinstance(reasoning_tokens, int) else None,
        )

    def transcribe(self, audio_bytes: bytes, language: str = 'en',
                   model: str | None = None, params: dict | None = None,
                   speaker_turns: str | None = None) -> TranscribeResult:
        import io
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key or 'not-needed')
        model_id = model or self.model_id

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = 'audio.wav'

        t0 = time.monotonic()
        resp = client.audio.transcriptions.create(
            model=model_id,
            file=audio_file,
            language=language,
            # The model's extra parameters (ADR-151), e.g. {"prompt": "…"} for a Whisper server.
            **({'extra_body': dict(params)} if params else {}),
        )
        duration = time.monotonic() - t0

        text = resp.text if hasattr(resp, 'text') else str(resp)
        return TranscribeResult(
            text=text.strip(),
            language=language,
            duration_seconds=duration,
            model_used=model_id,
        )

    def health_check(self) -> bool:
        from openai import OpenAI
        client = OpenAI(base_url=self.base_url, api_key=self.api_key or 'not-needed')
        client.models.list()
        return True

    def list_models(self) -> list[dict]:
        """Return [{model_id, display_name}] from the /models endpoint."""
        try:
            from openai import OpenAI
            client = OpenAI(base_url=self.base_url, api_key=self.api_key or 'not-needed')
            return [{'model_id': m.id, 'display_name': m.id} for m in client.models.list().data]
        except Exception:
            return []
