from app.services import practitioner_names
from app.sql.query_loader import ReadOnlySession, load_query


class ScheduleRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def get_appointments(self, date: str, provider_id: int | None = None) -> list[dict]:
        sql = load_query('schedule_appointments')
        params: list = [date]
        if provider_id is not None:
            sql += ' AND CAST(APPOINTMENTS.USERID AS INT) = ?'
            params.append(int(provider_id))
        sql += ' ORDER BY APPOINTMENTS.APPOINTMENTDATE, APPOINTMENTS.APPOINTMENTTIME'
        return practitioner_names.swap(self._session.execute(sql, params), 'provider_id', 'Provider',
                                       initials_mode=True)

    def get_daysheet(self, date: str, provider_id: int | None = None) -> list[dict]:
        sql = load_query('schedule_daysheet')
        params: list = [date]
        if provider_id is not None:
            sql += ' AND CAST(INVOICES.USERID AS INT) = ?'
            params.append(int(provider_id))
        sql += ' ORDER BY SERVICES.CREATED'
        return practitioner_names.swap(self._session.execute(sql, params), 'provider_id', 'UserName',
                                       initials_mode=True)
