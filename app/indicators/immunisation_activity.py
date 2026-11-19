import re
import time
from datetime import date

from app.repositories import quality_repository as repo

AGE_FIELDS = ('age_lt_18', 'age_19_50', 'age_51_plus')

OTHER_CATEGORY = 'Other'

_MAPPING_CACHE: tuple[dict[int, str], float] | None = None
_MAPPING_TTL = 300  # seconds — same pattern as vaccine_eligibility_service._get_mapping_rows


def _slug(category: str) -> str:
    """Turn a free-text disease-category name into a safe dict/column key."""
    return 'cat_' + re.sub(r'[^a-z0-9]+', '_', category.lower()).strip('_')


def _vaccine_lookup() -> dict[int, str]:
    """bpsdb_vaccine_id -> disease category, from the admin-managed
    mapdata_vaccine_mapping table (same source vaccine_eligibility_service
    uses for NIP eligibility) — briefly cached to avoid a DB round-trip on
    every compute() call within a request burst.
    """
    global _MAPPING_CACHE
    if _MAPPING_CACHE and (time.monotonic() - _MAPPING_CACHE[1]) < _MAPPING_TTL:
        return _MAPPING_CACHE[0]

    from app.services import mapping_service
    rows, _total = mapping_service.get_rows('vaccine_mapping', page=1, per_page=1000)
    lookup: dict[int, str] = {}
    for row in rows:
        vid = row.get('bpsdb_vaccine_id')
        if vid is None or not str(vid).strip().isdigit():
            continue
        disease = (row.get('diseases') or '').strip()
        if disease:
            lookup[int(vid)] = disease
    _MAPPING_CACHE = (lookup, time.monotonic())
    return lookup


def all_categories() -> list[str]:
    """Every distinct disease category from the mapping table, alphabetical,
    with 'Other' (unmapped/sentinel VACCINEIDs) always last."""
    categories = sorted(set(_vaccine_lookup().values()))
    return categories + [OTHER_CATEGORY]


def category_keys() -> dict[str, str]:
    """category label -> Column/segment key, e.g. 'Influenza' -> 'cat_influenza'."""
    return {c: _slug(c) for c in all_categories()}


def category_for(vaccineid: int | None) -> str:
    """Map a BPSDB VACCINEID to its disease category, defaulting to Other
    for unmapped or sentinel (0/None) ids."""
    if not vaccineid:
        return OTHER_CATEGORY
    return _vaccine_lookup().get(vaccineid, OTHER_CATEGORY)


def compute(start_date: date, end_date: date) -> list[dict]:
    """Per-doctor immunisation activity in [start_date, end_date): total
    doses given, distinct patients vaccinated, an age-at-vaccination
    breakdown (<18, 19-50, 51+), and a per-disease-category dose breakdown
    (categories come from the mapdata_vaccine_mapping admin table — BPSDB
    has no category lookup of its own).

    Every active doctor is included, even with all-zero activity; doses
    logged under a non-doctor userid (e.g. USERID=0 bulk/system entries) are
    excluded, same precedent as the other indicators.
    """
    keys = category_keys()
    doctors = repo.get_all_doctors()
    by_user: dict[int, dict] = {
        d['bpsdb_userid']: {
            'bpsdb_userid': d['bpsdb_userid'],
            'doctor_name': d['full_name'],
            'total': 0, 'patients': 0,
            **{f: 0 for f in AGE_FIELDS},
            **{key: 0 for key in keys.values()},
        }
        for d in doctors
    }

    for row in repo.get_immunisation_vaccine_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['total'] += row['cnt']
        category = category_for(row['vaccineid'])
        entry[keys[category]] += row['cnt']

    for row in repo.get_immunisation_patient_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['patients'] = row['patients']

    for row in repo.get_immunisation_age_bands(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        for field in AGE_FIELDS:
            entry[field] = row[field]

    return sorted(by_user.values(), key=lambda r: (-r['total'], r['doctor_name']))
