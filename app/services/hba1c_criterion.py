"""The HbA1c criterion behind the Disease Profile's results badge (ADR-107).

RACGP (Management of type 2 diabetes, 2024) and the Australian Diabetes Society
(MJA 2015): HbA1c at or above 48 mmol/mol (6.5%), confirmed on a different day.
Here: two different days with a result at or above the threshold, any time in
the record, adults only. It describes the results; whether the patient has
diabetes is the doctor's decision. Recorded conditions that affect how HbA1c reads
are explained beside it (influences table, ADR-108); none of them hides the badge.

Pure functions, no database: the repository passes in the series from
patient_hba1c_series.sql.
"""
import re
from datetime import date

THRESHOLD_MMOL = 48
THRESHOLD_PCT = 6.5
MIN_DAYS = 2
MIN_AGE = 18
MMOL_LOINC = '59261-8'
# Application Setup → General: show the results badge (default on).
SETTING_KEY = 'clinical.hba1c_criterion_badge'

_PLAUSIBLE = {'%': (3.0, 20.0), 'mmol/mol': (9.0, 200.0)}
_VALUE = re.compile(r'^\s*([<>])?\s*=?\s*(\d+(?:\.\d+)?)\s*$')


def unit_for(loinc) -> str:
    return 'mmol/mol' if str(loinc or '').strip() == MMOL_LOINC else '%'


def as_percent(raw, loinc) -> str:
    """The result as NGSP %, for display. A mmol/mol (IFCC) value is converted with the
    IFCC–NGSP master equation, % = 0.09148 × mmol/mol + 2.152 (48 mmol/mol = 6.5%),
    to one decimal; a % value is shown as written. The comparison with the threshold is
    made in the result's own unit (see qualifies)."""
    text = str(raw or '').strip()
    if unit_for(loinc) == '%':
        return f'{text}%'
    m = _VALUE.match(text)
    if not m:
        return text
    sign = m.group(1) or ''
    return f'{sign}{0.09148 * float(m.group(2)) + 2.152:.1f}%'


def qualifies(raw, loinc) -> bool | None:
    """True / False for a readable result, None for one that can't be read.
    '>14' counts as above; a '<' value never qualifies."""
    m = _VALUE.match(str(raw or ''))
    if not m:
        return None
    sign, number = m.group(1), float(m.group(2))
    unit = unit_for(loinc)
    # A value outside the unit's possible range was filed under the wrong code (BP holds a
    # few mmol/mol values under the % codes): unreadable, not reinterpreted.
    low, high = _PLAUSIBLE[unit]
    if not low <= number <= high:
        return None
    threshold = THRESHOLD_MMOL if unit == 'mmol/mol' else THRESHOLD_PCT
    if sign == '<':
        return False
    return number >= threshold


def evaluate(series: list[dict], min_days: int = MIN_DAYS) -> dict:
    """series: [{'ResultDate': date, 'Loinc': str, 'ResultValue': str}, ...] in any order.

    Returns {'state': 'met' | 'not_met' | 'no_results',
             'days': [{'date', 'value', 'unit', 'pct'}] (one per qualifying day, oldest first),
             'latest': {'date', 'value', 'unit', 'pct'} | None, 'ignored': int}.
    """
    by_day: dict[date, dict] = {}       # the qualifying result shown for each day
    latest = None
    ignored = 0
    for row in sorted(series, key=lambda r: r.get('ResultDate') or date.min):
        day, raw, loinc = row.get('ResultDate'), row.get('ResultValue'), row.get('Loinc')
        ok = qualifies(raw, loinc)
        if day is None or ok is None:
            ignored += 1
            continue
        entry = {'date': day, 'value': str(raw).strip(), 'unit': unit_for(loinc),
                 'pct': as_percent(raw, loinc)}
        # One per day: a sample is often reported in both units; mmol/mol preferred.
        if latest is None or day > latest['date'] or (day == latest['date'] and entry['unit'] == 'mmol/mol'):
            latest = entry
        if ok and (day not in by_day or entry['unit'] == 'mmol/mol'):
            by_day[day] = entry

    if latest is None:
        return {'state': 'no_results', 'days': [], 'latest': None, 'ignored': ignored}
    days = [by_day[d] for d in sorted(by_day)]
    state = 'met' if len(days) >= min_days else 'not_met'
    return {'state': state, 'days': days, 'latest': latest, 'ignored': ignored}


def latest_results(rows: list[dict]) -> dict:
    """The latest result of each marker from patient_marker_results.sql (any order):
    {'ferritin'|'haemoglobin'|'b12'|'folate': {date, value, units, range, flag}}."""
    out = {}
    for r in sorted(rows, key=lambda r: r.get('ResultDate') or date.min, reverse=True):
        marker = r.get('Marker')
        value = str(r.get('ResultValue') or '').strip()
        if marker and marker not in out and value:
            out[marker] = {'date': r.get('ResultDate'), 'value': value,
                           'units': str(r.get('Units') or '').split('^')[0].strip(),
                           'range': str(r.get('RefRange') or '').strip(),
                           'flag': str(r.get('Flag') or '').strip()}
    return out


def conditions_affecting(present: dict, pregnancy_years, latest_egfr_value, qualifying_years: set[int]) -> list[str]:
    """The recorded conditions that affect how these HbA1c results read (ADR-108): those in
    profile['present'], advanced CKD also from a latest eGFR below 30, and pregnancy only when
    recorded in a qualifying result's year or the year either side. What each one means is the
    influences table (situation 'hba1c_interpretation'); none of them hides the badge."""
    found = [c for c in (present or {}) if c != 'advanced_ckd']
    m = _VALUE.match(str(latest_egfr_value or ''))
    egfr_low = bool(m and m.group(1) != '>' and float(m.group(2)) < 30)
    if 'advanced_ckd' in (present or {}) or egfr_low:
        found.append('advanced_ckd')
    years = {int(y) for y in str(pregnancy_years or '').split(',') if y.strip().isdigit()}
    if any(abs(y - q) <= 1 for y in years for q in qualifying_years):
        found.append('pregnancy')
    return found
