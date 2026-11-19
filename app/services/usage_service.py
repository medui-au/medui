"""Usage recording — writes the permanent usage record (plans/usage_reporting_plan.md).

Best-effort throughout: a failure to record is logged and never affects the
task being recorded. Writes go through their own connection, so they neither
join nor disturb the request's or the pipeline's database transaction.

`run_rows()` turns a pipeline run into its usage rows and is shared by live
capture (the engine, when a run ends) and the one-off import of past runs, so
old and new runs are recorded identically.
"""
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.extensions import db

# BP GroupCode -> role, as for progress-note authors.
_ROLE_BY_GROUP = {3: 'Doctor', 4: 'Doctor', 42: 'Doctor', 28: 'Nurse practitioner',
                  5: 'Nurse', 6: 'Receptionist', 7: 'Receptionist', 1: 'Practice manager'}
_ROLE_TTL = 3600
_role_cache: tuple[dict[int, str], float] | None = None
_app_version: str | None = None

# Pipeline classifier -> where the run was started from.
_ORIGINS = (('[chatbot_generic_pii]', 'pii_erasure'), ('[chatbot_generic]', 'generic_chatbot'),
            ('[chatbot]', 'chatbot'), ('[ai_panel]', 'ai_panel'), ('[exp]', 'document_button'),
            ('[sum]', 'document_button'), ('[lib]', 'library'), ('[scribe]', 'scribe'),
            ('[data]', 'charts'), ('[recipe]', 'careplan_recipe'))


# ── Small helpers ───────────────────────────────────────────────────────────

def _tables():
    from app.models.usage import UsageAICall, UsageEvent
    return UsageEvent.__table__, UsageAICall.__table__


def app_version() -> str:
    """The running commit, so reports can be split by release."""
    global _app_version
    if _app_version is None:
        try:
            root = Path(__file__).resolve().parents[2]
            _app_version = subprocess.run(
                ['git', '-C', str(root), 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            _app_version = ''
    return _app_version


def role_of(user_id: int | None) -> str | None:
    """The user's role from their BP group, cached for an hour."""
    global _role_cache
    if not user_id:
        return None
    if not _role_cache or (time.monotonic() - _role_cache[1]) > _ROLE_TTL:
        _role_cache = (_load_roles(), time.monotonic())
    return _role_cache[0].get(user_id, 'Staff')


def _load_roles() -> dict[int, str]:
    from app.models.user import User
    from app.sql.query_loader import ReadOnlySession, load_query

    groups: dict[int, int] = {}
    conn_str = current_app.config.get('BPSDB_URI')
    if conn_str:
        try:
            with ReadOnlySession(conn_str) as session:
                groups = {r['user_id']: r['group_code']
                          for r in session.execute(load_query('usage_user_groups'))}
        except Exception as exc:  # BPSDB boundary: roles fall back to 'Staff'
            current_app.logger.warning('usage: BP user groups unavailable: %s', exc)
    return {u.id: _ROLE_BY_GROUP.get(groups.get(u.bpsdb_user_id), 'Staff')
            for u in User.query.all()}


def origin_of(classifier: str | None) -> str:
    text = (classifier or '').lower()
    return next((origin for tag, origin in _ORIGINS if tag in text), 'other')


def _write(event: dict, ai_calls: list[dict] | None = None) -> int | None:
    """Insert one event (and its AI calls); skip silently if its dedupe key exists."""
    events, calls = _tables()
    event.setdefault('app_version', app_version())
    with db.engine.begin() as conn:
        stmt = pg_insert(events).values(**event).returning(events.c.id)
        if event.get('dedupe_key'):
            stmt = stmt.on_conflict_do_nothing(index_elements=['dedupe_key'])
        event_id = conn.execute(stmt).scalar()
        if event_id and ai_calls:
            conn.execute(insert(calls), [dict(c, event_id=event_id) for c in ai_calls])
    return event_id


# ── Tasks (non-AI) ──────────────────────────────────────────────────────────

def record_task(task: str, area: str, *, user_id: int | None, patient_linked: bool,
                outcome: str = 'ok', duration_ms: int | None = None,
                workstation: str | None = None, detail: dict | None = None) -> None:
    """One task a person meant to do. Never raises."""
    try:
        _write({
            'occurred_at': datetime.now(timezone.utc), 'duration_ms': duration_ms,
            'user_id': user_id, 'actor_kind': 'user' if user_id else 'unspecified',
            'role_at_time': role_of(user_id), 'task': task, 'area': area, 'is_ai': False,
            'patient_linked': patient_linked, 'outcome': outcome,
            'detail_json': json.dumps(detail) if detail else None,
            'workstation': workstation, 'source': 'live', 'quality': 'exact',
        })
    except Exception as exc:  # broad by design: recording must never affect the task
        current_app.logger.warning('usage: could not record %s: %s', task, exc)


# ── AI pipeline runs ────────────────────────────────────────────────────────

def _privacy_verdict(check, is_local: bool | None) -> str | None:
    if isinstance(check, dict):
        if check.get('skipped'):
            return 'not_needed_local'
        if 'screening' in check:
            screening = check.get('screening') or {}
            return f"screening:{len(screening.get('matches') or screening.get('suspects') or {})}"
        tier = check.get('top_tier')
        return 'clear' if tier is None else f'tier:{tier}'
    return None if is_local else 'not_checked'


# Why a run failed, as a category — never the message itself, which can carry
# provider responses or other detail. Order matters: first match wins.
_FAILURE_RULES = (
    ('security_block', ('security block',)),
    ('interrupted', ('orphaned', 'interrupted', 'killed')),
    ('empty_response', ('returned no choices', 'empty response', 'no content')),
    ('model_unavailable', ('no endpoints available', 'model is overloaded', 'unavailable')),
    ('model_disabled', ('not found or disabled', 'no model selected')),
    ('too_large', ('max_tokens', 'reduce the length', 'context length', 'too long', 'too large')),
    ('authentication', ('authentication', 'unauthorized', 'api key', 'forbidden')),
    ('timeout', ('timeout', 'timed out')),
    ('connection', ('connection error', 'connection refused', 'connecterror', 'name resolution')),
    ('rate_limited', ('rate limit', 'too many requests')),
    ('internal_error', ('object is not subscriptable', 'is not defined', 'has no attribute',
                        'current_prompt is empty', 'keyerror', 'typeerror', 'valueerror')),
)


def _error_class(error: str | None) -> str | None:
    """The failure-reason category for an error message (see _FAILURE_RULES)."""
    if not error:
        return None
    lowered = error.lower()
    for code, needles in _FAILURE_RULES:
        if any(n in lowered for n in needles):
            return code
    return 'other'


def run_rows(run, source: str = 'live', workstation: str | None = None):
    """(event, ai_calls) for a finished pipeline run, or (None, []) if it is still running."""
    from app.models.ai_provider import AIModel
    from app.models.pipeline import Pipeline, RunStatus

    if run.status not in (RunStatus.completed, RunStatus.failed):
        return None, []
    pipeline = db.session.get(Pipeline, run.pipeline_id) if run.pipeline_id else None
    try:
        output = json.loads(run.output_json or '{}') or {}
    except ValueError:
        output = {}
    try:
        state = (json.loads(run.context_json or '{}') or {}).get('ai_state') or {}
    except ValueError:
        state = {}

    outcome = 'ok' if run.status == RunStatus.completed else (
        'blocked' if 'SECURITY BLOCK' in (run.error_message or '') else 'error')
    total_ms = (int((run.finished_at - run.started_at).total_seconds() * 1000)
                if run.finished_at and run.started_at else None)
    classifier = pipeline.classifier if pipeline else None
    event = {
        'occurred_at': run.started_at, 'duration_ms': total_ms,
        'user_id': run.initiated_by_id,
        'actor_kind': 'user' if run.initiated_by_id else 'system',
        'role_at_time': role_of(run.initiated_by_id),
        'task': 'ai.run', 'area': 'ai', 'is_ai': True,
        'patient_linked': bool(run.patient_id), 'outcome': outcome,
        'detail_json': json.dumps({'pipeline': pipeline.name if pipeline else None,
                                   'origin': origin_of(classifier)}),
        'workstation': workstation, 'source': source,
        'dedupe_key': f'run:{run.id}', 'quality': 'exact',
    }

    model_row = db.session.get(AIModel, int(state['model_id'])) if state.get('model_id') else None
    provider = model_row.provider if model_row else None
    common = {
        'pipeline_id': run.pipeline_id, 'pipeline_name': pipeline.name if pipeline else None,
        'pipeline_classifier': classifier, 'prompt_name': state.get('user_prompt_name'),
        'system_prompt_version': state.get('system_prompt_version'), 'origin': origin_of(classifier),
        'redaction_policy': run.redaction_policy.value if run.redaction_policy else None,
        'is_redacted': run.is_redacted, 'is_hcp_redacted': run.is_hcp_redacted,
        'total_ms': total_ms, 'error_class': _error_class(run.error_message),
        'pipeline_run_id': run.id, 'exported_after': False, 'quality': 'exact',
    }
    calls = []
    for response in output.get('ai_responses') or []:
        is_local = response.get('provider_is_local',
                                provider.is_local if provider else run.model_is_local)
        calls.append({
            'kind': 'inference',
            'provider_name': response.get('provider') or (provider.name if provider else None),
            'provider_is_local': is_local,
            'model': response.get('model_used'),
            'pipeline_id': run.pipeline_id,
            'pipeline_name': pipeline.name if pipeline else None,
            'pipeline_classifier': classifier,
            'prompt_name': state.get('user_prompt_name'),
            'system_prompt_version': state.get('system_prompt_version'),
            'origin': origin_of(classifier),
            'redaction_policy': run.redaction_policy.value if run.redaction_policy else None,
            'is_redacted': run.is_redacted, 'is_hcp_redacted': run.is_hcp_redacted,
            'tokens_in': response.get('tokens_input'), 'tokens_out': response.get('tokens_output'),
            'tokens_cached': response.get('cached_tokens'),
            'tokens_cache_write': response.get('cache_write_tokens'),
            'cost': response.get('cost'), 'model_ms': response.get('latency_ms'),
            'total_ms': total_ms,
            'prompt_chars': len(state.get('current_prompt') or ''),
            'response_chars': len(response.get('content') or ''),
            'privacy_verdict': _privacy_verdict(output.get('privacy_check'), is_local),
            'outcome': outcome, 'error_class': _error_class(run.error_message),
            'pipeline_run_id': run.id, 'exported_after': False, 'quality': 'exact',
        })
    if not calls and outcome != 'ok':
        # Failed before the model answered: record the call it was meant to
        # make, so failures show against the intended model and provider.
        calls.append(dict(common, kind='inference',
                          provider_name=provider.name if provider else None,
                          provider_is_local=provider.is_local if provider else run.model_is_local,
                          model=model_row.model_id if model_row else None,
                          prompt_chars=len(state.get('current_prompt') or '') or None,
                          outcome=outcome))
    return event, calls


def record_pipeline_run(run_db_id: int, workstation: str | None = None) -> None:
    """Called by the engine when a run ends. Never raises."""
    try:
        from app.models.pipeline import PipelineRun
        run = db.session.get(PipelineRun, run_db_id)
        if run:
            event, calls = run_rows(run, workstation=workstation)
            if event:
                _write(event, calls)
    except Exception as exc:  # broad by design: recording must never affect the run
        current_app.logger.warning('usage: could not record run %s: %s', run_db_id, exc)


def mark_run_output_used(pipeline_run_id: int | None) -> None:
    """The run's output was exported or sent — the AI output was used."""
    if not pipeline_run_id:
        return
    try:
        _, calls = _tables()
        with db.engine.begin() as conn:
            conn.execute(update(calls).where(calls.c.pipeline_run_id == int(pipeline_run_id))
                         .values(exported_after=True))
    except Exception as exc:  # broad by design
        current_app.logger.warning('usage: could not mark run %s used: %s', pipeline_run_id, exc)


# ── Scribe sessions: speech-to-text and speaker labelling, per session ─────────

def scribe_key(user_id: int | None, session_id: str) -> str:
    return f'scribe:{user_id or 0}:{session_id}'


def record_scribe_call(*, user_id: int | None, session_id: str, task: str, patient_linked: bool,
                       kind: str, model: str | None, provider_name: str | None,
                       provider_is_local: bool | None, model_ms: int | None = None,
                       chars: int = 0, tokens_in: int | None = None,
                       tokens_out: int | None = None, workstation: str | None = None) -> None:
    """Add one chunk's model call to its session: one row per model per session. Never raises."""
    if not session_id:
        return
    try:
        events, calls = _tables()
        key = scribe_key(user_id, session_id)
        now = datetime.now(timezone.utc)
        with db.engine.begin() as conn:
            event_id = conn.execute(select(events.c.id).where(events.c.dedupe_key == key)).scalar()
            if not event_id:
                event_id = conn.execute(
                    pg_insert(events).values(
                        occurred_at=now, user_id=user_id,
                        actor_kind='user' if user_id else 'unspecified',
                        role_at_time=role_of(user_id), task=task, area='ai', is_ai=True,
                        patient_linked=patient_linked, outcome='ok', workstation=workstation,
                        app_version=app_version(), source='live', dedupe_key=key, quality='exact')
                    .on_conflict_do_nothing(index_elements=['dedupe_key'])
                    .returning(events.c.id)).scalar() or conn.execute(
                    select(events.c.id).where(events.c.dedupe_key == key)).scalar()
            row = conn.execute(select(calls.c.id).where(
                calls.c.event_id == event_id, calls.c.kind == kind, calls.c.model == model)
                .with_for_update()).scalar()
            if row:
                conn.execute(update(calls).where(calls.c.id == row).values(
                    chunks=calls.c.chunks + 1,
                    model_ms=calls.c.model_ms + (model_ms or 0),
                    response_chars=calls.c.response_chars + (chars or 0),
                    tokens_in=calls.c.tokens_in + (tokens_in or 0),
                    tokens_out=calls.c.tokens_out + (tokens_out or 0)))
            else:
                conn.execute(insert(calls).values(
                    event_id=event_id, kind=kind, model=model, provider_name=provider_name,
                    provider_is_local=provider_is_local, origin='scribe', chunks=1,
                    model_ms=model_ms or 0, response_chars=chars or 0,
                    tokens_in=tokens_in or 0, tokens_out=tokens_out or 0,
                    outcome='ok', exported_after=False, quality='exact'))
            conn.execute(update(events).where(events.c.id == event_id).values(
                duration_ms=int((now - _aware(conn.execute(
                    select(events.c.occurred_at).where(events.c.id == event_id)).scalar()))
                    .total_seconds() * 1000)))
    except Exception as exc:  # broad by design: recording must never affect transcription
        current_app.logger.warning('usage: could not record scribe call: %s', exc)


def record_scribe_saved(*, user_id: int | None, session_id: str, char_count: int,
                        is_final: bool) -> None:
    """The transcript was saved: note its size and whether it was finalised. Never raises."""
    try:
        events, _ = _tables()
        with db.engine.begin() as conn:
            conn.execute(update(events).where(events.c.dedupe_key == scribe_key(user_id, session_id))
                         .values(detail_json=json.dumps({'chars': char_count, 'final': is_final})))
    except Exception as exc:  # broad by design
        current_app.logger.warning('usage: could not record scribe save: %s', exc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ── Export pseudonyms ───────────────────────────────────────────────────────

def ensure_labels() -> int:
    """Give every user who appears in the record a permanent number, in order of
    first appearance. Existing numbers are never changed. Returns how many were added."""
    from sqlalchemy import func
    from app.models.usage import UsageEvent, UsageUserLabel

    have = {row.user_id for row in UsageUserLabel.query.all()}
    first_seen = (db.session.query(UsageEvent.user_id, func.min(UsageEvent.occurred_at))
                  .filter(UsageEvent.user_id.isnot(None))
                  .group_by(UsageEvent.user_id).all())
    next_number = (db.session.query(func.max(UsageUserLabel.number)).scalar() or 0) + 1
    added = 0
    for user_id, _ in sorted(first_seen, key=lambda r: _aware(r[1])):
        if user_id in have:
            continue
        db.session.add(UsageUserLabel(user_id=user_id, number=next_number))
        next_number += 1
        added += 1
    db.session.commit()
    return added


def label_of(user_id: int | None) -> str:
    """Export label: the permanent number with the user's current role."""
    from app.models.usage import UsageUserLabel
    if not user_id:
        return 'Unspecified'
    row = db.session.get(UsageUserLabel, user_id)
    return f"{role_of(user_id) or 'Staff'} {row.number}" if row else 'Unlabelled'
