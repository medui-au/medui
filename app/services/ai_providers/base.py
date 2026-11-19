"""Base provider interface and result types for all AI providers."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GenerateResult:
    content: str
    model_used: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    cached_tokens: int = 0        # portion of tokens_input served from provider-side cache
    cache_write_tokens: int = 0   # portion of tokens_input newly written to cache this call
    cost: float | None = None     # USD, when the provider reports it (e.g. OpenRouter); None otherwise
    # How much the model reasoned before replying (ADR-119): the length of its reasoning text,
    # which is not kept, and the provider's reasoning-token count where it reports one.
    reasoning_chars: int = 0
    reasoning_tokens: int | None = None


@dataclass
class TranscribeResult:
    text: str
    language: str = 'en'
    duration_seconds: float = 0.0
    model_used: str = ''
    # True when the service itself split the text into speaker turns (Deepgram's
    # speaker separation, ADR-151); the local labelling step is then skipped.
    speaker_turns: bool = False


class BaseProvider(ABC):
    """Abstract base for all AI providers (LLM and ASR)."""

    is_cloud: bool = True   # False for local providers; controls the redaction wall
    is_asr: bool = False    # True for Whisper/Deepgram; generate() raises NotImplementedError

    def __init__(self, model_id: str, api_key: str | None = None,
                 base_url: str | None = None, **kwargs):
        self.model_id = model_id
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None,
                 temperature: float | None = None,
                 max_tokens: int | None = None,
                 **kwargs) -> GenerateResult: ...

    def transcribe(self, audio_bytes: bytes, language: str = 'en',
                   model: str | None = None, params: dict | None = None,
                   speaker_turns: str | None = None) -> TranscribeResult:
        """params: the model's extra request parameters (ADR-119/151), already checked.
        speaker_turns: a speaker-separation version to ask for, where the service has one."""
        raise NotImplementedError(f'{self.__class__.__name__} does not support transcription')

    @abstractmethod
    def health_check(self) -> bool: ...
