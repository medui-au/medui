"""Privacy Review list (ADR-120): which runs are listed, filters, outcome. Invented data only, no database."""
from datetime import date
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from app.services.privacy_review_service import (
    _check, _outcome, _row_matches, parse_filters, query_args, type_label)

HIT0 = {'tier': 0, 'type': 'patient_name_variant', 'start': 3, 'end': 7}
HIT2 = {'tier': 2, 'type': 'titled_name', 'start': 10, 'end': 18}


def _filters(**kw):
    return {**parse_filters(MultiDict()), **kw}


def test_own_check_is_preferred_to_the_old_card():
    out = {'precheck': {'top_tier': 0, 'hits': [HIT0]}, 'privacy_check': {'top_tier': 2, 'hits': [HIT2]}}
    assert _check(out)['top_tier'] == 0


def test_old_card_is_used_when_there_is_no_own_check():
    assert _check({'privacy_check': {'top_tier': 2, 'hits': [HIT2]}})['hits'] == [HIT2]


@pytest.mark.parametrize('out', [
    {}, {'privacy_check': {'skipped': 'local model'}}, {'privacy_check': {'screening': {'matches': []}}},
    {'privacy_check': {'audited_run_id': 1, 'findings': 2, 'detector_version': 'pattern-v9'}},
    {'precheck': {'error': 'Timeout'}},
])
def test_nothing_to_review_without_positioned_hits(out):
    assert _check(out) == {}


def test_default_list_is_tier_0_1_or_reported():
    f = _filters()
    assert f['tier'] == '01' and f['reviewed'] == 'any' and f['order'] == 'new'
    assert _row_matches(0, None, None, f)
    assert _row_matches(1, None, None, f)
    assert not _row_matches(2, None, None, f)
    assert _row_matches(2, {'open': 1, 'total': 1}, None, f)        # an open report
    assert not _row_matches(2, {'open': 0, 'total': 1}, None, f)    # a handled one


def test_tier_2_and_anything():
    assert _row_matches(2, None, None, _filters(tier='2'))
    assert not _row_matches(0, None, None, _filters(tier='2'))
    assert _row_matches(None, {'open': 0, 'total': 1}, None, _filters(tier='any'))
    assert not _row_matches(None, None, None, _filters(tier='any'))


def test_reviewed_filter():
    done = SimpleNamespace(disposition='false_positive')
    assert _row_matches(0, None, done, _filters(reviewed='yes'))
    assert not _row_matches(0, None, done, _filters(reviewed='no'))
    assert _row_matches(0, None, None, _filters(reviewed='no'))


def test_filters_survive_the_round_trip():
    args = MultiDict({'tier': '2', 'reviewed': 'no', 'order': 'old', 'workflow': '8',
                      'from': '2026-10-01', 'to': '2026-10-30'})
    f = parse_filters(args)
    assert f['pipeline_id'] == 8 and f['date_from'] == date(2026, 10, 1)
    assert parse_filters(MultiDict(query_args(f))) == f


@pytest.mark.parametrize('args', [{'tier': '9'}, {'reviewed': 'maybe'}, {'workflow': 'x'}, {'from': 'not a date'}])
def test_bad_filters_fall_back_to_defaults(args):
    f = parse_filters(MultiDict(args))
    assert f['tier'] in ('01', '2', 'any') and f['reviewed'] in ('any', 'no', 'yes')
    assert f['pipeline_id'] is None and f['date_from'] is None


def _run(status):
    return SimpleNamespace(status=SimpleNamespace(value=status))


def test_outcome_words():
    assert _outcome(_run('completed'), {}) == 'Sent'
    assert _outcome(_run('cancelled'), {'review': {'paused': True, 'outcome': 'timed out'}}) == 'Stopped at review'
    assert _outcome(_run('cancelled'), {}) == 'Cancelled'
    assert _outcome(_run('failed'), {}) == 'Failed'


def test_type_labels():
    assert type_label('patient_name_variant') == "short form of the patient's name"
    assert type_label('some_new_type') == 'some new type'
    assert type_label(None) == 'unknown'
