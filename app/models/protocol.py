"""Practice protocols (ADR-171): the practice's selectable target options per measure, with the
guidelines behind them and a default rule over coded conditions, and its wording modules per
condition. Owned by the practice; any administrator edits a draft version and approves it.

Phase 1 of the GPCCMP plan.
A protocol holds the practice's content only. Patients' own targets (PatientTarget, ADR-172) are
set by their GP; nothing here records a judgement about a patient.
"""
import enum
from datetime import datetime, timezone

from app.extensions import db
from app.utils.encrypted_type import EncryptedText


def _now():
    return datetime.now(timezone.utc)


class ProtocolStatus(str, enum.Enum):
    draft = 'draft'
    approved = 'approved'
    retired = 'retired'


class MeasureScope(str, enum.Enum):
    protocol = 'protocol'        # part of the GPCCMP protocol
    individual = 'individual'    # set by a GP for one patient only (decision 11)


class ProtocolMeasure(db.Model):
    """What a target is about (BP, LDL-C, HbA1c…). Not versioned: the options are."""
    __tablename__ = 'protocol_measures'

    id            = db.Column(db.Integer, primary_key=True)
    key           = db.Column(db.String(40), unique=True, nullable=False)
    label         = db.Column(db.String(100), nullable=False)
    unit          = db.Column(db.String(30))
    token_key     = db.Column(db.String(40))       # careplan_result_tokens.key, for the latest value
    scope         = db.Column(db.Enum(MeasureScope), nullable=False, default=MeasureScope.protocol)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    active        = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, default=_now)


class ProtocolVersion(db.Model):
    __tablename__ = 'protocol_versions'

    id              = db.Column(db.Integer, primary_key=True)
    version         = db.Column(db.Integer, nullable=False, unique=True)
    status          = db.Column(db.Enum(ProtocolStatus), nullable=False, default=ProtocolStatus.draft)
    change_note     = db.Column(db.Text)
    copied_from_id  = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'))
    approved_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at     = db.Column(db.DateTime)
    review_due_on   = db.Column(db.Date)
    created_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at      = db.Column(db.DateTime, default=_now)

    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    options     = db.relationship('ProtocolOption', backref='protocol_version', cascade='all, delete-orphan',
                                  order_by='ProtocolOption.priority')
    modules     = db.relationship('ProtocolModule', backref='protocol_version', cascade='all, delete-orphan',
                                  order_by='ProtocolModule.display_order')
    prevention  = db.relationship('ProtocolPreventionRule', backref='protocol_version',
                                  cascade='all, delete-orphan', order_by='ProtocolPreventionRule.display_order')


class ProtocolOption(db.Model):
    """One selectable target for a measure, e.g. LDL-C '< 1.4 mmol/L and ≥ 50% reduction'.

    default_rule (JSON) over the Disease Profile flags decides which option a GP sees
    preselected: {"any": [flags]}, {"all": [flags]}, {"none": [flags]} (combined with AND), or
    {"always": true} for a fallback. Null: never preselected. Options are tried by priority; the
    first whose rule matches is the default. gp_sets: the target is left for the GP to set."""
    __tablename__ = 'protocol_options'

    id            = db.Column(db.Integer, primary_key=True)
    version_id    = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'), nullable=False, index=True)
    measure_id    = db.Column(db.Integer, db.ForeignKey('protocol_measures.id'), nullable=False)
    code          = db.Column(db.String(60), nullable=False)
    label         = db.Column(db.String(200), nullable=False)
    plan_wording  = db.Column(db.Text)
    patient_group = db.Column(db.String(300))
    default_rule  = db.Column(db.JSON)
    priority      = db.Column(db.Integer, nullable=False, default=100)
    gp_sets       = db.Column(db.Boolean, nullable=False, default=False)
    rationale     = db.Column(db.Text)

    measure   = db.relationship('ProtocolMeasure')
    citations = db.relationship('ProtocolOptionCitation', backref='option', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('version_id', 'code', name='uq_protocol_option_code'),)


class ProtocolOptionCitation(db.Model):
    __tablename__ = 'protocol_option_citations'

    id           = db.Column(db.Integer, primary_key=True)
    option_id    = db.Column(db.Integer, db.ForeignKey('protocol_options.id'), nullable=False, index=True)
    guideline_id = db.Column(db.Integer, db.ForeignKey('careplan_guidelines.id'), nullable=False)
    section_ref  = db.Column(db.String(200))
    quote        = db.Column(db.Text)

    guideline = db.relationship('CareplanGuideline')


class ProtocolModule(db.Model):
    """The practice's wording for one condition: goals, measures, monitoring, standard services,
    patient information, safety-netting and 'For the GP' reference text. No targets (those are
    options) and no named medicines or doses in patient text (decision 7)."""
    __tablename__ = 'protocol_modules'

    id             = db.Column(db.Integer, primary_key=True)
    version_id     = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'), nullable=False, index=True)
    condition_key  = db.Column(db.String(60), nullable=False)
    label          = db.Column(db.String(150), nullable=False)
    applies_when   = db.Column(db.JSON)           # same rule shape as ProtocolOption.default_rule
    goals          = db.Column(db.Text)
    measures_text  = db.Column(db.Text)
    monitoring     = db.Column(db.Text)
    services       = db.Column(db.JSON)           # list of service categories, offered as checkboxes
    patient_info   = db.Column(db.Text)
    safety_netting = db.Column(db.Text)
    gp_reference   = db.Column(db.Text)
    source_note    = db.Column(db.Text)
    display_order  = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('version_id', 'condition_key', name='uq_protocol_module_key'),)


class ProtocolPreventionRule(db.Model):
    """A prevention line MedUI works out from recorded facts (decisions 6 and 8), never the AI.
    rule (JSON): {"sex": "F"|"M", "age_min": n, "age_max": n, "flags_any": [...],
    "flags_none": [...], "needs": "smoking_history"}; all parts must hold."""
    __tablename__ = 'protocol_prevention_rules'

    id            = db.Column(db.Integer, primary_key=True)
    version_id    = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'), nullable=False, index=True)
    key           = db.Column(db.String(60), nullable=False)
    label         = db.Column(db.String(150), nullable=False)
    rule          = db.Column(db.JSON, nullable=False, default=dict)
    wording       = db.Column(db.Text, nullable=False, default='')
    source        = db.Column(db.Text)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('version_id', 'key', name='uq_protocol_prevention_key'),)


class TargetBasis(str, enum.Enum):
    default = 'default'          # the GP confirmed the option the protocol preselected
    option = 'option'            # the GP chose another protocol option
    individual = 'individual'    # the GP set the value themselves


class PatientTarget(db.Model):
    """One patient's target for one measure (ADR-172). Append-only: a change closes the current
    row (superseded_at, superseded_by_id) and adds a new one, so every target ever set, who set
    it and under which protocol version stays on record. Set by the patient's GP; MedUI never
    sets or judges one. value_text is the target as written for this patient (the option's label
    when an option was chosen)."""
    __tablename__ = 'patient_targets'

    id                  = db.Column(db.Integer, primary_key=True)
    patient_id          = db.Column(db.Integer, nullable=False, index=True)
    measure_id          = db.Column(db.Integer, db.ForeignKey('protocol_measures.id'), nullable=False)
    option_id           = db.Column(db.Integer, db.ForeignKey('protocol_options.id'))
    value_text          = db.Column(db.String(300), nullable=False)
    basis               = db.Column(db.Enum(TargetBasis), nullable=False)
    reason              = db.Column(EncryptedText())
    set_by_id           = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    set_at              = db.Column(db.DateTime, nullable=False, default=_now)
    protocol_version_id = db.Column(db.Integer, db.ForeignKey('protocol_versions.id'))
    context             = db.Column(db.String(20), nullable=False, default='standalone')
    superseded_at       = db.Column(db.DateTime)
    superseded_by_id    = db.Column(db.Integer, db.ForeignKey('patient_targets.id'))

    measure          = db.relationship('ProtocolMeasure')
    option           = db.relationship('ProtocolOption')
    set_by           = db.relationship('User', foreign_keys=[set_by_id])
    protocol_version = db.relationship('ProtocolVersion')

    __table_args__ = (db.Index('ix_patient_targets_current', 'patient_id', 'measure_id', 'superseded_at'),)
