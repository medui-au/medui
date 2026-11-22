from datetime import datetime as _dt

from app.sql.query_loader import ReadOnlySession, load_query
from app.utils.bmi import bmi_height


def _format_clinical_age(dob_str: str) -> str:
    """Convert a DOB string (YYYY-MM-DD) to a clinical age label: '35y', '6m', '3w', '5d'."""
    if not dob_str:
        return ''
    try:
        dob = _dt.strptime(str(dob_str)[:10], '%Y-%m-%d')
    except ValueError:
        return ''
    today = _dt.today()
    days = (today - dob).days
    if days < 0:
        return 'Future'
    if days < 7:
        return f'{days}d'
    if days < 30:
        return f'{days // 7}w'
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if years < 1:
        months = (today.year - dob.year) * 12 + today.month - dob.month
        if today.day < dob.day:
            months -= 1
        return f'{months}m'
    return f'{years}y'


class PatientRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, q: str) -> list[dict]:
        """Parse 'Surname, Firstname' and run the appropriate BPSDB query."""
        term = q.strip().rstrip(',')
        parts = [p.strip() for p in term.split(',', 1)]
        surname = parts[0] if parts else ''
        firstname = parts[1] if len(parts) > 1 and parts[1] else None

        if not surname:
            return []

        if firstname:
            sql = load_query('patient_search_full')
            fn_pat = f'%{firstname}%'
            return self._session.execute(sql, [f'{surname}%', fn_pat, fn_pat])
        else:
            sql = load_query('patient_search')
            return self._session.execute(sql, [f'{surname}%'])

    # ── Demographics ──────────────────────────────────────────────────────────

    def get_demographics(self, patient_id: int) -> dict | None:
        sql = load_query('patient_get_demographics')
        rows = self._session.execute(sql, [patient_id, patient_id, patient_id])
        if not rows:
            return None
        data = rows[0]

        # Always expose patient_id for template url_for calls
        data['patient_id'] = patient_id

        # Clinical age
        if data.get('DOB'):
            data['CLINICAL_AGE'] = _format_clinical_age(str(data['DOB']))

        # BMI + weight excess/deficit
        weight = data.get('WEIGHTVALUE')
        height = bmi_height(data)      # not a childhood height for an adult
        if weight and height:
            try:
                wv = float(weight)
                hv = float(height)
                bmi = wv / (hv * hv)
                data['BMI'] = f'{bmi:.1f}'
                bmi20 = 20 * hv * hv
                bmi25 = 25 * hv * hv
                if wv < bmi20:
                    deficit = bmi20 - wv
                    data['BMI_STATUS'] = 'underweight' if deficit >= 5 else 'borderline'
                    data['WEIGHT_EXCESS'] = f'(-{deficit:.0f}kg)'
                elif wv > bmi25:
                    excess = wv - bmi25
                    data['BMI_STATUS'] = 'overweight' if excess >= 10 else 'borderline'
                    data['WEIGHT_EXCESS'] = f'(+{excess:.0f}kg)'
                else:
                    data['BMI_STATUS'] = 'normal'
                    data['WEIGHT_EXCESS'] = ''
            except (ValueError, TypeError):
                pass

        # CCMP eligibility (1 param)
        try:
            ccmp_rows = self._session.execute(load_query('patient_ccmp_eligibility'), [patient_id])
            if ccmp_rows:
                data['CCMP_Eligibility'] = ccmp_rows[0].get('Eligibility')
        except Exception:
            pass

        # HA eligibility (3 params)
        try:
            ha_rows = self._session.execute(load_query('patient_ha_eligibility'),
                                            [patient_id, patient_id, patient_id])
            if ha_rows:
                data['HA_Eligibility'] = ha_rows[0].get('Result')
        except Exception:
            pass

        # NOK/Emergency Contact patient linking — if a contact's phone number
        # uniquely matches another patient's mobile, expose that patient's id
        # (never displayed, only used to build the link) so the template can
        # make the contact's name clickable.
        try:
            if data.get('NOK'):
                link_id = self._find_linked_patient(patient_id, data.get('NOK1_PHONE1'), data.get('NOK1_PHONE2'))
                if link_id:
                    data['NOK1_LINK_ID'] = link_id
        except Exception:
            pass
        try:
            if data.get('NOK2'):
                link_id = self._find_linked_patient(patient_id, data.get('NOK2_PHONE1'), data.get('NOK2_PHONE2'))
                if link_id:
                    data['NOK2_LINK_ID'] = link_id
        except Exception:
            pass

        return data

    def _find_linked_patient(self, patient_id: int, phone1: str | None, phone2: str | None) -> int | None:
        """If exactly one of the two candidate numbers (an NOK/Emergency
        Contact's two phone fields — NEXTOFKIN doesn't label which slot is a
        mobile) belongs to exactly one other patient's mobile, return that
        patient's id. Returns None on zero or on 2+ matches (ambiguous —
        e.g. a shared family number — deliberately not linked)."""
        candidates = [p for p in (phone1, phone2) if p and len(p) >= 8]
        if not candidates:
            return None
        # find_patient_by_mobile.sql takes exactly two candidate params;
        # pad by repeating the one candidate when there's only one.
        p1 = candidates[0]
        p2 = candidates[1] if len(candidates) > 1 else candidates[0]
        rows = self._session.execute(load_query('find_patient_by_mobile'), [patient_id, p1, p2])
        if len(rows) == 1:
            return rows[0].get('InternalId')
        return None

    # ── Dashboard panels ──────────────────────────────────────────────────────

    def get_section(self, query_name: str, patient_id: int, param_count: int = 1) -> list[dict]:
        sql = load_query(query_name)
        return self._session.execute(sql, [patient_id] * param_count)

    def get_disease_profile(self, patient_id: int, show_hba1c_rule: bool = False,
                            show_egfr_rule: bool = False) -> dict:
        """Fetch disease profile + the results badges the viewing user chose + BMI.

        show_hba1c_rule / show_egfr_rule: the viewing user's own settings (ADR-166); the
        caller reads them. Off, a condition that isn't coded shows no results badge."""
        # Coded conditions (ADR-108): the patient's history items against the admin table
        # condition_codes (Admin → Mapping Tables).
        from app.services import condition_codes
        items = self._session.execute(load_query('patient_history_codes'), [patient_id])
        profile = condition_codes.profile_flags(items)
        egfr_series = None

        # eGFR (ADR-104, ADR-166): recorded CKD shows the latest eGFR beside it; otherwise the
        # last-result badge, if the viewing user chose it.
        try:
            from app.services import egfr_criterion
            if profile:
                recorded = bool(profile.get('isCKDRecorded'))
                if recorded or show_egfr_rule:
                    egfr_series = self._session.execute(load_query('patient_egfr_series'),
                                                        [patient_id, patient_id])
                    if recorded:
                        profile['egfr_latest'] = egfr_criterion.evaluate(egfr_series)['latest']
                    else:
                        profile['egfr_badge'] = dict(egfr_criterion.evaluate_last(egfr_series),
                                                     rule=egfr_criterion.BADGE_RULE)
        except Exception:
            pass

        demo = None
        try:
            demo = self.get_demographics(patient_id)
        except Exception:
            pass

        # HbA1c (ADR-107, ADR-166): recorded diabetes shows the latest HbA1c beside it;
        # otherwise, for adults, the highest-of-the-last-3 badge if the viewing user chose it.
        try:
            from app.services import hba1c_criterion
            if profile:
                recorded = bool(profile.get('isDiabetes'))
                age = (demo or {}).get('AGE')
                adult = isinstance(age, (int, float)) and age >= hba1c_criterion.MIN_AGE
                if recorded or (adult and show_hba1c_rule):
                    series = self._session.execute(load_query('patient_hba1c_series'), [patient_id, patient_id])
                    if recorded:
                        profile['hba1c_latest'] = hba1c_criterion.evaluate(series)['latest']
                    else:
                        badge = dict(hba1c_criterion.evaluate_last(series),
                                     rule=hba1c_criterion.BADGE_RULE,
                                     source=hba1c_criterion.BADGE_SOURCE)
                        if badge['state'] == 'met':
                            badge['influences'] = self._hba1c_influences(
                                patient_id, profile, {r['date'].year for r in badge['results']},
                                egfr_series)
                        profile['hba1c_badge'] = badge
        except Exception:
            pass

        # Integrate BMI vitals from demographics
        try:
            if demo and profile is not None:
                profile['BMI'] = demo.get('BMI')
                profile['WEIGHT_EXCESS'] = demo.get('WEIGHT_EXCESS')
                profile['WEIGHT_DATE'] = demo.get('WEIGHT_DATE')
        except Exception:
            pass

        # Recorded / criterion met / neither, per condition with a results criterion (ADR-108).
        try:
            from app.services import condition_codes as _cc
            profile['conditions'] = _cc.summary(profile)
        except Exception:
            pass
        return profile or {}

    def _hba1c_influences(self, patient_id: int, profile: dict, years: set[int], egfr_series) -> list[dict]:
        """The recorded conditions that affect how these HbA1c results read, each with its
        influence row (wording, effect, source) and the latest results it names (ADR-108).
        years: the years of the HbA1c results shown."""
        from app.services import egfr_criterion, hba1c_criterion, influences
        if egfr_series is None:
            egfr_series = self._session.execute(
                load_query('patient_egfr_series'), [patient_id, patient_id])
        latest_egfr = egfr_criterion.evaluate(egfr_series).get('latest')
        present = profile.get('present') or {}
        found = hba1c_criterion.conditions_affecting(present, profile.get('PregnancyYears'),
                                                     (latest_egfr or {}).get('value'), years)
        rows = influences.for_situation('hba1c_interpretation', found)
        results = {}
        if any(n != 'egfr' for r in rows for n in r['show']):
            results = hba1c_criterion.latest_results(self._session.execute(
                load_query('patient_marker_results'), [patient_id, patient_id]))
        if latest_egfr:
            results['egfr'] = {'date': latest_egfr['date'], 'value': latest_egfr['value'],
                               'units': 'mL/min/1.73m²', 'range': '', 'flag': ''}
        for r in rows:
            r['year'] = present.get(r['condition']) or None
            r['results'] = [(n, results.get(n)) for n in r['show']]
        return rows

    def get_family_history(self, patient_id: int) -> dict:
        """Returns {'detail': list, 'overview': dict|None}."""
        detail = self._session.execute(load_query('patient_family_history'), [patient_id])
        overview_rows = self._session.execute(load_query('patient_fhoverview'), [patient_id])
        return {
            'detail': detail,
            'overview': overview_rows[0] if overview_rows else None,
        }

    def get_social_history(self, patient_id: int) -> dict | None:
        rows = self._session.execute(load_query('patient_social_history'), [patient_id])
        return rows[0] if rows else None

    def get_last_items(self, patient_id: int) -> list[dict]:
        return self._session.execute(load_query('patient_last_items'), [patient_id])

    def get_actions(self, patient_id: int) -> list[dict]:
        return self._session.execute(load_query('patient_actions'), [patient_id])

    def get_pathology_trends(self, patient_id: int) -> list[dict]:
        return self._session.execute(load_query('patient_pathology_trends'), [patient_id] * 6)
