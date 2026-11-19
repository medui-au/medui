"""The Sent to AI tab shows local runs, labelled as staying in the practice (ADR-113)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / 'app/templates/clinical/partials/ai_assist_panel.html').read_text()
PRESEND = (ROOT / 'app/static/js/presend_review.js').read_text()


def _body(src, start):
    i = src.index(start)
    return src[i:src.index('\n}', i)]


def test_panel_no_longer_skips_local_runs():
    body = _body(PANEL, 'function reviewShowSent(d)')
    assert 'd.model_is_local ||' not in body
    assert '!!d.model_is_local' in body


def test_local_banner_says_nothing_left_the_practice():
    body = _body(PRESEND, 'function renderSent(panel, text, review, system, local, opts)')
    assert 'Sent to a local model as shown' in body
    assert 'nothing was sent outside it' in body
