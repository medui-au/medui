"""NIP eligibility wording (ADR-110): neutral, schedule-and-record wording. Invented doses only."""
import re
from datetime import date

from app.services import vaccine_eligibility_service as v

TODAY = date(2026, 10, 24)
ADVICE = re.compile(r"\b(you|your|overdue|worth|consider|book|promptly|benefit|should)\b", re.I)


def dose(d, brand='Shingrix'):
    return {'date': d, 'brand_name': brand, 'generic_name': brand}


def notes():
    rows = [
        v._eval_influenza(70, False, TODAY, []), v._eval_influenza(70, False, TODAY, [dose(date(2026, 4, 1), 'Fluad')]),
        v._eval_influenza(30, False, TODAY, []), v._eval_influenza(30, True, TODAY, []),
        v._eval_covid(80, False, set(), {}, set(), TODAY, []),
        v._eval_covid(80, False, set(), {}, set(), TODAY, [dose(date(2025, 1, 1), 'Comirnaty')]),
        v._eval_covid(40, False, set(), {}, set(), TODAY, [dose(date(2026, 6, 1), 'Comirnaty')]),
        v._eval_covid(40, False, {5}, {5: 'RISK CONDITION'}, {5}, TODAY, []),
        v._eval_covid(70, False, set(), {}, set(), TODAY, []), v._eval_covid(55, True, set(), {}, set(), TODAY, []),
        v._eval_covid(10, False, set(), {}, set(), TODAY, []),
        v._eval_pneumococcal(70, False, set(), {}, set(), TODAY, []),
        v._eval_pneumococcal(70, False, set(), {}, set(), TODAY, [dose(date(2026, 3, 1), 'Prevenar 13')]),
        v._eval_pneumococcal(70, False, set(), {}, set(), TODAY, [dose(date(2020, 3, 1), 'Prevenar 13')]),
        v._eval_pneumococcal(40, False, {5}, {5: 'RISK CONDITION'}, {5}, TODAY, []),
        v._eval_pneumococcal(40, False, set(), {}, set(), TODAY, []),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, []),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2026, 10, 1))]),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2026, 7, 1))]),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2025, 1, 1))]),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2026, 1, 1)), dose(date(2025, 9, 1))]),
        v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2015, 1, 1), 'Zostavax')]),
        v._eval_zoster(40, False, {5}, {5: 'RISK CONDITION'}, {5}, TODAY, []),
        v._eval_zoster(40, False, set(), {}, set(), TODAY, []),
    ]
    for age in (80, 65, 55, 30):
        rows.append(v._eval_rsv(age, False, {5}, {5}, TODAY, []))
    rows.append(v._eval_rsv(62, True, set(), set(), TODAY, []))
    rows.append(v._eval_rsv(80, False, set(), set(), TODAY, [dose(date(2025, 6, 1), 'Arexvy')]))
    return rows


def test_no_patient_addressed_or_advisory_wording():
    for r in notes():
        for field in ('note', 'eligibility_basis', 'product'):
            text = r.get(field) or ''
            assert not ADVICE.search(text), (r['vaccine'], text)


def test_rules_unchanged():
    assert v._eval_influenza(70, False, TODAY, [])['dose_due_now'] is True
    assert v._eval_zoster(70, False, set(), {}, set(), TODAY, [dose(date(2025, 1, 1))])['dose_due_now'] is True
    assert v._eval_rsv(65, False, set(), set(), TODAY, [])['eligible_for_funded_dose'] is False


def test_covid_nip_groups():
    c = lambda age, atsi=False, risk=False: v._eval_covid(age, atsi, {5} if risk else set(), {5: 'X'}, {5}, TODAY, [])
    assert c(80)['eligible_for_funded_dose'] and 'two doses a year' in c(80)['note']
    assert c(70)['eligible_for_funded_dose'] and 'one dose a year' in c(70)['note']
    assert c(55, atsi=True)['eligible_for_funded_dose']
    assert not c(55)['eligible_for_funded_dose']                 # 50-64 without ATSI or risk: not funded
    assert c(40, risk=True)['eligible_for_funded_dose'] and c(40, risk=True)['confirm_with_gp']
    assert not c(16, risk=True)['eligible_for_funded_dose']      # under 18
    # ADR-186: a second dose in the year, and the unfunded 18–64 group.
    for row in (c(70), c(55, atsi=True)):
        assert 'second dose in the year with a medical risk condition' in row['note']
    assert 'The schedule allows a second dose in the year.' in c(40, risk=True)['note']
    assert 'second dose' not in c(80)['note']
    plain = c(40)
    assert not plain['eligible_for_funded_dose'] and plain['eligibility_basis'] == 'Age 18–64 without severe immunocompromise'
    assert 'Not funded under the NIP' in plain['note'] and 'a dose each year as an option' in plain['note']
    assert 'Handbook' in c(16)['note']
    six_months_ago = [dose(date(2026, 4, 1), 'Comirnaty')]
    assert v._eval_covid(80, False, set(), {}, set(), TODAY, six_months_ago)['dose_due_now'] is True
    assert v._eval_covid(70, False, set(), {}, set(), TODAY, six_months_ago)['dose_due_now'] is False
