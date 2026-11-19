"""Extra request parameters for a model, with a per-step override (ADR-119).

A model can carry parameters MedUI does not name itself, such as
{"reasoning_effort": "none"} for a local reasoning model. They are set per model
(Setup → Models) and can be overridden on a pipeline's inference step, where a key
set to null removes the model's value for that step. They are not a privacy setting:
they never change redaction, the security wall or the pre-send check.
"""

from __future__ import annotations

import json

MAX_CHARS = 2000

# What MedUI sets itself, from its own fields; extra parameters cannot replace it.
RESERVED = frozenset({
    'model', 'messages', 'stream', 'stream_options', 'tools', 'tool_choice', 'functions',
    'temperature', 'max_tokens', 'max_completion_tokens', 'keep_alive', 'system', 'prompt',
})


# What MedUI sets itself on a transcription request (ADR-151): the model, the language,
# and Deepgram's speaker separation, which has its own setting because it changes how the
# reply is read (and Deepgram refuses diarize together with diarize_model).
ASR_RESERVED = frozenset({
    'model', 'language', 'diarize', 'diarize_model', 'diarize_version', 'utterances',
    'paragraphs', 'audio_file', 'file',
})


def for_asr(params: dict | None) -> dict:
    """A model's parameters as sent with a transcription request: MedUI's own keys left out,
    in case a model was marked ASR after its parameters were saved."""
    return {k: v for k, v in (params or {}).items()
            if k.lower() not in ASR_RESERVED and v is not None}


def parse(text: str | None, *, allow_null: bool = False, asr: bool = False) -> dict | None:
    """Check text typed into a parameters field; return the object, or None when blank.

    Raises ValueError with a message for the person editing. allow_null lets a step
    override remove a model's key by setting it to null. asr checks against the keys MedUI
    sets on a transcription request instead.
    """
    text = (text or '').strip()
    if not text:
        return None
    if len(text) > MAX_CHARS:
        raise ValueError(f'Extra request parameters are limited to {MAX_CHARS} characters')
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise ValueError(f'Extra request parameters are not valid JSON: {exc.msg}') from None
    return _check_object(value, allow_null, ASR_RESERVED if asr else RESERVED)


def check(value, *, allow_null: bool = False) -> dict | None:
    """Check an already-decoded value (a step's stored config); same rules as parse."""
    if isinstance(value, str):     # the editor sends what it could not read as JSON as text
        return parse(value, allow_null=allow_null)
    return _check_object(value, allow_null)


def _check_object(value, allow_null: bool, reserved_keys=RESERVED) -> dict | None:
    if value is None or value == {}:
        return None
    if not isinstance(value, dict):
        raise ValueError('Extra request parameters must be a JSON object, e.g. {"reasoning_effort": "none"}')
    reserved = sorted(k for k in value if k.lower() in reserved_keys)
    if reserved:
        raise ValueError('MedUI sets these itself, so they cannot be extra parameters: ' + ', '.join(reserved))
    if not allow_null and any(v is None for v in value.values()):
        raise ValueError('A model\'s parameters cannot be null (null is for a step removing a model\'s key)')
    return value


def load(text: str | None) -> dict:
    """A model's stored parameters, or {} when unset or unreadable (never raises)."""
    try:
        return parse(text) or {}
    except ValueError:
        return {}


def merged(model_params: dict | None, step_params: dict | None) -> dict:
    """The parameters sent: the model's, with the step's keys replacing them; null removes."""
    out = dict(model_params or {})
    for key, value in (step_params or {}).items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out
