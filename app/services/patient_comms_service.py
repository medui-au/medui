"""PatientCommsService — send, draft, revoke, history, PIT export for patient messages."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from flask import current_app
from flask_login import current_user
from sqlalchemy import desc

from app.extensions import db
from app.models.patient_message import (
    PatientMessage, MessageChannel, MessageStatus, MessageTemplate,
)
from app.models.system_setting import SystemSetting


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(patient_id: int, to_address: str, subject: str, body: str,
               is_ai_generated: bool = False) -> PatientMessage:
    """Render body → HTML, send via email_service, persist record."""
    from app.services.email_body_renderer import render
    from app.services import email_service

    result = render(body)

    msg = PatientMessage(
        patient_id=patient_id,
        channel=MessageChannel.email,
        to_address=to_address,
        subject=subject,
        is_ai_generated=is_ai_generated,
        created_by_id=current_user.id,
        status=MessageStatus.draft,
    )
    msg.body = body
    db.session.add(msg)
    db.session.flush()  # get id before sending

    try:
        email_service.send(
            to_address=to_address,
            subject=subject,
            body=result.html,
            use_html=True,
        )
        msg.status = MessageStatus.sent
        msg.sent_at = _now()
        current_app.logger.info(
            'patient_comms: email sent patient_id=%s msg_id=%s to=%s',
            patient_id, msg.id, to_address,
        )
    except Exception as exc:
        msg.status = MessageStatus.failed
        msg.error_message = str(exc)
        current_app.logger.warning(
            'patient_comms: email failed patient_id=%s: %s', patient_id, exc,
        )

    db.session.commit()
    return msg


def send_sms(patient_id: int, mobile_number: str, body: str,
             is_ai_generated: bool = False) -> PatientMessage:
    """Send SMS via sms_service and persist record."""
    from app.services import sms_service

    msg = PatientMessage(
        patient_id=patient_id,
        channel=MessageChannel.sms,
        to_address=mobile_number,
        is_ai_generated=is_ai_generated,
        created_by_id=current_user.id,
        status=MessageStatus.draft,
    )
    msg.body = body
    db.session.add(msg)
    db.session.flush()

    try:
        sms_service.send(mobile_number=mobile_number, message=body)
        msg.status = MessageStatus.sent
        msg.sent_at = _now()
        current_app.logger.info(
            'patient_comms: sms sent patient_id=%s msg_id=%s to=%s',
            patient_id, msg.id, mobile_number,
        )
    except Exception as exc:
        msg.status = MessageStatus.failed
        msg.error_message = str(exc)
        current_app.logger.warning(
            'patient_comms: sms failed patient_id=%s: %s', patient_id, exc,
        )

    db.session.commit()
    return msg


# ── Draft ─────────────────────────────────────────────────────────────────────

def save_draft(patient_id: int, channel: str, to_address: str,
               body: str, subject: str = '') -> PatientMessage:
    msg = PatientMessage(
        patient_id=patient_id,
        channel=MessageChannel(channel),
        to_address=to_address,
        subject=subject or None,
        created_by_id=current_user.id,
        status=MessageStatus.draft,
    )
    msg.body = body
    db.session.add(msg)
    db.session.commit()
    return msg


# ── History ───────────────────────────────────────────────────────────────────

def get_history(patient_id: int, limit: int = 50) -> list[PatientMessage]:
    return (PatientMessage.query
            .filter_by(patient_id=patient_id)
            .order_by(desc(PatientMessage.created_at))
            .limit(limit)
            .all())


def get_message(msg_id: int) -> PatientMessage | None:
    return PatientMessage.query.get(msg_id)


# ── Retry ─────────────────────────────────────────────────────────────────────

def retry(msg_id: int) -> PatientMessage:
    msg = PatientMessage.query.get_or_404(msg_id)
    if msg.channel == MessageChannel.email:
        return send_email(
            msg.patient_id, msg.to_address, msg.subject or '', msg.body or '',
            is_ai_generated=msg.is_ai_generated,
        )
    return send_sms(
        msg.patient_id, msg.to_address, msg.body or '',
        is_ai_generated=msg.is_ai_generated,
    )


# ── Revoke ────────────────────────────────────────────────────────────────────

def revoke(msg_id: int) -> PatientMessage:
    msg = PatientMessage.query.get_or_404(msg_id)
    msg.status = MessageStatus.revoked
    msg.revoked_at = _now()
    msg.revoked_by_id = current_user.id
    db.session.commit()
    return msg


# ── PIT export ────────────────────────────────────────────────────────────────

def export_pit(msg_id: int, patient: dict) -> bool:
    """Export message body as PIT investigation result. Returns True on success."""
    msg = PatientMessage.query.get_or_404(msg_id)
    from app.utils.pit_utils import send_as_pit

    label = 'Patient Message'
    if msg.channel == MessageChannel.email and msg.subject:
        label = msg.subject
    elif msg.channel == MessageChannel.sms:
        label = 'Patient SMS'

    ok = send_as_pit(patient=patient, pit_label=label, body=msg.body or '', user=current_user)
    if ok:
        msg.bp_exported = True
        msg.bp_exported_at = _now()
        db.session.commit()
    return ok


# ── Templates ─────────────────────────────────────────────────────────────────

def list_templates(channel: str | None = None) -> list[MessageTemplate]:
    q = MessageTemplate.query.filter_by(is_active=True)
    if channel:
        q = q.filter(
            (MessageTemplate.channel == channel) |
            (MessageTemplate.channel == None)  # noqa: E711
        )
    return q.order_by(MessageTemplate.sort_order, MessageTemplate.name).all()


def create_template(name: str, channel: str | None, subject: str,
                    body: str, sort_order: int = 0) -> MessageTemplate:
    t = MessageTemplate(
        name=name,
        channel=MessageChannel(channel) if channel else None,
        subject=subject or None,
        body=body,
        sort_order=sort_order,
    )
    db.session.add(t)
    db.session.commit()
    return t


def update_template(template_id: int, **kwargs: Any) -> MessageTemplate:
    t = MessageTemplate.query.get_or_404(template_id)
    for k, v in kwargs.items():
        if k == 'channel':
            v = MessageChannel(v) if v else None
        setattr(t, k, v)
    db.session.commit()
    return t


def delete_template(template_id: int) -> None:
    t = MessageTemplate.query.get_or_404(template_id)
    t.is_active = False
    db.session.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def practice_name() -> str:
    return SystemSetting.get('general.practice_name', 'The Practice')
