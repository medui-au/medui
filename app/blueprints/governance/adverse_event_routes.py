import csv
import io
from datetime import datetime, timezone, date

from flask import render_template, request, redirect, url_for, abort, Response
from flask_login import current_user, login_required

from . import bp
from .permissions import require_governance_level as _require_level, has_governance_level
from app.services.adverse_event_service import AdverseEventService
from app.services.clinical_service import ClinicalService
from app.models.adverse_event import (
    AEStatus, EventType, SeverityGrade, InvolvedPersonType, NotifiedAuthority, CrossLinkType,
)
from app.models.user import User


# ── Index ──────────────────────────────────────────────────────────────────

@bp.get('/adverse-events/')
@login_required
def ae_index():
    _require_level(1)
    filters = _parse_ae_filters()
    events = AdverseEventService.get_list(filters)
    users = User.query.order_by(User.display_name).all() if has_governance_level(6) else []
    selected_id = request.args.get('selected', type=int)
    return render_template(
        'governance/adverse_events/index.html',
        events=events,
        selected_id=selected_id,
        filters=filters,
        users=users,
        statuses=list(AEStatus),
        event_types=list(EventType),
        severities=list(SeverityGrade),
        overdue_fn=AdverseEventService.overdue_triage,
    )


# ── HTMX list ──────────────────────────────────────────────────────────────

@bp.get('/adverse-events/list')
@login_required
def ae_list():
    _require_level(1)
    filters = _parse_ae_filters()
    events = AdverseEventService.get_list(filters)
    return render_template(
        'governance/adverse_events/partials/list.html',
        events=events,
        filters=filters,
        overdue_fn=AdverseEventService.overdue_triage,
    )


# ── Detail ─────────────────────────────────────────────────────────────────

@bp.get('/adverse-events/<int:event_id>')
@login_required
def ae_detail(event_id: int):
    _require_level(1)
    if not request.headers.get('HX-Request'):
        return redirect(url_for('governance.ae_index', selected=event_id))

    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    if not has_governance_level(4) and event.reported_by_id != current_user.id:
        abort(403)

    patient = None
    if event.patient_id:
        try:
            patient = ClinicalService.get_patient_demographics(event.patient_id)
        except Exception:
            pass

    cross_links = _get_cross_links(adverse_event_id=event_id)
    users = User.query.order_by(User.display_name).all() if has_governance_level(6) else []
    can_close, close_msg = AdverseEventService.can_close(event)
    action_items = event.action_items.all()

    return render_template(
        'governance/adverse_events/partials/detail.html',
        event=event,
        patient=patient,
        cross_links=cross_links,
        users=users,
        can_close=can_close,
        close_msg=close_msg,
        action_items=action_items,
        all_actions_complete=AdverseEventService.all_actions_complete(event),
        overdue=AdverseEventService.overdue_triage(event),
        statuses=list(AEStatus),
        severities=list(SeverityGrade),
        authorities=list(NotifiedAuthority),
    )


# ── Audit log ──────────────────────────────────────────────────────────────

@bp.get('/adverse-events/<int:event_id>/actions')
@login_required
def ae_actions(event_id: int):
    _require_level(4)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    return render_template(
        'governance/adverse_events/partials/action_log.html',
        actions=event.actions.all(),
    )


# ── New event ──────────────────────────────────────────────────────────────

@bp.get('/adverse-events/new')
@login_required
def ae_new():
    _require_level(1)
    return render_template(
        'governance/adverse_events/partials/form_new.html',
        event_types=list(EventType),
        severities=list(SeverityGrade),
        involved_person_types=list(InvolvedPersonType),
    )


@bp.post('/adverse-events/new')
@login_required
def ae_create():
    _require_level(1)
    data = _parse_ae_form(request.form)
    if isinstance(data, str):
        return data, 400
    event = AdverseEventService.create(data, current_user)
    return redirect(url_for('governance.ae_index', selected=event.id))


# ── Edit ───────────────────────────────────────────────────────────────────

@bp.get('/adverse-events/<int:event_id>/edit')
@login_required
def ae_edit(event_id: int):
    _require_level(4)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    return render_template(
        'governance/adverse_events/partials/form_edit.html',
        event=event,
        event_types=list(EventType),
        severities=list(SeverityGrade),
        involved_person_types=list(InvolvedPersonType),
    )


@bp.post('/adverse-events/<int:event_id>/edit')
@login_required
def ae_save(event_id: int):
    _require_level(4)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    f = request.form
    event.title = f.get('title', event.title)
    event.description = f.get('description', event.description)
    event.immediate_actions = f.get('immediate_actions') or event.immediate_actions
    event.location = f.get('location') or event.location
    event.updated_at = datetime.now(timezone.utc)
    from app.extensions import db
    db.session.commit()
    return redirect(url_for('governance.ae_index', selected=event_id))


# ── Workflow actions ────────────────────────────────────────────────────────

@bp.post('/adverse-events/<int:event_id>/triage')
@login_required
def ae_triage(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    sev_str = request.form.get('confirmed_severity')
    confirmed_severity = SeverityGrade(sev_str) if sev_str else None
    AdverseEventService.triage(event, confirmed_severity, request.form.get('notes'), current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/transition')
@login_required
def ae_transition(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    try:
        new_status = AEStatus(request.form['status'])
    except (KeyError, ValueError):
        abort(400)
    AdverseEventService.transition(event, new_status, request.form.get('notes'), current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/note')
@login_required
def ae_note(event_id: int):
    _require_level(4)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    notes = request.form.get('notes', '').strip()
    if notes:
        AdverseEventService.add_note(event, notes, current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/rca')
@login_required
def ae_rca(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    AdverseEventService.update_rca(
        event,
        method=request.form.get('rca_method'),
        summary=request.form.get('rca_summary', ''),
        completed=bool(request.form.get('rca_completed')),
        actor=current_user,
    )
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/disclosure')
@login_required
def ae_disclosure(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    AdverseEventService.mark_disclosure(event, request.form.get('notes'), current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/disclosure-required')
@login_required
def ae_set_disclosure_required(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    AdverseEventService.set_disclosure_required(
        event, bool(request.form.get('open_disclosure_required')), current_user
    )
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/notify')
@login_required
def ae_notify(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    try:
        authority = NotifiedAuthority(request.form['authority'])
    except (KeyError, ValueError):
        abort(400)
    AdverseEventService.notify_authority(
        event, authority,
        ref=request.form.get('ref'),
        notes=request.form.get('notes'),
        actor=current_user,
    )
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/action-items')
@login_required
def ae_add_action_item(event_id: int):
    _require_level(6)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    description = request.form.get('description', '').strip()
    if not description:
        abort(400)
    assignee_id = int(request.form['assignee_id']) if request.form.get('assignee_id', '').strip() else None
    due_date_str = request.form.get('due_date', '').strip()
    due_date = date.fromisoformat(due_date_str) if due_date_str else None
    AdverseEventService.add_action_item(event, description, assignee_id, due_date, current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/action-items/<int:item_id>/complete')
@login_required
def ae_complete_action_item(event_id: int, item_id: int):
    _require_level(6)
    from app.models.adverse_event import AdverseEventActionItem
    item = AdverseEventActionItem.query.get_or_404(item_id)
    if item.adverse_event_id != event_id:
        abort(404)
    AdverseEventService.complete_action_item(item, request.form.get('notes'), current_user)
    return redirect(url_for('governance.ae_index', selected=event_id))


@bp.post('/adverse-events/<int:event_id>/close')
@login_required
def ae_close(event_id: int):
    _require_level(9)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    can_close, msg = AdverseEventService.can_close(event)
    if not can_close:
        abort(400, msg)
    AdverseEventService.transition(event, AEStatus.closed, request.form.get('notes'), current_user)
    return redirect(url_for('governance.ae_index'))


@bp.post('/adverse-events/<int:event_id>/void')
@login_required
def ae_void(event_id: int):
    _require_level(9)
    event = AdverseEventService.get_detail(event_id)
    if not event:
        abort(404)
    reason = request.form.get('reason', '').strip()
    if not reason:
        abort(400, 'A reason is required to void an event.')
    AdverseEventService.void(event, reason, current_user)
    return redirect(url_for('governance.ae_index'))


# ── Report ─────────────────────────────────────────────────────────────────

@bp.get('/adverse-events/report')
@login_required
def ae_report():
    _require_level(9)
    events = AdverseEventService.get_list()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Reference', 'Occurred', 'Reported', 'Type', 'Severity',
        'Involved Person', 'Title', 'Status', 'Triaged', 'RCA Required',
        'RCA Completed', 'Disclosure Required', 'Disclosure Completed',
        'Disclosure Notes',
        'Authority Notified', 'All Actions Complete', 'Closed',
    ])
    for e in events:
        writer.writerow([
            e.reference_no,
            e.occurred_at.strftime('%d/%m/%Y') if e.occurred_at else '',
            e.reported_at.strftime('%d/%m/%Y') if e.reported_at else '',
            e.event_type.value if e.event_type else '',
            e.severity.value if e.severity else '',
            e.involved_person_type.value if e.involved_person_type else '',
            e.title,
            e.status.value if e.status else '',
            e.triaged_at.strftime('%d/%m/%Y') if e.triaged_at else '',
            'Yes' if e.rca_required else 'No',
            e.rca_completed_at.strftime('%d/%m/%Y') if e.rca_completed_at else '',
            'Yes' if e.open_disclosure_required else 'No',
            e.open_disclosure_completed_at.strftime('%d/%m/%Y') if e.open_disclosure_completed_at else '',
            e.open_disclosure_notes or '',
            e.notified_authority.value if e.notified_authority and e.notified_authority.value != 'none' else '',
            'Yes' if AdverseEventService.all_actions_complete(e) else 'No',
            e.closed_at.strftime('%d/%m/%Y') if e.closed_at else '',
        ])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=adverse_events_register.csv'},
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_ae_filters() -> dict:
    f = {}
    if request.args.get('status'):
        f['status'] = request.args['status']
    if request.args.get('event_type'):
        f['event_type'] = request.args['event_type']
    if request.args.get('severity'):
        f['severity'] = request.args['severity']
    if request.args.get('search'):
        f['search'] = request.args['search']
    if request.args.get('show_voided') and has_governance_level(9):
        f['show_voided'] = True
    return f


def _parse_ae_form(form) -> dict | str:
    required = ('title', 'description', 'event_type', 'severity', 'involved_person_type', 'occurred_at')
    for field in required:
        if not form.get(field, '').strip():
            return f'Missing required field: {field}'
    try:
        event_type = EventType(form['event_type'])
        severity = SeverityGrade(form['severity'])
        involved_type = InvolvedPersonType(form['involved_person_type'])
    except ValueError as e:
        return str(e)

    return {
        'title': form['title'].strip(),
        'description': form['description'].strip(),
        'event_type': event_type,
        'severity': severity,
        'involved_person_type': involved_type,
        'patient_id': int(form['patient_id']) if form.get('patient_id', '').strip() else None,
        'external_name': form.get('external_name', '').strip() or None,
        'external_contact': form.get('external_contact', '').strip() or None,
        'immediate_actions': form.get('immediate_actions', '').strip() or None,
        'location': form.get('location', '').strip() or None,
        'occurred_at': _parse_datetime(form.get('occurred_at')),
        'notes': form.get('notes', '').strip() or None,
        'open_disclosure_required': bool(form.get('open_disclosure_required')),
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


def _get_cross_links(adverse_event_id: int):
    from app.models.adverse_event import RegisterCrossLink
    return RegisterCrossLink.query.filter_by(adverse_event_id=adverse_event_id).all()
