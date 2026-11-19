from datetime import date

from app.repositories import quality_repository as repo


def compute(start_date: date, end_date: date) -> list[dict]:
    """Per-doctor medication (CURRENTRX) housekeeping in [start_date, end_date):
    how many prescriptions were created, how many medications were ceased
    (and that as a % of created — a rough list-maintenance ratio, not a
    same-drug conversion rate), and how many cessations documented a reason
    rather than a silent removal.

    Every active doctor is included, even with all-zero activity; CURRENTRX
    rows created/ceased under a non-doctor userid (e.g. bulk import) are
    excluded, same precedent as the other indicators.
    """
    doctors = repo.get_all_doctors()
    by_user: dict[int, dict] = {
        d['bpsdb_userid']: {
            'bpsdb_userid': d['bpsdb_userid'],
            'doctor_name': d['full_name'],
            'created': 0, 'ceased': 0, 'pct_ceased': 0,
            'ceased_with_reason': 0, 'pct_reason': 0,
        }
        for d in doctors
    }

    for row in repo.get_medication_created_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['created'] = row['created']

    for row in repo.get_medication_ceased_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue
        entry['ceased'] = row['ceased']
        entry['ceased_with_reason'] = row['ceased_with_reason']
        entry['pct_reason'] = (
            round(row['ceased_with_reason'] / row['ceased'] * 100, 1) if row['ceased'] else 0
        )

    for entry in by_user.values():
        entry['pct_ceased'] = (
            round(entry['ceased'] / entry['created'] * 100, 1) if entry['created'] else 0
        )

    return sorted(by_user.values(), key=lambda r: (-r['ceased'], r['doctor_name']))
