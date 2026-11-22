from flask import current_app
from app.sql.query_loader import ReadOnlySession
from app.repositories.patient_repository import PatientRepository


class ClinicalService:
    @staticmethod
    def _session() -> ReadOnlySession:
        uri = current_app.config.get('BPSDB_URI')
        if not uri:
            raise RuntimeError('BPSDB_URI not configured — configure BPSDB_HOST and read-only credentials in the project .env')
        return ReadOnlySession(uri)

    @staticmethod
    def search_patients(q: str) -> list[dict]:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).search(q)

    @staticmethod
    def get_patient_demographics(patient_id: int) -> dict | None:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_demographics(patient_id)

    @staticmethod
    def get_disease_profile(patient_id: int, show_hba1c_rule: bool = False,
                            show_egfr_rule: bool = False) -> dict:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_disease_profile(
                patient_id, show_hba1c_rule=show_hba1c_rule, show_egfr_rule=show_egfr_rule)

    @staticmethod
    def get_family_history(patient_id: int) -> dict:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_family_history(patient_id)

    @staticmethod
    def get_social_history(patient_id: int) -> dict | None:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_social_history(patient_id)

    @staticmethod
    def get_last_items(patient_id: int) -> list[dict]:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_last_items(patient_id)

    @staticmethod
    def get_actions(patient_id: int) -> list[dict]:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_actions(patient_id)

    @staticmethod
    def get_pathology_trends(patient_id: int) -> list[dict]:
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_pathology_trends(patient_id)

    # Maps section slug → (query_name, param_count)
    _SECTIONS: dict[str, tuple[str, int]] = {
        'medications':    ('patient_medications', 1),
        'history':        ('patient_history', 1),
        'pathology':      ('patient_pathall', 2),
        'allergies':      ('patient_allergies', 1),
        'immunisations':  ('patient_immunizations', 1),
        'progress_notes': ('patient_progress_notes', 1),
        'recalls':        ('patient_recalls', 1),
        'letters':        ('patient_letters', 1),
        'scans':          ('patient_scans', 1),
    }

    @staticmethod
    def get_patient_section(patient_id: int, section: str) -> list[dict]:
        spec = ClinicalService._SECTIONS.get(section)
        if not spec:
            raise ValueError(f'Unknown section: {section!r}')
        query_name, param_count = spec
        with ClinicalService._session() as sess:
            return PatientRepository(sess).get_section(query_name, patient_id, param_count)
