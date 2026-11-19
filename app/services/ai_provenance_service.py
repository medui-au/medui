"""Provenance footer for AI drafts filed to Best Practice.

When a practice turns it on (Setup → Messaging), a document filed from an AI draft ends
with one line saying it was AI-assisted, who filed it, when, and the MedUI run it came from:

    AI-assisted draft · filed by A Example · 17/10/2026 14:32 · MedUI ref 1234

The run reference leads to the full record (model, prompt, what was sent), so the footer
stays short. The model name is a separate option. "Filed by", not "reviewed by": MedUI
records who filed a document, not whether they read it.
"""
from datetime import datetime

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

FOOTER_SETTING = 'ai.provenance_footer'
MODEL_SETTING = 'ai.provenance_include_model'


def _filer_name(user) -> str:
    first = (getattr(user, 'bpsdb_firstname', '') or '').strip()
    surname = (getattr(user, 'bpsdb_surname', '') or '').strip()
    return ' '.join(p for p in (first, surname) if p) or (getattr(user, 'display_name', '') or '').strip()


def _model_for_run(run_id: int) -> str:
    from app.extensions import db
    from app.models.usage import UsageAICall
    try:
        return db.session.execute(
            select(UsageAICall.model).where(UsageAICall.pipeline_run_id == run_id,
                                            UsageAICall.kind == 'inference').limit(1)).scalar() or ''
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.warning('provenance: no model for run %s: %s', run_id, exc)
        return ''


def footer_for_run(run_id, user) -> str:
    """The footer to append to a filed AI draft, or '' when the practice has it off or
    there is no run to point to."""
    from app.models.system_setting import SystemSetting
    if not SystemSetting.get(FOOTER_SETTING, False):
        return ''
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        return ''
    parts = ['AI-assisted draft']
    name = _filer_name(user)
    if name:
        parts.append(f'filed by {name}')
    parts.append(datetime.now().strftime('%d/%m/%Y %H:%M'))
    parts.append(f'MedUI ref {run_id}')
    if SystemSetting.get(MODEL_SETTING, False):
        model = _model_for_run(run_id)
        if model:
            parts.append(f'model: {model}')
    return '\n\n' + ' · '.join(parts)
