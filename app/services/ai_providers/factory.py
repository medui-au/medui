"""Provider factory — instantiates the correct BaseProvider subclass from an AIProviderConfig."""

from __future__ import annotations
from .base import BaseProvider


def get_provider(config, model_id: str) -> BaseProvider:
    """Instantiate a provider from an AIProviderConfig ORM object + a model_id string.

    Sets is_cloud = not config.is_local so the security pre-check has an authoritative source.
    """
    from flask import current_app
    if not current_app.config.get('AI_ENABLED', False):
        raise RuntimeError('AI features are disabled. Enable AI_ENABLED after configuring a provider.')
    ptype = (config.provider_type or 'openai_compatible').lower()
    api_key = config.api_key   # decrypted via the property
    base_url = config.base_url

    if ptype == 'anthropic':
        from .anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(model_id=model_id, api_key=api_key, base_url=base_url)
    elif ptype == 'asr_whisper':
        from .asr import WhisperProvider
        provider = WhisperProvider(model_id=model_id, api_key=api_key, base_url=base_url)
    elif ptype == 'asr_deepgram':
        from .asr import DeepgramProvider
        provider = DeepgramProvider(model_id=model_id, api_key=api_key, base_url=base_url)
    else:
        # Default: OpenAI-compatible (covers Ollama, OpenAI, OpenRouter, Groq, DeepSeek…)
        from .openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(model_id=model_id, api_key=api_key, base_url=base_url)

    # is_cloud is the authoritative locality flag — set from DB, not from provider class default
    provider.is_cloud = not config.is_local
    return provider
