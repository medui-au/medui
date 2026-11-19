from app.sql.query_loader import ReadOnlySession, load_query


class BillingAnalysisRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def get_daily_analysis(self, start, end, uid_param,
                            extra_predicates: str = '', extra_params: list | None = None) -> list[dict]:
        sql = load_query('doctor_billing_analysis_daily').replace('/*EXTRA_FILTERS*/', extra_predicates)
        params = [start, end, uid_param, uid_param, *(extra_params or [])]
        return self._session.execute(sql, params)
