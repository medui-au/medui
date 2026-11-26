"""Data retention — what Setup → Maintenance → Purge deletes (ADR-188).

Four kinds of row, each by its own retention window (Setup → Maintenance):
  - consultation transcripts: past their expiry, or older than the window;
  - patient messages: sent, failed or revoked, older than the window;
  - chats (ADR-189): no activity within the window, whatever their state (current, ended by
    New conversation, or removed from the list) — with their messages and generated files.
    Chat text is stored de-redacted, so it is not kept indefinitely;
  - pipeline runs: started before the window, **unless another record still points to the run**.

A run is kept while a chat reply, care plan, GPCCMP session, patient message, privacy report or any
other row refers to it through a foreign key that doesn't remove or clear itself
(ON DELETE CASCADE / SET NULL). Those records keep their AI record; the run becomes eligible once
nothing refers to it. The referring tables are read from the models, so a new table that points
to pipeline_runs is covered without changing this file. Before ADR-188 one such run made the whole
purge fail on the foreign key, and nothing was deleted.

Chats go before runs in the same transaction, so a purged chat's runs can go too.

Usage records keep pipeline_run_id without a foreign key on purpose and are never purged here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extensions import db

DEFAULT_DAYS = {'transcripts': 30, 'messages': 90, 'chats': 90, 'pipeline_runs': 180}


def windows() -> dict[str, int]:
    """The retention windows in days, from Setup → Maintenance."""
    from app.models.system_setting import SystemSetting
    out = {}
    for key, default in DEFAULT_DAYS.items():
        try:
            out[key] = max(1, int(SystemSetting.get(f'data.retention.{key}', default) or default))
        except (TypeError, ValueError):
            out[key] = default
    return out


def _run_references():
    """(table, column) pairs whose foreign key to pipeline_runs.id blocks deleting the run."""
    refs = []
    for table in db.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name != 'pipeline_runs' or fk.column.name != 'id':
                continue
            if (fk.ondelete or '').upper() in ('CASCADE', 'SET NULL'):
                continue
            refs.append((table, fk.parent))
    return refs


def _queries(now):
    from app.models.consultation_transcript import ConsultationTranscript
    from app.models.patient_message import PatientMessage, MessageStatus
    from app.models.pipeline import PipelineRun

    days = windows()
    transcripts = ConsultationTranscript.query.filter(db.or_(
        ConsultationTranscript.expires_at < now,
        ConsultationTranscript.created_at < now - timedelta(days=days['transcripts']),
    ))
    messages = PatientMessage.query.filter(
        PatientMessage.status.in_([MessageStatus.sent, MessageStatus.failed, MessageStatus.revoked]),
        PatientMessage.created_at < now - timedelta(days=days['messages']),
    )
    from app.models.chat import ChatSession
    chats = ChatSession.query.filter(
        db.func.coalesce(ChatSession.last_activity_at, ChatSession.created_at)
        < now - timedelta(days=days['chats']))
    old_runs = PipelineRun.query.filter(
        PipelineRun.started_at < now - timedelta(days=days['pipeline_runs']))
    free_runs = old_runs
    for _table, column in _run_references():
        free_runs = free_runs.filter(~PipelineRun.id.in_(
            db.select(column).where(column.isnot(None))))
    return transcripts, messages, chats, old_runs, free_runs


def eligible() -> dict[str, int]:
    """What a purge would delete now, and how many old runs it keeps because they are referred to."""
    transcripts, messages, chats, old_runs, free_runs = _queries(datetime.now(timezone.utc))
    runs = free_runs.count()
    out = {'transcripts': transcripts.count(), 'messages': messages.count(),
           'chats': chats.count(), 'runs': runs, 'runs_kept': old_runs.count() - runs}
    out['total'] = out['transcripts'] + out['messages'] + out['chats'] + out['runs']
    return out


def purge() -> dict[str, int]:
    """Delete what is eligible, in one transaction. Messages and chats go first, so a run that
    only an expired message or chat referred to can go in the same purge."""
    from app.models.chat import ChatGeneratedFile, ChatMessage, ChatSession
    from app.models.pipeline import PipelineRun
    now = datetime.now(timezone.utc)
    transcripts, messages, chats, _old, _free = _queries(now)
    deleted = {'transcripts': transcripts.delete(synchronize_session=False),
               'messages': messages.delete(synchronize_session=False)}
    chat_ids = [i for (i,) in chats.with_entities(ChatSession.id).all()]
    if chat_ids:
        ChatGeneratedFile.query.filter(ChatGeneratedFile.session_id.in_(chat_ids)).delete(
            synchronize_session=False)
        ChatMessage.query.filter(ChatMessage.session_id.in_(chat_ids)).delete(
            synchronize_session=False)
        ChatSession.query.filter(ChatSession.id.in_(chat_ids)).delete(synchronize_session=False)
    deleted['chats'] = len(chat_ids)
    db.session.flush()
    _t, _m, _c, old_runs, free_runs = _queries(now)
    ids = [r for (r,) in free_runs.with_entities(PipelineRun.id).all()]
    deleted['runs'] = (PipelineRun.query.filter(PipelineRun.id.in_(ids))
                       .delete(synchronize_session=False) if ids else 0)
    deleted['runs_kept'] = old_runs.count()   # the old runs still there are the ones kept
    db.session.commit()
    deleted['total'] = (deleted['transcripts'] + deleted['messages'] + deleted['chats']
                        + deleted['runs'])
    return deleted
