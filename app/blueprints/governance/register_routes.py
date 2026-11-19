from datetime import datetime

from flask import render_template, request, redirect, url_for, abort
from flask_login import login_required

from . import bp
from .permissions import require_governance_level as _require_level
from app.services.governance_register_service import GovernanceRegisterService
from app.models.adverse_event import SeverityGrade


_RECORD_TYPES = {'adverse_event', 'complaint'}


def _parse_filters() -> dict:
    return {
        'record_type': request.args.get('record_type', ''),
        'status_group': request.args.get('status_group', ''),
        'severity': request.args.get('severity', ''),
        'search': request.args.get('search', '').strip(),
        'sort': request.args.get('sort', 'date'),
        'dir': request.args.get('dir', 'desc'),
    }


@bp.get('/register/')
@login_required
def register_index():
    _require_level(4)
    filters = _parse_filters()
    entries = GovernanceRegisterService.get_list(filters)
    selected_type = request.args.get('selected_type')
    selected_id = request.args.get('selected_id', type=int)
    return render_template(
        'governance/register/index.html',
        entries=entries,
        filters=filters,
        selected_type=selected_type,
        selected_id=selected_id,
        severities=list(SeverityGrade),
    )


@bp.get('/register/list')
@login_required
def register_list():
    _require_level(4)
    filters = _parse_filters()
    entries = GovernanceRegisterService.get_list(filters)
    return render_template(
        'governance/register/partials/list.html',
        entries=entries,
        filters=filters,
    )


@bp.get('/register/<record_type>/<int:record_id>')
@login_required
def register_detail(record_type: str, record_id: int):
    _require_level(4)
    if record_type not in _RECORD_TYPES:
        abort(404)
    if not request.headers.get('HX-Request'):
        return redirect(url_for('governance.register_index',
                                 selected_type=record_type, selected_id=record_id))

    detail = GovernanceRegisterService.get_detail(record_type, record_id)
    if not detail:
        abort(404)

    return render_template('governance/register/partials/detail.html', **detail)


@bp.get('/register/report')
@login_required
def register_report():
    _require_level(4)
    filters = _parse_filters()
    report = GovernanceRegisterService.build_report(filters)
    return render_template(
        'governance/register/report.html',
        generated_at=datetime.now(),
        **report,
    )
