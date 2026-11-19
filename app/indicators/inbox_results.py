from datetime import date

from app.repositories import quality_repository as repo

AGE_FIELDS = ('age_lt_3m', 'age_3_6m', 'age_6_9m', 'age_9_12m', 'age_gt_12m')

_ZERO_ROW = {'patients': 0, 'total': 0, **{f: 0 for f in AGE_FIELDS}}


def compute(start_date: date, end_date: date) -> list[dict]:
    """Per-doctor snapshot of pending (unfiled) inbox items: how many
    patients have results waiting, the total item count, and an age
    breakdown by how long each has sat unactioned.

    Point-in-time snapshot — start_date/end_date are ignored (this indicator
    has uses_period_filter=False; see app/indicators/base.py). Every active
    doctor is included, even with an empty inbox; items assigned to a
    non-doctor userid (e.g. unassigned/system) are excluded.
    """
    doctors = repo.get_all_doctors()
    by_user: dict[int, dict] = {
        d['bpsdb_userid']: {
            'bpsdb_userid': d['bpsdb_userid'],
            'doctor_name': d['full_name'],
            **_ZERO_ROW,
        }
        for d in doctors
    }

    for row in repo.get_inbox_results():
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue  # not one of our doctors — skip
        entry['patients'] = row['patients']
        entry['total'] = row['total']
        for field in AGE_FIELDS:
            entry[field] = row[field]

    return sorted(by_user.values(), key=lambda r: (-r['total'], r['doctor_name']))
