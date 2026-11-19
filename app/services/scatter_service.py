"""Fetch and cache the full patient cohort for the scatter chart.

Returns a dict: {'patients': [...], 'bounds': {...}, 'row_count': int}

Cached for 10 minutes. Call bust_cache() before get_patient_data() to force a refresh.
"""
import csv
import io
import time
from typing import Any

from flask import current_app

_CACHE: dict = {'data': None, 'expires': 0.0}
_CACHE_TTL = 600  # 10 minutes

NUMERIC_COLS = [
    'Age', 'AgeAtWeight', 'SystolicBP', 'DiastolicBP', 'Height', 'Weight',
    'BMI', 'ExcessWeight', 'WeeklyAlcohol', 'LastPSA', 'LasteGFR', 'LastHbA1c',
]
FLAG_COLS = [
    'IsDiabetic', 'IsAF', 'IsOSA', 'IsWBOA',
    'IsDepressionOrAnxiety', 'IsHT', 'IsSmoker',
]
# Chart flag <- condition in the practice's condition_codes table (ADR-146), so the chart
# and the Disease Profile badges count the same codes. IsSmoker comes from TOBACCO.
CONDITION_FLAGS = {
    'IsDiabetic': 'diabetes', 'IsAF': 'af', 'IsHT': 'hypertension',
    'IsOSA': 'osa', 'IsWBOA': 'wboa', 'IsDepressionOrAnxiety': 'depression_anxiety',
}


# The patient list below the chart is shown, and can be downloaded, only for this many
# patients or fewer (ADR-147): a larger cohort is narrowed with the filters first.
EXPORT_LIMIT = 500

COL_LABELS = {
    'Age': 'Age (years)', 'AgeAtWeight': 'Age at last weight (years)',
    'SystolicBP': 'Systolic BP (mmHg)', 'DiastolicBP': 'Diastolic BP (mmHg)',
    'Height': 'Height (cm)', 'Weight': 'Weight (kg)', 'BMI': 'BMI',
    'ExcessWeight': 'Excess weight (kg)', 'WeeklyAlcohol': 'Weekly alcohol (units)',
    'LastPSA': 'Last PSA (ng/mL)', 'LasteGFR': 'Last eGFR (mL/min)', 'LastHbA1c': 'Last HbA1c (mmol/mol)',
}
_STATUS = {1: 'Active', 2: 'Inactive', 3: 'Deceased'}


def get_patient_data() -> dict[str, Any]:
    """Return cached cohort dict. Re-fetches from BPSDB after TTL expires."""
    now = time.monotonic()
    if _CACHE['data'] is not None and now < _CACHE['expires']:
        return _CACHE['data']
    try:
        rows = _fetch_raw()
        from app.services import condition_codes
        # A condition with no rows in the table uses its built-in codes, so a filter
        # works before the migration that adds the chart's conditions has run.
        table = {**condition_codes._defaults(), **condition_codes.codes()}
        patients = _post_process(rows, table)
        result: dict[str, Any] = {
            'patients':  patients,
            'bounds':    _compute_bounds(patients),
            'row_count': len(patients),
            'error':     None,
        }
    except Exception as exc:
        current_app.logger.error('scatter_service error: %s', exc)
        result = {'patients': [], 'bounds': {}, 'row_count': 0, 'error': str(exc)}
    _CACHE['data'] = result
    _CACHE['expires'] = now + _CACHE_TTL
    return result


def bust_cache() -> None:
    _CACHE['expires'] = 0.0


def _fetch_raw() -> list[dict]:
    from app.sql.query_loader import ReadOnlySession, load_query
    sql = load_query('charts_patient_scatter')
    conn_str = current_app.config.get('BPSDB_URI')
    if not conn_str:
        raise RuntimeError('BPSDB_URI not configured')
    with ReadOnlySession(conn_str) as session:
        return session.execute(sql)


def _active_codes(value) -> set[int]:
    """The comma list from the query's ActiveCodes, as item codes."""
    return {int(c) for c in str(value or '').split(',') if c.strip().isdigit()}


def _post_process(rows: list[dict], table: dict[str, frozenset]) -> list[dict]:
    out = []
    for r in rows:
        p = dict(r)

        # Condition flags from the patient's active coded items (ADR-146)
        active = _active_codes(p.pop('ActiveCodes', None))
        for flag, condition in CONDITION_FLAGS.items():
            p[flag] = bool(active & table.get(condition, frozenset()))

        # BMI and Excess Weight (ideal weight at BMI 22.5)
        h = _to_float(p.get('Height'))
        w = _to_float(p.get('Weight'))
        if h and w and h > 50 and w > 10:
            bmi = round(w * 10000 / (h * h), 1)
            ideal = 22.5 * (h / 100) ** 2
            p['BMI'] = bmi
            p['ExcessWeight'] = round(w - ideal, 1)
        else:
            p['BMI'] = None
            p['ExcessWeight'] = None

        # Cast integer-ish columns
        for col in ('SystolicBP', 'DiastolicBP', 'WeeklyAlcohol'):
            p[col] = _to_int(p.get(col))

        # Cast float columns (ages are exact, to one decimal: ADR-147)
        for col in ('Age', 'AgeAtWeight', 'Height', 'Weight', 'LastPSA', 'LasteGFR', 'LastHbA1c'):
            p[col] = _to_float(p.get(col))

        # Cast condition flags to bool
        for flag in FLAG_COLS:
            p[flag] = bool(p.get(flag))

        # NextApptDate → ISO date string
        nxt = p.get('NextApptDate')
        if nxt is not None:
            try:
                p['NextApptDate'] = nxt.strftime('%Y-%m-%d')
            except AttributeError:
                p['NextApptDate'] = str(nxt)[:10]

        out.append(p)
    return out


def _compute_bounds(patients: list[dict]) -> dict[str, dict]:
    bounds: dict[str, dict] = {}
    for col in NUMERIC_COLS:
        vals = [p[col] for p in patients if p.get(col) is not None]
        if vals:
            lo, hi = min(vals), max(vals)
            # Ensure range is non-zero so sliders render usefully
            if lo == hi:
                lo = max(0, lo - 1)
                hi = hi + 1
            bounds[col] = {'min': lo, 'max': hi}
        else:
            bounds[col] = {'min': 0, 'max': 100}
    return bounds


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if -1_000_000 < f < 1_000_000 else None
    except (TypeError, ValueError):
        return None


def _to_int(v) -> int | None:
    f = _to_float(v)
    return int(round(f)) if f is not None else None


# ── Patient list download (ADR-147) ─────────────────────────────────────────

def export_rows(patients: list[dict], ids: list[int], x_col: str, y_col: str) -> list[dict]:
    """The list's rows for these patients, in the order given, from the cohort the
    server holds (never values sent by the browser). Unknown ids are skipped."""
    by_id = {p.get('InternalId'): p for p in patients}
    cols = list(dict.fromkeys([x_col, y_col]))
    rows = []
    for pid in ids:
        p = by_id.get(pid)
        if p is None:
            continue
        row = {'Name': p.get('PatientName') or '', 'Age': p.get('Age'),
               'Sex': p.get('Gender') or '', 'Status': _STATUS.get(p.get('PatientStatus'), '')}
        for col in cols:
            if col != 'Age':
                row[COL_LABELS[col]] = p.get(col)
        row['Next appointment'] = p.get('NextApptDate') or ''
        rows.append(row)
    return rows


def _cell(value) -> str:
    if value is None:
        return ''
    text = str(value)
    # A spreadsheet runs a cell starting with these as a formula.
    return "'" + text if text[:1] in ('=', '+', '-', '@') and not _is_number(text) else text


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def to_csv(rows: list[dict], heading: str) -> str:
    out = io.StringIO()
    out.write(f'# {heading}\n')
    if rows:
        w = csv.writer(out)
        w.writerow(list(rows[0]))
        for r in rows:
            w.writerow([_cell(v) for v in r.values()])
    return out.getvalue()


def to_markdown(rows: list[dict], heading: str) -> str:
    def md(v) -> str:
        return _cell(v).replace('|', '\\|').replace('\n', ' ')
    lines = [f'# {heading}', '']
    if rows:
        cols = list(rows[0])
        lines.append('| ' + ' | '.join(cols) + ' |')
        lines.append('|' + '---|' * len(cols))
        lines += ['| ' + ' | '.join(md(v) for v in r.values()) + ' |' for r in rows]
    return '\n'.join(lines) + '\n'
