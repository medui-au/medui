from datetime import datetime, timezone
from app.extensions import db


class ScribeUsage(db.Model):
    """One row per scribe recording session, kept indefinitely.

    For analysing how the scribe is used — who, when, how much, and with which
    speech-to-text model. Holds no transcript text and no patient key, so it
    is not covered by the 30-day transcript expiry or the maintenance purge.
    Written by the transcript save (voice routes) alongside the transcript.
    """
    __tablename__ = 'scribe_usage'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'session_id', name='uq_scribe_usage_session'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(64), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc), index=True)
    last_saved_at = db.Column(db.DateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))
    chunks = db.Column(db.Integer, nullable=False, default=0)
    char_count = db.Column(db.Integer, nullable=False, default=0)
    # First chunk's model, and {model: {"chunks": n, "local": bool}}.
    asr_model_first = db.Column(db.String(120))
    asr_models_json = db.Column(db.Text)
    is_final = db.Column(db.Boolean, nullable=False, default=False)
