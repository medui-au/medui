from app.sql.query_loader import ReadOnlySession, load_query


class DoctorProfileRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    def get_billing_span(self, uid: int) -> dict | None:
        rows = self._session.execute(load_query('doctor_billing_span'), [uid])
        return rows[0] if rows else None

    def get_provider_numbers(self, uid: int) -> list[str]:
        rows = self._session.execute(load_query('auth_get_provider_numbers'), [uid])
        return [r['PROVIDERNUMBER'] for r in rows if r.get('PROVIDERNUMBER')]

    def get_registration_info(self, uid: int) -> dict | None:
        rows = self._session.execute(load_query('auth_get_user_by_id'), [uid])
        return rows[0] if rows else None

    # The details card (ADR-125)
    def get_card_identity(self, uid: int) -> dict | None:
        rows = self._session.execute(load_query('doctor_card_identity'), [uid])
        return rows[0] if rows else None

    def get_qualifications(self, uid: int) -> list[str]:
        rows = self._session.execute(load_query('doctor_card_qualifications'), [uid])
        return [r['qualification'] for r in rows if r.get('qualification')]

    def get_provider_sites(self, uid: int) -> list[dict]:
        return self._session.execute(load_query('doctor_card_provider_sites'), [uid])

    def get_visit_totals(self, uid: int) -> dict | None:
        rows = self._session.execute(load_query('doctor_card_visits'), [uid])
        return rows[0] if rows else None
