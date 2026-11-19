from app.services import practitioner_names
from app.sql.query_loader import ReadOnlySession, load_query


class InboxRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def get_list(self, provider_id: str | None = None) -> list[dict]:
        if provider_id and provider_id != 'all':
            sql = load_query('inbox_list_provider')
            return practitioner_names.swap(self._session.execute(sql, [provider_id]), 'user_id', 'doctor_name')
        sql = load_query('inbox_list')
        return practitioner_names.swap(self._session.execute(sql, []), 'user_id', 'doctor_name')

    def get_providers(self) -> list[dict]:
        sql = load_query('inbox_providers')
        return practitioner_names.swap(self._session.execute(sql, []), 'USERID', 'name')

    def get_report(self, report_id: int) -> dict | None:
        sql = load_query('viewer_path_inbox')
        rows = practitioner_names.swap(self._session.execute(sql, [report_id]), 'DOCTOR_USERID', 'DOCTOR_NAME')
        return rows[0] if rows else None
