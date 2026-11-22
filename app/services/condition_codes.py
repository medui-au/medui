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
COLUMNS = (('condition', 'TEXT'), ('item_code', 'INTEGER'), ('bp_item', 'TEXT'), ('practice_item', 'TEXT'),
           ('note', 'TEXT'))
_TTL = 300
_mem: tuple[dict, float] | None = None
_names_filled = False      # bp_item and practice_item filled once per process
_columns_checked = False   # practice_item added to an older table once per process
PRACTICE_MIN_ENTRIES = 3   # a recorded text names a code only if this many entries use it
DESCRIPTION = (
    'Which Best Practice past-history item codes count as each condition: the Disease '
    'Profile badges, and conditions that affect how results read (see the influences table), '
    'ADR-108. One row per condition and code; delete a row to stop a code counting, add one to '
    'make it count. For reading only, filled in automatically where blank: bp_item is Best '
    "Practice's dictionary name(s) for the code (needs read access to BPSDrugs), practice_item "
    'the wording most often recorded for it at this practice (used by at least 3 entries).')

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
    # ADR-171: for the practice protocols' default target options and their badges.
    'familial_hypercholesterolaemia': ((1446,), 'Familial hypercholesterolaemia, ADR-171'),
    'revascularisation':    ((3578, 3579, 3576, 7338, 3544, 6488),
                             'CABG, coronary angioplasty / stent, carotid endarterectomy, iliac stent, ADR-171'),
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
    'isFH': 'familial_hypercholesterolaemia', 'isRevascularisation': 'revascularisation',
}

# Conditions added after the table was first made (ADR-171): put into an existing table once,
# so a practice's own edits to the other conditions are kept. A condition an administrator
# later empties is not put back.
ADDED_LATER = ('familial_hypercholesterolaemia', 'revascularisation')
_ADDED_KEY = 'condition_codes.added_conditions'
# Conditions that aren't badges: reported in profile['present'] for the influences.
PRESENT = ('haemoglobinopathy', 'haemolysis', 'iron_deficiency', 'b12_folate_deficiency',
           'asplenia', 'advanced_ckd')


def _defaults() -> dict[str, frozenset]:
    return {c: frozenset(codes) for c, (codes, _n) in DEFAULTS.items()}


def ensure_added_conditions() -> list[str]:
    """Insert the rows of each ADDED_LATER condition into an existing table, once ever
    (remembered in a system setting). Returns the conditions added now."""
    from app.models.system_setting import SystemSetting
    from app.services import mapping_service
    done = set(SystemSetting.get(_ADDED_KEY, []) or [])
    todo = [c for c in ADDED_LATER if c not in done]
    if not todo:
        return []
    rows, _total = mapping_service.get_rows(TABLE, page=1, per_page=10000)
    present = {str(r.get('condition') or '').strip().lower() for r in rows}
    added = []
    for condition in todo:
        if condition not in present:
            codes_, note = DEFAULTS[condition]
            for code in codes_:
                mapping_service.row_insert(TABLE, {'condition': condition, 'item_code': code, 'note': note or None})
            added.append(condition)
    SystemSetting.set(_ADDED_KEY, sorted(done | set(todo)),
                      description='Conditions added to condition_codes after it was made (ADR-171)')
    return added


def _ensure_columns() -> None:
    """Add practice_item to a table made before ADR-183, once per process."""
    global _columns_checked
    if _columns_checked:
        return
    from app.services import mapping_service
    if 'practice_item' not in {c['column_name'] for c in mapping_service.get_schema(TABLE)}:
        mapping_service.column_add(TABLE, 'practice_item', 'TEXT')
        mapping_service.update_settings(TABLE, description=DESCRIPTION)
    _columns_checked = True


def ensure_table() -> bool:
    """Create and fill the table if it isn't there. True if it was created now."""
    from app.services import mapping_service
    if mapping_service.get_table(TABLE):
        ensure_added_conditions()
        _ensure_columns()
        return False
    mapping_service.create_table(TABLE, 'Condition codes (Disease Profile)', DESCRIPTION)
    for col, col_type in COLUMNS:
        mapping_service.column_add(TABLE, col, col_type)
    for condition, (codes, note) in DEFAULTS.items():
        for code in codes:
            mapping_service.row_insert(TABLE, {'condition': condition, 'item_code': code, 'note': note or None})
    from app.models.system_setting import SystemSetting
    SystemSetting.set(_ADDED_KEY, sorted(ADDED_LATER),
                      description='Conditions added to condition_codes after it was made (ADR-171)')
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
    _fill_names(rows)
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


def bp_names(terms: list[dict]) -> dict[int, str]:
    """{code: name} from BP's dictionary (BPSDrugs.TERMNAMES rows): every current synonym,
    joined with " / "; a retired term's names, marked, when it has no current one."""
    current: dict[int, list[str]] = {}
    retired: dict[int, list[str]] = {}
    for t in terms:
        name = (t.get('TERMNAME') or '').strip()
        if name:
            bucket = current if _int(t.get('RECORDSTATUS')) == 1 else retired
            bucket.setdefault(_int(t.get('TERMID')), []).append(name)
    out = {}
    for code in set(current) | set(retired):
        if current.get(code):
            out[code] = ' / '.join(dict.fromkeys(current[code]))[:270]
        else:   # a term BP has retired, still on patients' records
            out[code] = ' / '.join(dict.fromkeys(retired[code]))[:270] + ' (no longer current in BP)'
    return out


def practice_names(texts: list[dict], minimum: int = PRACTICE_MIN_ENTRIES) -> dict[int, str]:
    """{code: the text most often recorded for it} from condition_item_texts rows
    (ITEMCODE, ITEMTEXT, N). A text used by fewer than `minimum` entries never names a code."""
    best: dict[int, tuple[int, str]] = {}
    for t in texts:
        code, text, n = _int(t.get('ITEMCODE')), (t.get('ITEMTEXT') or '').strip(), _int(t.get('N')) or 0
        if code is None or not text or n < minimum:
            continue
        if code not in best or n > best[code][0] or (n == best[code][0] and text < best[code][1]):
            best[code] = (n, text)
    return {code: text[:270] for code, (n, text) in best.items()}


def _read_bp(query: str) -> list[dict] | None:
    """One BP query for the names; None (logged) if BP or that database can't be read."""
    from app.sql.query_loader import ReadOnlySession, load_query
    conn_str = current_app.config.get('BPSDB_URI')
    if not conn_str:
        return None
    try:
        with ReadOnlySession(conn_str) as session:
            return session.execute(load_query(query))
    except Exception as exc:  # BPSDB boundary: the names are for reading only
        current_app.logger.warning('condition_codes: %s unavailable: %s', query, exc)
        return None


def _fill_names(rows: list[dict]) -> None:
    """Fill blank bp_item and practice_item cells (ADR-183), once per process and only if
    there are blanks. Each column has its own source and fills on its own: bp_item from BP's
    dictionary (BPSDrugs, which a practice may not have access to), practice_item from the
    practice's own past-history wording (BPSPatients). A source that can't be read leaves its
    column blank. A cell that already has text is never changed."""
    global _names_filled
    sources = (('bp_item', 'condition_term_names', bp_names),
               ('practice_item', 'condition_item_texts', practice_names))
    wanted = [(col, q, fn) for col, q, fn in sources
              if any(not str(r.get(col) or '').strip() and r.get('item_code') is not None for r in rows)]
    if _names_filled or not wanted:
        return
    _names_filled = True
    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    from app.services import mapping_service
    for col, query, build in wanted:
        found = _read_bp(query)
        if found is None:
            continue
        names = build(found)
        try:
            for r in rows:
                if str(r.get(col) or '').strip() or r.get('item_code') is None:
                    continue
                text = names.get(_int(r.get('item_code')))
                if text:
                    mapping_service.cell_update(TABLE, r['id'], col, text)
                    r[col] = text
        except (ValueError, SQLAlchemyError) as exc:
            db.session.rollback()
            current_app.logger.warning('condition_codes: %s not filled: %s', col, exc)


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
    a1c = profile.get('hba1c_badge') or {}
    if profile.get('isDiabetes'):
        out['diabetes'] = {'status': 'recorded', 'year': profile.get('DiabetesRecordedYear'),
                           'latest': profile.get('hba1c_latest')}
    elif a1c.get('state') == 'met':
        out['diabetes'] = {'status': 'criterion_met', 'results': a1c.get('results'), 'latest': a1c.get('latest'),
                           'influences': a1c.get('influences') or []}
    else:
        out['diabetes'] = {'status': 'none'}
    egfr = profile.get('egfr_badge') or {}
    if profile.get('isCKDRecorded'):
        out['ckd'] = {'status': 'recorded', 'year': profile.get('CKDRecordedYear'),
                      'stage': profile.get('CKDRecordedStage'), 'latest': profile.get('egfr_latest')}
    elif egfr.get('state') == 'met':
        out['ckd'] = {'status': 'criterion_met', 'results': [egfr.get('latest')], 'latest': egfr.get('latest')}
    else:
        out['ckd'] = {'status': 'none'}
    return out
