"""Scope instructions — layer 1 of the AI scope guardrails (ADR-087).

Places a short boundary paragraph before the system prompt of every model
call made through a workflow, so the AI keeps to organising, summarising and
drafting from what was said or recorded (plans/TGA/05_ai_scope_guardrails.md).

Which wording applies, first match wins:
  1. the workflow's prompt step (step config 'scope_key');
  2. the system prompt's own scope_key;
  3. the practice default (Setup → AI scope, 'scope.default_key').
'none' at any level means no instruction. Nothing applies while the practice
switch 'scope.enabled' is off (the default).

Every wording ends with the same flag instruction, added here rather than kept
in each wording so an edited wording can't lose it. A reply that starts with
FLAG_TOKEN is flagged: the token is removed from the text and the flag recorded
on the run (results['scope']['model_flagged']).
"""
from __future__ import annotations

import re

from flask import current_app

from app.models.scope_wording import ScopeWording
from app.models.system_setting import SystemSetting

NONE = 'none'
FLAG_TOKEN = '[OUT OF SCOPE]'
_FLAG_RE = re.compile(re.escape(FLAG_TOKEN) + r'[ \t]*\n?')

# Only clinical requests about a particular patient are marked: "or opinion" alone made models
# flag (and refuse) harmless questions unrelated to medicine (2026-10-24).
FLAG_INSTRUCTION = (
    'If the request asks for a diagnosis, treatment, medicine, dose, prognosis or other clinical '
    'opinion about a particular patient that is not stated in the material provided, begin your '
    f'reply with the exact text {FLAG_TOKEN} on its own line. Then do only the part of the request '
    'that is within these limits, and say briefly what you have left out. A question that is not '
    "about a patient's care, including one unrelated to medicine, is not out of scope: answer it "
    'without this mark.'
)

# A second, separate mark: the request asked for help to do something unlawful. Never blocks;
# shown above the reply as a neutral line and recorded for the practice's oversight. Questions
# about the law, duties, reporting and ethics are left unmarked (2026-10-24, ADR-103).
LEGALITY_TOKEN = '[LEGALITY]'
_LEGALITY_RE = re.compile(re.escape(LEGALITY_TOKEN) + r'[ \t]*\n?')
LEGALITY_INSTRUCTION = (
    f'If the request asks for help to do something unlawful, begin your reply with {LEGALITY_TOKEN} '
    'on its own line, then answer within your usual limits. Do not use this mark for questions '
    'about the law, legal or medicolegal duties, mandatory reporting, ethics, the regulation of '
    "medicines (including medicinal cannabis), or a patient's conduct discussed for their care."
)
# What follows every scope wording, as sent and as shown in Setup → AI scope.
GUARDRAIL_INSTRUCTIONS = f'{FLAG_INSTRUCTION}\n{LEGALITY_INSTRUCTION}'

ENABLED_KEY = 'scope.enabled'
DEFAULT_KEY = 'scope.default_key'


# ── Practice settings ─────────────────────────────────────────────────────────

def is_enabled() -> bool:
    return bool(SystemSetting.get(ENABLED_KEY, False))


def practice_default_key() -> str:
    return SystemSetting.get(DEFAULT_KEY, 'record') or 'record'


def save_practice(enabled: bool, default_key: str) -> None:
    if default_key != NONE and not get_wording(default_key):
        raise ValueError(f'No scope wording {default_key!r}')
    SystemSetting.set(ENABLED_KEY, bool(enabled), description='Scope instructions on (ADR-087)')
    SystemSetting.set(DEFAULT_KEY, default_key,
                      description='Scope wording for system prompts without one (ADR-087)')


# ── Wordings ──────────────────────────────────────────────────────────────────

def wordings(kind: str = 'instruction') -> list[ScopeWording]:
    """Active wordings of one kind, one per key."""
    return (ScopeWording.query
            .filter_by(kind=kind, is_active=True)
            .order_by(ScopeWording.key)
            .all())


def get_wording(key: str, kind: str = 'instruction') -> ScopeWording | None:
    return ScopeWording.query.filter_by(kind=kind, key=key, is_active=True).first()


def edit_wording(key: str, label: str, text: str, user_id: int | None,
                 kind: str = 'instruction') -> ScopeWording:
    """Append-only, as for system prompts: deactivate the current version, insert version + 1."""
    from app.extensions import db
    current = get_wording(key, kind)
    if not current:
        raise ValueError(f'No {kind} wording {key!r}')
    text = (text or '').strip()
    if not text:
        raise ValueError('The wording cannot be empty')
    if text == current.text and (label or current.label) == current.label:
        return current
    current.is_active = False
    new = ScopeWording(kind=kind, key=key, label=(label or current.label).strip(),
                       text=text, version=current.version + 1, is_active=True,
                       created_by_id=user_id)
    db.session.add(new)
    db.session.commit()
    return new


def choices() -> list[tuple[str, str]]:
    """(key, label) for selects: every active wording, then 'none'."""
    return [(w.key, w.label) for w in wordings()] + [(NONE, 'None — no scope instruction')]


# ── Notices (layer 3, ADR-088) ────────────────────────────────────────────────
# The one-line notice shown above AI output (ADR-082), on screen only. Each page
# has a default notice; a workflow's inference step may choose another
# ('ai_notice'). Texts are 'notice' wordings, editable in Setup → AI scope.
# The built-in texts below are the fallback if a wording is missing.

NOTICES_ENABLED_KEY = 'notice.enabled'

BUILTIN_NOTICES = {
    'draft':        'AI draft — check it against the record before you file, send or act on it. '
                    'You remain responsible for what you use.',
    'chat_patient': 'Answers are drafted by AI from this patient’s record — check them against the '
                    'record before relying on them.',
    'chat_general': 'Answers are drafted by AI from general knowledge, not from a patient’s record — '
                    'check them before relying on them.',
}


def notices_enabled() -> bool:
    return bool(SystemSetting.get(NOTICES_ENABLED_KEY, True))


def notice_text(key: str | None) -> str:
    """Text of a notice, '' when notices are off."""
    if not notices_enabled():
        return ''
    key = key or 'draft'
    w = get_wording(key, 'notice')
    if w:
        return w.text
    return BUILTIN_NOTICES.get(key) or BUILTIN_NOTICES['draft']


def notice_choices() -> list[tuple[str, str]]:
    return [(w.key, w.label) for w in wordings('notice')]


def pipeline_notice_key(pipeline_id: int | None, page_default: str) -> str:
    """The notice a workflow chose on its inference step, else the page's default."""
    import json
    if not pipeline_id:
        return page_default
    from app.models.pipeline import PipelineStep
    for step in (PipelineStep.query.filter_by(pipeline_id=pipeline_id, node_type='inference')
                 .order_by(PipelineStep.step_order).all()):
        try:
            key = (json.loads(step.config_json or '{}').get('ai_notice') or '').strip()
        except ValueError:
            continue
        if key:
            return key
    return page_default


# ── Applying ──────────────────────────────────────────────────────────────────

def resolve_key(step_config: dict | None, system_prompt) -> tuple[str, str]:
    """(key, source) — source is 'step', 'system_prompt' or 'practice'."""
    step_key = ((step_config or {}).get('scope_key') or '').strip()
    if step_key:
        return step_key, 'step'
    sp_key = (getattr(system_prompt, 'scope_key', None) or '').strip()
    if sp_key:
        return sp_key, 'system_prompt'
    return practice_default_key(), 'practice'


def build_system_prompt(system_prompt_text: str, step_config: dict | None,
                        system_prompt) -> tuple[str, dict]:
    """The system prompt as sent, and the scope record for the run.

    The record always says whether a scope instruction applied and, if so,
    which wording and version, so any output can be traced to its boundary.
    """
    if not is_enabled():
        return system_prompt_text, {'enabled': False, 'applied': False}
    key, source = resolve_key(step_config, system_prompt)
    info = {'enabled': True, 'key': key, 'source': source, 'applied': False}
    if key == NONE:
        return system_prompt_text, info
    wording = get_wording(key)
    if not wording:
        # A step or prompt naming a wording that no longer exists: say so on
        # the run rather than silently sending a different boundary.
        current_app.logger.warning('scope: no active wording %r (source %s)', key, source)
        info['missing'] = True
        return system_prompt_text, info
    block = (f'## Scope of this software\n{wording.text}\n{GUARDRAIL_INSTRUCTIONS}')
    text = f'{block}\n\n---\n\n{system_prompt_text}' if system_prompt_text else block
    info.update(applied=True, version=wording.version, label=wording.label)
    return text, info


def detect_legality(content: str) -> tuple[str, bool]:
    """Remove the legality token from a reply; True if it was there."""
    if not content or LEGALITY_TOKEN not in content:
        return content, False
    return _LEGALITY_RE.sub('', content).lstrip('\n'), True


def detect_flag(content: str) -> tuple[str, bool]:
    """Remove the out-of-scope token from a reply; True if it was there."""
    if not content or FLAG_TOKEN not in content:
        return content, False
    return _FLAG_RE.sub('', content).lstrip('\n'), True
