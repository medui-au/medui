import enum
from datetime import datetime, timezone
from app.extensions import db


class RedactionPolicy(str, enum.Enum):
    redact_all = 'redact_all'        # PII + HCP stripped; cloud-safe
    redact_pii_only = 'redact_pii_only'  # patient PII only; local providers only
    redact_none = 'redact_none'      # no redaction; local providers only


class PipelineStatus(str, enum.Enum):
    draft = 'draft'
    active = 'active'
    archived = 'archived'


class RunStatus(str, enum.Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    cancelled = 'cancelled'


class Pipeline(db.Model):
    __tablename__ = 'pipelines'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.Enum(PipelineStatus), nullable=False, default=PipelineStatus.draft)
    redaction_policy = db.Column(
        db.Enum(RedactionPolicy), nullable=False, default=RedactionPolicy.redact_all
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    classifier = db.Column(db.String(80), nullable=True, index=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    show_in_topnav = db.Column(db.Boolean, nullable=False, default=False)

    steps = db.relationship('PipelineStep', backref='pipeline', lazy='dynamic',
                            order_by='PipelineStep.step_order',
                            cascade='all, delete-orphan')
    runs = db.relationship('PipelineRun', backref='pipeline', lazy='dynamic')

    @property
    def is_archived(self) -> bool:
        """Archived pipelines are hidden from the designer list and never run."""
        return self.status == PipelineStatus.archived

    def __repr__(self) -> str:
        return f'<Pipeline {self.name} [{self.redaction_policy}]>'


class PipelineStep(db.Model):
    __tablename__ = 'pipeline_steps'

    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipelines.id'), nullable=False)
    step_order = db.Column(db.Integer, nullable=False, default=0)
    node_type = db.Column(db.String(80), nullable=False)
    # JSON config for this node (prompt_id, bundle_id, model_id, routing rules, etc.)
    config_json = db.Column(db.Text, nullable=False, default='{}')
    label = db.Column(db.String(200))

    def __repr__(self) -> str:
        return f'<PipelineStep {self.node_type} #{self.step_order}>'


class PipelineRun(db.Model):
    __tablename__ = 'pipeline_runs'

    id = db.Column(db.Integer, primary_key=True)
    run_uuid = db.Column(db.String(36), nullable=True, index=True, unique=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipelines.id'), nullable=False)
    patient_id = db.Column(db.Integer, index=True)  # BPSDB InternalID
    initiated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.Enum(RunStatus), nullable=False, default=RunStatus.pending, index=True)
    current_step = db.Column(db.Integer, default=0)

    # Set from pipeline.redaction_policy at run start; immutable thereafter
    redaction_policy = db.Column(db.Enum(RedactionPolicy), nullable=False)
    # Resolved at run end by _finalise_run — nullable = honest about pre-Gen5 runs
    is_redacted = db.Column(db.Boolean)
    is_hcp_redacted = db.Column(db.Boolean)

    # model_is_local sent from UI (Improvement 1); validated by InferenceNode
    model_is_local = db.Column(db.Boolean)

    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    # WorkflowContext state at run start
    context_json = db.Column(db.Text, nullable=False, default='{}')
    # Array of full context snapshots, one per completed step
    step_snapshots_json = db.Column(db.Text, nullable=False, default='[]')
    # Final rendered output
    output_json = db.Column(db.Text)

    def __repr__(self) -> str:
        return f'<PipelineRun #{self.id} {self.status}>'
