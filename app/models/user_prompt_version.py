"""Earlier versions of user prompts (this edition only; see seed_resync_service)."""
from datetime import datetime, timezone
from app.extensions import db


class UserPromptVersion(db.Model):
    """Earlier text of a user prompt, saved before the seed resync replaces it, so
    the change can be reverted. One row per replaced version."""
    __tablename__ = 'user_prompt_versions'

    id                  = db.Column(db.Integer, primary_key=True)
    user_prompt_id      = db.Column(db.Integer, db.ForeignKey('user_prompts.id', ondelete='CASCADE'),
                                    nullable=False, index=True)
    version             = db.Column(db.Integer, nullable=False)
    name                = db.Column(db.String(200), nullable=False)
    description         = db.Column(db.Text)
    prompt_text         = db.Column(db.Text, nullable=False)
    system_prompt_name  = db.Column(db.String(200))
    classifier          = db.Column(db.String(80))
    temperature         = db.Column(db.Float)
    max_tokens          = db.Column(db.Integer)
    reason              = db.Column(db.String(200))
    saved_at            = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    saved_by_id         = db.Column(db.Integer, db.ForeignKey('users.id'))

    __table_args__ = (db.UniqueConstraint('user_prompt_id', 'version'),)

    def __repr__(self) -> str:
        return f'<UserPromptVersion {self.name} v{self.version}>'
