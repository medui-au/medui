"""The eGFR rules: the criterion review's KDIGO criterion (ADR-104, ADR-109) and the
Disease Profile badge's last-result rule (ADR-166, evaluate_last).

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

_VALUE = re.compile(r'^\s*([<>])?\s*\^?\s*(\d+(?:\.\d+)?)\s*$')


def read_value(raw, threshold: float = THRESHOLD) -> float | None:
    """A comparable number for the rule, or None when the value can't be placed
    either side of the threshold. '>90' and '>^90' read as 90 (at or above 60);
    '<5' as 5; '<60' as just below 60. '>45' and '<90' are None: they may be
    above or below 60."""
    m = _VALUE.match(str(raw or ''))
    if not m:
        return None
    sign, number = m.group(1), float(m.group(2))
    if sign == '>' and number < threshold:
        return None
    if sign == '<':
        if number > threshold:
            return None
        return min(number, threshold - 0.01)
    return number


# ── The Disease Profile badge (ADR-166): a rule the user chooses to display ───────────────
# The criterion review keeps the KDIGO series rule (evaluate). The badge uses its own rule,
# chosen by the maintainer and clinical lead: the latest eGFR is below BADGE_THRESHOLD. Labs
# report whole numbers, so a result of exactly 59 doesn't count here, although KDIGO's G3a
# (below 60) includes it. A personal setting ('clinical.badge_egfr_rule'), off until ticked.
BADGE_THRESHOLD = 59
BADGE_PREF_KEY = 'clinical.badge_egfr_rule'
BADGE_RULE = (f'Show a badge for patients without a diagnosis of CKD when their last eGFR is '
              f'below {BADGE_THRESHOLD}')


def evaluate_last(series: list[dict], threshold: float = BADGE_THRESHOLD) -> dict:
    """The badge rule. series as for evaluate().

    Returns {'state': 'met' | 'not_met' | 'no_results', 'latest': {'date', 'value'} | None}.
    The latest day is the latest result's date; with several results that day, the lowest
    readable one. If none that day can be placed either side of the threshold, no badge.
    """
    days: dict[date, list] = {}
    for row in series:
        day = row.get('ResultDate')
        if day is not None:
            days.setdefault(day, []).append(row.get('ResultValue'))
    if not days:
        return {'state': 'no_results', 'latest': None}
    last = max(days)
    readable = [(read_value(raw, threshold), str(raw).strip()) for raw in days[last]]
    readable = [r for r in readable if r[0] is not None]
    if not readable:
        value = str(days[last][0] or '').strip()
        return {'state': 'not_met', 'latest': {'date': last, 'value': value}}
    number, value = min(readable)
    return {'state': 'met' if number < threshold else 'not_met',
            'latest': {'date': last, 'value': value}}


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
