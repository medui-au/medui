"""Sent tab check and users' privacy reports (ADR-115). Invented text only, no database."""
from types import SimpleNamespace

import pytest

from app.services.pipeline.engine import _sent_check
from app.services.privacy_reports_service import MAX_SPAN, may_report, span_problem

PROMPT = 'Seen with [Redacted Patient: PT-0a1b2c3d] at Platypus Hearing Clinic today.'


def test_sent_check_keeps_positions_and_types_only():
    pre = {'top_tier': 2, 'detector_version': 'pattern-v22', 'lists': 'abcd1234', 'scanned_ms': 5,
           'patient_identifiers': 'loaded',
           'hits': [{'tier': 2, 'type': 'titled_name', 'kind': 'x', 'coverage': 'y', 'start': 1, 'end': 4}]}
    out = _sent_check(pre)
    assert out['hits'] == [{'tier': 2, 'type': 'titled_name', 'start': 1, 'end': 4}]
    assert 'lists' not in out and 'scanned_ms' not in out


@pytest.mark.parametrize('pre', [None, {}, {'error': 'x'}, {'top_tier': None}])
def test_sent_check_absent_when_not_checked(pre):
    assert _sent_check(pre) is None


def test_a_business_name_can_be_reported():
    start = PROMPT.index('Platypus')
    assert span_problem(PROMPT, start, start + len('Platypus Hearing Clinic')) is None


@pytest.mark.parametrize('start,end', [(None, 3), ('1', 3), (5, 5), (10, 2), (-1, 3), (0, len(PROMPT) + 1)])
def test_bad_spans_are_refused(start, end):
    assert span_problem(PROMPT, start, end) == 'Select the text in the prompt first.'


def test_whitespace_only_is_refused():
    assert span_problem('a    b', 1, 4) == 'Select the text in the prompt first.'


def test_a_token_is_already_redacted():
    start = PROMPT.index('['); end = PROMPT.index(']') + 1
    assert span_problem(PROMPT, start, end) == 'That is already redacted.'


def test_a_token_with_text_around_it_can_be_reported():
    start = PROMPT.index('with'); end = PROMPT.index(']') + 1
    assert span_problem(PROMPT, start, end) is None


def test_a_paragraph_is_refused():
    text = 'x' * (MAX_SPAN + 10)
    assert 'up to' in span_problem(text, 0, MAX_SPAN + 1)


def test_who_may_report():
    run = SimpleNamespace(initiated_by_id=1)
    assert may_report(run, SimpleNamespace(id=1, is_admin=False))
    assert not may_report(run, SimpleNamespace(id=2, is_admin=False))
    assert may_report(run, SimpleNamespace(id=2, is_admin=True))
    assert not may_report(None, SimpleNamespace(id=1, is_admin=True))
