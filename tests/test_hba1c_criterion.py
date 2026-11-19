"""The HbA1c criterion (ADR-107). Invented values only."""
from datetime import date

from app.services.hba1c_criterion import as_percent, conditions_affecting, evaluate, latest_results, qualifies

MMOL, PCT = '59261-8', '4548-4'


def row(d, value, loinc=MMOL):
    return {'ResultDate': d, 'Loinc': loinc, 'ResultValue': value}


def test_thresholds_in_both_units():
    assert qualifies('48', MMOL) and not qualifies('47', MMOL)
    assert qualifies('6.5', PCT) and not qualifies('6.4', PCT)
    assert qualifies('6.5', '17856-6')
    assert qualifies('>14.0', PCT)
    assert qualifies('<4.0', PCT) is False
    assert qualifies('see comment', PCT) is None


def test_value_under_the_wrong_code_is_unreadable():
    assert qualifies('54', PCT) is None          # a mmol/mol value filed under a % code
    assert qualifies('6.8', MMOL) is None        # a % value filed under the mmol/mol code


def test_padded_loinc_is_still_mmol():
    # BP pads codes; 50 mmol/mol must not be read as 50%
    assert qualifies('47', '59261-8   ') is False
    assert qualifies('47', '59261-8   ') is not None


def test_two_days_needed():
    assert evaluate([row(date(2025, 3, 1), '52')])['state'] == 'not_met'
    r = evaluate([row(date(2025, 3, 1), '52'), row(date(2025, 6, 1), '49')])
    assert r['state'] == 'met' and len(r['days']) == 2


def test_same_sample_in_two_units_counts_once():
    d = date(2025, 3, 1)
    r = evaluate([row(d, '52'), row(d, '6.9', PCT)])
    assert r['state'] == 'not_met'
    assert r['latest']['unit'] == 'mmol/mol'


def test_later_normal_results_do_not_undo_it():
    r = evaluate([row(date(2023, 1, 5), '55'), row(date(2023, 4, 2), '58'), row(date(2026, 2, 1), '44')])
    assert r['state'] == 'met'
    assert r['latest']['value'] == '44'


def test_no_condition_hides_the_badge():
    s = [row(date(2025, 3, 1), '52'), row(date(2025, 6, 1), '49')]
    assert evaluate(s)['state'] == 'met'


def test_no_results():
    assert evaluate([])['state'] == 'no_results'
    assert evaluate([row(date(2025, 1, 1), 'n/a')])['state'] == 'no_results'


def test_conditions_affecting():
    assert conditions_affecting({}, None, '65', {2025}) == []
    assert conditions_affecting({'iron_deficiency': 2021}, None, '65', {2025}) == ['iron_deficiency']
    assert conditions_affecting({}, None, '24', {2025}) == ['advanced_ckd']
    assert conditions_affecting({}, None, '>90', {2025}) == []
    assert conditions_affecting({}, '2024', '65', {2025}) == ['pregnancy']
    assert conditions_affecting({}, '2019', '65', {2025}) == []


def test_percent_display():
    assert as_percent('48', MMOL) == '6.5%'           # the two thresholds agree
    assert as_percent('53', MMOL) == '7.0%'
    assert as_percent('64', MMOL) == '8.0%'
    assert as_percent('7.1', PCT) == '7.1%'           # % shown as written
    assert as_percent('>130', MMOL) == '>14.0%'
    r = evaluate([row(date(2025, 3, 1), '52'), row(date(2025, 6, 1), '7.1', PCT)])
    assert [d['pct'] for d in r['days']] == ['6.9%', '7.1%']


def test_latest_results_of_each_marker():
    rows = [{'Marker': 'ferritin', 'ResultDate': date(2024, 1, 5), 'ResultValue': '12', 'Units': 'ug/L^ug/L', 'RefRange': '30-300', 'Flag': 'L'},
            {'Marker': 'ferritin', 'ResultDate': date(2025, 8, 1), 'ResultValue': '45', 'Units': 'ug/L', 'RefRange': '30-300', 'Flag': ''},
            {'Marker': 'b12', 'ResultDate': date(2025, 8, 1), 'ResultValue': '160', 'Units': 'pmol/L', 'RefRange': '>150', 'Flag': ''}]
    m = latest_results(rows)
    assert m['ferritin']['value'] == '45' and m['ferritin']['units'] == 'ug/L'
    assert m['b12']['value'] == '160' and 'haemoglobin' not in m
    assert latest_results([]) == {}
