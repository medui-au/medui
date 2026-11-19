"""Which Best Practice history items count as each condition (ADR-108).

An admin mapping table, condition_codes (Admin → Mapping Tables), one row per
(condition, BP item code): the practice can see and change what counts as
"recorded diabetes", "recorded CKD" and the rest. It is created on first use and
filled with the lists MedUI used before (DEFAULTS), so nothing changes until an
administrator edits it. The Disease Profile's flags are worked out here from the
patient's active history items; the results-based criteria (eGFR, HbA1c) stay in
code (egfr_criterion, hba1c_criterion) and are never merged with "recorded".
"""
import time

from flask import current_app

TABLE = 'condition_codes'
COLUMNS = (('condition', 'TEXT'), ('item_code', 'INTEGER'), ('bp_item', 'TEXT'), ('note', 'TEXT'))
_TTL = 300
_mem: tuple[dict, float] | None = None
_names_filled = False      # bp_item filled from BP's dictionary once per process

# condition → (codes, note). Exactly the lists in patient_disease_profile.sql before ADR-108.
DEFAULTS: dict[str, tuple[tuple[int, ...], str]] = {
    'diabetes':             ((778, 776, 775, 774), 'Recorded diabetes (not borderline/IFG 779 or gestational 780), ADR-107'),
    'diabetes_type1':       ((776,), 'Shown as "type 1"'),
    'diabetes_type2':       ((778,), 'Shown as "type 2"'),
    'ihd':                  ((2376, 7847, 1534, 3576, 3578, 3579, 226, 6847), ''),
    'hypertension':         ((5, 1470, 1471), ''),
    'af':                   ((1079, 1080, 1081, 5319), ''),
    'cva':                  ((677, 678, 4253, 682), ''),
    'vasculopathy':         ((677, 678, 682, 1534, 3578, 3579, 3481, 3083, 4651, 4253, 9520), ''),
    'colon_ca_polyps':      ((2429, 2805, 2812, 453, 1036, 480), ''),
    'fh_colon_ca':          ((1074,), ''),
    'hypercholesterolaemia': ((1438, 1446, 1445), ''),
    'cardiomyopathy':       ((496, 5180), ''),
    'covid19':              ((13338,), ''),
    'pacemaker':            ((2609, 2610, 2611, 2948, 5116, 7243, 7249, 10622), ''),
    'ckd':                  ((662, 7502, 7503, 7504, 7505, 7506, 8119, 8120, 3132, 1564),
                             'Recorded CKD (not acute renal failure / AKI or provisional items), ADR-104'),
    'ckd_staged':           ((7502, 7503, 7504, 7505, 7506, 8119, 8120), 'CKD items that carry a stage'),
    # Conditions that affect how results read; what each means in a situation is the
    # influences table (app/services/influences.py).
    'haemoglobinopathy':    ((211, 208, 7693), 'Thalassaemia (minor, trait)'),
    'haemolysis':           ((196, 8337), 'Haemolytic anaemia'),
    'iron_deficiency':      ((723, 199, 6005), ''),
    'b12_folate_deficiency': ((741, 203, 193, 721), 'B12 deficiency, pernicious anaemia, folate deficiency'),
    'asplenia':             ((3958, 3959, 5805), 'Splenectomy, asplenia'),
    'advanced_ckd':         ((7505, 7506, 3132, 2882, 2853), 'CKD 4-5, kidney failure, dialysis'),
    'pregnancy':            ((2971,), 'Counts in any status'),
    # Population chart filters only, no badge (ADR-146): the codes the chart always used.
    'osa':                  ((3347, 8070, 8071), 'Sleep apnoea: population chart filter'),
    'wboa':                 ((3718, 3719, 3793, 2577, 2576, 2573),
                             'Osteoarthritis of weight-bearing joints: population chart filter'),
    'depression_anxiety':   ((243, 2029, 758, 760, 757, 5205, 2233, 27517, 7920, 5893),
                             'Depression or anxiety: population chart filter'),
}

# Profile flag ← condition (the keys the badges and criteria already use).
FLAGS = {
    'isDiabetes': 'diabetes', 'isIDDM': 'diabetes_type1', 'isNIDDM': 'diabetes_type2',
    'isIHD': 'ihd', 'isHT': 'hypertension', 'isAF': 'af', 'isCVA': 'cva',
    'isVasculopathy': 'vasculopathy', 'isColonCaPolyps': 'colon_ca_polyps',
    'isFHCaColon': 'fh_colon_ca', 'isHypercholesterolaemia': 'hypercholesterolaemia',
    'isCardiomyopathy': 'cardiomyopathy', 'isCovid19': 'covid19', 'isPacemaker': 'pacemaker',
    'isCKDRecorded': 'ckd',
}
# Conditions that aren't badges: reported in profile['present'] for the influences.
PRESENT = ('haemoglobinopathy', 'haemolysis', 'iron_deficiency', 'b12_folate_deficiency',
           'asplenia', 'advanced_ckd')


def _defaults() -> dict[str, frozenset]:
    return {c: frozenset(codes) for c, (codes, _n) in DEFAULTS.items()}


def ensure_table() -> bool:
    """Create and fill the table if it isn't there. True if it was created now."""
    from app.services import mapping_service
    if mapping_service.get_table(TABLE):
        return False
    mapping_service.create_table(
        TABLE, 'Condition codes (Disease Profile)',
        'Which Best Practice past-history item codes count as each condition: the Disease '
        'Profile badges, and conditions that affect how results read (see the influences table), '
        'ADR-108. One row '
        'per condition and code; delete a row to stop a code counting, add one to make it count. '
        'bp_item is Best Practice\'s dictionary name(s) for the code, filled in automatically, '
        'for reading only.')
    for col, col_type in COLUMNS:
        mapping_service.column_add(TABLE, col, col_type)
    for condition, (codes, note) in DEFAULTS.items():
        for code in codes:
            mapping_service.row_insert(TABLE, {'condition': condition, 'item_code': code, 'note': note or None})
    return True


def codes() -> dict[str, frozenset]:
    """{condition: frozenset(item codes)} from the table, cached for five minutes. The
    built-in lists if the table can't be read or is empty."""
    global _mem
    if _mem and (time.monotonic() - _mem[1]) < _TTL:
        return _mem[0]
    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    from app.services import mapping_service
    try:
        ensure_table()
        rows, _total = mapping_service.get_rows(TABLE, page=1, per_page=10000)
    except (ValueError, SQLAlchemyError) as exc:
        db.session.rollback()
        current_app.logger.error('condition_codes unreadable, using the built-in lists: %s', exc)
        return _defaults()
    _fill_bp_items(rows)
    found: dict[str, set] = {}
    for row in rows:
        condition = str(row.get('condition') or '').strip().lower()
        try:
            code = int(row.get('item_code'))
        except (TypeError, ValueError):
            continue
        if condition:
            found.setdefault(condition, set()).add(code)
    result = {c: frozenset(v) for c, v in found.items()} if found else _defaults()
    _mem = (result, time.monotonic())
    return result


def _fill_bp_items(rows: list[dict]) -> None:
    """Fill blank bp_item cells with BP's current names for the code (its dictionary,
    BPSDrugs.TERMNAMES, never a patient's item text, which can be edited). Once per
    process, and only if there are blanks; skipped quietly if BP is unavailable."""
    global _names_filled
    blanks = [r for r in rows if not str(r.get('bp_item') or '').strip() and r.get('item_code') is not None]
    if _names_filled or not blanks:
        return
    _names_filled = True
    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    from app.services import mapping_service
    from app.sql.query_loader import ReadOnlySession, load_query
    conn_str = current_app.config.get('BPSDB_URI')
    if not conn_str:
        return
    try:
        with ReadOnlySession(conn_str) as session:
            terms = session.execute(load_query('condition_term_names'))
    except Exception as exc:  # BPSDB boundary: the names are for reading only
        current_app.logger.warning('condition_codes: BP term names unavailable: %s', exc)
        return
    current: dict[int, list[str]] = {}
    retired: dict[int, list[str]] = {}
    for t in terms:
        name = (t.get('TERMNAME') or '').strip()
        if name:
            bucket = current if _int(t.get('RECORDSTATUS')) == 1 else retired
            bucket.setdefault(_int(t.get('TERMID')), []).append(name)
    try:
        for r in blanks:
            code = _int(r.get('item_code'))
            found, suffix = current.get(code), ''
            if not found and retired.get(code):
                # A term BP has retired, still on patients' records.
                found, suffix = retired[code], ' (no longer current in BP)'
            if found:
                text = (' / '.join(dict.fromkeys(found))[:270] + suffix)
                mapping_service.cell_update(TABLE, r['id'], 'bp_item', text)
                r['bp_item'] = text
    except (ValueError, SQLAlchemyError) as exc:
        db.session.rollback()
        current_app.logger.warning('condition_codes: bp_item not filled: %s', exc)


# PASTHISTORY.STATUSCODE values that count as active (2 is inactive).
ACTIVE_STATUS = frozenset({0, 1})


def profile_flags(items: list[dict], table: dict[str, frozenset] | None = None) -> dict:
    """The Disease Profile's coded fields from the patient's history items
    (patient_history_codes.sql: ITEMCODE, ITEMTEXT, YEAR, RECORDID, STATUSCODE).
    Active items only, except pregnancy, which counts in any status. Active is STATUSCODE 1,
    or 0: a coded "Reason for visit" copied to Past History (ADR-145; the query is coded only)."""
    table = table if table is not None else codes()
    active = [i for i in items if _int(i.get('STATUSCODE')) in ACTIVE_STATUS]
    active_codes = {_int(i.get('ITEMCODE')) for i in active}
    out = {flag: 1 if active_codes & table.get(cond, frozenset()) else 0 for flag, cond in FLAGS.items()}

    def latest(cond: str, prefer: str | None = None):
        wanted = table.get(cond, frozenset())
        pool = [i for i in active if _int(i.get('ITEMCODE')) in wanted]
        if not pool:
            return None
        preferred = table.get(prefer, frozenset()) if prefer else frozenset()
        return max(pool, key=lambda i: (_int(i.get('ITEMCODE')) in preferred,
                                        _int(i.get('YEAR')) or 0, _int(i.get('RECORDID')) or 0))

    staged = latest('ckd_staged')
    out['CKDRecordedStage'] = (staged.get('ITEMTEXT') or '').strip() if staged else None
    ckd_item = latest('ckd', prefer='ckd_staged')
    out['CKDRecordedYear'] = (_int(ckd_item.get('YEAR')) or None) if ckd_item else None
    dm_item = latest('diabetes')
    out['DiabetesRecordedYear'] = (_int(dm_item.get('YEAR')) or None) if dm_item else None
    # {condition: year of its latest active item, or 0} for the conditions in PRESENT.
    out['present'] = {}
    for cond in PRESENT:
        found = latest(cond)
        if found:
            out['present'][cond] = _int(found.get('YEAR')) or 0
    preg = table.get('pregnancy', frozenset())
    years = sorted({_int(i.get('YEAR')) for i in items
                    if _int(i.get('ITEMCODE')) in preg and (_int(i.get('YEAR')) or 0) > 0})
    out['PregnancyYears'] = ','.join(str(y) for y in years) or None
    return out


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def summary(profile: dict) -> dict:
    """The three-way answer for the conditions that have a results criterion (ADR-108):
    {'diabetes'|'ckd': {'status': 'recorded' | 'criterion_met' | 'none', ...}}; a criterion
    met carries the conditions recorded that affect how its results read (influences).
    'recorded' comes from the codes; 'criterion_met' from the results (egfr_criterion,
    hba1c_criterion), never merged with it: a criterion met is not a diagnosis."""
    out = {}
    a1c = profile.get('hba1c_criterion') or {}
    if profile.get('isDiabetes'):
        out['diabetes'] = {'status': 'recorded', 'year': profile.get('DiabetesRecordedYear'),
                           'latest': profile.get('hba1c_latest')}
    elif a1c.get('state') == 'met':
        out['diabetes'] = {'status': 'criterion_met', 'results': a1c.get('days'), 'latest': a1c.get('latest'),
                           'influences': a1c.get('influences') or []}
    else:
        out['diabetes'] = {'status': 'none'}
    egfr = profile.get('egfr_criterion') or {}
    if profile.get('isCKDRecorded'):
        out['ckd'] = {'status': 'recorded', 'year': profile.get('CKDRecordedYear'),
                      'stage': profile.get('CKDRecordedStage'), 'latest': profile.get('egfr_latest')}
    elif egfr.get('state') in ('met', 'met_previously'):
        out['ckd'] = {'status': 'criterion_met', 'results': egfr.get('run'), 'latest': egfr.get('latest'),
                      'previously': egfr.get('state') == 'met_previously'}
    else:
        out['ckd'] = {'status': 'none'}
    return out
