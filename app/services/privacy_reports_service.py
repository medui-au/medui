"""Users report what got through to the AI; administrators act on it (ADR-115).

On the Sent to AI tab a user selects text in the prompt as sent and reports it. The
report holds positions in the run's stored prompt, never the text: the run already holds
it, and the text shown to an administrator is always read from there, so a report can
only point at what was actually sent. An administrator adds it to future redactions
(the always-redact or name-variant list, as for a checker hit, ADR-049) or dismisses it.
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db

MAX_SPAN = 200          # a name, an address, a business: not a paragraph
_CONTEXT = 60


def _sent_prompt(run) -> str:
    from app.services.pipeline.engine import extract_debug_info
    return extract_debug_info(run).get('current_prompt') or ''


def may_report(run, user) -> bool:
    """The user who started the run (who saw its Sent tab), or an administrator."""
    return bool(run) and (run.initiated_by_id == user.id or user.is_admin)


def span_problem(prompt: str, start, end) -> str | None:
    """Why this span can't be reported, or None."""
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(prompt):
        return 'Select the text in the prompt first.'
    text = prompt[start:end].strip()
    if not text:
        return 'Select the text in the prompt first.'
    if end - start > MAX_SPAN:
        return f'Select just the identifying part (up to {MAX_SPAN} characters).'
    if text.startswith('[Redacted') and text.endswith(']') and text.count('[') == 1:
        return 'That is already redacted.'
    return None


def create(run_id: int, user, start, end, note: str = '') -> dict:
    """Record a report. The span is checked against the stored prompt here."""
    from app.models.pipeline import PipelineRun
    from app.models.privacy_report import PrivacyReport
    run = db.session.get(PipelineRun, run_id)
    if not may_report(run, user):
        return {'ok': False, 'message': 'This run cannot be reported from here.'}
    if run.model_is_local:
        return {'ok': False, 'message': 'This run used a local model: nothing left the practice.'}
    problem = span_problem(_sent_prompt(run), start, end)
    if problem:
        return {'ok': False, 'message': problem}
    if PrivacyReport.query.filter_by(run_id=run.id, span_start=start, span_end=end).first():
        return {'ok': False, 'message': 'Already reported.'}
    db.session.add(PrivacyReport(run_id=run.id, reported_by_id=user.id, span_start=start, span_end=end,
                                 note=(note or '').strip()[:200] or None))
    db.session.commit()
    current_app.logger.info('privacy report: run %s, by user %s', run.id, user.id)
    return {'ok': True, 'message': 'Reported. An administrator will review it and can add it to the '
                                   'redactions, so it is removed from future requests.'}


def for_run(run, prompt: str | None = None) -> list[dict]:
    """The run's reports, with their text and context read from the stored prompt."""
    from app.models.privacy_report import PrivacyReport
    from app.models.user import User
    prompt = _sent_prompt(run) if prompt is None else prompt
    out = []
    for r in PrivacyReport.query.filter_by(run_id=run.id).order_by(PrivacyReport.id):
        if not 0 <= r.span_start < r.span_end <= len(prompt):
            continue
        reporter = db.session.get(User, r.reported_by_id)
        handler = db.session.get(User, r.handled_by_id) if r.handled_by_id else None
        out.append({
            'id': r.id, 'word': prompt[r.span_start:r.span_end],
            'before': prompt[max(0, r.span_start - _CONTEXT):r.span_start],
            'after': prompt[r.span_end:r.span_end + _CONTEXT],
            'note': r.note, 'status': r.status, 'outcome': r.outcome,
            'reported_at': r.reported_at, 'handled_at': r.handled_at,
            'reporter': (reporter.display_name or reporter.username) if reporter else '',
            'handler': (handler.display_name or handler.username) if handler else '',
            'single_word': len(prompt[r.span_start:r.span_end].split()) == 1,
        })
    return out


def counts(run_ids=None) -> dict[int, dict]:
    """{run_id: {'open': n, 'total': n}} for runs with reports (all of them, or these)."""
    from sqlalchemy import func
    from app.models.privacy_report import PrivacyReport
    q = db.session.query(PrivacyReport.run_id, PrivacyReport.status, func.count())
    if run_ids is not None:
        q = q.filter(PrivacyReport.run_id.in_(list(run_ids)))
    out: dict[int, dict] = {}
    for run_id, status, n in q.group_by(PrivacyReport.run_id, PrivacyReport.status):
        c = out.setdefault(run_id, {'open': 0, 'total': 0})
        c['total'] += n
        if status == 'open':
            c['open'] += n
    return out


def handle(run_id: int, report_id: int, action: str, user, label: str = '', name: str = '',
           confirmed: bool = False) -> dict:
    """An administrator's answer: add to a list, or dismiss."""
    from app.models.pipeline import PipelineRun
    from app.models.privacy_report import PrivacyReport
    from app.services import privacy_hits_service as hits
    report = db.session.get(PrivacyReport, report_id)
    run = db.session.get(PipelineRun, run_id)
    if not report or not run or report.run_id != run.id:
        return {'ok': False, 'message': 'No such report.'}
    if report.status != 'open':
        return {'ok': False, 'message': f'Already {report.status}.'}
    prompt = _sent_prompt(run)
    if not 0 <= report.span_start < report.span_end <= len(prompt):
        return {'ok': False, 'message': 'The reported text is no longer in the stored prompt.'}
    text = prompt[report.span_start:report.span_end]
    source = f'Reported by a user on run #{run.id}'
    if action == 'always_redact':
        result = hits.always_redact_from_text(run, text, label, user.username, source)
        outcome = f'always-redact list, as {label}'
    elif action == 'name_variant':
        result = hits.name_variant_from_text(run, text, name, user.username, confirmed, source)
        outcome = f'name variant of {name.capitalize()}'
    elif action == 'dismiss':
        result = {'ok': True, 'message': 'Dismissed: left as it is.'}
        outcome = 'dismissed'
    else:
        return {'ok': False, 'message': 'Unknown action.'}
    if result.get('ok'):
        report.status = 'dismissed' if action == 'dismiss' else 'added'
        report.outcome = outcome
        report.handled_by_id = user.id
        report.handled_at = datetime.now(timezone.utc)
        db.session.commit()
    return result
