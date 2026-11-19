from datetime import datetime, timedelta, timezone
from app.extensions import db
from app.utils.encrypted_type import EncryptedText


class ConsultationTranscript(db.Model):
    """Voice scribe transcripts encrypted at rest, 30-day auto-expiry.

    Written incrementally (is_final=False) during a consultation;
    marked final when the clinician confirms the session is complete.
    """
    __tablename__ = 'consultation_transcripts'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'patient_id', 'user_id',
                            name='uq_transcript_session'),
    )

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    session_id = db.Column(db.String(64), nullable=True)
    transcript_text = db.Column(EncryptedText(), nullable=True)
    is_final = db.Column(db.Boolean, nullable=False, default=False)
    extra_data_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='transcripts', lazy=True)

    @staticmethod
    def expiry_date() -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=30)

    def to_dict(self, include_transcript: bool = False) -> dict:
        d = {
            'id': self.id,
            'patient_id': self.patient_id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'is_final': self.is_final,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }
        if include_transcript:
            d['transcript_text'] = self.transcript_text
        return d

    def __repr__(self) -> str:
        return f'<ConsultationTranscript #{self.id} patient={self.patient_id} final={self.is_final}>'
