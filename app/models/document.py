import enum
from datetime import datetime, timezone
from app.extensions import db


class DocumentVisibility(str, enum.Enum):
    all_users = 'all'
    doctors_only = 'doctors_only'
    private = 'private'


class Document(db.Model):
    __tablename__ = 'documents'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(400), nullable=False)
    body         = db.Column(db.Text, nullable=False, default='')
    format       = db.Column(db.String(20), nullable=False, default='md')  # md, html, text
    keywords     = db.Column(db.Text, nullable=True)   # free-text; searched as substring
    visibility   = db.Column(db.Enum(DocumentVisibility), nullable=False,
                             default=DocumentVisibility.all_users)
    patient_id   = db.Column(db.Integer, index=True)   # null = not patient-specific
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    access_count = db.Column(db.Integer, nullable=False, default=0)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = db.Column(db.DateTime,
                             default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    record_status = db.Column(db.String(20), nullable=False, default='active')  # soft delete

    created_by = db.relationship('User', foreign_keys=[created_by_id], lazy='select')
    hides      = db.relationship('DocumentHide', back_populates='document',
                                 cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<Document {self.title[:40]}>'


class DocumentHide(db.Model):
    """Tracks which users have hidden a public document from their list view."""
    __tablename__ = 'document_hides'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False, index=True)

    document = db.relationship('Document', back_populates='hides')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'document_id', name='uq_doc_hide_user_doc'),
    )
