from pathlib import Path
import pyodbc

_SQL_DIR = Path(__file__).parent

# Registry: logical name → SQL filename (relative to app/sql/)
QUERY_REGISTRY: dict[str, str] = {
    # Patient — demographics & core data
    'patient_get_demographics':     'patient_get_demographics.sql',
    'patient_careplan_contact':     'patient_careplan_contact.sql',
    'find_patient_by_mobile':       'find_patient_by_mobile.sql',
    'patient_search':               'patient_search.sql',
    'patient_search_full':          'patient_search_full.sql',
    'patient_ccmp_eligibility':     'patient_ccmp_eligibility.sql',
    'patient_ha_eligibility':       'patient_ha_eligibility.sql',
    'patient_futureappts':          'patient_futureappts.sql',
    'patient_next_appointment':     'patient_next_appointment.sql',
    # Patient — clinical dashboard panels
    'patient_medications':          'patient_medications.sql',
    'patient_allergies':            'patient_allergies.sql',
    'patient_immunizations':        'patient_immunizations.sql',
    'patient_progress_notes':       'patient_progress_notes.sql',
    'patient_history':              'patient_history.sql',
    'patient_pathsummary':          'patient_pathsummary.sql',
    'patient_pathall':              'patient_pathall.sql',
    'patient_investigations_full':  'patient_investigations_full.sql',
    'patient_scans':                'patient_scans.sql',
    'patient_letters':              'patient_letters.sql',
    'patient_recalls':              'patient_recalls.sql',
    'patient_actions':              'patient_actions.sql',
    'patient_last_items':           'patient_last_items.sql',
    'patient_pathology_trends':     'patient_pathology_trends.sql',
    'patient_history_codes':        'patient_history_codes.sql',
    'condition_term_names':         'condition_term_names.sql',
    'condition_item_texts':         'condition_item_texts.sql',
    'patient_marker_results':       'patient_marker_results.sql',
    # Criterion review (ADR-109): practice-wide, the active patients seen in 24 months
    'review_cohort':                'review_cohort.sql',
    'review_history':               'review_history.sql',
    'review_hba1c':                 'review_hba1c.sql',
    'review_egfr':                  'review_egfr.sql',
    'patient_egfr_series':          'patient_egfr_series.sql',
    'patient_hba1c_series':         'patient_hba1c_series.sql',
    'patient_family_history':       'patient_family_history.sql',
    'patient_fhoverview':           'patient_fhoverview.sql',
    'patient_social_history':       'patient_social_history.sql',
    # PatientJSON atomic blocks (AI pipeline context assembly)
    'patient_json_demographics':         'patient_json_demographics.sql',
    'patient_json_demographics_noid':    'patient_json_demographics_noid.sql',
    'patient_json_history':              'patient_json_history.sql',
    'patient_json_medications':          'patient_json_medications.sql',
    'patient_json_medications_noid':     'patient_json_medications_noid.sql',
    'patient_json_ceased_medications':      'patient_json_ceased_medications.sql',
    'patient_json_ceased_medications_noid': 'patient_json_ceased_medications_noid.sql',
    'patient_json_allergies':            'patient_json_allergies.sql',
    'patient_json_allergies_noid':       'patient_json_allergies_noid.sql',
    'patient_json_immunizations':        'patient_json_immunizations.sql',
    'patient_json_immunizations_noid':   'patient_json_immunizations_noid.sql',
    'patient_json_vaccine_history':      'patient_json_vaccine_history.sql',
    'patient_json_social_history':       'patient_json_social_history.sql',
    'patient_json_social_history_noid':  'patient_json_social_history_noid.sql',
    'patient_json_pathology_all':        'patient_json_pathology_all.sql',
    'patient_json_pathology_all_noid':   'patient_json_pathology_all_noid.sql',
    'patient_json_pathology_summary':    'patient_json_pathology_summary.sql',
    'patient_json_pathology_compact':    'patient_json_pathology_compact.sql',
    'patient_json_pathology_compact_noid': 'patient_json_pathology_compact_noid.sql',
    'patient_json_fib4':                 'patient_json_fib4.sql',
    'patient_json_fib4_noid':            'patient_json_fib4_noid.sql',
    'patient_json_actions':              'patient_json_actions.sql',
    'patient_json_recalls':              'patient_json_recalls.sql',
    'patient_json_recalls_noid':         'patient_json_recalls_noid.sql',
    'patient_json_progress_notes':        'patient_json_progress_notes.sql',
    'patient_json_progress_notes_all':    'patient_json_progress_notes_all.sql',
    'patient_json_scans':                'patient_json_scans.sql',
    'patient_json_referrals':            'patient_json_referrals.sql',
    'patient_json_referrals_noid':       'patient_json_referrals_noid.sql',
    'patient_json_nok':                  'patient_json_nok.sql',
    'staff_users':                       'staff_users.sql',
    'usage_user_groups':                 'usage_user_groups.sql',
    # HCP data (for redaction)
    'patients_with_given_name':         'patients_with_given_name.sql',
    'privacy_staff_map':                'privacy_staff_map.sql',
    # Inbox & schedule
    'inbox_list':                   'inbox_list.sql',
    'inbox_list_provider':          'inbox_list_provider.sql',
    'inbox_providers':              'inbox_providers.sql',
    'inbox_outliers':               'inbox_outliers.sql',
    # Charts / Atomized Pathology
    'charts_patient_scatter':       'charts_patient_scatter.sql',
    'patient_pathatom':             'patient_pathatom.sql',
    'patient_result_history':       'patient_result_history.sql',
    'careplan_loinc_catalogue':     'careplan_loinc_catalogue.sql',
    'patient_charts_bp':            'patient_charts_bp.sql',
    'patient_charts_fib4':          'patient_charts_fib4.sql',
    'patient_charts_weight':        'patient_charts_weight.sql',
    'patient_charts_pathology':     'patient_charts_pathology.sql',
    # Viewer
    'viewer_letter_meta':           'viewer_letter_meta.sql',
    'viewer_path_filed':            'viewer_path_filed.sql',
    'viewer_path_inbox':            'viewer_path_inbox.sql',
    'viewer_scan_meta':             'viewer_scan_meta.sql',
    'schedule_appointments':        'schedule_appointments.sql',
    'schedule_daysheet':            'schedule_daysheet.sql',
    # Doctor
    'doctor_all_doctors':           'doctor_all_doctors.sql',
    'doctor_billings_summary':      'doctor_billings_summary.sql',
    'doctor_billings_items':        'doctor_billings_items.sql',
    'doctor_billing_analysis_daily': 'doctor_billing_analysis_daily.sql',
    'doctor_billing_span':          'doctor_billing_span.sql',
    'doctor_progress_notes':        'doctor_progress_notes.sql',
    'doctor_card_identity':         'doctor_card_identity.sql',
    'doctor_card_qualifications':   'doctor_card_qualifications.sql',
    'doctor_card_provider_sites':   'doctor_card_provider_sites.sql',
    'doctor_card_visits':           'doctor_card_visits.sql',
    # Quality indicators
    'quality_observation_entry_counts': 'quality_observation_entry_counts.sql',
    'quality_observation_anomalies':    'quality_observation_anomalies.sql',
    'quality_observation_misfiled':     'quality_observation_misfiled.sql',
    'quality_inbox_results':            'quality_inbox_results.sql',
    'quality_diagnosis_created':        'quality_diagnosis_created.sql',
    'quality_diagnosis_updated':        'quality_diagnosis_updated.sql',
    'quality_diagnosis_deleted':        'quality_diagnosis_deleted.sql',
    'quality_medication_created':       'quality_medication_created.sql',
    'quality_medication_ceased':        'quality_medication_ceased.sql',
    'quality_immunisation_counts':      'quality_immunisation_counts.sql',
    'quality_immunisation_patients':    'quality_immunisation_patients.sql',
    'quality_immunisation_age_bands':   'quality_immunisation_age_bands.sql',
    # Auth
    'auth_get_active_users':        'auth_get_active_users.sql',
    'auth_get_user_by_id':          'auth_get_user_by_id.sql',
    'auth_get_provider_numbers':    'auth_get_provider_numbers.sql',
    # Practice (administrative / practice-centric queries)
    'practice_reminders_due':       'practice_reminders_due.sql',
    # Setup: is the BP login read-only? (ADR-139)
    'bp_login_server_perms':        'bp_login_server_perms.sql',
    'bp_login_databases':           'bp_login_databases.sql',
    'bp_login_database_perms':      'bp_login_database_perms.sql',
}


class ReadOnlySession:
    """Thin wrapper around a pyodbc connection that refuses SQL starting with a write keyword.

    The check is only how the text starts: a write after a leading comment or a first
    statement is not caught (pathology queries use `SELECT ... INTO #temp` and `INSERT INTO
    #temp` this way, which is intended). It catches mistakes; the BP login's read-only
    permissions are the real control (ADR-139)."""

    _WRITE_PREFIXES = ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE')

    def __init__(self, connection_string: str):
        self._conn = pyodbc.connect(connection_string, autocommit=True)

    def execute(self, sql: str, params: list | tuple | None = None) -> list[dict]:
        stripped = sql.strip().upper()
        for prefix in self._WRITE_PREFIXES:
            if stripped.startswith(prefix):
                raise RuntimeError(
                    f'BPSDB is read-only. Attempted: {prefix} statement.'
                )
        cursor = self._conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def load_query(name: str) -> str:
    filename = QUERY_REGISTRY.get(name)
    if not filename:
        raise KeyError(f'Unknown query: {name!r}. Available: {sorted(QUERY_REGISTRY)}')
    path = _SQL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f'SQL file not found: {path}')
    return path.read_text()
