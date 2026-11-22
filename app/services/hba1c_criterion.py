"""The HbA1c rules: the criterion review's two-day criterion (ADR-107, ADR-109) and the
Disease Profile badge's highest-of-the-last-3 rule (ADR-166, evaluate_last).

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


# ── The Disease Profile badge (ADR-166): a rule the user chooses to display ───────────────
# The criterion review keeps the two-day criterion above (evaluate). The badge uses its own
# rule, chosen by the maintainer and clinical lead: the highest of the last BADGE_LAST_N results
# is at or above the threshold, each result compared in its own unit. It is a personal setting
# (user_settings_service 'clinical.badge_hba1c_rule'), off until the user ticks it.
BADGE_LAST_N = 3
BADGE_PREF_KEY = 'clinical.badge_hba1c_rule'
BADGE_RULE = (f'Show a badge for patients without a diagnosis of diabetes when the highest of '
              f'their last {BADGE_LAST_N} HbA1c results is {THRESHOLD_PCT}% ({THRESHOLD_MMOL} '
              f'mmol/mol) or more')
BADGE_SOURCE = ('HbA1c 6.5% (48 mmol/mol) or more is the diagnostic threshold in the RACGP '
                'handbook and the Australian Diabetes Society statement (2015), which ask for '
                'confirmation on a different day')


def evaluate_last(series: list[dict], n: int = BADGE_LAST_N) -> dict:
    """The badge rule. series as for evaluate().

    Returns {'state': 'met' | 'not_met' | 'no_results',
             'results': [{'date', 'value', 'unit', 'pct', 'qualifies'}] (the last n readable
             results, one per day, oldest first), 'highest': entry | None, 'latest': entry | None,
             'ignored': int}. Unreadable results are skipped, so the n are the last n readable
             ones; a sample reported in both units counts once (mmol/mol preferred).
    """
    by_day: dict[date, dict] = {}
    ignored = 0
    for row in series:
        day, raw, loinc = row.get('ResultDate'), row.get('ResultValue'), row.get('Loinc')
        ok = qualifies(raw, loinc)
        if day is None or ok is None:
            ignored += 1
            continue
        entry = {'date': day, 'value': str(raw).strip(), 'unit': unit_for(loinc),
                 'pct': as_percent(raw, loinc), 'qualifies': ok}
        if day not in by_day or (entry['unit'] == 'mmol/mol' and by_day[day]['unit'] != 'mmol/mol'):
            by_day[day] = entry
    if not by_day:
        return {'state': 'no_results', 'results': [], 'highest': None, 'latest': None,
                'ignored': ignored}
    results = [by_day[d] for d in sorted(by_day)][-n:]
    met = [r for r in results if r['qualifies']]
    highest = max(met or results, key=_pct_number)
    return {'state': 'met' if met else 'not_met', 'results': results, 'highest': highest,
            'latest': results[-1], 'ignored': ignored}


def _pct_number(entry: dict) -> float:
    m = re.search(r'(\d+(?:\.\d+)?)', entry.get('pct') or '')
    return float(m.group(1)) if m else 0.0


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
