"""Population chart condition flags (ADR-146). Invented values only."""
from app.services.condition_codes import DEFAULTS, _defaults
from app.services.scatter_service import CONDITION_FLAGS, _active_codes, _post_process

T = _defaults()


def row(codes):
    return {'InternalId': 1, 'Height': None, 'Weight': None, 'ActiveCodes': codes, 'IsSmoker': 0}


def test_every_chart_condition_has_a_default_list():
    assert set(CONDITION_FLAGS.values()) <= set(DEFAULTS)


def test_paroxysmal_af_counts_like_the_badge():
    p = _post_process([row('5319,1470')], T)[0]
    assert p['IsAF'] is True and p['IsHT'] is True and p['IsDiabetic'] is False


def test_the_table_decides():
    table = dict(T, af=frozenset({1079}))
    assert _post_process([row('5319')], table)[0]['IsAF'] is False


def test_no_items_and_the_codes_column_is_not_returned():
    p = _post_process([row(None)], T)[0]
    assert not any(p[f] for f in CONDITION_FLAGS)
    assert 'ActiveCodes' not in p


def test_active_codes_parsing():
    assert _active_codes('3347, 8070,x,') == {3347, 8070}
    assert _active_codes(None) == set()


def test_a_condition_missing_from_the_table_uses_its_built_in_codes():
    live = {'af': frozenset({1079})}                      # a table without the chart's conditions
    table = {**_defaults(), **live}
    p = _post_process([row('3347,5319')], table)[0]
    assert p['IsOSA'] is True and p['IsAF'] is False


# ── Patient list download (ADR-147). Invented patients. ─────────────────────

from app.services.scatter_service import EXPORT_LIMIT, export_rows, to_csv, to_markdown

COHORT = [
    {'InternalId': 1, 'PatientName': 'Ada Example', 'Age': 61.4, 'Gender': 'Female',
     'PatientStatus': 1, 'BMI': 27.3, 'NextApptDate': '2026-12-01'},
    {'InternalId': 2, 'PatientName': '=Bob | Sample', 'Age': 47.0, 'Gender': 'Male',
     'PatientStatus': 2, 'BMI': None, 'NextApptDate': None},
]


def test_export_rows_use_the_server_values_in_the_given_order():
    rows = export_rows(COHORT, [2, 1, 99], 'Age', 'BMI')
    assert [r['Name'] for r in rows] == ['=Bob | Sample', 'Ada Example']   # 99 unknown: skipped
    assert list(rows[0]) == ['Name', 'Age', 'Sex', 'Status', 'BMI', 'Next appointment']
    assert rows[0]['Status'] == 'Inactive' and rows[0]['BMI'] is None


def test_csv_guards_against_formulas_and_keeps_numbers():
    text = to_csv(export_rows(COHORT, [2, 1], 'Age', 'BMI'), 'heading')
    assert text.startswith('# heading\n')
    assert "'=Bob | Sample" in text and ',47.0,' in text


def test_markdown_escapes_pipes():
    text = to_markdown(export_rows(COHORT, [2], 'BMI', 'Age'), 'heading')
    assert '\\|' in text and text.count('\n| ') == 2      # header row and one patient


def test_the_limit():
    assert EXPORT_LIMIT == 500
