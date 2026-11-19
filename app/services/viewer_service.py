from flask import current_app
from app.sql.query_loader import ReadOnlySession
from app.repositories.viewer_repository import ViewerRepository
from app.services.clinical_service import ClinicalService


class ViewerService:
    @staticmethod
    def _session() -> ReadOnlySession:
        uri = current_app.config.get('BPSDB_URI')
        if not uri:
            raise RuntimeError('BPSDB_URI not configured')
        return ReadOnlySession(uri)

    @staticmethod
    def get_letter_meta(record_id: int) -> dict | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_letter_meta(record_id)

    @staticmethod
    def get_letter_binary(record_id: int, stored: int) -> bytes | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_letter_binary(record_id, stored)

    @staticmethod
    def get_path_inbox(report_id: int) -> dict | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_path_inbox(report_id)

    @staticmethod
    def get_path_filed(report_id: int) -> dict | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_path_filed(report_id)

    @staticmethod
    def get_path_binary(page_id: int, stored: int) -> bytes | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_path_binary(page_id, stored)

    @staticmethod
    def get_scan_meta(document_id: int) -> dict | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_scan_meta(document_id)

    @staticmethod
    def get_scan_binary(page_id: int, stored: int) -> tuple[bytes, str, int] | None:
        with ViewerService._session() as sess:
            return ViewerRepository(sess).get_scan_binary(page_id, stored)

    @staticmethod
    def get_patient(patient_id: int) -> dict | None:
        return ClinicalService.get_patient_demographics(patient_id)
