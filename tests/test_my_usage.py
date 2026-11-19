"""My usage (ADR-138): your figures are always yours; the practice's are totals only.

No database. The report's SQL is captured and answered with zeros, as in
test_usage_report_filters.
"""
import re
from datetime import date, datetime

import pytest
from werkzeug.datastructures import MultiDict

from app.services import my_usage_service as mine
from app.services import usage_report_service as reports
from app.services.usage_report_service import Filters, View

from tests.test_usage_report_filters import _select_width

ME = 42


@pytest.fixture
def captured(monkeypatch):
    seen = []

    def fake_rows(sql, params):
        seen.append((sql, dict(params)))
        if 'min(e.occurred_at)' in sql and 'with base' not in sql:
            return [(datetime(2026, 1, 1),)]
        if 'group by' in sql or 'limit' in sql:
            return []
        return [(0,) * _select_width(sql)]

    monkeypatch.setattr(reports, '_rows', fake_rows)
    monkeypatch.setattr(reports, 'person_namer', lambda show: (lambda uid: 'Me'))
    monkeypatch.setattr(reports, 'history_span', lambda: {'live_start': datetime(2026, 1, 1)})
    monkeypatch.setattr(reports, '_local_zone', lambda: reports.ZoneInfo('Australia/Brisbane'))
    return seen


def _f(**kw):
    return Filters(start=date(2026, 1, 1), end=date(2026, 1, 31), **kw)


def _views():
    for tab, measure in (('ai', 'runs'), ('ai', 'scribe'), ('nonai', 'runs')):
        kind = measure if tab == 'ai' else 'nonai'
        for by in mine.OWN_DIMENSIONS[kind]:
            for rows in (False, True):
                yield View(tab=tab, measure=measure, by=by, rows=rows)


@pytest.mark.parametrize('view', list(_views()), ids=lambda v: f'{v.tab}-{v.measure}-{v.by}-{v.rows}')
def test_every_query_is_mine_or_a_bare_practice_total(captured, view):
    # Even when someone else's id, a role and the access-log history are asked for.
    mine.build(ME, view, _f(user_id=7, role='Nurse', sources={'unattributed'}, pipeline='Invented'))
    queries = [(sql, p) for sql, p in captured if 'with base' in sql]
    assert any('e.user_id = :user_id' in sql for sql, _ in queries)
    assert any('e.user_id = :user_id' not in sql for sql, _ in queries)   # the practice totals
    for sql, p in queries:
        if 'e.user_id = :user_id' in sql:
            assert p['user_id'] == ME                       # never anyone else
            assert ':role' not in sql
        else:
            # A practice figure: one row of totals over the period, nothing more.
            final = re.split(r'\)\s+select\s', sql.lower())[-1]
            assert 'group by' not in final and 'limit' not in final, sql
            assert 'user_id,' not in final and 'occurred_at' not in final
            assert not any(k.startswith('f_') for k in p), 'practice totals take no filters'
        assert "e.quality = 'unattributed'" not in sql


def test_practice_figures_sit_beside_mine(captured):
    out = mine.build(ME, View(tab='nonai'), _f())
    assert [c['label'] for c in out['cards']] == ['Tasks', 'Charts opened', 'Messages sent',
                                                  'Exports to BP', 'Sign-ins']
    assert all('practice' in c for c in out['cards'])


def test_no_breakdown_by_person_or_role(captured):
    for kind in ('runs', 'scribe', 'nonai'):
        assert not {'user_id', 'role'} & set(mine.OWN_DIMENSIONS[kind])
    out = mine.build(ME, View(tab='ai', by='user_id'), _f())
    assert out['by'] == 'feature'
    assert all(c['go']['by'] not in ('user_id', 'role') for c in out['cards'])


def test_drill_never_leads_to_people():
    view = mine.own_view(View(tab='ai', by='pipeline'))
    for _ in range(5):
        changes = mine.drill(view, mine.lock(_f(), ME), 'x')
        assert changes.get('by') not in ('user_id', 'role')


def test_needs_a_person():
    with pytest.raises(ValueError):
        mine.build(None, View(), _f())


def test_route_ignores_a_person_in_the_address(monkeypatch):
    """The page is any signed-in user's own: user_id/role in the URL are dropped."""
    from app.blueprints.doctor.routes import _usage_filters
    f, _ = _usage_filters(MultiDict({'user_id': '7', 'role': 'Nurse'}))
    locked = mine.lock(f, ME)
    assert locked.user_id == ME and locked.role == '' and locked.sources == mine.SOURCES
