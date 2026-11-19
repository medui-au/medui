"""A user's report that something identifying got through to the AI (ADR-115).

The reported text is held as positions in the run's stored prompt as sent, never
copied: the run record already holds it. An administrator adds it to future
redactions or dismisses it on the run's Privacy hits page.
"""
from datetime import datetime, timezone

from app.extensions import db

STATUSES = ('open', 'added', 'dismissed')


class PrivacyReport(db.Model):
    __tablename__ = 'privacy_reports'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id'), nullable=False, index=True)
    reported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reported_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    span_start = db.Column(db.Integer, nullable=False)
    span_end = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(200))
    status = db.Column(db.String(16), nullable=False, default='open', index=True)
    handled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    handled_at = db.Column(db.DateTime)
    outcome = db.Column(db.String(200))         # which list it went on, or why it was dismissed
