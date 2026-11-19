"""PatientJsonRepository — atomic data fetchers for the PatientJSON / bundle system.

All methods return raw dicts/lists from BPSDB.  Formatting and assembly are
the responsibility of PatientJsonService.

Parameter counts per query (SQL placeholders):
  demographics           3  (CTE/UNION pattern repeats patient_id)
  pathology_all, fib4    2  (main query + subquery)
  pathology_compact      6  (AllValues ×2, AST_ALT_Results ×2, PLT_Results ×2)
  all others             1
"""

from flask import current_app

from app.sql.query_loader import ReadOnlySession, load_query


def _doctor_names(rows: list) -> list:
    """Progress notes: the doctor's preferred name (ADR-106); the user ID is dropped,
    as the model can't use it."""
    from app.services import practitioner_names
    for row in rows:
        uid = row.pop('DoctorUserId', None)
        if row.get('Doctor') and uid:
            row['Doctor'] = practitioner_names.name(uid, row['Doctor'])
    return rows


class PatientJsonRepository:

    def __init__(self, session: ReadOnlySession):
        self._session = session

    # ── Demographics ──────────────────────────────────────────────────────────

    def get_atomic_demographics(self, patient_id: int, deidentify: bool = False) -> dict:
        q = 'patient_json_demographics_noid' if deidentify else 'patient_json_demographics'
        rows = self._session.execute(load_query(q), [patient_id, patient_id, patient_id, patient_id])
        return rows[0] if rows else {}

    # ── History ───────────────────────────────────────────────────────────────

    def get_atomic_history(self, patient_id: int) -> list:
        return self._session.execute(load_query('patient_json_history'), [patient_id])

    # ── Medications ───────────────────────────────────────────────────────────

    def get_atomic_medications(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_medications_noid' if deidentify else 'patient_json_medications'
        return self._session.execute(load_query(q), [patient_id])

    def get_atomic_ceased_medications(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_ceased_medications_noid' if deidentify else 'patient_json_ceased_medications'
        return self._session.execute(load_query(q), [patient_id])

    # ── Allergies ─────────────────────────────────────────────────────────────

    def get_atomic_allergies(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_allergies_noid' if deidentify else 'patient_json_allergies'
        return self._session.execute(load_query(q), [patient_id])

    # ── Immunizations ─────────────────────────────────────────────────────────

    def get_atomic_immunizations(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_immunizations_noid' if deidentify else 'patient_json_immunizations'
        return self._session.execute(load_query(q), [patient_id])

    def get_atomic_vaccine_history(self, patient_id: int) -> list:
        """Immunisation history with coded VACCINEID, for eligibility matching.

        Kept separate from get_atomic_immunizations so adding VACCINEID here
        doesn't change what's rendered into existing AI bundle prompts.
        """
        return self._session.execute(load_query('patient_json_vaccine_history'), [patient_id])

    # ── Social History ────────────────────────────────────────────────────────

    def get_atomic_social_history(self, patient_id: int, deidentify: bool = False) -> dict:
        q = 'patient_json_social_history_noid' if deidentify else 'patient_json_social_history'
        rows = self._session.execute(load_query(q), [patient_id])
        return rows[0] if rows else {}

    # ── Pathology ─────────────────────────────────────────────────────────────

    def get_atomic_pathology_all(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_pathology_all_noid' if deidentify else 'patient_json_pathology_all'
        return self._session.execute(load_query(q), [patient_id, patient_id])

    def get_atomic_fib4(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_fib4_noid' if deidentify else 'patient_json_fib4'
        return self._session.execute(load_query(q), [patient_id, patient_id])

    def get_atomic_pathology_compact(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_pathology_compact_noid' if deidentify else 'patient_json_pathology_compact'
        return self._session.execute(load_query(q), [patient_id] * 6)

    def get_atomic_pathology_summary(self, patient_id: int) -> list:
        return self._session.execute(load_query('patient_json_pathology_summary'), [patient_id])

    # ── Actions / Recalls / Referrals ─────────────────────────────────────────

    def get_atomic_actions(self, patient_id: int) -> list:
        return self._session.execute(load_query('patient_json_actions'), [patient_id])

    def get_atomic_recalls(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_recalls_noid' if deidentify else 'patient_json_recalls'
        return self._session.execute(load_query(q), [patient_id])

    def get_atomic_referrals(self, patient_id: int, deidentify: bool = False) -> list:
        q = 'patient_json_referrals_noid' if deidentify else 'patient_json_referrals'
        return self._session.execute(load_query(q), [patient_id])

    # ── Progress Notes ────────────────────────────────────────────────────────

    def get_atomic_progress_notes(self, patient_id: int) -> list:
        return _doctor_names(self._session.execute(load_query('patient_json_progress_notes'), [patient_id]))

    def get_all_progress_notes(self, patient_id: int) -> list:
        return _doctor_names(self._session.execute(load_query('patient_json_progress_notes_all'), [patient_id]))

    # ── Scans ─────────────────────────────────────────────────────────────────

    def get_atomic_scans(self, patient_id: int) -> list:
        return self._session.execute(load_query('patient_json_scans'), [patient_id])

    # ── Next of Kin ───────────────────────────────────────────────────────────

    def get_atomic_nok(self, patient_id: int) -> list:
        return self._session.execute(load_query('patient_json_nok'), [patient_id])

    # ── Practice users (not patient data) ───────────────────────────────────

    def get_staff_users(self) -> list:
        return self._session.execute(load_query('staff_users'), [])

    # ── Inbox (recent, gap-filled) ───────────────────────────────────────────

    def get_inbox_filtered(self, patient_id: int, report_ids: list[int]) -> list:
        """Filter candidate INCOMINGREPORTS rows down to non-routine-pathology
        documents, using the same provider/testname exclusion logic as the
        external Document Summarisation Server (BP_Doc_Summarizer): routine
        chemistry/haematology/endocrinology work from the big pathology labs
        is dropped, but histology/cytology/FNA from those same labs — and
        anything from a non-pathology-lab provider (specialists, hospitals,
        radiology) — is kept.

        report_ids is caller-supplied from the summarisation server's own
        response (already validated as ints there); re-cast to int here as
        defense in depth before inlining into the IN-list — this list can't
        be passed as a normal bind param since its length varies per call.
        """
        if not report_ids:
            return []
        id_list = ','.join(str(int(i)) for i in report_ids)
        sql = f'''
            WITH ExcludedTests AS (
                SELECT DISTINCT TESTNAME
                FROM Incomingreports
                WHERE (
                    PROVIDERNAME LIKE 'QUEENSLAND MEDICAL LABORATORY%'
                    OR PROVIDERNAME LIKE 'QML%'
                    OR PROVIDERNAME LIKE 'SULLIVAN NICOLAIDES%'
                    OR PROVIDERNAME LIKE 'MATER Lab%'
                    OR PROVIDERNAME LIKE '%pathology q%'
                    OR TESTNAME LIKE '%GPMP%'
                )
                AND TESTNAME NOT LIKE '%histo%'
                AND TESTNAME NOT LIKE '%cytol%'
                AND TESTNAME NOT LIKE '%FNA%'
            )
            SELECT
                ir.ReportID AS report_id,
                FORMAT(ir.ReportDate, 'dd/MM/yy') AS report_date,
                ir.ReportDate AS report_date_raw,
                TRIM(ir.PROVIDERNAME) AS provider,
                TRIM(COALESCE(NULLIF(TRIM(ir.TESTNAME), ''), NULLIF(TRIM(ir.SUBJECT), ''), '')) AS test_name
            FROM Incomingreports ir
            WHERE ir.InternalId = ?
              AND ir.ReportID IN ({id_list})
              AND NOT EXISTS (SELECT 1 FROM ExcludedTests et WHERE et.TESTNAME = ir.TESTNAME)
            ORDER BY ir.ReportDate DESC
        '''
        return self._session.execute(sql, [patient_id])
