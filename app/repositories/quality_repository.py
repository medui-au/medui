from app.services import practitioner_names
from flask import current_app

from app.sql.query_loader import ReadOnlySession, load_query


def _session() -> ReadOnlySession:
    return ReadOnlySession(current_app.config['BPSDB_URI'])


def get_all_doctors() -> list[dict]:
    """Active BPSDB users with a prescriber number, i.e. doctors. Reuses the
    existing doctor_all_doctors query already used by doctor/routes.py."""
    with _session() as s:
        return practitioner_names.swap(s.execute(load_query('doctor_all_doctors')), 'bpsdb_userid', 'full_name')


def get_observation_entry_counts(start_date, end_date) -> list[dict]:
    """Per-user, per-datacode OBSERVATIONS entry counts in [start_date, end_date)."""
    with _session() as s:
        return s.execute(
            load_query('quality_observation_entry_counts'),
            [start_date, end_date],
        )


def get_observation_anomalies() -> list[dict]:
    """OBSERVATIONS rows with a non-numeric value in a measurement BP doesn't
    check at entry (height, weight, head circumference, BMI, blood pressure).
    Point-in-time; see the SQL file for what counts as non-numeric."""
    with _session() as s:
        return practitioner_names.swap(s.execute(load_query('quality_observation_anomalies')),
                                       'entered_by_id', 'entered_by')


def get_misfiled_observations() -> list[dict]:
    """OBSERVATIONS rows whose name isn't BP's own name for their code (mostly
    imported from another practice's export). Point-in-time."""
    with _session() as s:
        return practitioner_names.swap(s.execute(load_query('quality_observation_misfiled')),
                                       'entered_by_id', 'entered_by')


def get_inbox_results() -> list[dict]:
    """Per-doctor snapshot of pending (unfiled) INCOMINGREPORTS, with age
    buckets by REPORTDATE. Point-in-time — no date range parameters."""
    with _session() as s:
        return s.execute(load_query('quality_inbox_results'))


def get_diagnosis_created_counts(start_date, end_date) -> list[dict]:
    """Per-user PASTHISTORY creation counts in [start_date, end_date), plus
    how many have a coded item and/or clarifying detail."""
    with _session() as s:
        return s.execute(
            load_query('quality_diagnosis_created'), [start_date, end_date]
        )


def get_diagnosis_updated_counts(start_date, end_date) -> list[dict]:
    """Per-user PASTHISTORY edit counts in [start_date, end_date) (excludes
    deletions — see quality_diagnosis_deleted)."""
    with _session() as s:
        return s.execute(
            load_query('quality_diagnosis_updated'), [start_date, end_date]
        )


def get_diagnosis_deleted_counts(start_date, end_date) -> list[dict]:
    """Per-user PASTHISTORY deletion counts in [start_date, end_date) —
    RECORDSTATUS=0 rows, attributed to whoever deleted them (UPDATEDBY)."""
    with _session() as s:
        return s.execute(
            load_query('quality_diagnosis_deleted'), [start_date, end_date]
        )


def get_medication_created_counts(start_date, end_date) -> list[dict]:
    """Per-user CURRENTRX creation counts in [start_date, end_date)."""
    with _session() as s:
        return s.execute(
            load_query('quality_medication_created'), [start_date, end_date]
        )


def get_medication_ceased_counts(start_date, end_date) -> list[dict]:
    """Per-user CURRENTRX cessation counts in [start_date, end_date), plus
    how many have a documented DELETIONREASON."""
    with _session() as s:
        return s.execute(
            load_query('quality_medication_ceased'), [start_date, end_date]
        )


def get_immunisation_vaccine_counts(start_date, end_date) -> list[dict]:
    """Per-doctor, per-VACCINEID active immunisation counts in [start_date, end_date)."""
    with _session() as s:
        return s.execute(
            load_query('quality_immunisation_counts'), [start_date, end_date]
        )


def get_immunisation_patient_counts(start_date, end_date) -> list[dict]:
    """Distinct patients vaccinated per doctor in [start_date, end_date)."""
    with _session() as s:
        return s.execute(
            load_query('quality_immunisation_patients'), [start_date, end_date]
        )


def get_immunisation_age_bands(start_date, end_date) -> list[dict]:
    """Per-doctor age-at-vaccination band counts in [start_date, end_date)."""
    with _session() as s:
        return s.execute(
            load_query('quality_immunisation_age_bands'), [start_date, end_date]
        )
