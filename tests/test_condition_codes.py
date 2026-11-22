"""Condition codes (ADR-108). Invented items only."""
from app.services.condition_codes import DEFAULTS, FLAGS, _defaults, profile_flags


def item(code, year=2020, status=1, text='', rid=1):
    return {'ITEMCODE': code, 'ITEMTEXT': text, 'YEAR': year, 'RECORDID': rid, 'STATUSCODE': status}


T = _defaults()


def test_every_flag_has_a_default_list():
    assert set(FLAGS.values()) <= set(DEFAULTS)


def test_active_items_only():
    assert profile_flags([item(778)], T)['isDiabetes'] == 1
    assert profile_flags([item(778, status=2)], T)['isDiabetes'] == 0


def test_a_coded_reason_for_visit_counts_as_active():
    # STATUSCODE 0: copied from "Reason for visit" to Past History (ADR-145).
    assert profile_flags([item(778, status=0)], T)['isDiabetes'] == 1


def test_borderline_and_gestational_are_not_diabetes():
    f = profile_flags([item(779), item(780)], T)
    assert f['isDiabetes'] == 0


def test_type_and_year():
    f = profile_flags([item(778, year=2019)], T)
    assert (f['isNIDDM'], f['isIDDM'], f['DiabetesRecordedYear']) == (1, 0, 2019)


def test_ckd_stage_and_year_prefer_the_staged_item():
    f = profile_flags([item(662, year=2024, rid=5), item(8120, year=2021, text='CHRONIC KIDNEY DISEASE, STAGE 3B', rid=2)], T)
    assert f['isCKDRecorded'] == 1
    assert f['CKDRecordedStage'].endswith('3B')
    assert f['CKDRecordedYear'] == 2021


def test_pregnancy_counts_in_any_status():
    assert profile_flags([item(2971, year=2025, status=2)], T)['PregnancyYears'] == '2025'


def test_the_table_decides():
    table = dict(T, diabetes=frozenset({779}))
    assert profile_flags([item(779)], table)['isDiabetes'] == 1
    assert profile_flags([item(778)], table)['isDiabetes'] == 0


def test_no_history():
    f = profile_flags([], T)
    assert f['isDiabetes'] == 0 and f['CKDRecordedStage'] is None and f['PregnancyYears'] is None


def test_summary_never_merges_recorded_and_criterion():
    from app.services.condition_codes import summary
    s = summary({'isDiabetes': 1, 'DiabetesRecordedYear': 2019,
                 'hba1c_badge': {'state': 'met'}, 'egfr_badge': {'state': 'met', 'latest': {'value': '54'}}})
    assert s['diabetes']['status'] == 'recorded'
    assert s['ckd']['status'] == 'criterion_met'
    assert summary({})['diabetes']['status'] == 'none'
    s2 = summary({'hba1c_badge': {'state': 'met', 'results': [], 'influences': [{'condition': 'iron_deficiency'}]}})
    assert s2['diabetes']['status'] == 'criterion_met' and s2['diabetes']['influences']


def test_present_reports_non_badge_conditions_with_year():
    f = profile_flags([item(741, year=2018), item(3958, year=0)], T)
    assert f['present'] == {'b12_folate_deficiency': 2018, 'asplenia': 0}
