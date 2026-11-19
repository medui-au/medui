"""Your details card (ADR-125). Invented values only."""
import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from app.services import doctor_profile_service as dps
from app.sql.query_loader import QUERY_REGISTRY

BP = {
    'identity': {'registration_no': 'MED0001234567', 'hpii': '8003610000000000',
                 'provider_no': '1234567A', 'prescriber_no': '7654321'},
    'qualifications': ['MBBS', 'FRACGP'],
    'provider_sites': [{'provider_no': '1234567A', 'site': 'Sampleton'},
                       {'provider_no': '1234567B', 'site': ''}],
    'visits': {'visits': 12345, 'patients': 2345, 'first_visit': datetime.datetime(2007, 3, 5, 9, 30)},
}


@pytest.fixture(autouse=True)
def fresh_cache():
    dps._card_cache.clear()
    yield
    dps._card_cache.clear()


def _lines(bp):
    return {line['key']: line['values'] for line in dps.card_lines(bp)}


def test_every_field_with_a_value_is_shown_in_order():
    lines = dps.card_lines(BP)
    assert [l['key'] for l in lines] == ['qualifications', 'registration', 'hpii', 'provider',
                                         'prescriber', 'first_visit', 'visits', 'patients']
    got = _lines(BP)
    assert got['qualifications'] == ['MBBS', 'FRACGP']
    assert got['provider'] == ['1234567A (Sampleton)', '1234567B']
    assert got['first_visit'] == ['5 Mar 2007']
    assert got['visits'] == ['12,345'] and got['patients'] == ['2,345']


def test_lines_with_no_value_are_left_out():
    bp = {'identity': {'registration_no': '', 'hpii': '', 'provider_no': '', 'prescriber_no': ''},
          'qualifications': [], 'provider_sites': [],
          'visits': {'visits': 0, 'patients': 0, 'first_visit': None}}
    assert dps.card_lines(bp) == []


def test_single_provider_number_when_no_sites():
    bp = dict(BP, provider_sites=[])
    assert _lines(bp)['provider'] == ['1234567A']


def test_user_without_a_bp_link_gets_an_empty_card(monkeypatch):
    monkeypatch.setattr(dps, '_read_bp', lambda uid: pytest.fail('BP read without a BP user'))
    card = dps.get_card(SimpleNamespace(id=1, bpsdb_user_id=None))
    assert card == {'lines': [], 'as_at': None, 'unavailable': False}


def test_uses_the_real_bp_user_and_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(dps, '_read_bp', lambda uid: calls.append(uid) or BP)
    user = SimpleNamespace(id=1, bpsdb_user_id=42)
    first = dps.get_card(user)
    second = dps.get_card(user)
    assert calls == [42] and first is second and first['lines']


def test_bp_failure_says_so_and_is_not_cached(monkeypatch):
    def boom(uid):
        raise OSError('BP down')
    monkeypatch.setattr(dps, '_read_bp', boom)
    with Flask(__name__).app_context():
        card = dps.get_card(SimpleNamespace(id=1, bpsdb_user_id=42))
    assert card['unavailable'] and not dps._card_cache


def test_queries_are_registered_and_read_only():
    root = Path(__file__).resolve().parent.parent / 'app' / 'sql'
    for name in ('doctor_card_identity', 'doctor_card_qualifications',
                 'doctor_card_provider_sites', 'doctor_card_visits'):
        sql = (root / QUERY_REGISTRY[name]).read_text().upper()
        body = '\n'.join(l for l in sql.splitlines() if not l.strip().startswith('--'))
        assert body.strip().startswith('SELECT') and 'PASSWORD' not in body


def test_visits_exclude_non_visit_and_blank():
    sql = (Path(__file__).resolve().parent.parent / 'app' / 'sql' / 'doctor_card_visits.sql').read_text()
    assert 'NOT IN (0, 12)' in sql


# ── ADR-128: the admin lookup on Setup → Users ───────────────────────────────

@pytest.mark.parametrize('user, doctor', [
    (SimpleNamespace(bpsdb_user_id=42, bpsdb_provider_no='1234567A', bpsdb_prescriber_no=None), True),
    (SimpleNamespace(bpsdb_user_id=42, bpsdb_provider_no=None, bpsdb_prescriber_no='7654321'), True),
    (SimpleNamespace(bpsdb_user_id=42, bpsdb_provider_no=None, bpsdb_prescriber_no=None), False),   # nurse, reception
    (SimpleNamespace(bpsdb_user_id=None, bpsdb_provider_no='1234567A', bpsdb_prescriber_no=None), False),  # local account
])
def test_who_counts_as_a_doctor(user, doctor):
    assert dps.is_doctor(user) is doctor


def test_lookup_route_is_admin_only_and_doctors_only():
    src = (Path(__file__).resolve().parent.parent / 'app' / 'blueprints' / 'setup' / 'routes.py').read_text()
    block = src[src.index("@bp.get('/users/<int:user_id>/details-card')"):]
    block = block[:block.index('\n\n\n')]
    assert '@_require_admin' in block and 'not is_doctor(user)' in block and 'abort(404)' in block
