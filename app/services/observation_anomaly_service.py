"""Observation anomalies: measurements in BP with a value that isn't a plain number.

Best Practice doesn't check height, weight, head circumference, BMI or blood
pressure at entry, so "72kg" or "1.6 m" is stored as typed. Any query that
converts these values then fails for that patient, and the demographics query
that loads a patient's identifiers for redaction is one of them (a failure
there blocks the patient's cloud pipelines, ADR-007). The report lists the rows
so someone can correct them in BP.
"""

from app.repositories import quality_repository

MEASUREMENTS = {
    3: ('Systolic BP', ('systolic',)),
    4: ('Diastolic BP', ('diastolic',)),
    7: ('Height', ('height',)),
    8: ('Weight', ('weight',)),
    9: ('BMI', ('bmi',)),
    10: ('Head circumference', ('head circ.', 'head circ', 'headcirc')),
}

# Best Practice's own name for each code, for showing what a misfiled row's code
# means. The SQL holds the list it matches against.
NATIVE_NAMES = {
    0: '(none: BP has no measurement under code 0)', 1: 'Temp', 2: 'Pulse',
    3: 'Systolic', 4: 'Diastolic', 5: 'Resp', 6: 'Bsl', 7: 'Height', 8: 'Weight',
    9: 'BMI', 10: 'Head Circ.', 17: 'Waist', 18: 'Hip', 19: 'Inspiration',
    20: 'Expiration', 21: 'WHRatio', 22: 'MMSE', 23: 'MMSE', 24: 'K10',
    26: 'DiabRisk', 27: 'O2Sat', 28: 'PEFR', 29: 'CVRisk', 30: 'Audit-C',
    31: 'DASS21 Depression', 32: 'DASS21 Anxiety', 33: 'DASS21 Stress',
}

# What BP itself writes in the BMI field when it can't calculate one: not a typing
# slip, though it still isn't a number.
BP_BMI_PLACEHOLDER = '**.*'


def load() -> dict:
    """Rows for the report, grouped by measurement, with counts."""
    rows = []
    for r in quality_repository.get_observation_anomalies():
        label, names = MEASUREMENTS.get(r['datacode'], (f"Code {r['datacode']}", ()))
        dataname = (r.get('dataname') or '').strip()
        value = r.get('datavalue') or ''
        rows.append({
            'patient_id': r['patient_id'],
            'patient': ' '.join(p for p in ((r.get('firstname') or '').strip(),
                                            (r.get('surname') or '').strip()) if p) or '(no patient record)',
            'measurement': label,
            'filed_as': dataname if dataname.lower() not in names else '',
            'value': value.strip(),
            'value_raw': value.rstrip(),   # DATAVALUE is char(n): trailing padding isn't typed
            'bp_placeholder': value.strip() == BP_BMI_PLACEHOLDER,
            'obs_date': r.get('obs_date'),
            'entered_by': (r.get('entered_by') or '').strip(),
            'deleted': r.get('record_status') == 0,
            'record_id': r['record_id'],
        })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['measurement']] = counts.get(row['measurement'], 0) + 1
    return {
        'rows': rows,
        'counts': counts,
        'patients': len({r['patient_id'] for r in rows}),
        'placeholders': sum(1 for r in rows if r['bp_placeholder']),
    }


def load_misfiled() -> dict:
    """Observations filed under a code whose BP name they don't carry, grouped
    by patient, for deleting in BP (which sets RECORDSTATUS 3)."""
    rows = []
    for r in quality_repository.get_misfiled_observations():
        rows.append({
            'patient_id': r['patient_id'],
            'patient': ' '.join(p for p in ((r.get('firstname') or '').strip(),
                                            (r.get('surname') or '').strip()) if p) or '(no patient record)',
            'datacode': r['datacode'],
            'code_means': NATIVE_NAMES.get(r['datacode'], '(not in the native list)'),
            'dataname': (r.get('dataname') or '').strip(),
            'value_raw': (r.get('datavalue') or '').rstrip(),
            'obs_date': r.get('obs_date'),
            'created': r.get('created'),
            'imported': r.get('created_by') == 0,
            'entered_by': (r.get('entered_by') or '').strip(),
            'record_id': r['record_id'],
        })
    return {
        'misfiled': rows,
        'misfiled_patients': len({r['patient_id'] for r in rows}),
        'misfiled_imported': sum(1 for r in rows if r['imported']),
    }
