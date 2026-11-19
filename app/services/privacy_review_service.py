"""Privacy Review: what the pre-send check found, across runs, and a reviewer's verdict (ADR-120).

The pre-send check (ADR-084, ADR-111) stores its result with each run sent to a cloud model
(PipelineRun.output_json -> 'precheck': the tier, type and position of each hit, never the
text). Earlier runs carry the card AuditFilter returned when it checked them after sending
('privacy_check'), in the same shape. This lists the runs whose check found something, or that a user reported (ADR-115), so
an administrator can open each one on its Privacy hits page and record a verdict. It reads what
the runs already hold; the only thing it writes is the verdict (PrivacyReview).

The page is switched on and off by a system setting (Application Setup → Maintenance). The
check itself does not depend on it: it always runs, and a tier 0 or 1 hit still stops a request
for review.

Stored results are text and some aren't valid JSON, so the query narrows by text and each row
is parsed here, as in flagged_requests_service.
"""
import json
from datetime import date, datetime, timezone

from app.extensions import db

SETTING_KEY = 'privacy.review_page'
LIMIT = 500

TIER_LABELS = {
    0: "the patient's own details",
    1: 'a practice contact',
    2: 'looks like an identifier',
}
# Hit types in plain words. Anything not listed is shown with its underscores as spaces.
TYPE_LABELS = {
    'patient_name': "patient's name", 'patient_name_variant': "short form of the patient's name",
    'patient_dob': "patient's date of birth", 'patient_address': "patient's address",
    'patient_phone': "patient's phone", 'patient_email': "patient's email",
    'patient_medicareno': "patient's Medicare number", 'patient_nok_name': "next of kin's name",
    'patient_nok_phone': "next of kin's phone",
    'practice_contact_name': 'name of a practice contact', 'practice_contact_detail': 'practice contact detail',
    'titled_name': 'a name with a title (Dr, Mrs…)', 'name_after_token': 'a name next to a redacted one',
    'street_address': 'a street address', 'mobile_number': 'a mobile number',
    'landline_number': 'a landline number', 'email_address': 'an email address',
    'medicare_number': 'a Medicare number', 'dva_number': 'a DVA number', 'ihi_number': 'an IHI',
    'date_of_birth': 'a date of birth', 'provider_number': 'a provider number',
    'labelled_identifier': 'a labelled identifier', 'access_link': 'a link',
}
DISPOSITION_LABELS = {
    'unreviewed': 'Not reviewed',
    'true_leak': 'Real leak',
    'false_positive': 'False alarm',
    'acceptable': 'Acceptable',
}
SEVERITY_LABELS = {'none': 'None', 'minor': 'Minor', 'serious': 'Serious'}
TIER_FILTERS = ('01', '2', 'any')
REVIEWED_FILTERS = ('any', 'no', 'yes')


def enabled() -> bool:
    from app.models.system_setting import SystemSetting
    return bool(SystemSetting.get(SETTING_KEY, False))


def type_label(finding_type: str | None) -> str:
    return TYPE_LABELS.get(finding_type or '', (finding_type or 'unknown').replace('_', ' '))


def parse_filters(args) -> dict:
    """The list's filters from a request's query string, with defaults."""
    def _day(name):
        try:
            return date.fromisoformat(args.get(name, ''))
        except ValueError:
            return None
    workflow = args.get('workflow', '')
    tier = args.get('tier', '01')
    reviewed = args.get('reviewed', 'any')
    return {'pipeline_id': int(workflow) if workflow.isdigit() else None,
            'date_from': _day('from'), 'date_to': _day('to'),
            'tier': tier if tier in TIER_FILTERS else '01',
            'reviewed': reviewed if reviewed in REVIEWED_FILTERS else 'any',
            'order': 'old' if args.get('order') == 'old' else 'new'}


def query_args(filters: dict) -> dict:
    """The filters back as query-string arguments, so previous / next keep them."""
    out = {'tier': filters['tier'], 'reviewed': filters['reviewed'], 'order': filters['order']}
    if filters.get('pipeline_id'):
        out['workflow'] = str(filters['pipeline_id'])
    if filters.get('date_from'):
        out['from'] = filters['date_from'].isoformat()
    if filters.get('date_to'):
        out['to'] = filters['date_to'].isoformat()
    return out


def _outcome(run, output: dict) -> str:
    """Whether the request went to the AI, in a word or two."""
    status = getattr(run.status, 'value', run.status)
    review = output.get('review') if isinstance(output.get('review'), dict) else {}
    if status == 'completed':
        return 'Sent'
    if status == 'cancelled' and review.get('paused'):
        return 'Stopped at review'
    if status == 'cancelled':
        return 'Cancelled'
    if status == 'failed':
        return 'Failed'
    return status.capitalize() if isinstance(status, str) else 'Unknown'


def _check(output: dict) -> dict:
    """The check's result on a run: MedUI's own (precheck, from 2026-10-19), else the card
    AuditFilter returned when it checked runs after sending (before ADR-111). {} if neither
    holds hits with positions (a local model, a screening run, or a count-only result)."""
    for key in ('precheck', 'privacy_check'):
        check = output.get(key)
        if isinstance(check, dict) and isinstance(check.get('hits'), list):
            return check
    return {}


def _row_matches(top_tier, reports, review, filters) -> bool:
    has_reports = bool(reports and reports.get('open'))
    if filters['tier'] == '01' and not (top_tier in (0, 1) or has_reports):
        return False
    if filters['tier'] == '2' and top_tier != 2:
        return False
    if filters['tier'] == 'any' and top_tier is None and not reports:
        return False
    is_reviewed = review is not None and review.disposition != 'unreviewed'
    if filters['reviewed'] == 'no' and is_reviewed:
        return False
    if filters['reviewed'] == 'yes' and not is_reviewed:
        return False
    return True


def find(filters: dict) -> dict:
    """Runs whose check found something (or that a user reported), with the page's counts."""
    from sqlalchemy import or_
    from sqlalchemy.orm import load_only
    from app.models.pipeline import Pipeline, PipelineRun
    from app.models.privacy_report import PrivacyReport
    from app.models.privacy_review import PrivacyReview
    from app.models.user import User
    from app.services import practice_time, privacy_reports_service
    from app.services.flagged_requests_service import _utc_bounds

    lo, hi = _utc_bounds(filters.get('date_from'), filters.get('date_to'), practice_time.zone())
    reported = privacy_reports_service.counts()
    reviews = {r.run_id: r for r in PrivacyReview.query.all()}
    # Only the columns the list needs: a run's prompts and snapshots are large, and loading
    # them for every checked run made the page take seconds.
    q = (db.session.query(PipelineRun, Pipeline.name, User.display_name, User.username)
         .options(load_only(PipelineRun.id, PipelineRun.started_at, PipelineRun.status,
                            PipelineRun.pipeline_id, PipelineRun.initiated_by_id,
                            PipelineRun.model_is_local, PipelineRun.output_json))
         .join(Pipeline, Pipeline.id == PipelineRun.pipeline_id)
         .outerjoin(User, User.id == PipelineRun.initiated_by_id)
         .filter(or_(PipelineRun.output_json.like('%"precheck"%'),
                     PipelineRun.output_json.like('%"privacy_check"%'),
                     PipelineRun.id.in_(db.session.query(PrivacyReport.run_id)))))
    if filters.get('pipeline_id'):
        q = q.filter(PipelineRun.pipeline_id == filters['pipeline_id'])
    if lo:
        q = q.filter(PipelineRun.started_at >= lo)
    if hi:
        q = q.filter(PipelineRun.started_at < hi)
    order = PipelineRun.id.asc() if filters.get('order') == 'old' else PipelineRun.id.desc()

    rows, pipelines = [], {}
    counts = {'unreviewed_01': 0, 'unreviewed_2': 0, 'checked': 0}
    for run, pipeline_name, display_name, username in q.order_by(order):
        try:
            output = json.loads(run.output_json or '{}')
        except ValueError:
            output = {}
        check = _check(output)
        hits = [h for h in (check.get('hits') or []) if isinstance(h, dict)]
        top_tier = check.get('top_tier') if hits else None
        reports = reported.get(run.id)
        review = reviews.get(run.id)
        if 'hits' in check:
            counts['checked'] += 1
        if top_tier is None and not reports:
            continue                       # checked and clean: not for review here
        pipelines[run.pipeline_id] = pipeline_name
        is_reviewed = review is not None and review.disposition != 'unreviewed'
        if not is_reviewed and (top_tier in (0, 1) or (reports and reports.get('open'))):
            counts['unreviewed_01'] += 1
        elif not is_reviewed and top_tier == 2:
            counts['unreviewed_2'] += 1
        if not _row_matches(top_tier, reports, review, filters):
            continue
        if len(rows) < LIMIT:
            types = sorted({h.get('type') or 'unknown' for h in hits})
            rows.append({
                'run_id': run.id, 'started_at': run.started_at, 'pipeline': pipeline_name,
                'user': display_name or username or (f'user {run.initiated_by_id}' if run.initiated_by_id else '—'),
                'local': run.model_is_local, 'outcome': _outcome(run, output),
                'top_tier': top_tier, 'hit_count': len(hits),
                'types': [type_label(t) for t in types],
                'reports': reports,
                'disposition': review.disposition if review else 'unreviewed',
                'severity': review.severity if review else None,
            })
    return {'rows': rows, 'total': len(rows), 'truncated': len(rows) >= LIMIT, 'counts': counts,
            'pipelines': sorted(pipelines.items(), key=lambda p: (p[1] or '').lower())}


def neighbours(run_id: int, filters: dict) -> dict:
    """The runs either side of this one in the list as filtered, and where it sits."""
    ids = [r['run_id'] for r in find(filters)['rows']]
    if run_id not in ids:
        return {'previous': None, 'next': None, 'position': None, 'total': len(ids)}
    i = ids.index(run_id)
    # The list runs newest first by default, so "previous" is the row above, "next" the row below.
    return {'previous': ids[i - 1] if i > 0 else None,
            'next': ids[i + 1] if i + 1 < len(ids) else None,
            'position': i + 1, 'total': len(ids)}


def latest(filters: dict) -> int | None:
    """The newest run in the list as filtered."""
    rows = find({**filters, 'order': 'new'})['rows']
    return rows[0]['run_id'] if rows else None


def get(run_id: int):
    from app.models.privacy_review import PrivacyReview
    return PrivacyReview.query.filter_by(run_id=run_id).first()


def save(run_id: int, disposition: str, severity: str | None, comment: str | None, user_id: int) -> dict:
    """Record (or change) the verdict on a run. 'unreviewed' clears it."""
    from flask import current_app
    from app.models.pipeline import PipelineRun
    from app.models.privacy_review import DISPOSITIONS, SEVERITIES, PrivacyReview
    if not db.session.get(PipelineRun, run_id):
        return {'ok': False, 'message': 'No such run.'}
    review = get(run_id)
    if disposition == 'unreviewed':
        if review:
            db.session.delete(review)
            db.session.commit()
        return {'ok': True, 'message': 'Review cleared: the run shows as not reviewed.'}
    if disposition not in DISPOSITIONS:
        return {'ok': False, 'message': 'Choose what the hits were.'}
    severity = severity or None
    if severity is not None and severity not in SEVERITIES:
        return {'ok': False, 'message': 'Unrecognised severity.'}
    comment = (comment or '').strip()[:2000] or None
    if review is None:
        review = PrivacyReview(run_id=run_id)
        db.session.add(review)
    review.disposition = disposition
    review.severity = severity
    review.comment = comment
    review.reviewed_by_id = user_id
    review.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    current_app.logger.info('privacy review: run %s marked %s by user %s', run_id, disposition, user_id)
    return {'ok': True, 'message': 'Review saved.'}
