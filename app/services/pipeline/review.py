"""Pre-send review — the pause between redaction and a cloud call (ADR-090).

InferenceNode, for a cloud provider, after redaction and the pre-send privacy
check (ADR-084), may stop and show the user the prompt exactly as it will be
sent:
  - always, when the user's "Review before sending" setting is on;
  - and whatever the setting, when the check found a blocking hit — tier 0
    (the patient's own identifier) or tier 1 (a named practitioner or the
    practice). There is no "send anyway": the user removes or rewords the hit.

The run's thread waits here; the page answers through
POST /pipeline/run/<run_id>/review. The server checks the prompt again before
it goes and refuses while a blocking hit remains — the browser's state is
never trusted. Redaction tokens may be deleted but not changed or invented,
so the reply still de-redacts.

Only pages that can show the review ask for it (metadata 'review.capable');
elsewhere the check stays recorded only, as in ADR-084.
"""
from __future__ import annotations

import re
import threading

from flask import current_app

BLOCKING_TIERS = (0, 1)
TIMEOUT_S = 480  # inside the SSE stream's 10-minute limit
TOKEN_RE = re.compile(r'\[Redacted [A-Za-z]+: [A-Z]+-[0-9a-f]+\]')
REMOVED_TEXT = '[Redacted]'

_REVIEWS: dict[str, dict] = {}
# Text removed at review, by run, for a chatbot to redact in its stored copy of
# the user's message (ADR-091). In memory only — never in the run record.
_REMOVED: dict[str, list[str]] = {}


def meta_for(user, capable: bool, remember_removed: bool = False) -> dict | None:
    """The run's review metadata, from the server's view of the user — never the page's."""
    if not capable:
        return None
    from app.services import user_settings_service as user_settings
    return {'capable': True, 'user_id': user.id, 'remember_removed': remember_removed,
            'always': bool(user_settings.get(user, 'ai.review_before_send'))}


def removed_segments(original: str, sent: str) -> list[str]:
    """The stretches of original that the review removed or reworded, in whole words.

    Compared word by word (not character by character, which would split
    "Dr Smithson" into fragments like "son" and garble other words later).
    """
    import difflib
    split = re.compile(r'\s+|\w+|[^\w\s]')
    a, b = split.findall(original), split.findall(sent)
    out = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, _j1, _j2 in sm.get_opcodes():
        if op in ('replace', 'delete'):
            seg = ''.join(a[i1:i2]).strip()
            if len(seg) >= 3 and re.search(r'\w', seg) and not TOKEN_RE.fullmatch(seg):
                out.append(seg)
    return out


def redact_segments(text: str, segments: list[str]) -> str:
    """Replace each segment, as whole words only, with [Redacted]."""
    for seg in sorted(set(segments), key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(seg) + r'(?!\w)', REMOVED_TEXT, text)
    return text


def pop_removed(run_id: str) -> list[str]:
    return _REMOVED.pop(run_id, [])


class ReviewCancelled(Exception):
    """The user cancelled at review, or didn't answer in time."""


def is_blocking(verdict: dict | None) -> bool:
    return bool(verdict) and 'error' not in verdict and verdict.get('top_tier') in BLOCKING_TIERS


def check(text: str, patient_id: int | None) -> dict:
    """The pre-send check on (possibly edited) text."""
    from app.services.checker.scan import scan
    return scan(text, patient_id)


def token_problem(original: str, edited: str) -> str | None:
    """A message if the edit changed or invented a redaction token, else None."""
    allowed = set(TOKEN_RE.findall(original))
    forged = [t for t in TOKEN_RE.findall(edited) if t not in allowed]
    if forged:
        return ('A redaction token was changed. Undo that edit — tokens can be deleted '
                'but not altered.')
    # A token cut part-way ("[Redacted Name: PT-12") would reach the AI half-hidden.
    for m in re.finditer(r'\[Redacted [A-Za-z]+:', edited):
        if not TOKEN_RE.match(edited, m.start()):
            return 'A redaction token was cut part-way. Delete it whole or undo the edit.'
    return None


def wait_for_decision(run_id: str, user_id: int | None, patient_id: int | None,
                      payload: dict) -> dict | None:
    """Push a 'review' event to the page and wait for its answer (None on timeout)."""
    from app.services.pipeline.engine import _RUN_QUEUES, _push
    entry = {'event': threading.Event(), 'decision': None,
             'user_id': user_id, 'patient_id': patient_id}
    _REVIEWS[run_id] = entry
    q = _RUN_QUEUES.get(run_id)
    if q is None:  # nobody is listening
        _REVIEWS.pop(run_id, None)
        return None
    _push(q, 'review', **payload)
    try:
        entry['event'].wait(TIMEOUT_S)
    finally:
        _REVIEWS.pop(run_id, None)
    return entry['decision']


def pending(run_id: str, user_id: int) -> dict | None:
    """The waiting review for this run, if it belongs to this user."""
    entry = _REVIEWS.get(run_id)
    if not entry or entry['user_id'] != user_id:
        return None
    return entry


def submit(run_id: str, user_id: int, decision: dict) -> bool:
    entry = pending(run_id, user_id)
    if not entry:
        return False
    entry['decision'] = decision
    entry['event'].set()
    return True


def run_review(context, ai_state: dict, always: bool) -> None:
    """Pause until the user sends a prompt with no blocking hit, or cancels.

    On send, ai_state['current_prompt'] becomes the reviewed prompt and the run
    records what happened; on cancel or timeout, raises ReviewCancelled.
    """
    import time
    original = ai_state['current_prompt']
    verdict = context.results.get('precheck') or {}
    reason = 'blocking hit' if is_blocking(verdict) else 'user setting'
    meta = context.metadata.get('review') or {}
    prompt, rounds, message = original, 0, ''
    t0 = time.monotonic()
    while True:
        rounds += 1
        decision = wait_for_decision(context.run_id, meta.get('user_id'), context.patient_id, {
            'prompt':        prompt,
            'system_prompt': ai_state.get('system_prompt') or '',
            'hits':          verdict.get('hits') or [],
            'top_tier':      verdict.get('top_tier'),
            'blocking':      is_blocking(verdict),
            'reason':        reason,
            'message':       message,
            'timeout_s':     TIMEOUT_S,
        })
        if not decision or decision.get('action') != 'send':
            context.results['review'] = {'paused': True, 'reason': reason, 'outcome':
                                         'timed out' if not decision else 'cancelled',
                                         'rounds': rounds}
            raise ReviewCancelled('Cancelled at review' if decision else 'No answer at review')
        prompt = decision.get('prompt') or ''
        message = token_problem(original, prompt) or ''
        if message:
            continue
        verdict = check(prompt, context.patient_id)
        if is_blocking(verdict):
            message = 'An identifier is still there. Remove it or reword it before sending.'
            continue
        break
    ai_state['current_prompt'] = prompt
    if meta.get('remember_removed') and prompt != original:
        _REMOVED[context.run_id] = removed_segments(original, prompt)
    context.results['precheck'] = verdict
    context.results.setdefault('prechecks', []).append(verdict)
    context.results['review'] = {
        'paused':  True,
        'reason':  reason,
        'outcome': 'sent',
        'edited':  prompt != original,
        'removed': max(0, prompt.count(REMOVED_TEXT) - original.count(REMOVED_TEXT)),
        'rounds':  rounds,
        'waited_ms': int((time.monotonic() - t0) * 1000),
    }
    current_app.logger.info('pre-send review: run=%s reason=%s edited=%s rounds=%d',
                            context.run_id, reason, prompt != original, rounds)
