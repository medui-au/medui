from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.document import Document, DocumentHide, DocumentVisibility


class DocumentRepository:

    # ── List / Search ──────────────────────────────────────────────────────────

    @staticmethod
    def _visible_filter(query, user_id: int, security_level: int):
        """Apply visibility + soft-delete + hide filters to a Document query."""
        hidden_sub = select(DocumentHide.document_id).where(
            DocumentHide.user_id == user_id
        ).scalar_subquery()

        return query.filter(
            Document.record_status == 'active',
            db.or_(
                Document.visibility == DocumentVisibility.all_users,
                db.and_(
                    Document.visibility == DocumentVisibility.doctors_only,
                    security_level >= 4,
                ),
                Document.created_by_id == user_id,
            ),
            ~Document.id.in_(hidden_sub),
        )

    @staticmethod
    def _filtered_query(user_id: int, security_level: int, is_admin: bool,
                        filter_key: str | None):
        """Return a base query scoped to the given filter_key."""
        if filter_key == 'hidden':
            hidden_sub = select(DocumentHide.document_id).where(
                DocumentHide.user_id == user_id
            ).scalar_subquery()
            return Document.query.filter(
                Document.record_status == 'active',
                db.or_(
                    Document.visibility == DocumentVisibility.all_users,
                    db.and_(Document.visibility == DocumentVisibility.doctors_only,
                            security_level >= 4),
                    Document.created_by_id == user_id,
                ),
                Document.id.in_(hidden_sub),
            )
        if filter_key == 'deleted':
            q = Document.query.filter(Document.record_status == 'deleted')
            if not is_admin:
                q = q.filter(Document.created_by_id == user_id)
            return q
        _VIS = {
            'all_users': DocumentVisibility.all_users,
            'private':   DocumentVisibility.private,
            'doctors':   DocumentVisibility.doctors_only,
        }
        if filter_key in _VIS:
            return DocumentRepository._visible_filter(
                Document.query, user_id, security_level
            ).filter(Document.visibility == _VIS[filter_key])
        return DocumentRepository._visible_filter(Document.query, user_id, security_level)

    @staticmethod
    def list_for_user(user_id: int, security_level: int) -> list[Document]:
        q = DocumentRepository._visible_filter(
            Document.query, user_id, security_level
        )
        return q.order_by(Document.updated_at.desc()).all()

    @staticmethod
    def list_filtered(user_id: int, security_level: int, is_admin: bool,
                      filter_key: str | None) -> list[Document]:
        q = DocumentRepository._filtered_query(user_id, security_level, is_admin, filter_key)
        return q.order_by(Document.updated_at.desc()).all()

    @staticmethod
    def search(term: str, user_id: int, security_level: int,
               is_admin: bool = False, filter_key: str | None = None) -> list[Document]:
        like = f'%{term}%'
        q = DocumentRepository._filtered_query(
            user_id, security_level, is_admin, filter_key
        ).filter(
            db.or_(
                Document.title.ilike(like),
                Document.body.ilike(like),
                Document.keywords.ilike(like),
            )
        )
        return q.order_by(Document.updated_at.desc()).limit(100).all()

    # ── CRUD ───────────────────────────────────────────────────────────────────

    @staticmethod
    def get_by_id(doc_id: int) -> Document | None:
        return db.session.get(Document, doc_id)

    @staticmethod
    def save(document: Document) -> Document:
        if not document.updated_at:
            document.updated_at = datetime.now(timezone.utc)
        else:
            document.updated_at = datetime.now(timezone.utc)
        db.session.add(document)
        db.session.commit()
        return document

    @staticmethod
    def soft_delete(doc_id: int, user_id: int, is_admin: bool = False) -> bool:
        doc = db.session.get(Document, doc_id)
        if not doc or doc.record_status == 'deleted':
            return False
        if doc.created_by_id != user_id and not is_admin:
            return False
        doc.record_status = 'deleted'
        db.session.commit()
        return True

    # ── Hide ───────────────────────────────────────────────────────────────────

    @staticmethod
    def toggle_hide(doc_id: int, user_id: int) -> bool:
        """Returns True if document is now hidden, False if unhidden."""
        existing = DocumentHide.query.filter_by(
            document_id=doc_id, user_id=user_id
        ).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False
        try:
            db.session.add(DocumentHide(document_id=doc_id, user_id=user_id))
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return True  # already hidden (race condition)

    @staticmethod
    def is_hidden(doc_id: int, user_id: int) -> bool:
        return db.session.query(
            exists().where(
                DocumentHide.document_id == doc_id,
                DocumentHide.user_id == user_id,
            )
        ).scalar()
