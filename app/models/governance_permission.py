from datetime import datetime, timezone
from app.extensions import db


class GovernancePermission(db.Model):
    """Per-user governance level override, independent of general security_level.

    A user's effective governance level = max(security_level, governance_level).
    Allows e.g. a senior receptionist (security_level=1) to triage/acknowledge
    complaints (governance_level=6) without elevating their general app access.
    """
    __tablename__ = 'governance_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    governance_level = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    granted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    granted_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], lazy='select')
    granted_by = db.relationship('User', foreign_keys=[granted_by_id], lazy='select')

    def __repr__(self):
        return f'<GovernancePermission user={self.user_id} level={self.governance_level}>'
