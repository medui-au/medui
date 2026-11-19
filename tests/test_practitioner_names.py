"""Preferred names (ADR-106). Invented names only."""
import pytest

from app.services import practitioner_names as pn


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(pn, 'preferred_by_bp_user', lambda: {7: 'Dr Jo Rivers', 9: 'Sam'})


def test_name_swaps_by_user_id():
    assert pn.name(7, 'Dr Josephine Anne Rivers-Smythe') == 'Dr Jo Rivers'
    assert pn.name('7', 'x') == 'Dr Jo Rivers'
    assert pn.name(8, 'Dr Alex Brook') == 'Dr Alex Brook'
    assert pn.name(None, 'Dr Alex Brook') == 'Dr Alex Brook'


def test_initials_from_preferred_name_keep_bp_marker():
    assert pn.initials(7, 'JR') == 'JR'
    assert pn.initials(7, 'JR(K)') == 'JR(K)'
    assert pn.initials(9, 'SL') == 'S'
    assert pn.initials(8, 'AB') == 'AB'


def test_swap_rows_in_place():
    rows = [{'user_id': 7, 'doctor_name': 'Josephine Rivers-Smythe'},
            {'user_id': 8, 'doctor_name': 'Alex Brook'}]
    pn.swap(rows, 'user_id', 'doctor_name')
    assert [r['doctor_name'] for r in rows] == ['Dr Jo Rivers', 'Alex Brook']


def test_extra_rows_for_redaction_add_not_replace():
    rows = [{'user_id': 7, 'first_name': 'Josephine', 'surname': 'Rivers-Smythe', 'role': 'Doctor'},
            {'user_id': 9, 'first_name': 'Samantha', 'surname': 'Lake'},
            {'user_id': 8, 'first_name': 'Alex', 'surname': 'Brook'}]
    extra = pn.extra_rows(rows)
    assert extra == [{'user_id': 7, 'first_name': 'Jo', 'surname': 'Rivers', 'role': 'Doctor'}]
    assert rows[0]['first_name'] == 'Josephine'          # the BP row is untouched
    assert pn.extra_rows(rows, lower=True)[0]['surname'] == 'rivers'


def test_apply_to_user_falls_back_to_bp_name():
    class U:
        preferred_name = None
        bp_display_name = 'Dr Josephine Rivers-Smythe'
        display_name = 'Dr Jo Rivers'
    u = U()
    pn.apply_to_user(u)
    assert u.display_name == 'Dr Josephine Rivers-Smythe'
    u.preferred_name = 'Dr Jo Rivers'
    pn.apply_to_user(u)
    assert u.display_name == 'Dr Jo Rivers'
