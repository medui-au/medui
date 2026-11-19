import json
from app.extensions import db


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value_json = db.Column(db.Text, nullable=False, default='null')
    description = db.Column(db.String(300))

    @property
    def value(self):
        return json.loads(self.value_json)

    @value.setter
    def value(self, v):
        self.value_json = json.dumps(v)

    @classmethod
    def get(cls, key: str, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key: str, value, description: str | None = None) -> None:
        row = cls.query.filter_by(key=key).first()
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = value
        if description:
            row.description = description
        db.session.commit()

    def __repr__(self) -> str:
        return f'<SystemSetting {self.key}>'
