from datetime import datetime, timezone

from flask import current_app

from app.models.document import Document, DocumentVisibility
from app.models.pipeline import Pipeline
from app.repositories.document_repository import DocumentRepository


class DocLibraryService:

    # ── Pipeline lookup ────────────────────────────────────────────────────────

    @staticmethod
    def get_lib_pipeline_id() -> int | None:
        """Return the active [LIB] pipeline id, or None if not configured."""
        pipeline = Pipeline.query.filter_by(
            classifier='[LIB]', status='active'
        ).first()
        return pipeline.id if pipeline else None

    # ── Document queries ───────────────────────────────────────────────────────

    @staticmethod
    def list_documents(user) -> list[Document]:
        return DocumentRepository.list_for_user(user.id, user.security_level)

    @staticmethod
    def list_documents_filtered(user, filter_key: str | None) -> list[Document]:
        return DocumentRepository.list_filtered(
            user.id, user.security_level, user.is_local_admin, filter_key
        )

    @staticmethod
    def search_documents(term: str, user) -> list[Document]:
        return DocumentRepository.search(term.strip(), user.id, user.security_level)

    @staticmethod
    def search_documents_filtered(term: str, user, filter_key: str | None) -> list[Document]:
        return DocumentRepository.search(
            term.strip(), user.id, user.security_level,
            is_admin=user.is_local_admin, filter_key=filter_key
        )

    @staticmethod
    def get_document(doc_id: int, user) -> Document | None:
        doc = DocumentRepository.get_by_id(doc_id)
        if not doc or doc.record_status == 'deleted':
            return None
        if not DocLibraryService._can_read(doc, user):
            return None
        return doc

    # ── Mutations ──────────────────────────────────────────────────────────────

    @staticmethod
    def create_document(data: dict, user) -> Document:
        doc = Document(
            title=data.get('title', 'Untitled').strip() or 'Untitled',
            body=data.get('body', ''),
            format=data.get('format', 'md'),
            keywords=data.get('keywords', '') or None,
            visibility=DocLibraryService._parse_visibility(data.get('visibility', 'all')),
            patient_id=None,   # the Library is not linked to patients (ADR-093)
            created_by_id=user.id,
        )
        return DocumentRepository.save(doc)

    @staticmethod
    def update_document(doc_id: int, data: dict, user) -> tuple['Document | None', 'str | None']:
        """Update a document. Returns (doc, None) on success, (None, error_code) on failure.

        error_code values: None (not found/forbidden)
        """
        doc = DocumentRepository.get_by_id(doc_id)
        if not doc or doc.record_status == 'deleted':
            return None, None
        if doc.created_by_id != user.id and not user.is_local_admin:
            return None, None

        doc.title    = data.get('title', doc.title).strip() or doc.title
        doc.body     = data.get('body', doc.body)
        doc.format   = data.get('format', doc.format)
        doc.keywords = data.get('keywords', '') or None
        doc.visibility = DocLibraryService._parse_visibility(
            data.get('visibility', doc.visibility.value)
        )
        doc.patient_id = None   # the Library is not linked to patients (ADR-093)
        return DocumentRepository.save(doc), None

    @staticmethod
    def clone_document(doc_id: int, data: dict, user) -> Document | None:
        """Save As — create a copy of an existing document."""
        src = DocumentRepository.get_by_id(doc_id)
        if not src or src.record_status == 'deleted':
            return None
        title = (data.get('title') or f'Copy of {src.title}').strip()
        new_doc = Document(
            title=title,
            body=data.get('body', src.body),
            format=data.get('format', src.format),
            keywords=data.get('keywords') or src.keywords,
            visibility=DocLibraryService._parse_visibility(
                data.get('visibility', src.visibility.value)
            ),
            patient_id=None,
            created_by_id=user.id,
        )
        return DocumentRepository.save(new_doc)

    @staticmethod
    def delete_document(doc_id: int, user) -> bool:
        return DocumentRepository.soft_delete(doc_id, user.id, is_admin=user.is_local_admin)

    @staticmethod
    def toggle_hide(doc_id: int, user) -> bool:
        return DocumentRepository.toggle_hide(doc_id, user.id)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _can_read(doc: Document, user) -> bool:
        if doc.created_by_id == user.id or user.is_local_admin:
            return True
        if doc.visibility == DocumentVisibility.all_users:
            return True
        if doc.visibility == DocumentVisibility.doctors_only and user.security_level >= 4:
            return True
        return False

    @staticmethod
    def _parse_visibility(value: str) -> DocumentVisibility:
        try:
            return DocumentVisibility(value)
        except ValueError:
            return DocumentVisibility.all_users

