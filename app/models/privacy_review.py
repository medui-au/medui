"""An administrator's verdict on what the pre-send privacy check found in one run (ADR-120).

One row per run, made when the run is first reviewed on its Privacy hits page. It holds the
verdict and a comment, never the prompt or the matched words: those stay in the run record,
which the page reads them from. The comment is encrypted, as free text about a patient's
record can identify them. The row goes when the run is purged (ON DELETE CASCADE): without
the prompt there is nothing left to review.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.utils.encrypted_type import EncryptedText

DISPOSITIONS = ('true_leak', 'false_positive', 'acceptable')
SEVERITIES = ('none', 'minor', 'serious')


class PrivacyReview(db.Model):
    __tablename__ = 'privacy_reviews'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id', ondelete='CASCADE'),
                       nullable=False, unique=True, index=True)
    disposition = db.Column(db.String(20), nullable=False)
    severity = db.Column(db.String(10))
    comment = db.Column(EncryptedText())
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])
