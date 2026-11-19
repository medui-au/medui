import enum
from datetime import datetime, timezone
from app.extensions import db


class MessageChannel(str, enum.Enum):
    email = 'email'
    sms = 'sms'
    both = 'both'


class MessageStatus(str, enum.Enum):
    draft = 'draft'
    sent = 'sent'
    failed = 'failed'
    revoked = 'revoked'


class PatientMessage(db.Model):
    __tablename__ = 'patient_messages'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    channel = db.Column(db.Enum(MessageChannel), nullable=False)
    to_address = db.Column(db.String(300))
    subject = db.Column(db.String(500))
    # Body encrypted at rest with SCRIBE_ENCRYPTION_KEY
    body_encrypted = db.Column(db.LargeBinary)
    status = db.Column(db.Enum(MessageStatus), nullable=False, default=MessageStatus.draft)
    is_ai_generated = db.Column(db.Boolean, nullable=False, default=False)
    pipeline_run_id = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    # BP export tracking
    bp_exported    = db.Column(db.Boolean, nullable=False, default=False)
    bp_exported_at = db.Column(db.DateTime)

    # Soft-delete / revocation
    revoked_at     = db.Column(db.DateTime)
    revoked_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'))

    created_by  = db.relationship('User', foreign_keys=[created_by_id], lazy='select')
    revoked_by  = db.relationship('User', foreign_keys=[revoked_by_id], lazy='select')

    @property
    def body(self) -> str | None:
        if not self.body_encrypted:
            return None
        from app.utils.crypto import decrypt_secret
        return decrypt_secret(self.body_encrypted.decode('utf-8'))

    @body.setter
    def body(self, value: str | None) -> None:
        if value is None:
            self.body_encrypted = None
        else:
            from app.utils.crypto import encrypt_secret
            self.body_encrypted = encrypt_secret(value).encode('utf-8')

    def __repr__(self) -> str:
        return f'<PatientMessage #{self.id} {self.channel} {self.status}>'


class MessageTemplate(db.Model):
    __tablename__ = 'message_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    channel = db.Column(db.Enum(MessageChannel))
    subject = db.Column(db.String(500))
    body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f'<MessageTemplate {self.name}>'
