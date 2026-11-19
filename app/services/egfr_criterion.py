"""The eGFR criterion behind the Disease Profile's results badge (ADR-104).

The eGFR part of the KDIGO definition of chronic kidney disease: eGFR below 60
for more than 3 months. Here: at least MIN_RESULTS results below THRESHOLD, the
first and last at least MIN_DAYS apart, with no result of THRESHOLD or more in
between. It describes the results; whether the patient has CKD, and its stage,
is the doctor's decision, so nothing here stages or names a diagnosis.

Pure functions, no database: the repository passes in the series from
patient_egfr_series.sql.
"""
import re
from datetime import date

THRESHOLD = 60
MIN_RESULTS = 2
MIN_DAYS = 90
SOURCE = 'KDIGO: eGFR below 60 for more than 3 months'
# Application Setup → General: show the results badge (default on). Off: recorded CKD only.
SETTING_KEY = 'clinical.egfr_criterion_badge'

_VALUE = re.compile(r'^\s*([<>])?\s*\^?\s*(\d+(?:\.\d+)?)\s*$')


def read_value(raw) -> float | None:
    """A comparable number for the rule, or None when the value can't be placed
    either side of THRESHOLD. '>90' and '>^90' read as 90 (at or above 60);
    '<5' as 5; '<60' as just below 60. '>45' and '<90' are None: they may be
    above or below 60."""
    m = _VALUE.match(str(raw or ''))
    if not m:
        return None
    sign, number = m.group(1), float(m.group(2))
    if sign == '>' and number < THRESHOLD:
        return None
    if sign == '<':
        if number > THRESHOLD:
            return None
        return min(number, THRESHOLD - 0.01)
    return number


def evaluate(series: list[dict], threshold: float = THRESHOLD, min_results: int = MIN_RESULTS,
             min_days: int = MIN_DAYS) -> dict:
    """series: [{'ResultDate': date, 'ResultValue': str}, ...] in any order.

    Returns {'state': 'met' | 'met_previously' | 'not_met' | 'no_results',
             'run': [{'date', 'value'}] (the most recent qualifying run, values as written),
             'latest': {'date', 'value'} | None, 'ignored': int}.
    """
    by_day: dict[date, tuple[float, str]] = {}
    ignored = 0
    for row in series:
        day, raw = row.get('ResultDate'), row.get('ResultValue')
        number = read_value(raw)
        if day is None or number is None:
            ignored += 1
            continue
        # One value per day: the lowest, which also drops repeated copies of a report.
        if day not in by_day or number < by_day[day][0]:
            by_day[day] = (number, str(raw).strip())

    days = sorted(by_day)
    if not days:
        return {'state': 'no_results', 'run': [], 'latest': None, 'ignored': ignored}

    run, qualifying = [], []
    for day in days:
        number, raw = by_day[day]
        if number < threshold:
            run.append({'date': day, 'value': raw})
            if len(run) >= min_results and (run[-1]['date'] - run[0]['date']).days >= min_days:
                qualifying = list(run)
        else:
            run = []

    last = days[-1]
    latest = {'date': last, 'value': by_day[last][1]}
    if not qualifying:
        state = 'not_met'
    elif by_day[last][0] < threshold:
        state = 'met'
    else:
        state = 'met_previously'
    return {'state': state, 'run': qualifying, 'latest': latest, 'ignored': ignored}
