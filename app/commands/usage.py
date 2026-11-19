"""flask usage … — the permanent usage record (plans/usage_reporting_plan.md).

`import-history` is the one-off intake of the past. It is safe to re-run: every
row carries a dedupe key, and rows already present — from an earlier import or
from live recording — are skipped. Output is counts only.
"""
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import click
from flask import current_app
from flask.cli import AppGroup

from app.extensions import db

usage_cli = AppGroup('usage', help='The permanent usage record.')

_ACCESS_RE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d{3}) ')
_ASR_LOG_RE = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+\] INFO in voice_service: '
                         r'VoiceService: transcribed (\d+) chars for patient (\d+) via (\S+)')
_LOCAL_TZ = datetime.now().astimezone().tzinfo

# Tasks the import takes exactly from their own tables. The access log would
# count them a second time (unattributed), so it skips them.
_EXACT_ELSEWHERE = frozenset({
    'medmap.approve', 'message.send', 'message.revoke', 'library.create', 'chatbot.file',
    'governance.complaint_create', 'governance.complaint_step',
    'governance.adverse_event_create', 'governance.adverse_event_step',
})
_EXACT_ENDPOINTS = frozenset({'clinical_comms.api_export_pit'})      # message exports
_EXACT_ADMIN_PREFIX = 'prompt_manager.system_'                        # system prompt versions


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _event(task, area, *, when, user_id, source, key, patient_linked=False, detail=None,
           outcome='ok', quality='exact', duration_ms=None, workstation=None, is_ai=False):
    from app.services.usage_service import role_of
    return {
        'occurred_at': _naive_utc(when), 'duration_ms': duration_ms, 'user_id': user_id,
        'actor_kind': 'user' if user_id else 'unspecified', 'role_at_time': role_of(user_id),
        'task': task, 'area': area, 'is_ai': is_ai, 'patient_linked': bool(patient_linked),
        'outcome': outcome, 'detail_json': json.dumps(detail) if detail else None,
        'workstation': workstation, 'app_version': None, 'source': f'import:{source}',
        'dedupe_key': key, 'quality': quality,
    }


def _insert(rows: list[dict]) -> int:
    """Bulk insert events, skipping existing dedupe keys. Returns rows added."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.usage import UsageEvent
    if not rows:
        return 0
    added = 0
    with db.engine.begin() as conn:
        for start in range(0, len(rows), 1000):
            result = conn.execute(pg_insert(UsageEvent.__table__)
                                  .values(rows[start:start + 1000])
                                  .on_conflict_do_nothing(index_elements=['dedupe_key']))
            added += result.rowcount or 0
    return added


@usage_cli.command('import-history')
@click.option('--access-log', 'access_log', default=None,
              help='Web server access log to import unattributed tasks from '
                   '(default: none). Only lines before live recording began are used.')
@click.option('--app-log', 'app_log', default=None,
              help="MedUI's own log, for the speech-to-text model of past scribe sessions.")
@click.option('--refresh-failed', is_flag=True, default=False,
              help='Re-derive the usage rows of failed runs from their run records (adds the '
                   'intended model and the failure reason). Keeps each row\'s source and workstation.')
def import_history(access_log: str | None, app_log: str | None, refresh_failed: bool) -> None:
    """One-off intake of past usage into the permanent record (repeatable)."""
    from app.services import usage_service
    counts: dict[str, int] = {}

    if refresh_failed:
        counts['failed runs re-derived'] = _refresh_failed_runs()

    counts['AI runs (pipeline_runs)'] = _import_runs()
    counts['scribe sessions (transcripts)'] = _import_transcripts()
    counts['chatbot sessions / files'] = _import_simple_chat()
    counts['patient messages (send / revoke / export)'] = _import_messages()
    counts['library, medication mappings, prompt versions'] = _import_other()
    counts['governance steps'] = _import_governance()
    if app_log:
        counts['speech-to-text models from the app log (inferred)'] = _import_asr_log(app_log)
    if access_log:
        counts['tasks from the access log (unattributed)'] = _import_access_log(access_log)
    labels = usage_service.ensure_labels()

    for name, n in counts.items():
        click.echo(f'{n:8,}  {name}')
    click.echo(f'{labels:8,}  new user labels')


def _import_runs() -> int:
    from app.models.pipeline import PipelineRun
    from app.services.usage_service import _write, run_rows
    added = 0
    for run in PipelineRun.query.order_by(PipelineRun.id).yield_per(200):
        event, calls = run_rows(run, source='import:pipeline_runs')
        if event and _write(event, calls):
            added += 1
    return added


def _refresh_failed_runs() -> int:
    """Replace the usage rows of failed runs with ones carrying model and reason.

    Only possible while the run records still exist (they are purgeable).
    """
    from sqlalchemy import select
    from app.models.pipeline import PipelineRun, RunStatus
    from app.models.usage import UsageEvent
    from app.services.usage_service import _write, run_rows

    events = UsageEvent.__table__
    done = 0
    for run in PipelineRun.query.filter(PipelineRun.status == RunStatus.failed).all():
        key = f'run:{run.id}'
        with db.engine.begin() as conn:
            old = conn.execute(select(events.c.source, events.c.workstation)
                               .where(events.c.dedupe_key == key)).first()
            conn.execute(events.delete().where(events.c.dedupe_key == key))
        event, calls = run_rows(run, source=old[0] if old else 'import:pipeline_runs',
                                workstation=old[1] if old else None)
        if event and _write(event, calls):
            done += 1
    return done


def _import_transcripts() -> int:
    """Scribe sessions, with their speech-to-text models where the transcript recorded them."""
    from sqlalchemy import insert, select
    from app.models.ai_provider import AIModel
    from app.models.consultation_transcript import ConsultationTranscript
    from app.models.usage import UsageAICall, UsageEvent
    from app.services.usage_service import scribe_key

    providers = {m.model_id: m.provider for m in AIModel.query.filter_by(is_asr=True).all()}
    added = 0
    for t in ConsultationTranscript.query.order_by(ConsultationTranscript.id).all():
        try:
            extra = json.loads(t.extra_data_json or '{}') or {}
        except ValueError:
            extra = {}
        key = scribe_key(t.user_id, t.session_id or f'transcript-{t.id}')
        duration = (int((t.updated_at - t.created_at).total_seconds() * 1000)
                    if t.updated_at and t.created_at else None)
        n = _insert([_event('scribe.session', 'ai', when=t.created_at, user_id=t.user_id,
                            source='consultation_transcripts', key=key, patient_linked=True,
                            is_ai=True, duration_ms=duration,
                            detail={'chars': extra.get('char_count'), 'final': t.is_final})])
        added += n
        tally = extra.get('asr_models') or {}
        if n and isinstance(tally, dict) and tally:
            with db.engine.begin() as conn:
                event_id = conn.execute(select(UsageEvent.__table__.c.id)
                                        .where(UsageEvent.__table__.c.dedupe_key == key)).scalar()
                conn.execute(insert(UsageAICall.__table__), [{
                    'event_id': event_id, 'kind': 'speech_to_text', 'model': model,
                    'provider_name': providers[model].name if providers.get(model) else None,
                    'provider_is_local': (providers[model].is_local if providers.get(model)
                                          else (extra.get('asr_local') or {}).get(model)),
                    'origin': 'scribe', 'chunks': int(count), 'outcome': 'ok',
                    'exported_after': False, 'quality': 'exact'} for model, count in tally.items()])
    return added


def _import_simple_chat() -> int:
    from app.models.chat import ChatGeneratedFile, ChatSession
    rows = [_event('chatbot.session_start', 'communication', when=s.created_at,
                   user_id=s.user_id, source='chat_sessions', key=f'chat:{s.id}',
                   patient_linked=s.patient_id) for s in ChatSession.query.all()]
    rows += [_event('chatbot.file', 'communication', when=f.created_at,
                    user_id=f.created_by_id, source='chat_generated_files',
                    key=f'chatfile:{f.id}') for f in ChatGeneratedFile.query.all()]
    return _insert(rows)


def _import_messages() -> int:
    from app.models.patient_message import PatientMessage
    rows = []
    for m in PatientMessage.query.all():
        channel = getattr(m.channel, 'value', m.channel)
        rows.append(_event('message.send', 'communication', when=m.created_at,
                           user_id=m.created_by_id, source='patient_messages', key=f'msg:{m.id}',
                           patient_linked=m.patient_id,
                           detail={'channel': channel, 'ai_generated': bool(m.is_ai_generated)},
                           outcome='ok' if not m.error_message else 'error'))
        if m.revoked_at:
            rows.append(_event('message.revoke', 'communication', when=m.revoked_at,
                               user_id=m.revoked_by_id, source='patient_messages',
                               key=f'msgrevoke:{m.id}', patient_linked=m.patient_id))
        if m.bp_exported and m.bp_exported_at:
            # Who exported is not stored; the sender is the likely exporter.
            rows.append(_event('export.pit', 'export', when=m.bp_exported_at,
                               user_id=m.created_by_id, source='patient_messages',
                               key=f'msgexport:{m.id}', patient_linked=m.patient_id,
                               detail={'from': 'message'}, quality='inferred'))
    return _insert(rows)


def _import_other() -> int:
    from app.models.document import Document
    from app.models.drug_mapping import DrugMapping
    from app.models.prompt import SystemPrompt
    rows = [_event('library.create', 'communication', when=d.created_at, user_id=d.created_by_id,
                   source='documents', key=f'doc:{d.id}', patient_linked=d.patient_id)
            for d in Document.query.all()]
    rows += [_event('medmap.approve', 'clinical', when=m.approved_at, user_id=m.approved_by_id,
                    source='drug_mappings', key=f'medmap:{m.id}')
             for m in DrugMapping.query.filter(DrugMapping.approved_at.isnot(None)).all()]
    rows += [_event('admin.change', 'administration', when=p.created_at, user_id=p.created_by_id,
                    source='system_prompts', key=f'sysprompt:{p.id}',
                    detail={'endpoint': 'system_prompt.new_version'})
             for p in SystemPrompt.query.all()]
    return _insert(rows)


def _import_governance() -> int:
    from app.models.adverse_event import AdverseEvent
    from app.models.complaint import Complaint
    stages = {
        Complaint: ('complaint', [('create', 'received_by_id', 'received_at'),
                                  ('step', 'open_disclosure_by_id', 'open_disclosure_completed_at'),
                                  ('step', 'closed_by_id', 'closed_at'),
                                  ('step', 'voided_by_id', 'voided_at')]),
        AdverseEvent: ('adverse_event', [('create', 'reported_by_id', 'reported_at'),
                                         ('step', 'triaged_by_id', 'triaged_at'),
                                         ('step', 'rca_completed_by_id', 'rca_completed_at'),
                                         ('step', 'open_disclosure_by_id', 'open_disclosure_completed_at'),
                                         ('step', 'closed_by_id', 'closed_at'),
                                         ('step', 'voided_by_id', 'voided_at')]),
    }
    rows = []
    for model, (name, steps) in stages.items():
        for record in model.query.all():
            for kind, by, at in steps:
                when = getattr(record, at, None)
                if when:
                    rows.append(_event(f'governance.{name}_{kind}', 'governance', when=when,
                                       user_id=getattr(record, by, None),
                                       source=model.__tablename__,
                                       key=f'{name}:{record.id}:{at}',
                                       patient_linked=getattr(record, 'patient_id', None)))
    return _insert(rows)


def _import_asr_log(path: str) -> int:
    """Speech-to-text model per chunk from MedUI's log, matched to scribe sessions.

    The log names the patient and time, not the user or session, so each chunk
    is matched to the transcript of the same patient whose session spans it.
    Only sessions with no model recorded get these rows, marked 'inferred'.
    """
    from sqlalchemy import insert, select
    from app.models.ai_provider import AIModel
    from app.models.consultation_transcript import ConsultationTranscript
    from app.models.usage import UsageAICall, UsageEvent
    from app.services.usage_service import scribe_key

    by_patient = defaultdict(list)
    for t in ConsultationTranscript.query.all():
        extra = {}
        try:
            extra = json.loads(t.extra_data_json or '{}') or {}
        except ValueError:
            pass
        if extra.get('asr_models') or not t.created_at:
            continue
        by_patient[t.patient_id].append(t)

    tally = defaultdict(lambda: [0, 0])          # (transcript id, model) -> [chunks, chars]
    with open(path, errors='ignore') as handle:
        for line in handle:
            m = _ASR_LOG_RE.match(line)
            if not m:
                continue
            when = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=_LOCAL_TZ)
            when = _naive_utc(when)
            patient = int(m.group(3))
            best = None
            for t in by_patient.get(patient, []):
                start = t.created_at - timedelta(hours=2)
                end = (t.updated_at or t.created_at) + timedelta(minutes=5)
                if start <= when <= end:
                    gap = abs((t.created_at - when).total_seconds())
                    if best is None or gap < best[0]:
                        best = (gap, t)
            if best:
                entry = tally[(best[1].id, m.group(4))]
                entry[0] += 1
                entry[1] += int(m.group(2))

    providers = {m.model_id: m.provider for m in AIModel.query.filter_by(is_asr=True).all()}
    transcripts = {t.id: t for ts in by_patient.values() for t in ts}
    added = 0
    events = UsageEvent.__table__
    calls = UsageAICall.__table__
    with db.engine.begin() as conn:
        for (tid, model), (chunks, chars) in tally.items():
            t = transcripts[tid]
            event_id = conn.execute(select(events.c.id).where(
                events.c.dedupe_key == scribe_key(t.user_id, t.session_id or f'transcript-{t.id}'))).scalar()
            if not event_id or conn.execute(select(calls.c.id).where(
                    calls.c.event_id == event_id, calls.c.kind == 'speech_to_text',
                    calls.c.model == model)).scalar():
                continue
            provider = providers.get(model)
            conn.execute(insert(calls).values(
                event_id=event_id, kind='speech_to_text', model=model,
                provider_name=provider.name if provider else None,
                provider_is_local=provider.is_local if provider else None,
                origin='scribe', chunks=chunks, response_chars=chars, outcome='ok',
                exported_after=False, quality='inferred'))
            added += 1
    return added


def _import_access_log(path: str) -> int:
    """Tasks from the web server's access log, with no user (decided): the log
    records the workstation, not the person. Stops where live recording began."""
    from sqlalchemy import func
    from werkzeug.exceptions import HTTPException
    from app.models.usage import UsageEvent
    from app.services.usage_tasks import task_for

    live_start = (db.session.query(func.min(UsageEvent.occurred_at))
                  .filter(UsageEvent.source == 'live').scalar())
    until = live_start or datetime.now(timezone.utc).replace(tzinfo=None)
    adapter = current_app.url_map.bind('localhost')
    rows = []
    with open(path, errors='ignore') as handle:
        for line in handle:
            m = _ACCESS_RE.match(line)
            if not m or '/static/' in m.group(4):
                continue
            ip, stamp, method, target, status = m.groups()
            if int(status) >= 400:
                continue
            when = _naive_utc(datetime.strptime(stamp, '%d/%b/%Y:%H:%M:%S %z'))
            if when >= until:
                continue
            try:
                endpoint, view_args = adapter.match(target.split('?', 1)[0], method=method)
            except HTTPException:
                continue
            hit = task_for(endpoint, method)
            if (not hit or hit[0] == 'auth.sign_out' or hit[0] in _EXACT_ELSEWHERE
                    or endpoint in _EXACT_ENDPOINTS
                    or (hit[0] == 'admin.change' and endpoint.startswith(_EXACT_ADMIN_PREFIX))):
                continue
            rows.append(_event(hit[0], hit[1], when=when, user_id=None, source='access_log',
                               key='access:' + hashlib.sha1(line.encode()).hexdigest()[:32],
                               patient_linked=view_args.get('patient_id'),
                               quality='unattributed', workstation=ip,
                               detail={'endpoint': endpoint} if hit[0] == 'admin.change' else None))
    return _insert(rows)
