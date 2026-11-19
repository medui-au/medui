import enum
from datetime import datetime, timezone
from app.extensions import db
from app.utils.encrypted_type import EncryptedText


class EventType(str, enum.Enum):
    adverse_event = 'adverse_event'
    near_miss = 'near_miss'
    sentinel_event = 'sentinel_event'


class SeverityGrade(str, enum.Enum):
    sac1_catastrophic = 'sac1_catastrophic'
    sac2_major = 'sac2_major'
    sac3_moderate = 'sac3_moderate'
    sac4_minor = 'sac4_minor'
    sac5_near_miss = 'sac5_near_miss'


class InvolvedPersonType(str, enum.Enum):
    patient = 'patient'
    family_carer = 'family_carer'
    visitor = 'visitor'
    staff = 'staff'
    other = 'other'


class AEStatus(str, enum.Enum):
    reported = 'reported'
    triaged = 'triaged'
    under_review = 'under_review'
    rca_in_progress = 'rca_in_progress'
    action_plan_set = 'action_plan_set'
    monitoring = 'monitoring'
    closed = 'closed'
    no_action_required = 'no_action_required'


class NotifiedAuthority(str, enum.Enum):
    none = 'none'
    ahpra = 'ahpra'
    coroner = 'coroner'
    health_complaints_commissioner = 'health_complaints_commissioner'
    health_dept = 'health_dept'
    other = 'other'


class AEActionType(str, enum.Enum):
    created = 'created'
    status_changed = 'status_changed'
    triaged = 'triaged'
    note_added = 'note_added'
    assigned = 'assigned'
    rca_updated = 'rca_updated'
    action_item_added = 'action_item_added'
    action_item_completed = 'action_item_completed'
    document_linked = 'document_linked'
    disclosure_updated = 'disclosure_updated'
    authority_notified = 'authority_notified'
    closed = 'closed'
    reopened = 'reopened'


class ActionItemStatus(str, enum.Enum):
    open = 'open'
    in_progress = 'in_progress'
    completed = 'completed'
    overdue = 'overdue'
    cancelled = 'cancelled'


class CrossLinkType(str, enum.Enum):
    related = 'related'
    triggered_by = 'triggered_by'
    same_incident = 'same_incident'


class AdverseEvent(db.Model):
    __tablename__ = 'adverse_events'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    seq_num = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    # Event classification
    event_type = db.Column(db.Enum(EventType), nullable=False)
    severity = db.Column(db.Enum(SeverityGrade), nullable=False)

    # Involved person
    involved_person_type = db.Column(db.Enum(InvolvedPersonType), nullable=False)
    patient_id = db.Column(db.Integer, nullable=True, index=True)
    external_name = db.Column(EncryptedText(), nullable=True)
    external_contact = db.Column(EncryptedText(), nullable=True)

    # Event detail
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(EncryptedText(), nullable=False)
    immediate_actions = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False)
    reported_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    reported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Assignment
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Workflow
    status = db.Column(db.Enum(AEStatus), nullable=False, default=AEStatus.reported)

    # Triage
    triaged_at = db.Column(db.DateTime, nullable=True)
    triaged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    triage_notes = db.Column(db.Text, nullable=True)
    triage_severity_confirmed = db.Column(db.Boolean, nullable=True)

    # Root Cause Analysis
    rca_required = db.Column(db.Boolean, nullable=False, default=False)
    rca_method = db.Column(db.String(100), nullable=True)
    rca_summary = db.Column(db.Text, nullable=True)
    rca_completed_at = db.Column(db.DateTime, nullable=True)
    rca_completed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Open disclosure
    open_disclosure_required = db.Column(db.Boolean, nullable=False, default=False)
    open_disclosure_completed_at = db.Column(db.DateTime, nullable=True)
    open_disclosure_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    open_disclosure_notes = db.Column(db.Text, nullable=True)

    # Authority notification
    notified_authority = db.Column(db.Enum(NotifiedAuthority), nullable=False, default=NotifiedAuthority.none)
    notified_authority_ref = db.Column(db.String(100), nullable=True)
    notified_authority_notes = db.Column(db.Text, nullable=True)
    notified_at = db.Column(db.DateTime, nullable=True)

    # Close
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Void (erroneous entry — hidden from register but retained for audit)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    void_reason = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    reported_by = db.relationship('User', foreign_keys=[reported_by_id], lazy='select')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], lazy='select')
    triaged_by = db.relationship('User', foreign_keys=[triaged_by_id], lazy='select')
    rca_completed_by = db.relationship('User', foreign_keys=[rca_completed_by_id], lazy='select')
    open_disclosure_by = db.relationship('User', foreign_keys=[open_disclosure_by_id], lazy='select')
    closed_by = db.relationship('User', foreign_keys=[closed_by_id], lazy='select')
    voided_by = db.relationship('User', foreign_keys=[voided_by_id], lazy='select')
    actions = db.relationship('AdverseEventAction', back_populates='adverse_event',
                              order_by='AdverseEventAction.timestamp.desc()', lazy='dynamic')
    action_items = db.relationship('AdverseEventActionItem', back_populates='adverse_event',
                                   order_by='AdverseEventActionItem.due_date', lazy='dynamic')
    documents = db.relationship('AdverseEventDocument', back_populates='adverse_event', lazy='dynamic')

    def __repr__(self):
        return f'<AdverseEvent {self.reference_no} {self.status}>'


class AdverseEventAction(db.Model):
    __tablename__ = 'adverse_event_actions'

    id = db.Column(db.Integer, primary_key=True)
    adverse_event_id = db.Column(db.Integer, db.ForeignKey('adverse_events.id'), nullable=False, index=True)
    action_type = db.Column(db.Enum(AEActionType), nullable=False)
    old_status = db.Column(db.Enum(AEStatus), nullable=True)
    new_status = db.Column(db.Enum(AEStatus), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    adverse_event = db.relationship('AdverseEvent', back_populates='actions')
    actor = db.relationship('User', foreign_keys=[actor_id], lazy='select')


class AdverseEventActionItem(db.Model):
    __tablename__ = 'adverse_event_action_items'

    id = db.Column(db.Integer, primary_key=True)
    adverse_event_id = db.Column(db.Integer, db.ForeignKey('adverse_events.id'), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Enum(ActionItemStatus), nullable=False, default=ActionItemStatus.open)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    completion_notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    adverse_event = db.relationship('AdverseEvent', back_populates='action_items')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], lazy='select')
    completed_by = db.relationship('User', foreign_keys=[completed_by_id], lazy='select')
    created_by = db.relationship('User', foreign_keys=[created_by_id], lazy='select')


class AdverseEventDocument(db.Model):
    __tablename__ = 'adverse_event_documents'

    id = db.Column(db.Integer, primary_key=True)
    adverse_event_id = db.Column(db.Integer, db.ForeignKey('adverse_events.id'), nullable=False, index=True)
    bpsdb_document_id = db.Column(db.Integer, nullable=True)
    bpsdb_document_type = db.Column(db.String(10), nullable=True)
    gen5_document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    description = db.Column(db.String(300), nullable=True)
    added_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    adverse_event = db.relationship('AdverseEvent', back_populates='documents')
    added_by = db.relationship('User', foreign_keys=[added_by_id], lazy='select')


class RegisterCrossLink(db.Model):
    __tablename__ = 'register_cross_links'

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=True)
    adverse_event_id = db.Column(db.Integer, db.ForeignKey('adverse_events.id'), nullable=True)
    link_type = db.Column(db.Enum(CrossLinkType), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    complaint = db.relationship('Complaint', foreign_keys=[complaint_id], lazy='select')
    adverse_event = db.relationship('AdverseEvent', foreign_keys=[adverse_event_id], lazy='select')
    created_by = db.relationship('User', foreign_keys=[created_by_id], lazy='select')
