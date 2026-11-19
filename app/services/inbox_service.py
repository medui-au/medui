from flask import current_app
from app.sql.query_loader import ReadOnlySession
from app.repositories.inbox_repository import InboxRepository


class InboxService:
    @staticmethod
    def _session() -> ReadOnlySession:
        uri = current_app.config.get('BPSDB_URI')
        if not uri:
            raise RuntimeError('BPSDB_URI not configured — configure BPSDB_HOST and read-only credentials in the project .env')
        return ReadOnlySession(uri)

    @staticmethod
    def get_list(provider_id: str | None = None) -> list[dict]:
        with InboxService._session() as sess:
            return InboxRepository(sess).get_list(provider_id)

    @staticmethod
    def get_providers() -> list[dict]:
        with InboxService._session() as sess:
            return InboxRepository(sess).get_providers()

    @staticmethod
    def get_report(report_id: int) -> dict | None:
        with InboxService._session() as sess:
            return InboxRepository(sess).get_report(report_id)
