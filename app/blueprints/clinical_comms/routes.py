from flask import render_template, request, abort, jsonify, current_app
from flask_login import login_required, current_user

from . import bp
from app.services.clinical_service import ClinicalService
from app.services import patient_comms_service as _svc


def _get_patient(patient_id: int) -> dict:
    patient = ClinicalService.get_patient_demographics(patient_id)
    if not patient:
        abort(404)
    return patient


# ── Pages ─────────────────────────────────────────────────────────────────────

@bp.get('/')
@login_required
def choose_patient():
    """Comms without a patient: choose one first (ADR-093). Content handed over
    by the Library waits in the browser's session storage and fills in once the
    patient's Comms page opens."""
    return render_template(
        'clinical/search.html',
        search_heading='Choose the patient',
        search_note='The document you are sending opens in Comms once you choose the patient.',
        search_then='comms',
    )


@bp.get('/patient/<int:patient_id>')
@login_required
def patient_comms(patient_id: int):
    patient = _get_patient(patient_id)
    templates = _svc.list_templates()
    history = _svc.get_history(patient_id, limit=30)
    practice = _svc.practice_name()

    # Next appointment — formatted string from dedicated query
    next_appointment = ''
    try:
        from app.sql.query_loader import load_query, ReadOnlySession
        from flask import current_app
        with ReadOnlySession(current_app.config['BPSDB_URI']) as sess:
            rows = sess.execute(load_query('patient_next_appointment'), [patient_id])
            if rows:
                next_appointment = rows[0].get('AppointmentSummary') or ''
    except Exception as exc:
        current_app.logger.warning('comms: next_appointment query failed: %s', exc)

    default_subject = f'Email from {practice}'
    user_signature = current_user.email_signature or ''

    return render_template(
        'clinical_comms/patient_comms.html',
        patient=patient,
        patient_id=patient_id,
        templates=templates,
        history=history,
        practice_name=practice,
        default_subject=default_subject,
        user_signature=user_signature,
        next_appointment=next_appointment,
    )


# ── API: send ─────────────────────────────────────────────────────────────────

@bp.post('/api/patient/<int:patient_id>/send')
@login_required
def api_send(patient_id: int):
    _get_patient(patient_id)
    data = request.get_json(silent=True) or {}
    channel = data.get('channel', 'email')

    try:
        if channel == 'email':
            msg = _svc.send_email(
                patient_id=patient_id,
                to_address=data.get('to_address', ''),
                subject=data.get('subject', ''),
                body=data.get('body', ''),
                is_ai_generated=bool(data.get('is_ai_generated', False)),
            )
        elif channel == 'sms':
            msg = _svc.send_sms(
                patient_id=patient_id,
                mobile_number=data.get('to_address', ''),
                body=data.get('body', ''),
                is_ai_generated=bool(data.get('is_ai_generated', False)),
            )
        else:
            return jsonify({'ok': False, 'error': 'Unknown channel'}), 400

        return jsonify({
            'ok': msg.status.value == 'sent',
            'status': msg.status.value,
            'msg_id': msg.id,
            'error': msg.error_message,
        })
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── API: draft ────────────────────────────────────────────────────────────────

@bp.post('/api/patient/<int:patient_id>/draft')
@login_required
def api_draft(patient_id: int):
    _get_patient(patient_id)
    data = request.get_json(silent=True) or {}
    msg = _svc.save_draft(
        patient_id=patient_id,
        channel=data.get('channel', 'email'),
        to_address=data.get('to_address', ''),
        body=data.get('body', ''),
        subject=data.get('subject', ''),
    )
    return jsonify({'ok': True, 'msg_id': msg.id})


# ── API: history ──────────────────────────────────────────────────────────────

@bp.get('/api/patient/<int:patient_id>/history')
@login_required
def api_history(patient_id: int):
    _get_patient(patient_id)
    history = _svc.get_history(patient_id, limit=50)
    return render_template(
        'clinical_comms/partials/comms_history.html',
        history=history,
        patient_id=patient_id,
    )


# ── API: retry ────────────────────────────────────────────────────────────────

@bp.post('/api/patient/<int:patient_id>/<int:msg_id>/retry')
@login_required
def api_retry(patient_id: int, msg_id: int):
    _get_patient(patient_id)
    msg = _svc.retry(msg_id)
    return jsonify({
        'ok': msg.status.value == 'sent',
        'status': msg.status.value,
        'msg_id': msg.id,
        'error': msg.error_message,
    })


# ── API: revoke ───────────────────────────────────────────────────────────────

@bp.post('/api/patient/<int:patient_id>/<int:msg_id>/revoke')
@login_required
def api_revoke(patient_id: int, msg_id: int):
    _get_patient(patient_id)
    _svc.revoke(msg_id)
    return jsonify({'ok': True})


# ── API: PIT export ───────────────────────────────────────────────────────────

@bp.post('/api/patient/<int:patient_id>/<int:msg_id>/export-pit')
@login_required
def api_export_pit(patient_id: int, msg_id: int):
    patient = _get_patient(patient_id)
    ok = _svc.export_pit(msg_id, patient)
    return jsonify({'ok': ok})


@bp.post('/api/patient/<int:patient_id>/file-bp')
@login_required
def api_file_bp(patient_id: int):
    """File a document into the patient's Best Practice record without sending it
    (ADR-093) — e.g. a Library document handed over to Comms."""
    from datetime import datetime
    from app.utils.pit_utils import send_as_pit
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'Nothing to file.'}), 400
    label = (data.get('label') or '').strip()[:200] or f'[DOCUMENT] {datetime.now().strftime("%d-%m-%Y")}'
    patient = _get_patient(patient_id)
    try:
        ok = send_as_pit(patient=patient, pit_label=label, body=content, user=current_user)
    except Exception as exc:  # delivery to the BP shared folder; report, don't crash
        current_app.logger.error('Comms file-to-BP failed: %s', type(exc).__name__)
        return jsonify({'ok': False, 'error': 'Filing failed — see the server log.'}), 500
    return jsonify({'ok': bool(ok)})


# ── API: preview ─────────────────────────────────────────────────────────────


@bp.post('/api/preview')
@login_required
def api_preview():
    data = request.get_json(silent=True) or {}
    body = data.get('body', '')
    from app.services.email_body_renderer import render
    result = render(body)
    return jsonify({'html': result.html})


# ── API: templates ────────────────────────────────────────────────────────────

@bp.get('/api/templates')
@login_required
def api_templates_list():
    channel = request.args.get('channel')
    templates = _svc.list_templates(channel=channel)
    return jsonify([
        {
            'id': t.id,
            'name': t.name,
            'channel': t.channel.value if t.channel else None,
            'subject': t.subject or '',
            'body': t.body,
        }
        for t in templates
    ])


@bp.post('/api/templates')
@login_required
def api_templates_create():
    data = request.get_json(silent=True) or {}
    t = _svc.create_template(
        name=data.get('name', 'Template'),
        channel=data.get('channel'),
        subject=data.get('subject', ''),
        body=data.get('body', ''),
        sort_order=int(data.get('sort_order', 0)),
    )
    return jsonify({'ok': True, 'id': t.id}), 201


@bp.put('/api/templates/<int:template_id>')
@login_required
def api_templates_update(template_id: int):
    data = request.get_json(silent=True) or {}
    _svc.update_template(template_id, **data)
    return jsonify({'ok': True})


@bp.delete('/api/templates/<int:template_id>')
@login_required
def api_templates_delete(template_id: int):
    _svc.delete_template(template_id)
    return jsonify({'ok': True})
