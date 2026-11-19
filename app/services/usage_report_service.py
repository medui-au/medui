"""Application Usage over the permanent usage record (ADR-137).

Two tabs, AI and Non-AI. Each tab is one filtered set of records, the
``base``/``f`` CTE, and every figure, the chart, the breakdown and the rows
are read from that set. So a filter cannot miss a card: no card has a WHERE
clause of its own. The page goes figure → breakdown (by a chosen dimension) →
the underlying rows. A breakdown row becomes a filter, and the breakdown moves
to the next dimension.

The AI tab has two measures. *AI runs* (one per text-model run, ``ai.run``) and
*scribe sessions* (speech-to-text), so the provider and model filters cover
both. The record holds no patient. Staff appear by their permanent label
("Doctor 2") unless names are asked for; the page's switch and the export
confirmation decide that, never this module. See
plans/usage_reports_redesign_proposal.md and plans/usage_reporting_plan.md.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.extensions import db

TABS = {'ai': 'AI', 'nonai': 'Non-AI'}
MEASURES = {'runs': 'AI runs', 'scribe': 'Scribe sessions'}
GROUPS = {'day': 'day', 'week': 'week', 'month': 'month'}
SOURCES = ('live', 'imported', 'unattributed')
PAGE_SIZE = 50
EXPORT_ROWS = 20000
NOT_RECORDED = '(not recorded)'

SCRIBE_TASKS = ('scribe.session', 'scribe.quick', 'dictation')

# Breakdown dimensions per view: key (also the filter's name) -> heading.
DIMENSIONS = {
    'runs': {'feature': 'Feature', 'provider': 'Provider', 'model': 'Model', 'pipeline': 'Pipeline',
             'user_id': 'Person', 'role': 'Role', 'result': 'Result', 'privacy': 'Privacy check',
             'locality': 'Local or cloud'},
    'scribe': {'user_id': 'Person', 'role': 'Role', 'provider': 'Provider', 'model': 'Model',
               'locality': 'Local or cloud', 'task': 'Kind'},
    'nonai': {'area': 'Area', 'task': 'Task', 'user_id': 'Person', 'role': 'Role',
              'outcome': 'Outcome', 'weekday': 'Weekday', 'hour': 'Hour of day'},
}
# After clicking a breakdown row: the next dimensions to try, in order, skipping
# any already filtered. When none is left, the rows are shown.
NEXT = {
    'feature': ('pipeline', 'model', 'user_id'), 'pipeline': ('model', 'user_id'),
    'model': ('pipeline', 'user_id'), 'provider': ('model', 'pipeline', 'user_id'),
    'user_id': ('feature', 'task', 'pipeline', 'model'), 'role': ('user_id',),
    'result': ('model', 'pipeline', 'user_id'), 'privacy': ('pipeline', 'model', 'user_id'),
    'locality': ('provider', 'model', 'user_id'), 'area': ('task', 'user_id'),
    'task': ('user_id',), 'outcome': ('task', 'user_id'),
}
UNDRILLABLE = ('weekday', 'hour')        # shown for pattern, not a filter
AI_FILTERS = ('feature', 'provider', 'model', 'pipeline', 'locality', 'result', 'privacy')
NONAI_FILTERS = ('area', 'task', 'outcome')

FEATURE_LABELS = {
    'ai_panel': 'AI panel', 'document_button': 'Document button', 'chatbot': 'Patient chatbot',
    'generic_chatbot': 'Generic chatbot', 'pii_erasure': 'Chatbot identifier erasure',
    'library': 'Library', 'scribe': 'Scribe', 'charts': 'Charts',
    'careplan_recipe': 'Care plan recipe', 'other': 'Other',
}
RESULT_LABELS = {
    'ok': 'Completed',
    'security_block': 'Security block',
    'empty_response': 'Failed: provider returned an empty answer',
    'internal_error': 'Failed: MedUI internal error',
    'model_unavailable': 'Failed: model not available from the provider',
    'connection': 'Failed: connection error',
    'model_disabled': 'Failed: model not found or switched off in MedUI',
    'too_large': 'Failed: request too large (token limit)',
    'authentication': 'Failed: provider authentication failed',
    'interrupted': 'Failed: interrupted',
    'timeout': 'Failed: timed out',
    'rate_limited': 'Failed: rate limited by the provider',
    'other': 'Failed: other',
}
PRIVACY_LABELS = {
    'clear': 'Clear',
    'tier:0': 'Patient identifier (tier 0)',
    'tier:1': 'Non-patient identifier (tier 1)',
    'tier:2': 'Possible non-patient identifier (tier 2)',
    'tier:3': 'Flagged by a model only (tier 3)',
    'not_needed_local': 'Not needed (local model)',
    'not_checked': 'Not checked (pre-send check unavailable)',
    'before_checks': 'Before privacy checks began',
    'screening': 'PII screening run',
    'none': 'None recorded',
}
LOCALITY_LABELS = {'local': 'Local', 'cloud': 'Cloud', 'unknown': 'Unknown'}
WEEKDAYS = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday',
            6: 'Saturday', 7: 'Sunday'}
SCRIBE_KINDS = {'scribe.session': 'Scribe session', 'scribe.quick': 'Quick scribe',
                'dictation': 'Dictation'}


def _local_zone() -> ZoneInfo:
    """The practice's timezone (ADR-101): report days are the practice's days."""
    from app.services import practice_time
    return practice_time.zone()


@dataclass
class Filters:
    start: date
    end: date
    user_id: int | None = None
    role: str = ''
    sources: set = field(default_factory=lambda: set(SOURCES))
    group: str = 'week'
    # AI tab
    feature: str = ''
    provider: str = ''
    model: str = ''
    pipeline: str = ''
    locality: str = ''                    # '' | local | cloud | unknown
    result: str = ''
    privacy: str = ''
    # Non-AI tab
    area: str = ''
    task: str = ''
    outcome: str = ''

    def utc_bounds(self) -> tuple[datetime, datetime]:
        lo = datetime.combine(self.start, time.min, _local_zone()).astimezone(timezone.utc)
        hi = datetime.combine(self.end + timedelta(days=1), time.min, _local_zone()).astimezone(timezone.utc)
        return lo.replace(tzinfo=None), hi.replace(tzinfo=None)


@dataclass
class View:
    tab: str = 'ai'
    measure: str = 'runs'                 # AI tab only
    by: str = ''
    rows: bool = False
    page: int = 1

    @property
    def kind(self) -> str:
        """Which record set: runs, scribe or nonai."""
        return self.measure if self.tab == 'ai' else 'nonai'

    def normalise(self) -> 'View':
        self.tab = self.tab if self.tab in TABS else 'ai'
        self.measure = self.measure if self.measure in MEASURES else 'runs'
        dims = DIMENSIONS[self.kind]
        if self.by not in dims:
            self.by = next(iter(dims))
        self.page = max(1, self.page)
        return self


def tab_filters(tab: str) -> tuple:
    return AI_FILTERS if tab == 'ai' else NONAI_FILTERS


# ── The one filtered set per view ────────────────────────────────────────────

def _event_where(f: Filters) -> tuple[str, dict]:
    lo, hi = f.utc_bounds()
    clauses = ['e.occurred_at >= :lo', 'e.occurred_at < :hi']
    params = {'lo': lo, 'hi': hi}
    kinds = []
    if 'live' in f.sources:
        kinds.append("e.source = 'live'")
    if 'imported' in f.sources:
        kinds.append("(e.source <> 'live' AND e.quality <> 'unattributed')")
    if 'unattributed' in f.sources:
        kinds.append("e.quality = 'unattributed'")
    clauses.append('(' + (' OR '.join(kinds) or 'false') + ')')
    if f.user_id:
        clauses.append('e.user_id = :user_id')
        params['user_id'] = f.user_id
    if f.role:
        clauses.append(f"coalesce(e.role_at_time, '{NOT_RECORDED}') = :role")
        params['role'] = f.role
    return ' AND '.join(clauses), params


def _filtered(f: Filters, names: tuple) -> tuple[str, dict]:
    """WHERE over the base's own columns, for every filter of this tab that is set."""
    clauses, params = [], {}
    for name in names:
        value = getattr(f, name)
        if value:
            clauses.append(f'{name} = :f_{name}')
            params[f'f_{name}'] = value
    return (' AND '.join(clauses) or 'true'), params


def _locality(alias: str) -> str:
    return (f"case when {alias}.provider_is_local then 'local' "
            f"when {alias}.provider_is_local = false then 'cloud' else 'unknown' end")


# A cloud call with no verdict before the first check ever recorded was not
# "not checked": the check did not exist yet. Local calls need no check.
_PRIVACY = ("case when a.id is null then 'none' "
            "when a.privacy_verdict like 'screening%' then 'screening' "
            "when a.privacy_verdict = 'not_checked' and e.occurred_at < :checks_began then 'before_checks' "
            "when a.privacy_verdict is null and a.provider_is_local then 'not_needed_local' "
            "else coalesce(a.privacy_verdict, 'none') end")


def checks_began() -> datetime:
    return _rows("""select coalesce(min(e.occurred_at), now() at time zone 'UTC')
        from usage_ai_calls a join usage_events e on e.id = a.event_id
        where a.privacy_verdict = 'clear' or a.privacy_verdict like 'tier:%'""", {})[0][0]


def history_span() -> dict:
    """When live recording began, and the span of imported history (empty when none was imported).

    Keys: 'live_start' (first live entry), and, only when present, 'imported_until' (last imported
    entry) and 'unattributed' ((first, last) of the web server log's tasks, which have no person).
    """
    row = _rows("""select min(occurred_at) filter (where source = 'live'),
                          max(occurred_at) filter (where source <> 'live'),
                          min(occurred_at) filter (where quality = 'unattributed'),
                          max(occurred_at) filter (where quality = 'unattributed')
                   from usage_events""", {})[0]
    out = {'live_start': row[0]}
    if row[1] is not None:
        out['imported_until'] = row[1]
    if row[2] is not None:
        out['unattributed'] = (row[2], row[3])
    return out


def _base(kind: str, f: Filters, began: datetime | None = None) -> tuple[str, dict]:
    """``with base as (...), f as (...)``: the view's whole filtered set."""
    ew, params = _event_where(f)
    zone = _local_zone().key
    local = f"((e.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE '{zone}')"
    if kind == 'runs':
        params['checks_began'] = began or checks_began()
        base = f"""
            select e.id, e.occurred_at, e.user_id, coalesce(e.role_at_time, '{NOT_RECORDED}') as role,
                   coalesce(a.origin, 'other') as feature,
                   coalesce(a.provider_name, '{NOT_RECORDED}') as provider,
                   coalesce(a.model, '{NOT_RECORDED}') as model,
                   coalesce(a.pipeline_name, '{NOT_RECORDED}') as pipeline,
                   {_locality('a')} as locality,
                   case when e.outcome = 'ok' then 'ok' when e.outcome = 'blocked' then 'security_block'
                        else coalesce(a.error_class, 'other') end as result,
                   {_PRIVACY} as privacy,
                   a.tokens_in, a.tokens_out, a.cost, a.model_ms,
                   coalesce(a.exported_after, false) as exported, a.pipeline_run_id as run_id
            from usage_events e
            left join usage_ai_calls a on a.event_id = e.id and a.kind = 'inference'
            where {ew} and e.task = 'ai.run'"""
        names = AI_FILTERS
    elif kind == 'scribe':
        # A session has no pipeline and no pre-send check, so a pipeline or
        # privacy filter leaves no sessions; that is the filter obeyed.
        base = f"""
            select e.id, e.occurred_at, e.user_id, coalesce(e.role_at_time, '{NOT_RECORDED}') as role,
                   e.task, 'scribe'::text as feature,
                   coalesce(s.provider_name, '{NOT_RECORDED}') as provider,
                   coalesce(s.model, '{NOT_RECORDED}') as model,
                   null::text as pipeline, {_locality('s')} as locality,
                   case when e.outcome = 'ok' then 'ok' else 'other' end as result,
                   null::text as privacy, coalesce(s.chunks, 0) as chunks,
                   exists (select 1 from usage_ai_calls d where d.event_id = e.id
                           and d.kind = 'diarization') as labelled
            from usage_events e
            left join usage_ai_calls s on s.event_id = e.id and s.kind = 'speech_to_text'
            where {ew} and e.task in {SCRIBE_TASKS!r}"""
        names = AI_FILTERS
    else:
        base = f"""
            select e.id, e.occurred_at, e.user_id, coalesce(e.role_at_time, '{NOT_RECORDED}') as role,
                   e.area, e.task, e.outcome, e.duration_ms, e.source, e.quality,
                   extract(isodow from {local})::int as weekday, extract(hour from {local})::int as hour
            from usage_events e
            where {ew} and not e.is_ai"""
        names = NONAI_FILTERS
    fw, fp = _filtered(f, names)
    params.update(fp)
    return f'with base as ({base}), f as (select * from base where {fw}) ', params


def _rows(sql: str, params: dict) -> list:
    return db.session.execute(text(sql), params).fetchall()


def _period(f: Filters) -> str:
    unit = GROUPS.get(f.group, 'week')
    return (f"date_trunc('{unit}', (occurred_at AT TIME ZONE 'UTC') "
            f"AT TIME ZONE '{_local_zone().key}')::date")


# ── Labels ───────────────────────────────────────────────────────────────────

def person_namer(show_names: bool):
    """user_id -> what to show: the permanent label, or the name when asked for."""
    from app.models.user import User
    from app.services.usage_service import label_of
    names = {u.id: (u.display_name or u.username) for u in User.query.all()} if show_names else {}

    def name(user_id):
        if not user_id:
            return 'Unspecified (history)'
        return (names.get(user_id) or label_of(user_id)) if show_names else label_of(user_id)
    return name


def value_label(dim: str, value, name=None) -> str:
    if value is None or value == '':
        return '—'
    if dim == 'user_id':
        return name(value) if name else str(value)
    if dim == 'feature':
        return FEATURE_LABELS.get(value, value)
    if dim == 'result':
        return RESULT_LABELS.get(value, f'Failed: {value}')
    if dim == 'privacy':
        return PRIVACY_LABELS.get(value, value)
    if dim == 'locality':
        return LOCALITY_LABELS.get(value, value)
    if dim == 'weekday':
        return WEEKDAYS.get(value, str(value))
    if dim == 'hour':
        return f'{int(value):02d}:00'
    if dim == 'task' and value in SCRIBE_KINDS:
        return SCRIBE_KINDS[value]
    return str(value)


def _local(value: datetime | None, with_time: bool = False) -> str:
    if not value:
        return '—'
    local = value.replace(tzinfo=timezone.utc).astimezone(_local_zone())
    return local.strftime('%d %b %Y %H:%M' if with_time else '%d %b %Y')


def _pct(part, whole) -> str:
    return f'{100 * part / whole:.0f}%' if whole else '—'


def _secs(ms) -> str:
    return f'{ms / 1000:.1f}' if ms is not None else '—'


# ── Building a view ──────────────────────────────────────────────────────────

def build(view: View, f: Filters, show_names: bool = False, export: bool = False) -> dict:
    """Figures, chart and either the breakdown or the rows for one view.

    Every query starts from the same ``_base`` with the same parameters.
    """
    view.normalise()
    name = person_namer(show_names)
    began = checks_began() if view.kind == 'runs' else None
    cte, p = _base(view.kind, f, began)
    out = {'tab': view.tab, 'kind': view.kind, 'by': view.by, 'rows_view': view.rows,
           'title': TABS[view.tab], 'cards': [], 'chart': None, 'chart_type': 'bar',
           'table': {'columns': [], 'rows': [], 'keys': []}, 'notes': [],
           'dimensions': DIMENSIONS[view.kind], 'page': view.page, 'pages': 1, 'total': 0}

    if view.tab == 'ai':
        _ai_cards(f, view, cte, p, began, out)
    else:
        _nonai_cards(cte, p, out)

    out['chart'] = _chart(view.kind, f, cte, p)
    if view.rows:
        _rows_table(view, cte, p, name, out, export)
        out['description'] = f"{MEASURES.get(view.measure) if view.tab == 'ai' else 'Tasks'}: the records"
    else:
        _breakdown(view, cte, p, name, out)
        out['description'] = (f"{MEASURES.get(view.measure) if view.tab == 'ai' else 'Tasks'} "
                              f"by {DIMENSIONS[view.kind][view.by].lower()}")
    _notes(view, f, began, out)
    return out


def _ai_cards(f, view, cte, p, began, out):
    # The run figures come from the runs set and the session figure from the
    # scribe set, both under the very same filters, whichever measure is open.
    if view.measure != 'runs':
        cte, p = _base('runs', f, began)
    runs, local, known, cost, failed = _rows(cte + """
        select count(*), count(*) filter (where locality = 'local'),
               count(*) filter (where locality in ('local', 'cloud')),
               coalesce(sum(cost), 0), count(*) filter (where result <> 'ok') from f""", p)[0]
    s_cte, s_p = _base('scribe', f, began)
    sessions = _rows(s_cte + 'select count(*) from f', s_p)[0][0]
    out['total'] = runs if view.measure == 'runs' else sessions
    out['cards'] = [
        {'label': 'AI runs', 'value': f'{runs:,}', 'go': {'measure': 'runs', 'by': 'feature'},
         'hint': 'Text-model runs, by feature'},
        {'label': 'Local share', 'value': _pct(local, known), 'go': {'measure': 'runs', 'by': 'provider'},
         'hint': 'Share of runs on local models, by provider'},
        {'label': 'Reported cost', 'value': f'${cost:,.2f}', 'go': {'measure': 'runs', 'by': 'model'},
         'hint': 'Cost reported by cloud providers, by model'},
        {'label': 'Failure rate', 'value': f'{100 * failed / runs:.1f}%' if runs else '—',
         'go': {'measure': 'runs', 'by': 'result'}, 'hint': 'Failed and blocked runs, by reason'},
        {'label': 'Scribe sessions', 'value': f'{sessions:,}', 'go': {'measure': 'scribe', 'by': 'user_id'},
         'hint': 'Speech-to-text sessions, by person'},
    ]
    for card in out['cards']:
        card['active'] = card['go']['measure'] == view.measure and card['go']['by'] == view.by


_NONAI_CARDS = (('Charts opened', 'chart.open'), ('Messages sent', 'message.send'),
                ('Exports to BP', 'export.pit'), ('Sign-ins', 'auth.sign_in'))


def _nonai_cards(cte, p, out):
    counts = ', '.join(f"count(*) filter (where task = '{task}')" for _, task in _NONAI_CARDS)
    row = _rows(cte + f'select count(*), count(distinct user_id), {counts} from f', p)[0]
    out['total'] = row[0]
    out['cards'] = [
        {'label': 'Tasks', 'value': f'{row[0]:,}', 'go': {'by': 'area'}, 'hint': 'All tasks, by area'},
        {'label': 'People active', 'value': f'{row[1]:,}', 'go': {'by': 'user_id'},
         'hint': 'People with a recorded task (history from the access log has none), by person'},
    ] + [{'label': label, 'value': f'{n:,}', 'go': {'task': task, 'by': 'user_id'},
          'hint': f'{label}, by person'} for (label, task), n in zip(_NONAI_CARDS, row[2:])]


def _chart(kind, f, cte, p) -> dict:
    series = 'area' if kind == 'nonai' else 'locality'
    rows = _rows(cte + f'select {_period(f)}, {series}, count(*) from f group by 1, 2 order by 1', p)
    periods = sorted({r[0] for r in rows})
    names = sorted({r[1] or 'unknown' for r in rows})
    values = {(r[0], r[1] or 'unknown'): r[2] for r in rows}
    label = (lambda n: n) if kind == 'nonai' else (lambda n: LOCALITY_LABELS.get(n, n))
    return {'labels': [per.isoformat() for per in periods],
            'datasets': [{'label': label(n), 'data': [values.get((per, n), 0) for per in periods]}
                         for n in names]}


def _breakdown(view, cte, p, name, out):
    dim = view.by
    if view.kind == 'runs':
        rows = _rows(cte + f"""
            select {dim}, count(*), count(*) filter (where locality = 'local'),
                   count(*) filter (where locality in ('local', 'cloud')),
                   coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0), sum(cost),
                   percentile_cont(0.5) within group (order by model_ms),
                   count(*) filter (where result <> 'ok'), count(*) filter (where exported)
            from f group by 1 order by 2 desc""", p)
        total = sum(r[1] for r in rows)
        columns = ['Runs', 'Share', 'Local', 'Tokens in', 'Tokens out', 'Cost', 'Median answer (s)',
                   'Not completed', 'Output exported']
        body = [[r[1], _pct(r[1], total), _pct(r[2], r[3]), f'{r[4]:,}', f'{r[5]:,}',
                 f'${r[6]:,.2f}' if r[6] is not None else '—', _secs(r[7]), r[8], r[9]] for r in rows]
    elif view.kind == 'scribe':
        rows = _rows(cte + f"""
            select {dim}, count(*), coalesce(sum(chunks), 0), count(*) filter (where labelled),
                   count(*) filter (where provider = '{NOT_RECORDED}')
            from f group by 1 order by 2 desc""", p)
        total = sum(r[1] for r in rows)
        columns = ['Sessions', 'Share', 'Speech-to-text chunks', 'With speaker labels', 'Model not recorded']
        body = [[r[1], _pct(r[1], total), f'{r[2]:,}', r[3], r[4]] for r in rows]
    else:
        order = '1' if dim in UNDRILLABLE else '2 desc'
        rows = _rows(cte + f"""
            select {dim}, count(*), count(distinct user_id),
                   percentile_cont(0.5) within group (order by duration_ms),
                   count(*) filter (where outcome <> 'ok')
            from f group by 1 order by {order}""", p)
        total = sum(r[1] for r in rows)
        columns = ['Tasks', 'Share', 'People', 'Median time (s)', 'Not OK']
        body = [[r[1], _pct(r[1], total), r[2], _secs(r[3]), r[4]] for r in rows]
    heading = DIMENSIONS[view.kind][dim]
    out['table'] = {'columns': [heading] + columns,
                    'rows': [[value_label(dim, r[0], name)] + b for r, b in zip(rows, body)],
                    # The value a click filters on; None where a row can't be a filter.
                    'keys': [None if dim in UNDRILLABLE or r[0] is None
                             or (view.kind == 'scribe' and dim == 'task') else r[0] for r in rows]}


def drill(view: View, f: Filters, value) -> dict:
    """URL changes for clicking a breakdown row: filter on it, then the next dimension."""
    changes = {view.by: value, 'page': None}
    filtered = {n for n in DIMENSIONS[view.kind] if getattr(f, n, None)} | {view.by}
    nxt = next((d for d in NEXT.get(view.by, ()) if d in DIMENSIONS[view.kind] and d not in filtered), None)
    if nxt:
        changes['by'] = nxt
    else:
        changes['view'] = 'rows'
    return changes


def _rows_table(view, cte, p, name, out, export):
    limit = EXPORT_ROWS if export else PAGE_SIZE
    offset = 0 if export else (view.page - 1) * PAGE_SIZE
    out['pages'] = max(1, -(-out['total'] // PAGE_SIZE))
    page = f' order by occurred_at desc, id desc limit {limit} offset {offset}'
    if view.kind == 'runs':
        rows = _rows(cte + 'select occurred_at, user_id, role, feature, pipeline, provider, model, '
                     'locality, tokens_in, tokens_out, cost, model_ms, result, privacy, exported, run_id '
                     'from f' + page, p)
        out['table'] = {'columns': ['When', 'Person', 'Role', 'Feature', 'Pipeline', 'Provider', 'Model',
                                    'Local or cloud', 'Tokens in', 'Tokens out', 'Cost', 'Answer (s)',
                                    'Result', 'Privacy check', 'Output exported', 'Run'],
                        'rows': [[_local(r[0], True), name(r[1]), r[2], value_label('feature', r[3]), r[4],
                                  r[5], r[6], value_label('locality', r[7]),
                                  r[8] if r[8] is not None else '—', r[9] if r[9] is not None else '—',
                                  f'${r[10]:,.4f}' if r[10] is not None else '—', _secs(r[11]),
                                  value_label('result', r[12]), value_label('privacy', r[13]),
                                  'yes' if r[14] else '', f'#{r[15]}' if r[15] else '—'] for r in rows]}
    elif view.kind == 'scribe':
        rows = _rows(cte + 'select occurred_at, user_id, role, task, provider, model, locality, chunks, '
                     'labelled from f' + page, p)
        out['table'] = {'columns': ['When', 'Person', 'Role', 'Kind', 'Provider', 'Model', 'Local or cloud',
                                    'Speech-to-text chunks', 'Speaker labels'],
                        'rows': [[_local(r[0], True), name(r[1]), r[2], value_label('task', r[3]), r[4],
                                  r[5], value_label('locality', r[6]), r[7], 'yes' if r[8] else '']
                                 for r in rows]}
    else:
        rows = _rows(cte + 'select occurred_at, user_id, role, task, area, outcome, duration_ms, source '
                     'from f' + page, p)
        out['table'] = {'columns': ['When', 'Person', 'Role', 'Task', 'Area', 'Outcome', 'Time (s)', 'Source'],
                        'rows': [[_local(r[0], True), name(r[1]), r[2], r[3], r[4], r[5], _secs(r[6]),
                                  'live' if r[7] == 'live' else 'history'] for r in rows]}
    out['table']['keys'] = [None] * len(out['table']['rows'])


def _notes(view, f, began, out):
    notes = out['notes']
    span = history_span()
    live = span['live_start']
    imported = 'imported_until' in span and live is not None
    if view.kind == 'runs':
        notes.append('An AI run is one text-model run, from any feature: AI panel, document buttons, '
                     'chatbots, scribe issue lists, library, care plans.')
        cost = 'Cost is as reported by cloud providers.'
        if imported:
            cost += f' "Output exported" is recorded from {live:%d %b %Y}.'
        notes.append(cost)
        if view.by == 'privacy' or f.privacy:
            notes.append(f'Privacy checks began {began:%d %b %Y}; earlier cloud runs show "Before privacy '
                         'checks began". Local runs need no check.')
    elif view.kind == 'scribe':
        if imported:
            notes.append(f'The speech-to-text model is recorded from {live:%d %b %Y}; for earlier '
                         'sessions it was matched from the app log where it could be, and some are '
                         '"(not recorded)".')
        if f.pipeline or f.privacy or (f.feature and f.feature != 'scribe'):
            notes.append('Scribe sessions have no pipeline, privacy check or other feature, so this '
                         'filter leaves none.')
    elif 'unattributed' in span:
        first, last = span['unattributed']
        notes.append(f'Tasks from the web server log ({first:%b %Y} – {last:%b %Y}) have no person: '
                     'they count, but not under any person or role.')
    if view.tab == 'ai' and view.measure == 'runs':
        notes.append('The figures above all count from the same filtered set: change a filter and '
                     'every figure, the chart and the table follow it.')


# ── Filter choices ───────────────────────────────────────────────────────────

def choices() -> dict:
    """Distinct values for the filter lists."""
    one = lambda sql: [r[0] for r in _rows(sql, {}) if r[0] not in (None, '')]
    calls = "from usage_ai_calls where kind in ('inference', 'speech_to_text')"
    out = {
        'roles': one('select distinct role_at_time from usage_events order by 1'),
        'features': one("select distinct coalesce(origin, 'other') from usage_ai_calls "
                        "where kind = 'inference' order by 1"),
        'providers': one(f'select distinct provider_name {calls} order by 1'),
        'models': one(f'select distinct model {calls} order by 1'),
        'pipelines': one("select distinct pipeline_name from usage_ai_calls "
                         "where kind = 'inference' order by 1"),
        'results': one("""select distinct case when e.outcome = 'ok' then 'ok'
                                when e.outcome = 'blocked' then 'security_block'
                                else coalesce(a.error_class, 'other') end
                          from usage_events e left join usage_ai_calls a
                            on a.event_id = e.id and a.kind = 'inference'
                          where e.task = 'ai.run' order by 1"""),
        'privacy': [k for k in PRIVACY_LABELS],
        'areas': one('select distinct area from usage_events where not is_ai order by 1'),
        'tasks': one('select distinct task from usage_events where not is_ai order by 1'),
        'outcomes': one('select distinct outcome from usage_events where not is_ai order by 1'),
        'users': [r[0] for r in _rows('select distinct user_id from usage_events '
                                      'where user_id is not null order by 1', {})],
    }
    for key, column in (('providers', 'provider_name'), ('models', 'model'), ('pipelines', 'pipeline_name')):
        kinds = "('inference')" if key == 'pipelines' else "('inference', 'speech_to_text')"
        if _rows(f'select 1 from usage_ai_calls where kind in {kinds} and {column} is null limit 1', {}):
            out[key].append(NOT_RECORDED)
    return out


def describe(f: Filters, view: View, name) -> list[str]:
    """The filters in words, for the page heading and every export."""
    out = [f'{f.start:%d %b %Y} – {f.end:%d %b %Y}', TABS[view.tab]]
    if view.tab == 'ai':
        out.append(MEASURES[view.measure])
    if f.user_id:
        out.append(f'Person: {name(f.user_id)}')
    if f.role:
        out.append(f'Role: {f.role}')
    for n in tab_filters(view.tab):
        value = getattr(f, n)
        if value:
            out.append(f'{FILTER_LABELS[n]}: {value_label(n, value)}')
    if f.sources != set(SOURCES):
        out.append('Includes: ' + ', '.join(s for s in SOURCES if s in f.sources))
    return out


FILTER_LABELS = {'feature': 'Feature', 'provider': 'Provider', 'model': 'Model', 'pipeline': 'Pipeline',
                 'locality': 'Local or cloud', 'result': 'Result', 'privacy': 'Privacy check',
                 'area': 'Area', 'task': 'Task', 'outcome': 'Outcome', 'user_id': 'Person', 'role': 'Role'}


# ── Exports ──────────────────────────────────────────────────────────────────

def to_csv(report: dict) -> str:
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(report['table']['columns'])
    writer.writerows(report['table']['rows'])
    return buf.getvalue()


def to_markdown(report: dict, identified: bool) -> str:
    lines = [f"# Application Usage — {report['title']}", '', report['description'], '',
             '**Filters:** ' + '; '.join(report['filters']), '',
             '**Staff:** ' + ('named — keep inside the practice' if identified
                              else 'de-identified (permanent labels)'), '']
    if report['cards']:
        lines += ['| ' + ' | '.join(c['label'] for c in report['cards']) + ' |',
                  '|' + '---|' * len(report['cards']),
                  '| ' + ' | '.join(str(c['value']) for c in report['cards']) + ' |', '']
    cols = report['table']['columns']
    lines += ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    lines += ['| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |'
              for row in report['table']['rows']]
    for note in report['notes']:
        lines += ['', f'_{note}_']
    return '\n'.join(lines) + '\n'
