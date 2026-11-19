import json
from datetime import datetime, timezone
from app.extensions import db


class UserPreference(db.Model):
    """One user's value for one personal setting (ADR-085).

    Which keys exist, their types, defaults and labels live in code
    (app/services/user_settings_service.py), not here: this table only holds
    the values users have chosen. Practice defaults and locks are SystemSettings.
    """
    __tablename__ = 'user_preferences'
    __table_args__ = (db.UniqueConstraint('user_id', 'key', name='uq_user_preferences_user_key'),)

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    key        = db.Column(db.String(120), nullable=False)
    value_json = db.Column(db.Text, nullable=False, default='null')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    @property
    def value(self):
        return json.loads(self.value_json)

    @value.setter
    def value(self, v):
        self.value_json = json.dumps(v)

    def __repr__(self) -> str:
        return f'<UserPreference u{self.user_id} {self.key}>'
