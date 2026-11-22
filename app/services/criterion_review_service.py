"""A record-coding audit: results that meet a published criterion where the condition isn't
coded (ADR-109, wording ADR-165).

Practice-wide, over active patients seen in the last 24 months: the published criteria in
egfr_criterion.evaluate and hba1c_criterion.evaluate (adults for HbA1c), not the Disease
Profile badges' per-user rules (ADR-166), with the same codes (condition_codes). Each
row carries the results that met the criterion and, for HbA1c, the recorded
conditions that affect how it reads (influences). A list for a doctor to review:
a criterion met is not a diagnosis.
"""
from collections import defaultdict

from flask import current_app

from app.repositories.criterion_review_repository import CriterionReviewRepository
from app.services import (condition_codes, egfr_criterion, hba1c_criterion, influences,
                          practitioner_names)
from app.sql.query_loader import ReadOnlySession

# Application Setup → General → Patient Record: the page and its menu item (default on).
SETTING_KEY = 'clinical.criterion_review'


def enabled() -> bool:
    from app.models.system_setting import SystemSetting
    return bool(SystemSetting.get(SETTING_KEY, True))


def load() -> dict:
    with ReadOnlySession(current_app.config['BPSDB_URI']) as session:
        repo = CriterionReviewRepository(session)
        cohort = repo.cohort()
        history, a1c_rows, egfr_rows = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in repo.history():
            history[r['patient_id']].append(r)
        for r in repo.hba1c():
            a1c_rows[r['patient_id']].append(r)
        for r in repo.egfr():
            egfr_rows[r['patient_id']].append(r)

        table = condition_codes.codes()
        practitioner_names.swap(cohort, 'last_doctor_id', 'last_doctor')
        diabetes, ckd = [], []
        recorded = {'diabetes': 0, 'ckd': 0}
        for p in cohort:
            pid = p['patient_id']
            flags = condition_codes.profile_flags(history.get(pid, []), table)
            egfr = egfr_criterion.evaluate(egfr_rows.get(pid, []))
            recorded['diabetes'] += flags['isDiabetes']
            recorded['ckd'] += flags['isCKDRecorded']

            if not flags['isCKDRecorded'] and egfr['state'] in ('met', 'met_previously'):
                ckd.append(dict(p, results=egfr['run'], latest=egfr['latest'],
                                previously=egfr['state'] == 'met_previously'))

            age = p.get('age')
            if (not flags['isDiabetes'] and isinstance(age, int) and age >= hba1c_criterion.MIN_AGE
                    and a1c_rows.get(pid)):
                a1c = hba1c_criterion.evaluate(a1c_rows[pid])
                if a1c['state'] == 'met':
                    found = hba1c_criterion.conditions_affecting(
                        flags['present'], flags['PregnancyYears'], (egfr['latest'] or {}).get('value'),
                        {d['date'].year for d in a1c['days']})
                    rows = influences.for_situation('hba1c_interpretation', found)
                    if any(n != 'egfr' for r in rows for n in r['show']):
                        results = hba1c_criterion.latest_results(repo.markers(pid))
                    else:
                        results = {}
                    if egfr['latest']:
                        results['egfr'] = {'date': egfr['latest']['date'], 'value': egfr['latest']['value'],
                                           'units': 'mL/min/1.73m²', 'range': '', 'flag': ''}
                    for r in rows:
                        r['year'] = flags['present'].get(r['condition']) or None
                        r['results'] = [(n, results.get(n)) for n in r['show']]
                    diabetes.append(dict(p, results=a1c['days'], latest=a1c['latest'], influences=rows))

    order = lambda r: (r.get('patient') or '').lower()
    return {
        'diabetes': sorted(diabetes, key=order),
        'ckd': sorted(ckd, key=order),
        'cohort': len(cohort),
        'recorded': recorded,
    }
