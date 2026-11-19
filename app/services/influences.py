"""What a recorded condition means for reading a result, by situation (ADR-108).

An admin mapping table, influences (Admin → Mapping Tables): one row per
(situation, condition) with the effect, the results worth showing, the wording
and its source. The rules themselves (when a badge appears) stay in tested code;
this table is their interpretation, visible and editable by the practice. A
situation is a hook a rule asks for, e.g. 'hba1c_interpretation' from the HbA1c
badge. Created on first use and filled with DEFAULTS.
"""
import time

from flask import current_app

TABLE = 'influences'
COLUMNS = (('situation', 'TEXT'), ('condition', 'TEXT'), ('effect', 'TEXT'),
           ('show_results', 'TEXT'), ('wording', 'TEXT'), ('source', 'TEXT'))
# Results MedUI can fetch for show_results (patient_marker_results.sql, and eGFR).
KNOWN_RESULTS = ('ferritin', 'haemoglobin', 'b12', 'folate', 'egfr')
EFFECTS = ('may raise', 'may lower', 'either')
_TTL = 300
_mem: tuple[list, float] | None = None

_ADS = 'ADS position statement, MJA 2015 (Box 1); RACGP Management of type 2 diabetes'
DEFAULTS = (
    ('hba1c_interpretation', 'iron_deficiency', 'may raise', 'ferritin, haemoglobin',
     'Iron deficiency can raise HbA1c independently of glucose (older red cells); iron treatment can lower it.', _ADS),
    ('hba1c_interpretation', 'b12_folate_deficiency', 'may raise', 'b12, folate, haemoglobin',
     'B12 or folate deficiency can raise HbA1c (older red cells); treatment can lower it.', _ADS),
    ('hba1c_interpretation', 'asplenia', 'may raise', '',
     'After splenectomy or with asplenia, red cells live longer and HbA1c can read higher.', _ADS),
    ('hba1c_interpretation', 'haemolysis', 'may lower', 'haemoglobin',
     'Haemolysis shortens red-cell life and can lower HbA1c: glucose may be higher than the result suggests.', _ADS),
    ('hba1c_interpretation', 'advanced_ckd', 'either', 'egfr',
     'In advanced CKD, renal anaemia and erythropoietin can lower HbA1c; some methods read it higher in uraemia.', _ADS),
    ('hba1c_interpretation', 'pregnancy', 'may lower', '',
     'HbA1c can read lower in pregnancy (faster red-cell turnover).', _ADS),
    ('hba1c_interpretation', 'haemoglobinopathy', 'either', 'haemoglobin',
     'A haemoglobin variant can move HbA1c either way, depending on the laboratory\'s method; '
     'fasting glucose or an OGTT confirms.', _ADS),
)


def ensure_table() -> bool:
    from app.services import mapping_service
    if mapping_service.get_table(TABLE):
        return False
    mapping_service.create_table(
        TABLE, 'Influences on results',
        'What a recorded condition means for reading a result, by situation (ADR-108): effect '
        '(may raise / may lower / either), the results to show beside it (' + ', '.join(KNOWN_RESULTS)
        + '), the wording shown, and its source. condition is a key from condition_codes. The '
        'rules themselves are fixed; this is how their results are explained.')
    for col, col_type in COLUMNS:
        mapping_service.column_add(TABLE, col, col_type)
    for situation, condition, effect, show, wording, source in DEFAULTS:
        mapping_service.row_insert(TABLE, {'situation': situation, 'condition': condition, 'effect': effect,
                                           'show_results': show or None, 'wording': wording, 'source': source})
    return True


def _all_rows() -> list[dict]:
    global _mem
    if _mem and (time.monotonic() - _mem[1]) < _TTL:
        return _mem[0]
    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    from app.services import mapping_service
    try:
        ensure_table()
        rows, _total = mapping_service.get_rows(TABLE, page=1, per_page=5000)
    except (ValueError, SQLAlchemyError) as exc:
        db.session.rollback()
        current_app.logger.error('influences unreadable, using the built-in rows: %s', exc)
        rows = [dict(zip(('situation', 'condition', 'effect', 'show_results', 'wording', 'source'), d))
                for d in DEFAULTS]
    _mem = (rows, time.monotonic())
    return rows


def for_situation(situation: str, conditions) -> list[dict]:
    """The influence rows for this situation whose condition is in `conditions`, cleaned:
    [{'condition', 'effect', 'show': [known result names], 'wording', 'source'}]."""
    wanted = set(conditions)
    out = []
    for row in _all_rows():
        if str(row.get('situation') or '').strip() != situation:
            continue
        condition = str(row.get('condition') or '').strip()
        if condition not in wanted:
            continue
        show = [n.strip().lower() for n in str(row.get('show_results') or '').split(',') if n.strip()]
        unknown = [n for n in show if n not in KNOWN_RESULTS]
        if unknown:
            current_app.logger.warning('influences: unknown result name(s) %s ignored', unknown)
        out.append({'condition': condition,
                    'effect': str(row.get('effect') or '').strip().lower(),
                    'show': [n for n in show if n in KNOWN_RESULTS],
                    'wording': str(row.get('wording') or '').strip(),
                    'source': str(row.get('source') or '').strip()})
    return out
