"""Harmonising never merges a percentage with a count (ADR-132). Invented values only."""
from pathlib import Path

from app.services.inbox_outlier_service import harmonise

ROOT = Path(__file__).resolve().parents[1]


def _row(date, code, name, value, units):
    return {'ReportDate': date, 'LoincCode': code, 'ResultName': name,
            'ResultValue': value, 'Units': units, 'Range': '', 'AbnormalFlag': ''}


def _codes(rows):
    return {(r['LoincCode'], r['Units']) for r in harmonise(rows)}


def test_a_percentage_keeps_its_own_code_beside_a_count():
    rows = [_row('2021-03-01', '5905-5', 'Monocytes', '8', '%'),
            _row('2021-03-01', '742-7', 'Monocytes', '0.7', 'x10*9/L'),
            _row('2025-06-01', '742-7', 'Monocytes', '0.9', 'x10*9/L')]
    assert _codes(rows) == {('5905-5', '%'), ('742-7', 'x10*9/L')}


def test_counts_under_two_codes_still_merge():
    rows = [_row('2020-01-01', '26484-6', 'Monocytes', '0.6', '10*9/L'),
            _row('2025-06-01', '742-7', 'Monocytes', '0.9', 'x10*9/L')]
    assert {c for c, _ in _codes(rows)} == {'742-7'}


def test_percentages_under_two_codes_still_merge():
    rows = [_row('2020-01-01', '26485-3', 'Monocytes', '7', '%'),
            _row('2025-06-01', '5905-5', 'Monocytes', '8', '%')]
    assert {c for c, _ in _codes(rows)} == {'5905-5'}


def test_one_code_under_two_names_still_takes_the_latest_name():
    rows = [_row('2020-01-01', '742-7', 'Mono', '0.6', 'x10*9/L'),
            _row('2025-06-01', '742-7', 'Monocytes', '0.9', 'x10*9/L')]
    assert {r['ResultName'] for r in harmonise(rows)} == {'Monocytes'}
    assert all('_name_kind' not in r for r in harmonise(rows))


def test_the_atomised_query_splits_pass_2_by_percentage():
    # One key column, not an extra grouping column: with the extra column SQL
    # Server picked a plan 100 times slower (80 s for one patient).
    sql = (ROOT / 'app' / 'sql' / 'patient_pathatom.sql').read_text()
    assert "CASE WHEN a.UNITS LIKE '%[%]%' THEN N' [%]' ELSE N'' END AS CODEKEY" in sql
    assert 'GROUP BY INTERNALID, CODEKEY' in sql
    assert 'PARTITION BY INTERNALID, CODEKEY' in sql
    assert sql.count('nh.CODEKEY    = ') == 2
    assert 'nh.RESULTNAME = mc.RESULTNAME' not in sql


def test_a_name_with_both_kinds_gets_a_percentage_chart():
    from app.services.chart_service import chart_name, names_with_percent_and_count
    rows = [_row('2021-03-01', '5905-5', 'Monocytes', '8', '%'),
            _row('2025-06-01', '742-7', 'Monocytes', '0.9', 'x10*9/L'),
            _row('2025-06-01', '4548-4', 'HbA1c', '6.1', '%')]
    mixed = names_with_percent_and_count(rows)
    assert mixed == {'Monocytes'}
    assert [chart_name(r, mixed) for r in rows] == ['Monocytes (%)', 'Monocytes', 'HbA1c']


def test_the_charts_page_draws_them_apart(monkeypatch):
    from app.services.chart_service import ChartService
    svc = ChartService.__new__(ChartService)
    monkeypatch.setattr(svc, '_get_patient_demographics', lambda pid: {})
    rows = [_row('2021-03-01', '5905-5', 'Monocytes', '8', '%'),
            _row('2025-06-01', '742-7', 'Monocytes', '0.9', 'x10*9/L')]
    charts = svc._build_chart_data(1, rows, [], [], [])
    assert set(charts) == {'Monocytes', 'Monocytes (%)'}
