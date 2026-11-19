from datetime import date

from app.repositories import quality_repository as repo

DATACODE_LABELS = {
    3: 'systolic',
    4: 'diastolic',
    7: 'height',
    8: 'weight',
}


def compute(start_date: date, end_date: date) -> list[dict]:
    """Per-doctor count of vital-sign OBSERVATIONS entered in [start_date, end_date).

    Proof-of-concept indicator: how many systolic/diastolic/height/weight values
    each clinician has recorded. Used as data-quality context for AI-assisted
    features that rely on these observations being present and current.

    Every active local doctor is included, even with all-zero counts. Entries
    recorded under a USERID that isn't one of our doctors (e.g. nurses/other
    staff taking vitals, or historical data imported under another practice's
    userids) are excluded rather than shown as "Unknown user".
    """
    doctors = repo.get_all_doctors()
    by_user: dict[int, dict] = {
        d['bpsdb_userid']: {
            'bpsdb_userid': d['bpsdb_userid'],
            'doctor_name': d['full_name'],
            'systolic': 0, 'diastolic': 0, 'height': 0, 'weight': 0, 'total': 0,
        }
        for d in doctors
    }

    for row in repo.get_observation_entry_counts(start_date, end_date):
        entry = by_user.get(row['bpsdb_userid'])
        if entry is None:
            continue  # not one of our doctors — skip rather than label "unknown"
        label = DATACODE_LABELS.get(row['datacode'])
        if label:
            entry[label] += row['entry_count']
            entry['total'] += row['entry_count']

    return sorted(by_user.values(), key=lambda r: (-r['total'], r['doctor_name']))
