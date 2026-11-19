"""The eGFR criterion (ADR-104). Invented values only."""
from datetime import date, timedelta

from app.services.egfr_criterion import evaluate, read_value

D0 = date(2025, 1, 10)


def series(*pairs):
    """pairs of (days after D0, value as written)."""
    return [{'ResultDate': D0 + timedelta(days=d), 'ResultValue': v} for d, v in pairs]


def test_read_value_forms():
    assert read_value('52') == 52
    assert read_value(' 52.5 ') == 52.5
    assert read_value('<5') == 5
    assert read_value('<60') < 60
    assert read_value('>90') == 90
    assert read_value('> 90') == 90
    assert read_value('>^90') == 90
    assert read_value('>45') is None
    assert read_value('<90') is None
    assert read_value('') is None
    assert read_value(None) is None
    assert read_value('see comment') is None


def test_no_results():
    assert evaluate([])['state'] == 'no_results'
    assert evaluate(series((0, 'n/a')))['state'] == 'no_results'


def test_one_low_result_is_not_met():
    assert evaluate(series((0, '45')))['state'] == 'not_met'


def test_span_89_days_not_met_90_days_met():
    assert evaluate(series((0, '50'), (89, '50')))['state'] == 'not_met'
    r = evaluate(series((0, '50'), (90, '52')))
    assert r['state'] == 'met'
    assert [x['value'] for x in r['run']] == ['50', '52']


def test_run_broken_by_60_or_above_90():
    assert evaluate(series((0, '50'), (40, '60'), (100, '50')))['state'] == 'not_met'
    assert evaluate(series((0, '50'), (40, '>90'), (100, '50')))['state'] == 'not_met'
    assert evaluate(series((0, '50'), (40, '>^90'), (100, '50')))['state'] == 'not_met'


def test_threshold_edges():
    assert evaluate(series((0, '59'), (120, '59')))['state'] == 'met'
    assert evaluate(series((0, '60'), (120, '60')))['state'] == 'not_met'
    assert evaluate(series((0, '<5'), (120, '8')))['state'] == 'met'


def test_unreadable_values_are_ignored_and_counted():
    r = evaluate(series((0, '50'), (30, '>45'), (100, '50')))
    assert r['state'] == 'met'
    assert r['ignored'] == 1


def test_same_day_duplicates_take_lowest():
    r = evaluate(series((0, '58'), (0, '62'), (95, '55')))
    assert r['state'] == 'met'
    assert len(r['run']) == 2


def test_met_previously_when_latest_recovered():
    r = evaluate(series((0, '50'), (100, '48'), (300, '66')))
    assert r['state'] == 'met_previously'
    assert r['latest']['value'] == '66'
    assert r['run'][-1]['value'] == '48'


def test_most_recent_run_is_shown():
    r = evaluate(series((0, '50'), (100, '50'), (200, '70'), (300, '40'), (400, '42')))
    assert r['state'] == 'met'
    assert r['run'][0]['date'] == D0 + timedelta(days=300)


def test_order_of_input_does_not_matter():
    a = series((0, '50'), (100, '52'))
    assert evaluate(list(reversed(a)))['state'] == 'met'


def test_values_kept_as_written():
    r = evaluate(series((0, '<5'), (100, '7')))
    assert r['run'][0]['value'] == '<5'
