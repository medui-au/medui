"""Permanent usage record — see plans/usage_reporting_plan.md.

Three append-only tables holding no clinical content: one row per task a person
meant to do (not per web request), one row per call to an AI model, and the
permanent export pseudonyms. Excluded from the maintenance purge by design.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UsageEvent(db.Model):
    """One task: "opened a chart", "sent an SMS", "ran a care plan"."""
    __tablename__ = 'usage_events'

    id = db.Column(db.Integer, primary_key=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    duration_ms = db.Column(db.Integer)
    # Null when not known: API keys, and tasks imported from the access log.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    actor_kind = db.Column(db.String(12), nullable=False, default='user')  # user|unspecified|api_key|system
    role_at_time = db.Column(db.String(40))          # snapshotted: later role changes don't rewrite history
    task = db.Column(db.String(60), nullable=False, index=True)
    area = db.Column(db.String(30), nullable=False, index=True)
    is_ai = db.Column(db.Boolean, nullable=False, default=False)
    patient_linked = db.Column(db.Boolean, nullable=False, default=False)  # yes/no only — no patient reference
    outcome = db.Column(db.String(12), nullable=False, default='ok')        # ok|error|blocked|cancelled
    detail_json = db.Column(db.Text)                 # small structured extras, never content
    workstation = db.Column(db.String(64))
    app_version = db.Column(db.String(40))
    source = db.Column(db.String(40), nullable=False, default='live')      # live | import:<source>
    # Makes live capture and imports idempotent against each other,
    # e.g. 'run:4935', 'scribe:<user>:<session>', 'msg:12'.
    dedupe_key = db.Column(db.String(160), unique=True)
    quality = db.Column(db.String(12), nullable=False, default='exact')     # exact|inferred|unattributed

    ai_calls = db.relationship('UsageAICall', backref='event', lazy='select',
                               cascade='all, delete-orphan')


class UsageAICall(db.Model):
    """One call to an AI model (speech-to-text: one row per model per session)."""
    __tablename__ = 'usage_ai_calls'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('usage_events.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # inference|speech_to_text|diarization|...
    provider_name = db.Column(db.String(120))
    provider_is_local = db.Column(db.Boolean)
    model = db.Column(db.String(160), index=True)
    pipeline_id = db.Column(db.Integer)
    pipeline_name = db.Column(db.String(200))        # snapshotted — pipelines get renamed
    pipeline_classifier = db.Column(db.String(80))
    prompt_name = db.Column(db.String(200))
    system_prompt_version = db.Column(db.String(80))
    origin = db.Column(db.String(30))                # ai_panel|document_button|chatbot|scribe|library|...
    redaction_policy = db.Column(db.String(20))
    is_redacted = db.Column(db.Boolean)
    is_hcp_redacted = db.Column(db.Boolean)
    tokens_in = db.Column(db.Integer)
    tokens_out = db.Column(db.Integer)
    tokens_cached = db.Column(db.Integer)
    tokens_cache_write = db.Column(db.Integer)
    cost = db.Column(db.Float)
    model_ms = db.Column(db.Integer)                 # "query time"; summed per session for speech-to-text
    total_ms = db.Column(db.Integer)
    chunks = db.Column(db.Integer)                   # speech-to-text / diarization: chunks in the session
    prompt_chars = db.Column(db.Integer)
    response_chars = db.Column(db.Integer)
    privacy_verdict = db.Column(db.String(40))
    outcome = db.Column(db.String(12), nullable=False, default='ok')
    error_class = db.Column(db.String(40))
    pipeline_run_id = db.Column(db.Integer, index=True)   # kept after the run itself is purged
    exported_after = db.Column(db.Boolean, nullable=False, default=False)  # output later exported/sent
    quality = db.Column(db.String(12), nullable=False, default='exact')


class UsageUserLabel(db.Model):
    """Permanent export pseudonym: one practice-wide number per user.

    Assigned once in order of first appearance and never reused or renumbered.
    Exports show the number with the user's role: "Doctor 2", "Receptionist 5".
    """
    __tablename__ = 'usage_user_labels'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    number = db.Column(db.Integer, nullable=False, unique=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
