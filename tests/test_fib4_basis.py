"""FIB-4 is shown as MedUI's calculation, with its formula, inputs and source, and no cut-off
(ADR-168). Invented values only."""
from datetime import date
from pathlib import Path

from app.services import chart_service

SQL = Path(__file__).resolve().parent.parent / 'app' / 'sql'
AI_QUERIES = ('patient_json_fib4.sql', 'patient_json_fib4_noid.sql',
              'patient_json_pathology_compact.sql', 'patient_json_pathology_compact_noid.sql')


def test_no_cut_off_of_medui_own_anywhere():
    for f in SQL.glob('*.sql'):
        text = f.read_text()
        assert '1.45' not in text, f.name


def test_ai_queries_label_fib4_as_calculated_with_inputs_and_source():
    for name in AI_QUERIES:
        text = (SQL / name).read_text()
        assert 'FIB-4 (calculated by MedUI, not a laboratory result)' in text, name
        assert 'Sterling et al., Hepatology 2006' in text, name
        assert "', platelets '" in text and "'from age '" in text, name
        assert "'0-1.45'" not in text and "THEN '+'" not in text, name


def test_chart_query_returns_the_inputs():
    text = (SQL / 'patient_charts_fib4.sql').read_text()
    for col in ('AS Age', 'AS AST', 'AS ALT', 'AS PLT', 'AS PLTDate'):
        assert col in text


def test_chart_subtitle_states_formula_method_and_source():
    text = ' '.join(chart_service.FIB4_SUBTITLE)
    assert 'calculated by MedUI, not reported by the laboratory' in text
    assert 'same day' in text and 'within 30 days' in text
    assert 'Sterling' in text and 'No cut-off' in text


def test_point_inputs():
    s = chart_service.fib4_inputs({'Age': 61, 'AST': '40', 'ALT': '35', 'PLT': '210',
                                   'PLTDate': date(2026, 3, 2)})
    assert s == 'Age 61, AST 40, ALT 35, platelets 210 (02/03/2026)'
