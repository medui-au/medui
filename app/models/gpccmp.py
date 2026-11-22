"""GPCCMP sessions (ADR-173): the GP's plan decisions for one plan, before any AI step.

The decisions are a structured record of what the GP decided: plan type, issues, modifiers,
directions and services per issue, review interval and consent. Phase 4 hands them to the AI as
data it may not contradict or add to, and links the run and the draft care plan here.
"""
import enum
from datetime import datetime, timezone

from app.extensions import db
from app.utils.encrypted_type import EncryptedText


def _now():
    return datetime.now(timezone.utc)


class SessionStatus(str, enum.Enum):
    draft = 'draft'          # being filled in
    ready = 'ready'          # the GP confirmed the decisions ("Proceed with GPCCMP")
    drafted = 'drafted'      # the AI draft exists (phase 4)
    abandoned = 'abandoned'


class GpccmpSession(db.Model):
    __tablename__ = 'gpccmp_sessions'

    id                  = db.Column(db.Integer, primary_key=True)
    patient_id          = db.Column(db.Integer, nullable=False, index=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_type           = db.Column(db.String(10), nullable=False, default='prepare')   # prepare | review
    status              = db.Column(db.Enum(SessionStatus), nullable=False, default=SessionStatus.draft)
    decisions_json      = db.Column(EncryptedText())                   # the form, as JSON text
    protocol_version_id = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'))
    pipeline_run_id     = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id'))
    careplan_id         = db.Column(db.Integer, db.ForeignKey('careplans.id'))
    check_results       = db.Column(db.JSON)
    created_at          = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at          = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    confirmed_at        = db.Column(db.DateTime)

    user             = db.relationship('User')
    protocol_version = db.relationship('ProtocolVersion')
