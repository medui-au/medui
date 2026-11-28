"""Patient Charts print with their charts drawn (ADR-192): the print redraw is not animated, and
it runs on the browser's beforeprint event, so Ctrl+P prints them too."""
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / 'app/templates/clinical/patient_charts.html'


def test_print_charts_are_drawn_before_the_print_is_taken():
    html = TEMPLATE.read_text()
    assert 'animation: isPrinting ? false : undefined' in html
    assert "addEventListener('beforeprint', () => redraw(true))" in html
    assert "addEventListener('afterprint',  () => redraw(false))" in html
    # The Print button only prints; the redraw belongs to beforeprint, not to a timer.
    assert 'setTimeout' not in html.split('window.printCharts')[1].split('};')[0]


def test_printed_page_names_the_patient_and_the_date():
    html = TEMPLATE.read_text()
    assert 'class="charts-print-patient"' in html and ".charts-print-patient { display: none; }" in html
    assert "patient.get('DOB') | clinical_date" in html and 'id="charts-printed-date"' in html
    assert '.charts-header {\n            display: none !important;' in html
