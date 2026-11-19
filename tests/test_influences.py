"""Influences (ADR-108). Invented rows only."""
import pytest

from app.services import influences


@pytest.fixture(autouse=True)
def rows(monkeypatch):
    monkeypatch.setattr(influences, '_all_rows', lambda: [
        {'situation': 'hba1c_interpretation', 'condition': 'iron_deficiency', 'effect': 'May raise',
         'show_results': 'ferritin, Haemoglobin, potassium', 'wording': 'w', 'source': 's'},
        {'situation': 'other', 'condition': 'iron_deficiency', 'effect': '', 'show_results': '', 'wording': '', 'source': ''},
    ])


def test_rows_for_situation_and_present_conditions(app_ctx=None):
    from flask import Flask
    with Flask('t').app_context():
        out = influences.for_situation('hba1c_interpretation', ['iron_deficiency'])
        assert len(out) == 1
        assert out[0]['effect'] == 'may raise'
        assert out[0]['show'] == ['ferritin', 'haemoglobin']      # unknown names dropped
        assert influences.for_situation('hba1c_interpretation', ['asplenia']) == []


def test_every_default_effect_and_result_is_known():
    for _s, _c, effect, show, _w, _src in influences.DEFAULTS:
        assert effect in influences.EFFECTS
        assert all(n.strip() in influences.KNOWN_RESULTS for n in show.split(',') if n.strip())


def test_default_conditions_exist_in_condition_codes():
    from app.services.condition_codes import DEFAULTS as CODES
    assert {c for _s, c, *_ in influences.DEFAULTS} <= set(CODES)
