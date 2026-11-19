"""Chart bands are the laboratory's range from the most recent result (ADR-105). Invented values."""
from datetime import datetime

from app.services.chart_service import ChartService, parse_range_string


def test_parse_range_forms():
    assert parse_range_string('3.5-5.5') == (3.5, 5.5)
    assert parse_range_string('0.5 - 4.0') == (0.5, 4.0)
    assert parse_range_string('>60') == (60.0, None)
    assert parse_range_string('over 90') == (90.0, None)
    assert parse_range_string('under 7') == (None, 7.0)
    assert parse_range_string('>90/Male') == (90.0, None)
    assert parse_range_string('') == (None, None)
    assert parse_range_string('see report') == (None, None)


def _charts(records, monkeypatch):
    svc = ChartService('unused')
    monkeypatch.setattr(svc, '_get_patient_demographics', lambda pid: {})
    return svc._build_chart_data(1, records, [], [], [])


def test_band_uses_most_recent_range(monkeypatch):
    rows = [
        {'ResultName': 'PSA', 'ResultValue': '2.1', 'ReportDate': datetime(2019, 3, 1), 'Range': '<3.0'},
        {'ResultName': 'PSA', 'ResultValue': '3.9', 'ReportDate': datetime(2025, 6, 1), 'Range': '<5.5'},
        {'ResultName': 'PSA', 'ResultValue': '4.2', 'ReportDate': datetime(2026, 2, 1), 'Range': ''},
    ]
    scale = _charts(rows, monkeypatch)['PSA']['scale']
    assert scale['normalMax'] == 5.5
    assert 'normalMin' not in scale


def test_no_medui_target_without_a_lab_range(monkeypatch):
    rows = [{'ResultName': 'HbA1c', 'ResultValue': '7.4', 'ReportDate': datetime(2026, 1, 5), 'Range': ''}]
    scale = _charts(rows, monkeypatch)['HbA1c']['scale']
    assert 'normalMax' not in scale and 'normalMin' not in scale
    assert scale['max'] == 15          # the axis setting stays


def test_caption_names_the_result_whose_range_is_shown(monkeypatch):
    rows = [{'ResultName': 'TSH', 'ResultValue': '2.0', 'ReportDate': datetime(2026, 4, 2), 'Range': '0.5-4.0'}]
    lines = _charts(rows, monkeypatch)['TSH']['subtitle']
    assert any("Laboratory's range 0.5-4.0" in line and '2026-04-02' in line for line in lines)
