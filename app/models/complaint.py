import enum
from datetime import datetime, timezone
from app.extensions import db
from app.utils.encrypted_type import EncryptedText


class ComplainantType(str, enum.Enum):
    patient = 'patient'
    family_carer = 'family_carer'
    visitor = 'visitor'
    staff = 'staff'
    external_agency = 'external_agency'
    anonymous = 'anonymous'


class ComplaintCategory(str, enum.Enum):
    clinical_care = 'clinical_care'
    medication = 'medication'
    communication = 'communication'
    admin_process = 'admin_process'
    facilities = 'facilities'
    billing = 'billing'
    staff_conduct = 'staff_conduct'
    privacy = 'privacy'
    other = 'other'


class ComplaintStatus(str, enum.Enum):
    received = 'received'
    acknowledged = 'acknowledged'
    under_review = 'under_review'
    resolved = 'resolved'
    closed = 'closed'
    withdrawn = 'withdrawn'


class EscalationTarget(str, enum.Enum):
    none = 'none'
    agpal = 'agpal'
    ahpra = 'ahpra'
    health_complaints_commissioner = 'health_complaints_commissioner'
    ombudsman = 'ombudsman'
    other = 'other'


class ComplaintActionType(str, enum.Enum):
    created = 'created'
    status_changed = 'status_changed'
    acknowledged = 'acknowledged'
    note_added = 'note_added'
    assigned = 'assigned'
    document_linked = 'document_linked'
    disclosure_updated = 'disclosure_updated'
    escalated = 'escalated'
    closed = 'closed'
    reopened = 'reopened'
    withdrawn = 'withdrawn'


class Complaint(db.Model):
    __tablename__ = 'complaints'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    seq_num = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    # Who complained
    complainant_type = db.Column(db.Enum(ComplainantType), nullable=False)
    patient_id = db.Column(db.Integer, nullable=True, index=True)
    external_name = db.Column(EncryptedText(), nullable=True)
    external_contact = db.Column(EncryptedText(), nullable=True)

    # Complaint detail
    subject = db.Column(db.String(500), nullable=False)
    description = db.Column(EncryptedText(), nullable=False)
    category = db.Column(db.Enum(ComplaintCategory), nullable=False)

    # Receipt
    received_at = db.Column(db.DateTime, nullable=False)
    received_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    acknowledgement_method = db.Column(db.String(100), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Workflow
    status = db.Column(db.Enum(ComplaintStatus), nullable=False, default=ComplaintStatus.received)

    # Open disclosure
    open_disclosure_required = db.Column(db.Boolean, nullable=False, default=False)
    open_disclosure_completed_at = db.Column(db.DateTime, nullable=True)
    open_disclosure_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    open_disclosure_notes = db.Column(db.Text, nullable=True)

    # Resolution
    resolution_summary = db.Column(db.Text, nullable=True)
    corrective_action = db.Column(db.Text, nullable=True)

    # Escalation
    escalated_to = db.Column(db.Enum(EscalationTarget), nullable=False, default=EscalationTarget.none)
    escalation_ref = db.Column(db.String(100), nullable=True)
    escalation_notes = db.Column(db.Text, nullable=True)

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

    received_by = db.relationship('User', foreign_keys=[received_by_id], lazy='select')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], lazy='select')
    open_disclosure_by = db.relationship('User', foreign_keys=[open_disclosure_by_id], lazy='select')
    closed_by = db.relationship('User', foreign_keys=[closed_by_id], lazy='select')
    voided_by = db.relationship('User', foreign_keys=[voided_by_id], lazy='select')
    actions = db.relationship('ComplaintAction', back_populates='complaint',
                              order_by='ComplaintAction.timestamp.desc()', lazy='dynamic')
    documents = db.relationship('ComplaintDocument', back_populates='complaint', lazy='dynamic')

    def __repr__(self):
        return f'<Complaint {self.reference_no} {self.status}>'


class ComplaintAction(db.Model):
    __tablename__ = 'complaint_actions'

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False, index=True)
    action_type = db.Column(db.Enum(ComplaintActionType), nullable=False)
    old_status = db.Column(db.Enum(ComplaintStatus), nullable=True)
    new_status = db.Column(db.Enum(ComplaintStatus), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    complaint = db.relationship('Complaint', back_populates='actions')
    actor = db.relationship('User', foreign_keys=[actor_id], lazy='select')


class ComplaintDocument(db.Model):
    __tablename__ = 'complaint_documents'

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False, index=True)
    bpsdb_document_id = db.Column(db.Integer, nullable=True)
    bpsdb_document_type = db.Column(db.String(10), nullable=True)
    gen5_document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    description = db.Column(db.String(300), nullable=True)
    added_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    complaint = db.relationship('Complaint', back_populates='documents')
    added_by = db.relationship('User', foreign_keys=[added_by_id], lazy='select')
