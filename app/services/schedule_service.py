from flask import current_app
from app.sql.query_loader import ReadOnlySession
from app.repositories.schedule_repository import ScheduleRepository


class ScheduleService:
    @staticmethod
    def _session() -> ReadOnlySession:
        uri = current_app.config.get('BPSDB_URI')
        if not uri:
            raise RuntimeError('BPSDB_URI not configured — configure BPSDB_HOST and read-only credentials in the project .env')
        return ReadOnlySession(uri)

    @staticmethod
    def get_appointments(date: str, provider_id: int | None = None) -> list[dict]:
        with ScheduleService._session() as sess:
            return ScheduleRepository(sess).get_appointments(date, provider_id)

    @staticmethod
    def get_daysheet(date: str, provider_id: int | None = None) -> list[dict]:
        with ScheduleService._session() as sess:
            return ScheduleRepository(sess).get_daysheet(date, provider_id)
