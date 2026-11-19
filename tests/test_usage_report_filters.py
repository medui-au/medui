"""Application Usage: every figure counts from the tab's one filtered set (ADR-136, ADR-137).

No database. The report's SQL is captured and answered with zeros. Every query a
view runs must start from the same ``base``/``f`` set, with each filter that is set.
"""
import re
from datetime import date, datetime

import pytest
from werkzeug.datastructures import MultiDict

from app.services import usage_report_service as reports
from app.services.usage_report_service import Filters, View


def _select_width(sql: str) -> int:
    """Columns in the final select list (commas at bracket depth 0)."""
    low = sql.lower()
    final = re.split(r'\)\s+select\s', low)          # after the CTE: the final select
    body = final[-1] if len(final) > 1 else low.split('select', 1)[1]
    depth, width, i = 0, 1, 0
    while i < len(body):
        ch = body[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and body.startswith('from', i) and body[i - 1].isspace():
            return width
        elif depth == 0 and ch == ',':
            width += 1
        i += 1
    return width


@pytest.fixture
def captured(monkeypatch):
    seen = []

    def fake_rows(sql, params):
        seen.append((sql, dict(params)))
        if 'min(e.occurred_at)' in sql and 'with base' not in sql:
            return [(datetime(2026, 1, 1),)]
        if 'group by' in sql or 'limit' in sql:     # breakdowns, series, records: none
            return []
        return [(0,) * _select_width(sql)]

    monkeypatch.setattr(reports, '_rows', fake_rows)
    monkeypatch.setattr(reports, 'person_namer', lambda show: (lambda uid: 'Doctor 1'))
    monkeypatch.setattr(reports, 'history_span', lambda: {'live_start': datetime(2026, 1, 1)})
    monkeypatch.setattr(reports, '_local_zone', lambda: reports.ZoneInfo('Australia/Brisbane'))
    return seen


def _f(**kw):
    return Filters(start=date(2026, 1, 1), end=date(2026, 1, 31), **kw)


def _view_queries(seen):
    return [(sql, p) for sql, p in seen if 'with base' in sql]


AI_SET = {'feature': 'ai_panel', 'provider': 'Invented@local', 'model': 'invented-model',
          'pipeline': 'Invented Pipeline', 'locality': 'local', 'result': 'ok', 'privacy': 'clear'}
NONAI_SET = {'area': 'clinical', 'task': 'chart.open', 'outcome': 'ok'}


@pytest.mark.parametrize('measure', ['runs', 'scribe'])
@pytest.mark.parametrize('rows', [False, True])
@pytest.mark.parametrize('name,value', list(AI_SET.items()))
def test_every_ai_query_carries_each_ai_filter(captured, measure, rows, name, value):
    reports.build(View(tab='ai', measure=measure, rows=rows), _f(**{name: value}))
    queries = _view_queries(captured)
    assert len(queries) >= 4                      # figures, scribe figure, chart, table
    for sql, params in queries:
        assert f'{name} = :f_{name}' in sql, sql
        assert params[f'f_{name}'] == value


@pytest.mark.parametrize('rows', [False, True])
@pytest.mark.parametrize('name,value', list(NONAI_SET.items()))
def test_every_nonai_query_carries_each_nonai_filter(captured, rows, name, value):
    reports.build(View(tab='nonai', rows=rows), _f(**{name: value}))
    queries = _view_queries(captured)
    assert len(queries) >= 3
    for sql, params in queries:
        assert f'{name} = :f_{name}' in sql and params[f'f_{name}'] == value


@pytest.mark.parametrize('tab', ['ai', 'nonai'])
def test_person_and_role_reach_every_query(captured, tab):
    reports.build(View(tab=tab), _f(user_id=7, role='Doctor'))
    for sql, params in _view_queries(captured):
        assert 'e.user_id = :user_id' in sql and params['user_id'] == 7
        assert ':role' in sql and params['role'] == 'Doctor'


def test_the_other_tabs_filters_are_ignored(captured):
    reports.build(View(tab='nonai'), _f(provider='Invented@local'))
    assert all(':f_provider' not in sql for sql, _ in captured)


def test_no_filter_no_clause(captured):
    reports.build(View(tab='ai'), _f())
    assert all(' f as (select * from base where true)' in sql for sql, _ in _view_queries(captured))


@pytest.mark.parametrize('by', list(reports.DIMENSIONS['runs']))
def test_each_runs_breakdown_groups_on_its_own_column(captured, by):
    out = reports.build(View(tab='ai', by=by), _f())
    assert out['by'] == by
    assert any(f'select {by}, count(*)' in sql for sql, _ in captured)


def test_bad_view_values_fall_back():
    v = View(tab='nope', measure='nope', by='nope', page=-3).normalise()
    assert (v.tab, v.measure, v.by, v.page) == ('ai', 'runs', 'feature', 1)
    assert View(tab='nonai', by='feature').normalise().by == 'area'


def test_drill_filters_the_row_then_moves_on():
    changes = reports.drill(View(tab='ai', by='feature').normalise(), _f(), 'ai_panel')
    assert changes['feature'] == 'ai_panel' and changes['by'] == 'pipeline'
    # pipeline already filtered: skip it
    changes = reports.drill(View(tab='ai', by='feature').normalise(), _f(pipeline='Invented'), 'ai_panel')
    assert changes['by'] == 'model'


def test_drill_ends_in_the_records():
    v = View(tab='nonai', by='task').normalise()
    assert reports.drill(v, _f(user_id=3), 'chart.open') == {'task': 'chart.open', 'page': None,
                                                              'view': 'rows'}


def test_cards_link_to_their_breakdown(captured):
    out = reports.build(View(tab='ai'), _f())
    goes = {c['label']: c['go'] for c in out['cards']}
    assert goes['Failure rate'] == {'measure': 'runs', 'by': 'result'}
    assert goes['Scribe sessions']['measure'] == 'scribe'
    out = reports.build(View(tab='nonai'), _f())
    assert [c['label'] for c in out['cards']] == ['Tasks', 'People active', 'Charts opened',
                                                  'Messages sent', 'Exports to BP', 'Sign-ins']


def test_scribe_kind_rows_are_not_drillable(monkeypatch, captured):
    monkeypatch.setattr(reports, '_rows', lambda sql, p: (
        [('scribe.session', 3, 10, 1, 0)] if 'select task, count(*)' in sql else
        [(0,) * _select_width(sql)] if 'group by' not in sql else []))
    out = reports.build(View(tab='ai', measure='scribe', by='task'), _f())
    assert out['table']['keys'] == [None]


def test_route_keeps_only_the_open_tabs_filters():
    from app.blueprints.doctor.routes import _usage_filters
    f, _ = _usage_filters(MultiDict({'tab': 'nonai', 'provider': 'Invented@local', 'area': 'clinical'}))
    assert f.provider == '' and f.area == 'clinical'
    f, _ = _usage_filters(MultiDict({'provider': 'Invented@local', 'area': 'clinical'}))
    assert f.provider == 'Invented@local' and f.area == ''


# ── Notes: dates come from the record, history notes only when history was imported ──

def _notes_for(monkeypatch, span, view):
    monkeypatch.setattr(reports, 'history_span', lambda: span)
    return reports.build(view, _f())['notes']


@pytest.mark.parametrize('view', [View(tab='ai', measure='runs'), View(tab='ai', measure='scribe'),
                                  View(tab='nonai')])
def test_a_new_installation_has_no_history_notes(monkeypatch, captured, view):
    notes = ' '.join(_notes_for(monkeypatch, {'live_start': datetime(2026, 3, 2)}, view))
    for phrase in ('recorded from', 'web server log', '2026'):
        assert phrase not in notes


def test_imported_history_dates_come_from_the_record(monkeypatch, captured):
    span = {'live_start': datetime(2026, 3, 2), 'imported_until': datetime(2026, 3, 1),
            'unattributed': (datetime(2026, 1, 5), datetime(2026, 2, 20))}
    runs = ' '.join(_notes_for(monkeypatch, span, View(tab='ai', measure='runs')))
    scribe = ' '.join(_notes_for(monkeypatch, span, View(tab='ai', measure='scribe')))
    nonai = ' '.join(_notes_for(monkeypatch, span, View(tab='nonai')))
    assert '"Output exported" is recorded from 02 Mar 2026' in runs
    assert 'speech-to-text model is recorded from 02 Mar 2026' in scribe
    assert 'web server log (Jan 2026 – Feb 2026)' in nonai
