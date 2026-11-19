"""Anthropic native provider using the anthropic SDK."""

from __future__ import annotations
import time
from .base import BaseProvider, GenerateResult


class AnthropicProvider(BaseProvider):
    is_cloud: bool = True   # Anthropic is always cloud

    def generate(self, prompt: str, system_prompt: str | None = None,
                 temperature: float | None = None,
                 max_tokens: int | None = None,
                 **kwargs) -> GenerateResult:
        # Extra request parameters (ADR-119) are not sent to Anthropic's own API yet.
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        create_kwargs: dict = {
            'model':      self.model_id,
            'max_tokens': max_tokens or 2048,
            'messages':   [{'role': 'user', 'content': prompt}],
        }
        if system_prompt:
            create_kwargs['system'] = system_prompt
        if temperature is not None:
            create_kwargs['temperature'] = temperature

        t0 = time.monotonic()
        resp = client.messages.create(**create_kwargs)
        latency = int((time.monotonic() - t0) * 1000)

        content = next((b.text for b in (resp.content or []) if getattr(b, 'type', 'text') == 'text'), '')
        reasoning_chars = sum(len(getattr(b, 'thinking', '') or '') for b in (resp.content or [])
                              if getattr(b, 'type', '') == 'thinking')
        return GenerateResult(
            content=content,
            model_used=resp.model or self.model_id,
            tokens_input=resp.usage.input_tokens,
            tokens_output=resp.usage.output_tokens,
            latency_ms=latency,
            reasoning_chars=reasoning_chars,
        )

    def health_check(self) -> bool:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            client.models.list()
            return True
        except Exception:
            return False
