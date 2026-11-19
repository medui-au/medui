from datetime import datetime, timezone
from app.extensions import db


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'

    id = db.Column(db.Integer, primary_key=True)
    # HMAC key for TokenVault, stable across every turn in this session —
    # separate from id so redaction consistency doesn't depend on a leakable PK.
    token_key = db.Column(db.String(64), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, nullable=True, index=True)  # BPSDB InternalID; NULL = generic (no-patient) chat
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipelines.id'), nullable=False)
    chatbot_model_id_override = db.Column(db.Integer, db.ForeignKey('ai_models.id'))
    title = db.Column(db.String(200))
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    # Soft-delete for the previous-chats sidebar — deliberately separate from
    # is_archived, which already means something else ("not the currently
    # active session, but still shown in the list"). A hard delete would also
    # need to cascade chat_generated_files (no ON DELETE rule on that FK
    # today), so hiding is both simpler and avoids that failure mode entirely.
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic',
                               order_by='ChatMessage.created_at',
                               cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<ChatSession #{self.id} patient={self.patient_id}>'


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # 'user' | 'assistant' | 'error'
    content = db.Column(db.Text, nullable=False)  # de-redacted display text
    pipeline_run_id = db.Column(db.Integer, db.ForeignKey('pipeline_runs.id'))  # null for role='user'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    pipeline_run = db.relationship('PipelineRun')

    def __repr__(self) -> str:
        return f'<ChatMessage #{self.id} {self.role}>'


class ChatSavedPrompt(db.Model):
    """User-scoped reusable prompt snippets for the chatbot's Save/Insert prompt buttons.
    Not patient-scoped — a saved prompt is reusable across every patient's chat."""
    __tablename__ = 'chat_saved_prompts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    description = db.Column(db.String(200), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f'<ChatSavedPrompt #{self.id} {self.description!r}>'


class ChatGeneratedFile(db.Model):
    __tablename__ = 'chat_generated_files'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(100), nullable=False, default='text/plain')
    content = db.Column(db.Text, nullable=False)  # file body, DB-stored — matches Document.body
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    session = db.relationship('ChatSession')

    def __repr__(self) -> str:
        return f'<ChatGeneratedFile #{self.id} {self.filename}>'
