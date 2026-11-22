"""Disease Profile results badges as rules each user chooses to display (ADR-166).

HbA1c: the highest of the last 3 results is 6.5% (48 mmol/mol) or more, no diabetes coded.
eGFR: the last result is below 59, no CKD coded. Invented values only.
"""
import re
from datetime import date

import pytest
from jinja2 import Environment, FileSystemLoader

from app.services import egfr_criterion, hba1c_criterion, user_settings_service
from app.services.egfr_criterion import evaluate_last as egfr_last
from app.services.hba1c_criterion import evaluate_last as a1c_last

MMOL, PCT = '59261-8', '4548-4'


def a1c(d, value, loinc=PCT):
    return {'ResultDate': d, 'Loinc': loinc, 'ResultValue': value}


def gfr(d, value):
    return {'ResultDate': d, 'ResultValue': value}


# ── HbA1c: highest of the last 3 ─────────────────────────────────────────────

def test_highest_of_last_three_triggers_and_all_three_are_shown():
    r = a1c_last([a1c(date(2026, 1, 5), '6.1'), a1c(date(2026, 6, 5), '6.8'),
                  a1c(date(2026, 10, 5), '6.4'), a1c(date(2020, 1, 1), '5.2')])
    assert r['state'] == 'met'
    assert [x['value'] for x in r['results']] == ['6.1', '6.8', '6.4']
    assert r['highest']['value'] == '6.8'


def test_exactly_threshold_counts_in_both_units():
    assert a1c_last([a1c(date(2026, 1, 5), '6.5')])['state'] == 'met'
    assert a1c_last([a1c(date(2026, 1, 5), '48', MMOL)])['state'] == 'met'
    assert a1c_last([a1c(date(2026, 1, 5), '6.4'), a1c(date(2026, 2, 5), '47', MMOL)])['state'] == 'not_met'


def test_a_high_result_older_than_the_last_three_does_not_count():
    r = a1c_last([a1c(date(2024, 1, 5), '7.2'), a1c(date(2025, 1, 5), '6.0'),
                  a1c(date(2025, 6, 5), '6.1'), a1c(date(2026, 1, 5), '6.2')])
    assert r['state'] == 'not_met'
    assert len(r['results']) == 3


def test_unreadable_results_are_skipped_so_three_readable_are_used():
    r = a1c_last([a1c(date(2025, 1, 5), '6.9'), a1c(date(2025, 6, 5), '6.0'),
                  a1c(date(2026, 1, 5), '6.1'), a1c(date(2026, 3, 5), 'see comment')])
    assert r['state'] == 'met' and r['ignored'] == 1
    assert [x['value'] for x in r['results']] == ['6.9', '6.0', '6.1']


def test_same_sample_in_two_units_counts_once_mmol_preferred():
    r = a1c_last([a1c(date(2026, 1, 5), '6.6'), a1c(date(2026, 1, 5), '49', MMOL)])
    assert len(r['results']) == 1 and r['results'][0]['unit'] == 'mmol/mol'


def test_fewer_than_three_and_none():
    assert len(a1c_last([a1c(date(2026, 1, 5), '6.7')])['results']) == 1
    assert a1c_last([])['state'] == 'no_results'


# ── eGFR: last result below 59 ───────────────────────────────────────────────

def test_last_egfr_below_59():
    assert egfr_last([gfr(date(2025, 1, 1), '40'), gfr(date(2026, 1, 1), '58')])['state'] == 'met'
    assert egfr_last([gfr(date(2025, 1, 1), '40'), gfr(date(2026, 1, 1), '62')])['state'] == 'not_met'


def test_exactly_59_does_not_trigger():
    assert egfr_last([gfr(date(2026, 1, 1), '59')])['state'] == 'not_met'
    assert egfr_last([gfr(date(2026, 1, 1), '58')])['state'] == 'met'


def test_lab_forms_on_the_last_day():
    assert egfr_last([gfr(date(2026, 1, 1), '>90')])['state'] == 'not_met'
    assert egfr_last([gfr(date(2026, 1, 1), '<15')])['state'] == 'met'
    # Can't be placed either side of 59: no badge.
    assert egfr_last([gfr(date(2025, 1, 1), '30'), gfr(date(2026, 1, 1), '>45')])['state'] == 'not_met'
    assert egfr_last([])['state'] == 'no_results'


def test_same_day_takes_the_lowest_readable():
    r = egfr_last([gfr(date(2026, 1, 1), '61'), gfr(date(2026, 1, 1), '57')])
    assert r['state'] == 'met' and r['latest']['value'] == '57'


# ── The rule text matches the code ───────────────────────────────────────────

def test_rule_text_states_the_constants():
    assert hba1c_criterion.BADGE_LAST_N == 3
    assert f'last {hba1c_criterion.BADGE_LAST_N} HbA1c' in hba1c_criterion.BADGE_RULE
    assert f'{hba1c_criterion.THRESHOLD_PCT}% ({hba1c_criterion.THRESHOLD_MMOL} mmol/mol) or more' \
        in hba1c_criterion.BADGE_RULE
    assert '>' not in hba1c_criterion.BADGE_RULE
    assert egfr_criterion.BADGE_THRESHOLD == 59
    assert f'last eGFR is below {egfr_criterion.BADGE_THRESHOLD}' in egfr_criterion.BADGE_RULE


# ── Per user only ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('key', [hba1c_criterion.BADGE_PREF_KEY, egfr_criterion.BADGE_PREF_KEY])
def test_badge_settings_are_personal_off_and_never_lockable(key):
    pref = user_settings_service.REGISTRY[key]
    assert pref.kind == 'bool' and pref.default is False
    assert pref.lockable is False and pref.on_page is True
    assert pref.section in user_settings_service.SECTION_ORDER


def test_badge_settings_are_not_in_user_defaults():
    keys = {hba1c_criterion.BADGE_PREF_KEY, egfr_criterion.BADGE_PREF_KEY}
    shown = {k for k, p in user_settings_service.REGISTRY.items() if p.lockable and p.on_page}
    assert not keys & shown


def test_labels_are_the_rule_text():
    assert user_settings_service.REGISTRY[hba1c_criterion.BADGE_PREF_KEY].label == hba1c_criterion.BADGE_RULE
    assert user_settings_service.REGISTRY[egfr_criterion.BADGE_PREF_KEY].label == egfr_criterion.BADGE_RULE


def test_no_practice_wide_badge_switch_left():
    root = __import__('pathlib').Path(__file__).resolve().parent.parent / 'app'
    for f in list(root.rglob('*.py')) + list(root.rglob('*.html')):
        assert 'criterion_badge' not in f.read_text(errors='ignore'), f


# ── The profile only carries a badge the viewing user chose ──────────────────

class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query, params):
        return self.rows.get(query, [])


@pytest.fixture
def repo_factory(monkeypatch):
    from app.repositories import patient_repository as pr
    from app.services import condition_codes
    monkeypatch.setattr(pr, 'load_query', lambda name: name)
    monkeypatch.setattr(condition_codes, 'profile_flags',
                        lambda items: {'isDiabetes': 0, 'isCKDRecorded': 0, 'present': {}})
    monkeypatch.setattr(condition_codes, 'summary', lambda profile: {})

    def make():
        repo = pr.PatientRepository(FakeSession({
            'patient_hba1c_series': [a1c(date(2026, 1, 5), '6.1'), a1c(date(2026, 6, 5), '6.8'),
                                     a1c(date(2026, 10, 5), '6.4')],
            'patient_egfr_series': [gfr(date(2026, 10, 5), '54')],
        }))
        repo.get_demographics = lambda pid: {'AGE': 50}
        repo._hba1c_influences = lambda *a, **k: []
        return repo
    return make


def test_unticked_user_sees_no_badge(repo_factory):
    p = repo_factory().get_disease_profile(1)
    assert 'hba1c_badge' not in p and 'egfr_badge' not in p


def test_ticked_user_sees_both(repo_factory):
    p = repo_factory().get_disease_profile(1, show_hba1c_rule=True, show_egfr_rule=True)
    assert p['hba1c_badge']['state'] == 'met' and p['hba1c_badge']['rule'] == hba1c_criterion.BADGE_RULE
    assert p['egfr_badge']['state'] == 'met' and p['egfr_badge']['rule'] == egfr_criterion.BADGE_RULE


def test_each_switch_alone(repo_factory):
    p = repo_factory().get_disease_profile(1, show_hba1c_rule=True)
    assert 'hba1c_badge' in p and 'egfr_badge' not in p
    p = repo_factory().get_disease_profile(1, show_egfr_rule=True)
    assert 'egfr_badge' in p and 'hba1c_badge' not in p


# ── The badges render the values; the tooltip the rule and source ────────────

def render(profile):
    root = __import__('pathlib').Path(__file__).resolve().parent.parent / 'app' / 'templates'
    env = Environment(loader=FileSystemLoader(str(root)))
    env.filters['clinical_date'] = lambda d: d.strftime('%d/%m/%Y') if d else ''
    t = env.from_string('{% from "clinical/macros/clinical_components.html" import render_disease_badges %}'
                        '{{ render_disease_badges(p) }}')
    return t.render(p=profile)


def test_badges_render_values_dates_rule_and_source():
    profile = {
        'hba1c_badge': dict(a1c_last([a1c(date(2026, 1, 5), '6.1'), a1c(date(2026, 6, 5), '49', MMOL),
                                      a1c(date(2026, 10, 5), '6.4')]),
                            rule=hba1c_criterion.BADGE_RULE, source=hba1c_criterion.BADGE_SOURCE),
        'egfr_badge': dict(egfr_last([gfr(date(2026, 10, 5), '54')]), rule=egfr_criterion.BADGE_RULE),
    }
    html = render(profile)
    flat = re.sub(r'\s+', ' ', html)
    # ADR-170: the label is in %; a mmol/mol result is converted (49 -> 6.6%) and the tooltip
    # keeps the laboratory's value.
    assert 'HbA1c 6.1% (Jan 2026) · 6.6% (Jun 2026) · 6.4% (Oct 2026)' in flat
    assert '49 mmol/mol (Jun 2026)' not in flat
    assert 'HbA1c 6.6% (laboratory: 49 mmol/mol)' in flat
    assert 'eGFR 54 (Oct 2026)' in html
    assert hba1c_criterion.BADGE_RULE in html and egfr_criterion.BADGE_RULE in html
    assert 'RACGP' in html and 'KDIGO' in html
    assert 'No diabetes is coded' in html and 'No CKD is coded' in html


def test_not_met_renders_nothing():
    profile = {'hba1c_badge': dict(a1c_last([a1c(date(2026, 1, 5), '5.9')]), rule='r', source='s'),
               'egfr_badge': dict(egfr_last([gfr(date(2026, 1, 5), '75')]), rule='r')}
    html = render(profile)
    assert 'HbA1c 5.9' not in html and 'eGFR 75' not in html
