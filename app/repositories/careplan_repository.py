"""Practice-wide reads for the care plan builder (ADR-129)."""
from app.sql.query_loader import ReadOnlySession, load_query


class CareplanRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def loinc_catalogue(self) -> list[dict]:
        return self._session.execute(load_query('careplan_loinc_catalogue'))
