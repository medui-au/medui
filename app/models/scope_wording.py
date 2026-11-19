from datetime import datetime, timezone
from app.extensions import db


class ScopeWording(db.Model):
    """Append-only versioned scope wordings (ADR-087).

    kind 'instruction': a boundary paragraph placed before a system prompt,
    chosen per system prompt or per workflow step by `key` (record, scribe,
    correspondence, general…). 'none' is not a row: it means no instruction.
    kind 'notice' is reserved for the on-screen notices (guardrails step 4).
    Never update a row's text — insert key/version + 1 and deactivate the old one,
    so a run's recorded key + version always names the text it was given.
    """
    __tablename__ = 'scope_wordings'
    __table_args__ = (db.UniqueConstraint('kind', 'key', 'version', name='uq_scope_wordings_kind_key_version'),)

    id            = db.Column(db.Integer, primary_key=True)
    kind          = db.Column(db.String(20), nullable=False, default='instruction')
    key           = db.Column(db.String(40), nullable=False)
    label         = db.Column(db.String(120), nullable=False)
    text          = db.Column(db.Text, nullable=False)
    version       = db.Column(db.Integer, nullable=False, default=1)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self) -> str:
        return f'<ScopeWording {self.kind}:{self.key} v{self.version}>'
