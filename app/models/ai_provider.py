from datetime import datetime, timezone
from app.extensions import db


class AIProviderPreset(db.Model):
    """Read-only seed table of known provider templates. Admins pick a preset to pre-fill the
    add-provider form; new entries can be added via flask seed providers without code changes."""
    __tablename__ = 'ai_provider_presets'

    id                      = db.Column(db.Integer, primary_key=True)
    provider_key            = db.Column(db.String(60), nullable=False, unique=True)
    display_name            = db.Column(db.String(120), nullable=False)
    # 'openai_compatible' | 'anthropic' | 'asr_whisper' | 'asr_deepgram'
    provider_type           = db.Column(db.String(40), nullable=False)
    base_url_default        = db.Column(db.String(500))
    is_local_default        = db.Column(db.Boolean, nullable=False, default=False)
    supports_model_fetching = db.Column(db.Boolean, nullable=False, default=False)
    # JSON list of model dicts for providers whose /models endpoint can't be queried
    static_models_json      = db.Column(db.Text)
    notes                   = db.Column(db.Text)
    sort_order              = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f'<AIProviderPreset {self.provider_key}>'


class AIProviderConfig(db.Model):
    __tablename__ = 'ai_provider_configs'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    provider_key     = db.Column(db.String(60), nullable=False, unique=True)
    # 'openai_compatible' | 'anthropic' | 'asr_whisper' | 'asr_deepgram'
    provider_type    = db.Column(db.String(40), nullable=False, default='openai_compatible')
    base_url         = db.Column(db.String(500), nullable=False)
    is_local         = db.Column(db.Boolean, nullable=False, default=False)
    is_enabled       = db.Column(db.Boolean, nullable=False, default=True)
    supports_model_fetching = db.Column(db.Boolean, nullable=False, default=False)
    # If set, overrides the default /models path when fetching the model list (e.g. OpenRouter ZDR)
    models_endpoint  = db.Column(db.String(500))
    # Fernet-encrypted API key stored in DB (use .api_key property, never access this directly)
    api_key_token_ref = db.Column(db.String(500))
    last_tested_at   = db.Column(db.DateTime)
    last_test_status = db.Column(db.String(20))   # 'ok' | 'fail'
    notes            = db.Column(db.Text)

    models = db.relationship('AIModel', backref='provider', lazy='dynamic',
                             cascade='all, delete-orphan')

    @property
    def api_key(self) -> str | None:
        if not self.api_key_token_ref:
            return None
        from app.utils.crypto import decrypt_secret
        return decrypt_secret(self.api_key_token_ref)

    @api_key.setter
    def api_key(self, plaintext: str | None) -> None:
        if plaintext:
            from app.utils.crypto import encrypt_secret
            self.api_key_token_ref = encrypt_secret(plaintext)
        else:
            self.api_key_token_ref = None

    def __repr__(self) -> str:
        return f'<AIProviderConfig {self.provider_key} local={self.is_local}>'


class AIModel(db.Model):
    __tablename__ = 'ai_models'

    id            = db.Column(db.Integer, primary_key=True)
    provider_id   = db.Column(db.Integer, db.ForeignKey('ai_provider_configs.id'), nullable=False)
    model_id      = db.Column(db.String(200), nullable=False)
    display_name  = db.Column(db.String(200))
    context_length = db.Column(db.Integer)
    is_enabled    = db.Column(db.Boolean, nullable=False, default=True)
    supports_vision = db.Column(db.Boolean, nullable=False, default=False)
    is_asr        = db.Column(db.Boolean, nullable=False, default=False)
    show_in_ai_assist = db.Column(db.Boolean, nullable=False, default=False)
    show_in_chatbot = db.Column(db.Boolean, nullable=False, default=False)
    # Admin hint for model selection: 'fast' | 'balanced' | 'quality'
    task_tier     = db.Column(db.String(20))
    is_recommended = db.Column(db.Boolean, nullable=False, default=False)
    notes         = db.Column(db.Text)
    # Extra request parameters (JSON object) sent with every request to this model,
    # e.g. {"reasoning_effort": "none"}; a pipeline step can override them (ADR-119).
    request_params = db.Column(db.Text)
    # ASR only, Deepgram only (ADR-151): ask the service to separate speakers on Scribe and
    # Quick Scribe chunks — 'latest', 'v2' or 'v1' (Deepgram's diarize_model); NULL is off.
    # Dictation never asks for it.
    speaker_turns = db.Column(db.String(10))

    __table_args__ = (
        db.UniqueConstraint('provider_id', 'model_id', name='uq_provider_model'),
    )

    def __repr__(self) -> str:
        return f'<AIModel {self.model_id}>'
