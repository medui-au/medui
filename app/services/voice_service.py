"""VoiceService — Stage 1 per-chunk audio processing.

Per-chunk pipeline:
  audio bytes → ASR transcription → LLM speaker diarization → labelled text

Diarization uses the UserPrompt named 'LLM Diarize transcript'.  If that
prompt is absent the raw ASR text is returned as-is (graceful degradation).

The diarization LLM call bypasses the redaction wall intentionally: the chunk
contains only live audio captured in the room — no EHR data — so it is treated
as cloud-safe by the clinician's choice to record.  See legacy ADR rationale.
"""
from __future__ import annotations
from flask import current_app

DIARIZE_PROMPT_NAME = 'LLM Diarize transcript'


def _diarization_model_is_local(diarize_prompt) -> bool:
    """True when diarization will run on a local provider.

    Fails closed: an unresolvable model counts as not local. The override
    exists so a practice can make a documented decision, not so the check can
    be skipped by accident.
    """
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting

    if SystemSetting.get('voice.allow_cloud_diarization', False):
        current_app.logger.warning(
            'VoiceService: cloud diarization is explicitly permitted — raw '
            'consultation transcripts may leave the practice unredacted.')
        return True

    model_id = getattr(diarize_prompt, 'default_model_id', None)
    if not model_id:
        # No model pinned means the system default, which may be a cloud model.
        return False

    model = AIModel.query.filter_by(id=model_id).first()
    return bool(model and model.provider and model.provider.is_local)


def _labelling_prompt():
    """The active 'LLM Diarize transcript' prompt, or None."""
    from app.models.prompt import UserPrompt
    return UserPrompt.query.filter_by(name=DIARIZE_PROMPT_NAME, is_active=True).first()


def speaker_label_status(asr_model) -> dict:
    """How a Scribe chunk transcribed by asr_model gets its speakers (ADR-151).

    Returns {'kind': 'turns'|'local'|'none', 'text': a line for the Scribe page}. Mirrors
    process_chunk: Deepgram's speaker turns when switched on for the model, else the local
    labelling step when its prompt is set to a local model, else none (and why).
    """
    from app.services.ai_providers.asr import DEEPGRAM_SPEAKER_VERSIONS
    provider = getattr(asr_model, 'provider', None)
    if (getattr(asr_model, 'speaker_turns', None) in DEEPGRAM_SPEAKER_VERSIONS
            and provider is not None and provider.provider_type == 'asr_deepgram'):
        return {'kind': 'turns',
                'text': f'Speaker turns: from Deepgram ({asr_model.speaker_turns})'}
    prompt = _labelling_prompt()
    if prompt is None:
        return {'kind': 'none',
                'text': f'No speaker labels: the "{DIARIZE_PROMPT_NAME}" prompt is missing '
                        'or switched off'}
    if not _diarization_model_is_local(prompt):
        return {'kind': 'none',
                'text': f'No speaker labels: "{DIARIZE_PROMPT_NAME}" has no local model '
                        'set (Prompt Manager)'}
    return {'kind': 'local', 'text': 'Speaker labels: local model'}


class VoiceService:

    @staticmethod
    def resolve_asr_model(model_id: int | None = None):
        """The ASR model a chunk will use: the caller's choice, else the practice
        default (SystemSetting 'active_asr_model_id'), else the first enabled.

        Also used by the chunk routes to tell the page which model transcribed
        each chunk, so a saved transcript can record it.

        Raises:
            ValueError: No ASR model is available or enabled.
        """
        from app.models.ai_provider import AIModel

        model = None
        if model_id:
            model = AIModel.query.filter_by(id=model_id, is_asr=True, is_enabled=True).first()

        if model is None:
            from app.models.system_setting import SystemSetting
            configured_id = SystemSetting.get('active_asr_model_id')
            if configured_id:
                model = AIModel.query.filter_by(id=int(configured_id), is_asr=True, is_enabled=True).first()

        if model is None:
            model = AIModel.query.filter_by(is_asr=True, is_enabled=True).first()

        if model is None:
            raise ValueError(
                "No ASR model is configured. "
                "Add a Whisper or Deepgram provider in Setup → AI Providers, "
                "then select it on the Scribe page."
            )
        return model

    @staticmethod
    def process_chunk(
        audio_bytes: bytes,
        patient_id: int,
        model_id: int | None = None,
        diarize: bool = True,
        usage_hook=None,
    ) -> str:
        """Transcribe a WAV chunk and optionally apply speaker diarization.

        Steps:
          1. Resolve ASR model (explicit id → first enabled ASR model)
          2. Call provider.transcribe() → raw_text, with the model's extra parameters and,
             when diarize=True and the model has speaker turns on, Deepgram's speakers
          3. Silent-chunk guard → return ''
          4. If diarize=True: return the service's speaker turns as they are (ADR-151);
             otherwise look up UserPrompt named DIARIZE_PROMPT_NAME; skip if absent
          5. Run PromptAssemblyNode + InferenceNode on raw_text
          6. Return labelled segment (or raw_text on diarization failure)

        Args:
            audio_bytes: Raw WAV data from the browser AudioWorklet.
            patient_id:  BPSDB InternalId — used for logging only.
            model_id:    AIModel.id (ASR) to use; falls back to first enabled.
            diarize:     If False, skip the LLM diarization step and return raw ASR text.
                         Set False for single-speaker dictation (no [DOCTOR]/[PATIENT] labels).

        Returns:
            Speaker-labelled text, raw text, or '' for a silent chunk.

        Raises:
            ValueError: No ASR model is available or enabled.
            RuntimeError: ASR provider call failed.
        """
        from app.services.ai_providers.factory import get_provider

        # ── 1. Resolve ASR model ──────────────────────────────────────────────
        model = VoiceService.resolve_asr_model(model_id)

        # ── 2. Transcribe ─────────────────────────────────────────────────────
        try:
            provider = get_provider(model.provider, model.model_id)
        except Exception as exc:
            raise RuntimeError(f"Could not build ASR provider: {exc}") from exc

        from app.services import request_params
        params = request_params.for_asr(request_params.load(model.request_params))
        # Speaker turns from the service itself (ADR-151): only where speakers are wanted.
        turns_version = getattr(model, 'speaker_turns', None) if diarize else None

        import time as _time
        asr_t0 = _time.monotonic()
        try:
            result = provider.transcribe(audio_bytes, language='en', model=model.model_id,
                                         params=params or None, speaker_turns=turns_version)
        except Exception as exc:
            exc_str = str(exc)
            # faster-whisper-server crashes with "list index out of range" when a chunk
            # contains no detectable speech segments.  Treat this as a silent chunk so
            # the session continues uninterrupted rather than erroring the browser.
            if 'list index out of range' in exc_str:
                current_app.logger.warning(
                    'VoiceService: WhisperX no-speech chunk for patient %s (treating as silent)',
                    patient_id,
                )
                return ''
            current_app.logger.error(
                'VoiceService: ASR failed for patient %s model %s: %s',
                patient_id, model.model_id, exc,
            )
            raise RuntimeError(f"ASR transcription failed: {exc}") from exc

        raw_text = (result.text if hasattr(result, 'text') else str(result)).strip()
        # Usage record (plans/usage_reporting_plan.md): the caller aggregates per session.
        _usage(usage_hook, kind='speech_to_text', model=model.model_id,
               provider_name=model.provider.name if model.provider else None,
               provider_is_local=bool(model.provider and model.provider.is_local),
               model_ms=int((_time.monotonic() - asr_t0) * 1000), chars=len(raw_text))

        # ── 3. Silent-chunk guard ─────────────────────────────────────────────
        if not raw_text:
            current_app.logger.debug('VoiceService: silent chunk for patient %s', patient_id)
            return ''

        current_app.logger.info(
            'VoiceService: transcribed %d chars for patient %s via %s',
            len(raw_text), patient_id, model.model_id,
        )

        # ── 4. Resolve diarization prompt ─────────────────────────────────────
        if not diarize:
            return raw_text

        # The service already split the chunk into speaker turns (ADR-151): the local step
        # would only guess doctor and patient again, so it is skipped.
        if getattr(result, 'speaker_turns', False):
            current_app.logger.info(
                'VoiceService: speaker turns from %s for patient %s; local labelling skipped',
                model.model_id, patient_id)
            return raw_text
        if turns_version:
            current_app.logger.warning(
                'VoiceService: %s was asked for speaker turns but returned none for patient '
                '%s; using the local labelling step', model.model_id, patient_id)

        diarize_prompt = _labelling_prompt()

        if not diarize_prompt:
            current_app.logger.warning(
                "VoiceService: UserPrompt '%s' not found — returning raw ASR text.",
                DIARIZE_PROMPT_NAME,
            )
            return raw_text

        # ── 5. Diarization LLM call ───────────────────────────────────────────
        # This path does NOT go through PipelineEngine: there is no run record,
        # no DataAssemblyNode and no vault, so nothing is redacted and nothing
        # is audited. A consultation transcript is identified health
        # information — names, dates of birth and history said out loud — so
        # the model must be local. Checked here rather than assumed from
        # configuration (ADR-027).
        if not _diarization_model_is_local(diarize_prompt):
            current_app.logger.error(
                'VoiceService: diarization model is not local — returning raw ASR '
                'text for patient %s. Point "%s" at a local model in Prompt '
                'Manager, or set voice.allow_cloud_diarization if this is '
                'deliberate and documented.',
                patient_id, DIARIZE_PROMPT_NAME,
            )
            return raw_text

        try:
            from app.services.pipeline.context import WorkflowContext
            from app.services.pipeline.nodes.prompt_assembly import PromptAssemblyNode
            from app.services.pipeline.nodes.inference import InferenceNode

            import uuid
            context = WorkflowContext(
                run_id=f'diarize-{uuid.uuid4().hex[:12]}',
                patient_id=patient_id,
                metadata={'source': 'voice_service'},
                input={'raw_transcript': raw_text},
            )
            # Deliberately not setting is_redacted: nothing here is redacted,
            # and claiming otherwise would misreport the run (ADR-005).

            config = {'user_prompt_id': diarize_prompt.id}
            if diarize_prompt.default_model_id:
                config['model_id'] = diarize_prompt.default_model_id

            context = PromptAssemblyNode().execute(context, config)
            context = InferenceNode().execute(context, config)

        except Exception as exc:
            current_app.logger.error(
                'VoiceService: diarization failed for patient %s: %s', patient_id, exc,
            )
            return raw_text  # degrade gracefully — raw text beats an error

        responses = context.results.get('ai_responses') or []
        if responses:
            last = responses[-1]
            _usage(usage_hook, kind='diarization', model=last.get('model_used'),
                   provider_name=last.get('provider'),
                   provider_is_local=last.get('provider_is_local'),
                   model_ms=last.get('latency_ms'),
                   chars=len(context.results.get('final_output') or ''),
                   tokens_in=last.get('tokens_input'), tokens_out=last.get('tokens_output'))

        # ── 6. Return labelled segment ────────────────────────────────────────
        return context.results.get('final_output') or raw_text


def _usage(hook, **call) -> None:
    """Report one model call to the caller's usage hook; never affects transcription."""
    if hook is None:
        return
    try:
        hook(**call)
    except Exception as exc:  # broad by design: the usage record is best-effort
        current_app.logger.warning('VoiceService: usage hook failed: %s', exc)

