"""BMI is not worked out from a childhood height for an adult; weight and height are still shown.

Invented values only.
"""
from datetime import date

from app.utils.bmi import bmi_height

ADULT = {'WEIGHTVALUE': 92, 'WEIGHT_DATE': '2026-08-01', 'HEIGHTVALUE': '1.75',
         'HEIGHT_DATE': '2025-02-01', 'HEIGHT_AGE': 66, 'AGE': 67}


def test_an_adult_height_is_used_whatever_the_weight_date():
    assert bmi_height(ADULT) == 1.75


def test_a_childhood_height_is_not_used_for_an_adult():
    assert bmi_height({**ADULT, 'HEIGHT_AGE': 14, 'AGE': 30}) is None
    assert bmi_height({**ADULT, 'HEIGHT_AGE': 17, 'AGE': 18}) is None


def test_a_child_uses_their_latest_height():
    assert bmi_height({**ADULT, 'HEIGHT_AGE': 12, 'AGE': 13}) == 1.75


def test_no_date_of_birth_is_as_before_and_no_height_is_none():
    assert bmi_height({**ADULT, 'HEIGHT_AGE': None, 'AGE': None}) == 1.75
    assert bmi_height({**ADULT, 'HEIGHTVALUE': None}) is None
    assert bmi_height({**ADULT, 'HEIGHTVALUE': '0'}) is None


def test_care_plan_tokens_keep_weight_and_height_but_drop_bmi():
    from app.services import careplan_service as svc
    f = svc.facts_from({**ADULT, 'HEIGHT_AGE': 15, 'AGE': 40}, [], None, date(2026, 10, 31))
    assert f['weight'][0] == '92' and f['height'][0] == '1.75'
    assert 'bmi' not in f and 'weight_excess' not in f
    assert svc.facts_from(ADULT, [], None, date(2026, 10, 31))['bmi'][0] == '30.0'


def test_weight_caption_says_why_there_is_no_bmi():
    from app.services.chart_service import ChartService
    svc = ChartService.__new__(ChartService)
    info = svc._get_weight_info({**ADULT, 'HEIGHT_AGE': 15, 'AGE': 40})
    assert 'BMI not worked out: no height measured from age 18' in info['subtitle']
    assert '92 kg' in info['subtitle'] and 'excess' not in info
    assert 'BMI 30' in svc._get_weight_info(ADULT)['subtitle']
