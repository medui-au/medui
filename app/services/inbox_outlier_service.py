"""Inbox results outside range (ADR-097).

Lists the most recent inbox result for each (patient, LOINC) pair that is outside
its reference range, as the laboratory reports it: the lab's own abnormal flag
when it gives one, otherwise the value compared with the lab's stated range. No
thresholds, multiples or trend scoring of MedUI's own — nothing is graded or
ranked, so the doctor sees what the lab reported and judges it. Earlier results
for the same test are shown as data beside it, never turned into a flag.

The same rule decides which tests the patient's results page charts
(`patient_results`).
"""

from datetime import datetime

# Lab flags that mean "within range". Anything else the lab sends (H, L, HH, LL,
# A, *, …) is shown as given.
_NORMAL_FLAGS = {'', 'N'}

# Earlier results shown beside a result, as data.
PREVIOUS_SHOWN = 3


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_range(s) -> tuple:
    """(low, high) floats from a reference-range string; either may be None.

    "x-y" → (x, y)   "<n" / "<=n" → (None, n)   ">n" / ">=n" → (n, None)
    Anything else → (None, None).
    """
    if not isinstance(s, str):
        return None, None
    s = s.strip()
    if not s:
        return None, None
    try:
        if s.startswith('<'):
            return None, float(s[1:].lstrip('= ').strip())
        if s.startswith('>'):
            return float(s[1:].lstrip('= ').strip()), None
        if '-' in s[1:]:
            cut = s.index('-', 1)            # a leading minus belongs to the low value
            return float(s[:cut].strip()), float(s[cut + 1:].strip())
    except ValueError:
        pass
    return None, None


def parse_value(s) -> tuple:
    """(comparator, number) — comparator '<', '>' or '' — or (None, None)."""
    if isinstance(s, (int, float)):
        return '', float(s)
    if not isinstance(s, str):
        return None, None
    s = s.strip()
    comp = ''
    if s[:1] in '<>':
        comp, s = s[0], s[1:].lstrip('= ').strip()
    try:
        return comp, float(s)
    except ValueError:
        return None, None


def outside_range(value, range_str) -> str:
    """'H', 'L' or '' — the value against the stated range only.

    A reported '<n' is low only if n is at or below the lower limit; '>n' is high
    only if n is at or above the upper limit. Otherwise it can't be placed.
    """
    comp, val = parse_value(value)
    low, high = parse_range(range_str)
    if val is None:
        return ''
    if comp == '<':
        return 'L' if low is not None and val <= low else ''
    if comp == '>':
        return 'H' if high is not None and val >= high else ''
    if high is not None and val > high:
        return 'H'
    if low is not None and val < low:
        return 'L'
    return ''


def result_flag(value, range_str, lab_flag) -> tuple:
    """(flag shown, from_lab) — the lab's flag if it gave one, else 'H'/'L' from the
    stated range, else ('', False) for a result within range."""
    lab = (lab_flag or '').strip()
    if lab.upper() not in _NORMAL_FLAGS:
        return lab, True
    return outside_range(value, range_str), False


def _parse_date(val) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if not isinstance(val, str):
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _range_display(row) -> str:
    return ' '.join(filter(None, [str(row.get('RANGE') or '').strip(),
                                  str(row.get('UNITS') or '').strip()]))


# ── The inbox list ────────────────────────────────────────────────────────────

def analyse(rows: list[dict]) -> list[dict]:
    """Most recent result per (patient, LOINC) that is outside range.

    Input rows (the inbox_outliers query): INTERNALID, LOINCCODE, REPORTDATE,
    PATIENTNAME, RESULTNAME, RESULTVALUE, UNITS, RANGE, ABNORMALFLAG.
    Returns rows for the template, newest first, then by patient name.
    """
    if not rows:
        return []

    working = []
    seen = set()
    for r in rows:
        dt = _parse_date(r.get('REPORTDATE'))
        if dt is None:
            continue
        key = (r.get('INTERNALID'), r.get('LOINCCODE'), dt.date(), str(r.get('RESULTVALUE', '')))
        if key in seen:
            continue
        seen.add(key)
        working.append({**r, '_date': dt})

    # One name per LOINC code: the most recent one.
    latest_name: dict[str, tuple] = {}
    for r in working:
        lc = r.get('LOINCCODE', '')
        if lc and (lc not in latest_name or r['_date'] > latest_name[lc][0]):
            latest_name[lc] = (r['_date'], r.get('RESULTNAME', ''))

    groups: dict[tuple, list] = {}
    for r in working:
        groups.setdefault((r.get('INTERNALID'), r.get('LOINCCODE')), []).append(r)

    flagged = []
    for (internalid, loinccode), group in groups.items():
        group.sort(key=lambda x: x['_date'])
        latest = group[-1]
        flag, from_lab = result_flag(latest.get('RESULTVALUE'), latest.get('RANGE'),
                                     latest.get('ABNORMALFLAG'))
        if not flag:
            continue
        previous = [{'date': r['_date'].strftime('%d/%m/%Y'),
                     'value': str(r.get('RESULTVALUE') or '').strip()}
                    for r in reversed(group[:-1])][:PREVIOUS_SHOWN]
        flagged.append({
            'PATIENTNAME': latest.get('PATIENTNAME', ''),
            'INTERNALID': internalid,
            'LOINCCODE': loinccode,
            'RESULTNAME': latest_name.get(loinccode, (None, latest.get('RESULTNAME', '')))[1],
            'RESULTVALUE': latest.get('RESULTVALUE', ''),
            'RANGE': _range_display(latest),
            'RANGE_RAW': str(latest.get('RANGE') or '').strip(),
            'REPORTDATE': latest['_date'].strftime('%Y-%m-%d'),
            'FLAG': flag,
            'FLAG_FROM_LAB': from_lab,
            'PREVIOUS': previous,
        })

    flagged.sort(key=lambda x: (-datetime.strptime(x['REPORTDATE'], '%Y-%m-%d').toordinal(),
                                x['PATIENTNAME']))
    return flagged


# ── One patient's results page ────────────────────────────────────────────────

def harmonise(rows: list[dict]) -> list[dict]:
    """The name/code tidying patient_pathatom.sql does in SQL, done once here:
    a LOINC code reported under several names takes its most recent name; then a
    name reported under several codes takes its most recent code, percentages and
    counts apart ("Monocytes" as 5905-5 % and as 742-7 x10*9/L are two tests). Rows
    are patient_result_history rows (ReportDate, LoincCode, ResultName, …)."""
    def latest(rows, key, value):
        # Most recent; on the same date (a count and a percentage reported
        # together), the one with more results — a fixed choice where the SQL's
        # was arbitrary.
        freq = {}
        for r in rows:
            freq[(r.get(key), r.get(value))] = freq.get((r.get(key), r.get(value)), 0) + 1
        best = {}
        for r in rows:
            k, v, dt = r.get(key), r.get(value), _parse_date(r.get('ReportDate'))
            if not (k and dt):
                continue
            rank = (dt, freq[(k, v)], str(v))
            if k not in best or rank > best[k][0]:
                best[k] = (rank, v)
        return {k: v for k, (_, v) in best.items()}

    rows = [{**r, 'LoincCode': str(r.get('LoincCode') or '').strip(),
             'ResultName': str(r.get('ResultName') or '').strip()} for r in rows]
    names = {}
    for r in rows:
        names.setdefault(r['LoincCode'], set()).add(r['ResultName'])
    latest_name = latest(rows, 'LoincCode', 'ResultName')
    for r in rows:
        if len(names.get(r['LoincCode'], ())) > 1:
            r['ResultName'] = latest_name[r['LoincCode']]
    for r in rows:
        r['_name_kind'] = (r['ResultName'], '%' in str(r.get('Units') or ''))
    codes = {}
    for r in rows:
        codes.setdefault(r['_name_kind'], set()).add(r['LoincCode'])
    latest_code = latest(rows, '_name_kind', 'LoincCode')
    for r in rows:
        if len(codes.get(r['_name_kind'], ())) > 1:
            r['LoincCode'] = latest_code[r['_name_kind']]
        del r['_name_kind']
    return rows


def patient_results(patient_id: int, inbox_rows: list[dict], history_rows: list[dict],
                    clicked_loinc: str | None, today: datetime | None = None,
                    older_than_years: int = 5) -> dict:
    """The charts for one patient: tests outside range in the inbox, then tests not in
    the inbox whose last result was outside range.

    inbox_rows: the inbox_outliers rows (any patients; this one is picked out).
    history_rows: the patient_result_history rows — every numeric result, filed and
    inbox (ReportDate, LoincCode, ResultName, ResultValue, Units, Range, AbnormalFlag);
    harmonised here.

    Returns {'latest': [chart], 'earlier': [chart], 'earlier_older': [chart]}; a chart
    is {loinc, name, units, range, flag, flag_from_lab, latest, previous, points,
    low, high}. The clicked test comes first in 'latest'. Each band is the range the
    lab reported with that test's most recent result.
    """
    today = today or datetime.now()
    mine = [r for r in inbox_rows if r.get('INTERNALID') == patient_id]
    inbox_flagged = analyse(mine)
    inbox_loincs = {str(r.get('LOINCCODE') or '').strip() for r in mine}

    series: dict[str, list] = {}
    for r in harmonise(history_rows):
        lc = str(r.get('LoincCode') or '').strip()
        dt = _parse_date(r.get('ReportDate'))
        if not lc or dt is None:
            continue
        series.setdefault(lc, []).append({**r, '_date': dt})
    for rows in series.values():
        rows.sort(key=lambda x: x['_date'])

    def chart(loinc, latest_row, flag, from_lab, name=None):
        rows = series.get(loinc, [])
        low, high = parse_range(latest_row.get('Range') or latest_row.get('RANGE'))
        points = []
        for r in rows:
            _, val = parse_value(r.get('ResultValue'))
            if val is not None:
                points.append({'x': r['_date'].strftime('%Y-%m-%d'), 'y': val})
        latest_value = str(latest_row.get('ResultValue') or latest_row.get('RESULTVALUE') or '').strip()
        latest_date = _parse_date(latest_row.get('ReportDate') or latest_row.get('REPORTDATE'))
        earlier = [r for r in rows if latest_date is None or r['_date'] < latest_date]
        return {
            'loinc': loinc,
            'name': name or str(latest_row.get('ResultName') or latest_row.get('RESULTNAME') or loinc).strip(),
            'units': str(latest_row.get('Units') or latest_row.get('UNITS') or '').strip(),
            'range': str(latest_row.get('Range') or latest_row.get('RANGE') or '').strip(),
            'flag': flag,
            'flag_from_lab': from_lab,
            'latest': {'value': latest_value,
                       'date': latest_date.strftime('%d/%m/%Y') if latest_date else ''},
            'previous': [{'value': str(r.get('ResultValue') or '').strip(),
                          'date': r['_date'].strftime('%d/%m/%Y')}
                         for r in reversed(earlier)][:PREVIOUS_SHOWN],
            'points': points,
            'low': low,
            'high': high,
            '_last': latest_date,
        }

    latest = []
    for row in inbox_flagged:
        lc = str(row['LOINCCODE'] or '').strip()
        source = next((r for r in reversed(series.get(lc, []))
                       if r['_date'].strftime('%Y-%m-%d') == row['REPORTDATE']), None)
        base = source or {'ResultValue': row['RESULTVALUE'], 'ReportDate': row['REPORTDATE'],
                          'Range': row['RANGE_RAW'], 'ResultName': row['RESULTNAME']}
        latest.append(chart(lc, base, row['FLAG'], row['FLAG_FROM_LAB'], name=row['RESULTNAME']))
    if clicked_loinc:
        latest.sort(key=lambda c: c['loinc'] != clicked_loinc)

    earlier, older = [], []
    try:
        cutoff = today.replace(year=today.year - older_than_years)
    except ValueError:                       # 29 February
        cutoff = today.replace(year=today.year - older_than_years, day=28)
    for lc, rows in series.items():
        if lc in inbox_loincs:
            continue
        last = rows[-1]
        flag, from_lab = result_flag(last.get('ResultValue'), last.get('Range'), last.get('AbnormalFlag'))
        if not flag:
            continue
        (older if last['_date'] < cutoff else earlier).append(chart(lc, last, flag, from_lab))
    earlier.sort(key=lambda c: c['_last'], reverse=True)
    older.sort(key=lambda c: c['_last'], reverse=True)

    for c in latest + earlier + older:
        c.pop('_last', None)
    return {'latest': latest, 'earlier': earlier, 'earlier_older': older}
