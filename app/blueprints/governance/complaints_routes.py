import csv
import io
from datetime import datetime, timezone

from flask import render_template, request, redirect, url_for, jsonify, abort, Response
from flask_login import current_user, login_required

from . import bp
from .permissions import require_governance_level as _require_level, has_governance_level
from app.services.complaints_service import ComplaintsService
from app.services.clinical_service import ClinicalService
from app.models.complaint import (
    ComplaintStatus, ComplaintCategory, ComplainantType, EscalationTarget,
)
from app.models.user import User


# ── Index ──────────────────────────────────────────────────────────────────

@bp.get('/complaints/')
@login_required
def complaints_index():
    _require_level(1)
    filters = _parse_filters()
    complaints = ComplaintsService.get_list(filters)
    users = User.query.order_by(User.display_name).all() if has_governance_level(6) else []
    selected_id = request.args.get('selected', type=int)
    return render_template(
        'governance/complaints/index.html',
        complaints=complaints,
        selected_id=selected_id,
        filters=filters,
        users=users,
        statuses=list(ComplaintStatus),
        categories=list(ComplaintCategory),
        overdue_fn=ComplaintsService.overdue_acknowledgement,
    )


# ── HTMX list ──────────────────────────────────────────────────────────────

@bp.get('/complaints/list')
@login_required
def complaints_list():
    _require_level(1)
    filters = _parse_filters()
    complaints = ComplaintsService.get_list(filters)
    return render_template(
        'governance/complaints/partials/list.html',
        complaints=complaints,
        filters=filters,
        overdue_fn=ComplaintsService.overdue_acknowledgement,
    )


# ── Detail ─────────────────────────────────────────────────────────────────

@bp.get('/complaints/<int:complaint_id>')
@login_required
def complaints_detail(complaint_id: int):
    _require_level(1)
    # Non-HTMX browser request (e.g. direct URL or post-redirect GET): serve the full page
    if not request.headers.get('HX-Request'):
        return redirect(url_for('governance.complaints_index', selected=complaint_id))

    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    if not has_governance_level(4) and complaint.received_by_id != current_user.id:
        abort(403)

    patient = None
    if complaint.patient_id:
        try:
            patient = ClinicalService.get_patient_demographics(complaint.patient_id)
        except Exception:
            pass

    cross_links = _get_cross_links(complaint_id=complaint_id)
    users = User.query.order_by(User.display_name).all() if has_governance_level(6) else []
    can_close, close_msg = ComplaintsService.can_close(complaint)

    return render_template(
        'governance/complaints/partials/detail.html',
        complaint=complaint,
        patient=patient,
        cross_links=cross_links,
        users=users,
        can_close=can_close,
        close_msg=close_msg,
        days_to_ack=ComplaintsService.days_to_acknowledge(complaint),
        overdue=ComplaintsService.overdue_acknowledgement(complaint),
        statuses=list(ComplaintStatus),
        escalation_targets=list(EscalationTarget),
    )


# ── Audit log ──────────────────────────────────────────────────────────────

@bp.get('/complaints/<int:complaint_id>/actions')
@login_required
def complaints_actions(complaint_id: int):
    _require_level(4)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    return render_template(
        'governance/complaints/partials/action_log.html',
        actions=complaint.actions.all(),
    )


# ── New complaint ──────────────────────────────────────────────────────────

@bp.get('/complaints/new')
@login_required
def complaints_new():
    _require_level(1)
    return render_template(
        'governance/complaints/partials/form_new.html',
        categories=list(ComplaintCategory),
        complainant_types=list(ComplainantType),
    )


@bp.post('/complaints/new')
@login_required
def complaints_create():
    _require_level(1)
    data = _parse_complaint_form(request.form)
    if isinstance(data, str):
        return data, 400
    complaint = ComplaintsService.create(data, current_user)
    return redirect(url_for('governance.complaints_index', selected=complaint.id))


# ── Edit ───────────────────────────────────────────────────────────────────

@bp.get('/complaints/<int:complaint_id>/edit')
@login_required
def complaints_edit(complaint_id: int):
    _require_level(4)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    return render_template(
        'governance/complaints/partials/form_edit.html',
        complaint=complaint,
        categories=list(ComplaintCategory),
        complainant_types=list(ComplainantType),
        escalation_targets=list(EscalationTarget),
    )


@bp.post('/complaints/<int:complaint_id>/edit')
@login_required
def complaints_save(complaint_id: int):
    _require_level(4)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    f = request.form
    complaint.subject = f.get('subject', complaint.subject)
    complaint.description = f.get('description', complaint.description)
    complaint.category = f.get('category', complaint.category)
    complaint.open_disclosure_required = bool(f.get('open_disclosure_required'))
    complaint.resolution_summary = f.get('resolution_summary') or complaint.resolution_summary
    complaint.corrective_action = f.get('corrective_action') or complaint.corrective_action
    complaint.updated_at = datetime.now(timezone.utc)
    from app.extensions import db
    db.session.commit()
    return redirect(url_for('governance.complaints_index', selected=complaint_id))


# ── Workflow actions ────────────────────────────────────────────────────────

@bp.post('/complaints/<int:complaint_id>/acknowledge')
@login_required
def complaints_acknowledge(complaint_id: int):
    _require_level(6)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    method = request.form.get('method', 'phone')
    ack_date = _parse_datetime(request.form.get('ack_date'))
    ComplaintsService.acknowledge(complaint, method, current_user, ack_date=ack_date)
    return redirect(url_for('governance.complaints_index', selected=complaint_id))


@bp.post('/complaints/<int:complaint_id>/transition')
@login_required
def complaints_transition(complaint_id: int):
    _require_level(6)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    new_status_str = request.form.get('status')
    try:
        new_status = ComplaintStatus(new_status_str)
    except ValueError:
        abort(400)
    notes = request.form.get('notes')
    ComplaintsService.transition(complaint, new_status, notes, current_user)
    return redirect(url_for('governance.complaints_index', selected=complaint_id))


@bp.post('/complaints/<int:complaint_id>/note')
@login_required
def complaints_note(complaint_id: int):
    _require_level(4)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    notes = request.form.get('notes', '').strip()
    if notes:
        ComplaintsService.add_note(complaint, notes, current_user)
    return redirect(url_for('governance.complaints_index', selected=complaint_id))


@bp.post('/complaints/<int:complaint_id>/disclosure')
@login_required
def complaints_disclosure(complaint_id: int):
    _require_level(6)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    ComplaintsService.mark_disclosure(complaint, request.form.get('notes'), current_user)
    return redirect(url_for('governance.complaints_index', selected=complaint_id))


@bp.post('/complaints/<int:complaint_id>/close')
@login_required
def complaints_close(complaint_id: int):
    _require_level(9)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    can_close, msg = ComplaintsService.can_close(complaint)
    if not can_close:
        abort(400, msg)
    action = request.form.get('action', 'close')
    new_status = ComplaintStatus.withdrawn if action == 'withdraw' else ComplaintStatus.closed
    ComplaintsService.transition(complaint, new_status, request.form.get('notes'), current_user)
    return redirect(url_for('governance.complaints_index'))


@bp.post('/complaints/<int:complaint_id>/void')
@login_required
def complaints_void(complaint_id: int):
    _require_level(9)
    complaint = ComplaintsService.get_detail(complaint_id)
    if not complaint:
        abort(404)
    reason = request.form.get('reason', '').strip()
    if not reason:
        abort(400, 'A reason is required to void a complaint.')
    ComplaintsService.void(complaint, reason, current_user)
    return redirect(url_for('governance.complaints_index'))


# ── Report ─────────────────────────────────────────────────────────────────

@bp.get('/complaints/report')
@login_required
def complaints_report():
    _require_level(9)
    complaints = ComplaintsService.get_list()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Reference', 'Received', 'Category', 'Complainant Type',
        'Status', 'Acknowledged', 'Days to Ack', 'Disclosure Required',
        'Disclosure Completed', 'Corrective Action', 'Closed',
    ])
    for c in complaints:
        writer.writerow([
            c.reference_no,
            c.received_at.strftime('%d/%m/%Y') if c.received_at else '',
            c.category.value if c.category else '',
            c.complainant_type.value if c.complainant_type else '',
            c.status.value if c.status else '',
            c.acknowledged_at.strftime('%d/%m/%Y') if c.acknowledged_at else '',
            ComplaintsService.days_to_acknowledge(c) or '',
            'Yes' if c.open_disclosure_required else 'No',
            c.open_disclosure_completed_at.strftime('%d/%m/%Y') if c.open_disclosure_completed_at else '',
            c.corrective_action or '',
            c.closed_at.strftime('%d/%m/%Y') if c.closed_at else '',
        ])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=complaints_register.csv'},
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_filters() -> dict:
    f = {}
    if request.args.get('status'):
        f['status'] = request.args['status']
    if request.args.get('category'):
        f['category'] = request.args['category']
    if request.args.get('search'):
        f['search'] = request.args['search']
    if request.args.get('show_voided') and has_governance_level(9):
        f['show_voided'] = True
    return f


def _parse_complaint_form(form) -> dict | str:
    required = ('subject', 'description', 'category', 'complainant_type')
    for field in required:
        if not form.get(field, '').strip():
            return f'Missing required field: {field}'
    try:
        category = ComplaintCategory(form['category'])
        complainant_type = ComplainantType(form['complainant_type'])
    except ValueError as e:
        return str(e)

    return {
        'subject': form['subject'].strip(),
        'description': form['description'].strip(),
        'category': category,
        'complainant_type': complainant_type,
        'patient_id': int(form['patient_id']) if form.get('patient_id', '').strip() else None,
        'external_name': form.get('external_name', '').strip() or None,
        'external_contact': form.get('external_contact', '').strip() or None,
        'open_disclosure_required': bool(form.get('open_disclosure_required')),
        'notes': form.get('notes', '').strip() or None,
        'received_at': _parse_datetime(form.get('received_at')),
    }


def _parse_datetime(value: str | None):
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _get_cross_links(complaint_id: int):
    from app.models.adverse_event import RegisterCrossLink
    return RegisterCrossLink.query.filter_by(complaint_id=complaint_id).all()
