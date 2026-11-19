import datetime

from flask import current_app

from app.sql.query_loader import ReadOnlySession
from app.repositories.practice_repository import PracticeRepository


class PracticeService:
    @staticmethod
    def _session() -> ReadOnlySession:
        return ReadOnlySession(current_app.config['BPSDB_URI'])

    @staticmethod
    def get_reminders_due() -> list[dict]:
        with PracticeService._session() as sess:
            rows = PracticeRepository(sess).get_reminders_due()
        for row in rows:
            for key in ('REMINDERDUE', 'LAST_ACTION_DATE'):
                val = row.get(key)
                if isinstance(val, (datetime.date, datetime.datetime)):
                    row[key] = val.isoformat()
        return rows
