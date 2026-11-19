"""Flagged AI requests: the runs the scope checks marked (ADR-103).

Two marks are recorded on a run (PipelineRun.output_json), neither of which stops it:
- the **request check** (ADR-089, results['scope_check']): what the user typed matched a
  pattern such as asking for a dose or a diagnosis;
- the **AI's own flag** (ADR-083, results['scope']['model_flagged']): the model marked its
  reply out of scope and answered only the part within MedUI's purpose;
- the **legality mark** (results['scope']['legality']): the request touched on questions of
  legality (help to do something unlawful); a neutral note, never a block.

This lists them for the practice's own oversight, by user, date and workflow. It reads what
the runs already hold; nothing new is recorded. Some stored results aren't valid JSON, so
the query narrows by text and each row is confirmed here.
"""
import json
from datetime import date, datetime, time, timedelta, timezone

from app.extensions import db

# Request-check patterns (app/services/checker/scope.py) in plain words.
PATTERN_LABELS = {
    'dose_or_treatment_ask': 'asks for a dose or treatment',
    'should_act': 'asks what should be done',
    'diagnosis_ask': 'asks for a diagnosis',
    'differential': 'asks for a differential',
    'second_opinion': 'asks for a second opinion',
    'is_this_serious': 'asks whether it is serious',
    'recommend_ask': 'asks for a recommendation',
    'prognosis_ask': 'asks for a prognosis',
    'interpret_results': 'asks to interpret results',
}
LIMIT = 500


def _flags(output: dict) -> dict | None:
    """What was flagged on a run, or None."""
    check = output.get('scope_check') or {}
    patterns = sorted({h.get('pattern') for h in (check.get('hits') or []) if h.get('pattern')}) \
        if check.get('flagged') else []
    scope = output.get('scope') or {}
    model = bool(scope.get('model_flagged'))
    legality = bool(scope.get('legality'))
    if not patterns and not model and not legality:
        return None
    return {'request': [PATTERN_LABELS.get(p, p.replace('_', ' ')) for p in patterns],
            'reply': model, 'legality': legality}


def _utc_bounds(date_from: date | None, date_to: date | None, zone) -> tuple:
    """Practice-local day bounds as naive UTC (how started_at is stored)."""
    lo = hi = None
    if date_from:
        lo = datetime.combine(date_from, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
    if date_to:
        hi = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
    return lo, hi


def find(user_id: int | None = None, pipeline_id: int | None = None,
         date_from: date | None = None, date_to: date | None = None, kind: str = 'any') -> dict:
    """Flagged runs, newest first, with the filter choices that have any."""
    from app.services import practice_time
    lo, hi = _utc_bounds(date_from, date_to, practice_time.zone())
    from sqlalchemy import or_
    from app.models.pipeline import Pipeline, PipelineRun
    from app.models.privacy_report import PrivacyReport
    from app.models.user import User
    from app.services import privacy_reports_service
    reported = privacy_reports_service.counts()          # users' reports (ADR-115)
    q = (db.session.query(PipelineRun, Pipeline.name, User.display_name, User.username)
         .join(Pipeline, Pipeline.id == PipelineRun.pipeline_id)
         .outerjoin(User, User.id == PipelineRun.initiated_by_id)
         .filter(or_(PipelineRun.output_json.like('%"model_flagged": true%'),
                     PipelineRun.output_json.like('%"legality": true%'),
                     PipelineRun.output_json.like('%"flagged": true%'),
                     PipelineRun.id.in_(db.session.query(PrivacyReport.run_id)))))
    if user_id:
        q = q.filter(PipelineRun.initiated_by_id == user_id)
    if pipeline_id:
        q = q.filter(PipelineRun.pipeline_id == pipeline_id)
    if lo:
        q = q.filter(PipelineRun.started_at >= lo)
    if hi:
        q = q.filter(PipelineRun.started_at < hi)
    rows, users, pipelines = [], {}, {}
    for run, pipeline_name, display_name, username in q.order_by(PipelineRun.started_at.desc()):
        try:
            flags = _flags(json.loads(run.output_json or '{}'))
        except ValueError:
            flags = None
        if run.id in reported:
            flags = {**(flags or {'request': [], 'reply': False, 'legality': False}), 'reported': reported[run.id]}
        if not flags or (kind == 'request' and not flags['request']) or (kind == 'reply' and not flags['reply']) \
                or (kind == 'legality' and not flags['legality']) or (kind == 'reported' and not flags.get('reported')):
            continue
        users[run.initiated_by_id] = display_name or username or f'user {run.initiated_by_id}'
        pipelines[run.pipeline_id] = pipeline_name
        if len(rows) < LIMIT:
            rows.append({'run_id': run.id, 'started_at': run.started_at, 'patient_linked': bool(run.patient_id),
                         'user': users[run.initiated_by_id], 'pipeline': pipeline_name,
                         'local': run.model_is_local, **flags})
    return {'rows': rows, 'total': len(rows), 'truncated': len(rows) >= LIMIT,
            'open_reports': sum(c['open'] for c in reported.values()),
            'users': sorted(users.items(), key=lambda u: (u[1] or '').lower()),
            'pipelines': sorted(pipelines.items(), key=lambda p: (p[1] or '').lower())}


def detail(run_id: int) -> dict | None:
    """The request as typed and the reply, for one flagged run."""
    from app.models.pipeline import PipelineRun
    run = db.session.get(PipelineRun, run_id)
    if not run:
        return None
    try:
        context = json.loads(run.context_json or '{}')
        output = json.loads(run.output_json or '{}')
    except ValueError:
        context, output = {}, {}
    flags = _flags(output)
    from app.services import privacy_reports_service
    reported = privacy_reports_service.counts([run.id]).get(run.id)
    if reported:
        flags = {**(flags or {'request': [], 'reply': False, 'legality': False}), 'reported': reported}
    if not flags:
        return None
    # Text under its own names: 'request' and 'reply' are the flags (as in find()).
    return {'run_id': run.id, 'flags': flags,
            'request_text': ((context.get('input') or {}).get('user_prompt') or '').strip(),
            'reply_text': (output.get('final_output') or '').strip()}
