from datetime import date

from app.repositories import quality_repository as repo


def compute(start_date: date, end_date: date) -> list[dict]:
    """Per-doctor diagnosis (PastHistory) housekeeping in [start_date, end_date):
    how many diagnoses were created, edited, or deleted, and — of those
    created — how many have a coded item and/or clarifying free-text detail
    rather than just a bare item.

    Every active doctor is included, even with all-zero activity; PASTHISTORY
    rows created/updated/deleted under a non-doctor userid (e.g. bulk import)
    are excluded, same precedent as the other indicators.
    """
    doctors = repo.get_all_doctors()
    by_user: dict[int, dict] = {
        d['bpsdb_userid']: {
            'bpsdb_userid': d['bpsdb_userid'],
            'doctor_name': d['full_name'],
            'created': 0, 'updated': 0, 'deleted': 0, 'total_activity': 0,
            'created_with_itemcode': 0, 'pct_itemcode': 0, 'created_with_details': 0,
        }
        for d in doctors
    }

    for row in repo.get_diagnosis_created_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['created'] = row['created']
        entry['created_with_itemcode'] = row['created_with_itemcode']
        entry['created_with_details'] = row['created_with_details']
        entry['pct_itemcode'] = (
            round(row['created_with_itemcode'] / row['created'] * 100, 1) if row['created'] else 0
        )

    for row in repo.get_diagnosis_updated_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['updated'] = row['updated']

    for row in repo.get_diagnosis_deleted_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['deleted'] = row['deleted']

    for entry in by_user.values():
        entry['total_activity'] = entry['created'] + entry['updated']

    return sorted(by_user.values(), key=lambda r: (-r['total_activity'], r['doctor_name']))
