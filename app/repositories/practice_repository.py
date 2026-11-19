from app.sql.query_loader import ReadOnlySession, load_query


class PracticeRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def get_reminders_due(self) -> list[dict]:
        return self._session.execute(load_query('practice_reminders_due'))
