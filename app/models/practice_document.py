"""Practice documents and their saved versions (ADR-184).

A generic store for the practice's own governance documents. Today it holds one: the AI-use policy
(key 'ai_use_policy'). Later it may hold practice-manual documents and similar.

Versions are only ever added. A saved version's text and snapshot never change; its approval (who,
when, next review) is written once, if the version is approved.
"""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PracticeDocument(db.Model):
    __tablename__ = 'practice_documents'

    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(60), unique=True, nullable=False)   # e.g. 'ai_use_policy'
    kind       = db.Column(db.String(40), nullable=False)                # e.g. 'policy'
    title      = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    versions = db.relationship('PracticeDocumentVersion', backref='document',
                               order_by='PracticeDocumentVersion.number')


class PracticeDocumentVersion(db.Model):
    __tablename__ = 'practice_document_versions'

    id             = db.Column(db.Integer, primary_key=True)
    document_id    = db.Column(db.Integer, db.ForeignKey('practice_documents.id'), nullable=False, index=True)
    number         = db.Column(db.Integer, nullable=False)
    markdown       = db.Column(db.Text, nullable=False)
    note           = db.Column(db.String(300))         # what changed, in the saver's words
    snapshot       = db.Column(db.JSON)                # what the document showed when saved (the AI policy: Appendix A)
    saved_by_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    saved_by_name  = db.Column(db.String(120))         # as shown then; kept if the user is later renamed
    saved_at       = db.Column(db.DateTime, nullable=False, default=_now)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_name = db.Column(db.String(120))
    approved_at    = db.Column(db.DateTime)
    review_due_on  = db.Column(db.Date)

    __table_args__ = (db.UniqueConstraint('document_id', 'number', name='uq_practice_document_version'),)
