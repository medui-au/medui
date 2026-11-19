from datetime import datetime, timezone
from app.extensions import db


class SystemPrompt(db.Model):
    """Append-only versioned system prompts. Never update a row — call PromptService.edit()
    which deactivates the current version and inserts a new row with version + 1."""
    __tablename__ = 'system_prompts'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    prompt_text   = db.Column(db.Text, nullable=False)
    description   = db.Column(db.Text)
    version       = db.Column(db.Integer, nullable=False, default=1)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    is_default    = db.Column(db.Boolean, nullable=False, default=False)
    # Scope instruction placed before this prompt (ADR-087): a ScopeWording key,
    # 'none', or NULL for the practice default (Setup → AI scope).
    scope_key     = db.Column(db.String(40))
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self) -> str:
        return f'<SystemPrompt {self.name} v{self.version}>'


class UserPrompt(db.Model):
    """Directly editable prompt templates. `show_in_assistant=True` surfaces the prompt
    in the AI assistant quick-select panel. System prompt is resolved by name at runtime
    (chain: pipeline step override → user_prompt.system_prompt_name → global default)."""
    __tablename__ = 'user_prompts'

    id                  = db.Column(db.Integer, primary_key=True)
    name                = db.Column(db.String(200), nullable=False)
    description         = db.Column(db.Text)
    prompt_text         = db.Column(db.Text, nullable=False)
    # Resolved at runtime: SystemPrompt.query.filter_by(name=..., is_active=True).first()
    system_prompt_name  = db.Column(db.String(200))
    default_model_id    = db.Column(db.Integer, db.ForeignKey('ai_models.id'))
    classifier          = db.Column(db.String(80), nullable=True, index=True)
    show_in_assistant   = db.Column(db.Boolean, nullable=False, default=False)
    temperature         = db.Column(db.Float)
    max_tokens          = db.Column(db.Integer)
    is_active           = db.Column(db.Boolean, nullable=False, default=True)
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id       = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self) -> str:
        return f'<UserPrompt {self.name}>'
