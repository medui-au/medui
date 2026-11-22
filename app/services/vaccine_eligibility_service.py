"""VaccineEligibilityService — NIP-funded vaccine eligibility for patients.

Implements the 2026 NIP eligibility ruleset (effective
2026-07-01) for five vaccines: Influenza, COVID-19, Pneumococcal,
Varicella Zoster (Shingles) and RSV (COVID-19 on the NIP from 2026: health.gov.au,
updated 1 October 2026). Age/ATSI/recency gates are fully
deterministic. Disease-based "at risk condition" eligibility (which also
drops the default age gate to 18+) is resolved via two curated Postgres
lookup tables maintained by admins through the mapping-table UI:

  mapdata_vaccine_mapping   — brand_name / generic_name / diseases / bpsdb_vaccine_id
  mapdata_nip_risk_mapping  — bpsdb_vaccine_id / vaccine_name / eligible_condition_codes

A PASTHISTORY.ItemCode match against nip_risk_mapping is not proof of
current qualifying severity (e.g. a bare "Immunosuppression" diagnosis code
doesn't reveal drug/dose) — by design it always resolves to
eligible=True + confirm_with_gp=True rather than a hard/soft distinction.
"""

import time
from datetime import date, datetime, timedelta

from app.repositories.patient_json_repository import PatientJsonRepository

_MAPPING_CACHE: dict[str, tuple[list[dict], float]] = {}

# The schedule these rules follow (ADR-167): shown beside the patient-page line and in the AI
# context, so the rule's source and version travel with the result. Change it with the rules.
SCHEDULE = ('National Immunisation Program schedule, 2026 (from 1 July 2026; COVID-19 as updated '
            '1 October 2026)')
SCHEDULE_SOURCE = 'Australian Government Department of Health, health.gov.au'
SCHEDULE_TEXT = f'{SCHEDULE}. Source: {SCHEDULE_SOURCE}.'

# Notes state what the schedule says and what is recorded, for the health professional (and the
# AI drafting for them); they don't advise the patient or say what to do (ADR-110).
_NOT_FUNDED = 'Not funded for this age or risk group under the NIP; available privately.'
_NOT_ASSESSED = ('Funded eligibility not assessed for this age group (this check covers age 50+, and '
                 'Aboriginal and Torres Strait Islander people for influenza).')
_MAPPING_TTL = 300  # seconds


def _get_mapping_rows(table_name: str) -> list[dict]:
    """Fetch all rows of a small mapdata_* table, cached briefly."""
    cached = _MAPPING_CACHE.get(table_name)
    if cached and (time.monotonic() - cached[1]) < _MAPPING_TTL:
        return cached[0]

    from app.services import mapping_service
    rows, _total = mapping_service.get_rows(table_name, page=1, per_page=1000)
    _MAPPING_CACHE[table_name] = (rows, time.monotonic())
    return rows


def _parse_condition_codes(raw: str | None) -> set[int]:
    if not raw:
        return set()
    codes = set()
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            codes.add(int(part))
    return codes


def _build_vaccine_lookup() -> dict[int, dict]:
    """bpsdb_vaccine_id -> {brand_name, generic_name, diseases}."""
    lookup = {}
    for row in _get_mapping_rows('vaccine_mapping'):
        vid = row.get('bpsdb_vaccine_id')
        if vid is None or not str(vid).strip().isdigit():
            continue
        lookup[int(vid)] = {
            'brand_name':   (row.get('brand_name') or '').strip(),
            'generic_name': (row.get('generic_name') or '').strip(),
            'diseases':     (row.get('diseases') or '').strip(),
        }
    return lookup


def _build_risk_codes_by_disease(vaccine_lookup: dict[int, dict]) -> dict[str, set[int]]:
    """diseases string -> union of at-risk condition codes for that disease."""
    by_disease: dict[str, set[int]] = {}
    for row in _get_mapping_rows('nip_risk_mapping'):
        vid = row.get('bpsdb_vaccine_id')
        if vid is None:
            continue
        info = vaccine_lookup.get(int(vid))
        if not info:
            continue
        disease = info['diseases']
        by_disease.setdefault(disease, set()).update(
            _parse_condition_codes(row.get('eligible_condition_codes'))
        )
    return by_disease


def _parse_dose_date(vac_date: str | None) -> date | None:
    if not vac_date:
        return None
    try:
        return datetime.strptime(vac_date, '%d/%m/%Y').date()
    except ValueError:
        return None


def _build_dose_history(vaccine_history: list[dict], vaccine_lookup: dict[int, dict]) -> dict[str, list[dict]]:
    """diseases string -> list of dose dicts (most recent first). Unmapped VACCINEIDs are skipped."""
    by_disease: dict[str, list[dict]] = {}
    for row in vaccine_history:
        vid = row.get('VACCINEID')
        if vid is None:
            continue
        info = vaccine_lookup.get(int(vid))
        if not info:
            continue
        dose_date = _parse_dose_date(row.get('VacDate'))
        if dose_date is None:
            continue
        by_disease.setdefault(info['diseases'], []).append({
            'date':         dose_date,
            'sequence':     row.get('SEQUENCE'),
            'brand_name':   info['brand_name'],
            'generic_name': info['generic_name'],
        })
    for doses in by_disease.values():
        doses.sort(key=lambda d: d['date'], reverse=True)
    return by_disease


def _matched_conditions(item_codes: set[int], item_text_by_code: dict[int, str], risk_codes: set[int]) -> list[str]:
    matched = item_codes & risk_codes
    return sorted({item_text_by_code[c] for c in matched if c in item_text_by_code})


def _row(vaccine, product, eligible, basis, confirm_with_gp, matched_conditions,
         doses, due_now, note) -> dict:
    last = doses[0] if doses else None
    return {
        'vaccine':                vaccine,
        'product':                product,
        'eligible_for_funded_dose': eligible,
        'eligibility_basis':      basis,
        'confirm_with_gp':        confirm_with_gp,
        'matched_conditions':     matched_conditions,
        'last_dose_date':         last['date'].strftime('%d/%m/%Y') if last else None,
        'last_dose_product':      (last['brand_name'] or last['generic_name']) if last else None,
        'dose_due_now':           due_now,
        'note':                   note,
        'schedule':               SCHEDULE_TEXT,
    }


def _eval_influenza(age: int, is_atsi: bool, today: date, doses: list[dict]) -> dict:
    had_this_year = any(d['date'].year == today.year for d in doses)

    if age >= 65:
        basis, product = 'Age 65+', 'Fluad Quad (adjuvanted; the NIP influenza vaccine for age 65+)'
    elif is_atsi:
        basis, product = 'Aboriginal and Torres Strait Islander (any age)', 'Influenza vaccine'
    elif age >= 50:
        basis, product = 'Age 50–64 (state-funded program)', 'Influenza vaccine'
    else:
        return _row('Influenza', 'Influenza vaccine', False,
                     'Outside the age/risk groups assessed by this tool', False, [],
                     doses, False, _NOT_ASSESSED)

    if had_this_year:
        return _row('Influenza', product, True, basis, False, [], doses, False,
                     'An influenza vaccine is recorded this year.')
    return _row('Influenza', product, True, basis, False, [], doses, True,
                 f'Funded annually ({basis}). None recorded this year; the program schedule is from April, before winter.')


def _eval_covid(age: int, is_atsi: bool, item_codes: set[int], item_text_by_code: dict[int, str],
                risk_codes: set[int], today: date, doses: list[dict]) -> dict:
    """COVID-19 on the NIP (health.gov.au, updated 1 October 2026): free for adults 75+ (two doses a
    year, about 6 months apart), 65–74 (one a year), Aboriginal and Torres Strait Islander people
    50–74 (one a year) and adults 18–64 with severe immunocompromise (one a year); Medicare card or
    eligibility needed. risk_codes: the NIP risk mapping for COVID-19 if there is one, else the
    shingles immunocompromise list; a match is confirmed by the doctor."""
    matched = _matched_conditions(item_codes, item_text_by_code, risk_codes)
    confirm = False
    if age >= 75:
        basis, interval_months, per_year = 'Age 75+', 6, 'two doses a year, about 6 months apart'
    elif age >= 65:
        basis, interval_months, per_year = 'Age 65–74', 12, 'one dose a year'
    elif is_atsi and age >= 50:
        basis, interval_months, per_year = 'Aboriginal and Torres Strait Islander, age 50–74', 12, 'one dose a year'
    elif age >= 18 and matched:
        basis, interval_months, per_year = 'Severe immunocompromise, age 18–64', 12, 'one dose a year'
        confirm = True
    else:
        return _row('COVID-19', 'COVID-19 vaccine', False, 'Not funded for this age or risk group under the NIP',
                    False, [], doses, False,
                    _NOT_FUNDED + ' The Australian Immunisation Handbook gives recommendations for other groups.')

    last = doses[0] if doses else None
    if last is None:
        note = f'Funded under the NIP ({basis}): {per_year}. No COVID-19 vaccine is recorded.'
        due_now = True
    else:
        months_since = (today.year - last['date'].year) * 12 + (today.month - last['date'].month)
        due_now = months_since >= interval_months
        note = (f'Funded under the NIP ({basis}): {per_year}. Last COVID-19 dose recorded {months_since} '
                f'months ago.')
    note += ' Medicare card or eligibility needed.'
    if confirm:
        note = (f'Funded if a recorded condition ({", ".join(matched)}) is a severe immunocompromise under the '
                f'NIP specified medical risk conditions; the doctor confirms. {note}')
    return _row('COVID-19', 'COVID-19 vaccine', True, basis, confirm, matched if confirm else [],
                doses, due_now, note)


def _eval_pneumococcal(age: int, is_atsi: bool, item_codes: set[int], item_text_by_code: dict[int, str],
                        risk_codes: set[int], today: date, doses: list[dict]) -> dict:
    last = doses[0] if doses else None
    if last and (today - last['date']).days <= 365:
        return _row('Pneumococcal', 'Capvaxive', True, 'Recent pneumococcal vaccine on record', False, [],
                     doses, False, 'A pneumococcal vaccine is recorded within the last 12 months.')

    matched = _matched_conditions(item_codes, item_text_by_code, risk_codes)

    if age >= 65:
        basis, confirm = 'Age 65+', False
    elif is_atsi:
        basis, confirm = 'ATSI, age 25+', False
    elif matched:
        basis, confirm = 'At-risk medical condition (funded from age 18+)', True
    else:
        return _row('Pneumococcal', 'Capvaxive', False,
                     'Not currently funded for this age/risk group', False, [], doses, False,
                     _NOT_FUNDED)

    note = f'Capvaxive is funded ({basis}); a single dose replaces the older Prevenar 13 / Pneumovax 23 schedule.'
    if last:
        note += (f' {last["brand_name"] or last["generic_name"]} recorded {last["date"].strftime("%d/%m/%Y")}; '
                 'Capvaxive can be given 12 months or more after it.')
    if confirm:
        note = (f'Funded if a recorded condition ({", ".join(matched)}) meets the NIP at-risk criteria; '
                f'the doctor confirms its current severity. {note}')

    return _row('Pneumococcal', 'Capvaxive', True, basis, confirm, matched if confirm else [], doses, True, note)


_SHINGRIX_MIN_INTERVAL = timedelta(days=60)   # 2 months
_SHINGRIX_MAX_INTERVAL = timedelta(days=183)  # ~6 months


def _eval_zoster(age: int, is_atsi: bool, item_codes: set[int], item_text_by_code: dict[int, str],
                  risk_codes: set[int], today: date, doses: list[dict]) -> dict:
    shingrix_doses = [d for d in doses if d['brand_name'] == 'Shingrix']
    zostavax_doses = [d for d in doses if d['brand_name'] == 'Zostavax']

    if len(shingrix_doses) >= 2:
        return _row('Varicella Zoster', 'Shingrix', True, 'Course complete', False, [],
                     doses, False, 'Two Shingrix doses are recorded: the course is complete.')

    matched = _matched_conditions(item_codes, item_text_by_code, risk_codes)

    if age >= 65:
        basis, confirm = 'Age 65+', False
    elif is_atsi and age >= 50:
        basis, confirm = 'ATSI, age 50+', False
    elif matched:
        basis, confirm = 'Immunocompromising condition (funded from age 18+)', True
    else:
        return _row('Varicella Zoster', 'Shingrix', False,
                     'Not currently funded for this age/risk group', False, [], doses, False,
                     _NOT_FUNDED)

    if shingrix_doses:
        first_dose_date = shingrix_doses[0]['date']
        since_first = today - first_dose_date
        earliest = first_dose_date + _SHINGRIX_MIN_INTERVAL
        latest = first_dose_date + _SHINGRIX_MAX_INTERVAL
        if since_first < _SHINGRIX_MIN_INTERVAL:
            due_now = False
            note = (f'First Shingrix dose recorded {first_dose_date.strftime("%d/%m/%Y")}; the schedule gives the '
                    f'second from {earliest.strftime("%d/%m/%Y")} (2 months after the first), ideally by '
                    f'{latest.strftime("%d/%m/%Y")} (6 months).')
        elif since_first <= _SHINGRIX_MAX_INTERVAL:
            due_now = True
            note = (f'First Shingrix dose recorded {first_dose_date.strftime("%d/%m/%Y")}; the schedule window '
                    f'for the second is open now, ideally by {latest.strftime("%d/%m/%Y")}.')
        else:
            due_now = True
            note = (f'First Shingrix dose recorded {first_dose_date.strftime("%d/%m/%Y")}; no second dose recorded, '
                    'and the schedule window (2–6 months after the first) has passed.')
    elif zostavax_doses:
        due_now = True
        note = f'Zostavax is recorded; it is no longer used. Shingrix is the current vaccine, funded ({basis}).'
    else:
        due_now = True
        note = f'Shingrix (two doses, 2–6 months apart) is funded ({basis}).'
    if confirm:
        note = (f'Funded if a recorded condition ({", ".join(matched)}) meets the NIP immunocompromise criteria; '
                f'the doctor confirms. {note}')

    return _row('Varicella Zoster', 'Shingrix', True, basis, confirm, matched if confirm else [], doses, due_now, note)


def _eval_rsv(age: int, is_atsi: bool, item_codes: set[int], pneumococcal_risk_codes: set[int],
              today: date, doses: list[dict]) -> dict:
    last = doses[0] if doses else None
    if last and (today - last['date']).days <= 730:
        return _row('RSV', 'Arexvy / Abrysvo', True, 'Recent RSV vaccine on record', False, [],
                     doses, False, 'An RSV vaccine is recorded within the last two years.')

    if age >= 75:
        return _row('RSV', 'Arexvy / Abrysvo', True, 'Age 75+', False, [], doses, True,
                     'A single RSV dose is funded (age 75+).')
    if is_atsi and age >= 60:
        return _row('RSV', 'Arexvy / Abrysvo', True, 'Aboriginal and Torres Strait Islander, age 60+', False, [],
                     doses, True, 'A single RSV dose is funded (Aboriginal and Torres Strait Islander, age 60+).')
    if 60 <= age < 75:
        return _row('RSV', 'Arexvy / Abrysvo', False, 'Not currently funded for this age group', False, [],
                     doses, False, _NOT_FUNDED)
    if 50 <= age < 60:
        # Reuses the pneumococcal at-risk condition list as a proxy for "chronic
        # condition" here — there is no dedicated nip_risk_mapping row for RSV
        # since a condition match never changes the funded=False outcome for
        # this age band, only whether a private-recommendation note is shown.
        at_risk = bool(item_codes & pneumococcal_risk_codes)
        if at_risk:
            return _row('RSV', 'Arexvy / Abrysvo', False, 'Not currently funded for this age group', False, [],
                         doses, False, _NOT_FUNDED + ' A condition on the pneumococcal at-risk list is recorded.')
        return _row('RSV', 'Arexvy / Abrysvo', False, 'Not currently funded for this age group', False, [], doses, False,
                     _NOT_FUNDED)

    return _row('RSV', 'Arexvy / Abrysvo', False, 'Outside the age/risk groups assessed by this tool', False, [],
                 doses, False, _NOT_ASSESSED)


def get_vaccine_eligibility(patient_id: int, repo: PatientJsonRepository) -> list[dict]:
    """Return the NIP funding-eligibility grid for the 5 target vaccines."""
    try:
        if not all(_get_mapping_rows(name) for name in ('vaccine_mapping', 'nip_risk_mapping')):
            return [{'Status': 'Unavailable', 'Reason': 'Vaccine reference tables are not configured; eligibility has not been assessed.'}]
    except ValueError:
        return [{'Status': 'Unavailable', 'Reason': 'Vaccine reference tables are not configured; eligibility has not been assessed.'}]
    demographics = repo.get_atomic_demographics(patient_id)
    history = repo.get_atomic_history(patient_id)
    vaccine_history = repo.get_atomic_vaccine_history(patient_id)

    age = demographics.get('AGE')
    age = int(age) if isinstance(age, (int, float)) or (isinstance(age, str) and age.strip().isdigit()) else 0
    is_atsi = str(demographics.get('Is_ATSI', 'Not recorded')).strip() == 'True'

    item_codes: set[int] = set()
    item_text_by_code: dict[int, str] = {}
    for h in history:
        code = str(h.get('ItemCode') or '').strip()
        if code.isdigit():
            code_int = int(code)
            item_codes.add(code_int)
            item_text_by_code.setdefault(code_int, (h.get('ItemText') or '').strip())

    vaccine_lookup = _build_vaccine_lookup()
    risk_codes_by_disease = _build_risk_codes_by_disease(vaccine_lookup)
    doses_by_disease = _build_dose_history(vaccine_history, vaccine_lookup)

    today = date.today()
    pneumo_risk = risk_codes_by_disease.get('Pneumococcal Disease', set())
    zoster_risk = risk_codes_by_disease.get('Shingles (Herpes Zoster)', set())

    return [
        _eval_influenza(age, is_atsi, today, doses_by_disease.get('Influenza', [])),
        _eval_covid(age, is_atsi, item_codes, item_text_by_code,
                    risk_codes_by_disease.get('COVID-19') or zoster_risk, today,
                    doses_by_disease.get('COVID-19', [])),
        _eval_pneumococcal(age, is_atsi, item_codes, item_text_by_code, pneumo_risk, today,
                            doses_by_disease.get('Pneumococcal Disease', [])),
        _eval_zoster(age, is_atsi, item_codes, item_text_by_code, zoster_risk, today,
                     doses_by_disease.get('Shingles (Herpes Zoster)', [])),
        _eval_rsv(age, is_atsi, item_codes, pneumo_risk, today,
                  doses_by_disease.get('Respiratory Syncytial Virus (RSV)', [])),
    ]
