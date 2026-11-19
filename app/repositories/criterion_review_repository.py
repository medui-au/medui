"""Practice-wide reads for the criterion review (ADR-109)."""
from app.sql.query_loader import ReadOnlySession, load_query


class CriterionReviewRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def cohort(self) -> list[dict]:
        return self._session.execute(load_query('review_cohort'))

    def history(self) -> list[dict]:
        return self._session.execute(load_query('review_history'))

    def hba1c(self) -> list[dict]:
        return self._session.execute(load_query('review_hba1c'))

    def egfr(self) -> list[dict]:
        return self._session.execute(load_query('review_egfr'))

    def markers(self, patient_id: int) -> list[dict]:
        return self._session.execute(load_query('patient_marker_results'), [patient_id, patient_id])
