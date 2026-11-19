"""My usage: each person's own Application Usage, beside the practice's totals (ADR-138).

The same engine as the admin page (usage_report_service, ADR-137), with two
locks the caller cannot undo:

- **Your figures** always carry ``user_id = <the signed-in person>``. The
  person and role are set here, never read from the address, so no link can
  show anyone else. Person and role are not offered as breakdowns.
- **Practice figures** are totals only: the headline numbers for the same
  period and tab, never a breakdown, never rows, and never under your other
  filters. With a small staff, "the practice under this pipeline filter" or
  "the nurses" can be one colleague; whole-period totals cannot be narrowed
  that way. They count attributed records only (live and imported), the same
  kinds as yours, so the two are comparable.
"""
from dataclasses import replace

from app.services import usage_report_service as reports
from app.services.usage_report_service import Filters, View

# Attributed records only: the access-log history has no person, so it can be
# neither yours nor a fair part of the practice figure beside yours.
SOURCES = {'live', 'imported'}
OWN_DIMENSIONS = {kind: {k: v for k, v in dims.items() if k not in ('user_id', 'role')}
                  for kind, dims in reports.DIMENSIONS.items()}
# Where a card goes on your page, instead of "by person".
_OWN_GO = {'runs': 'feature', 'scribe': 'model', 'nonai': 'weekday'}
_DROP_CARDS = ('People active',)          # always 1 for one person


def lock(f: Filters, user_id: int) -> Filters:
    """Your filters: this person, any role, attributed records."""
    return replace(f, user_id=user_id, role='', sources=set(SOURCES))


def practice_filters(f: Filters) -> Filters:
    """The practice's: same period and chart grouping, nothing else."""
    return Filters(start=f.start, end=f.end, group=f.group, sources=set(SOURCES))


def own_view(view: View) -> View:
    view.normalise()
    if view.by not in OWN_DIMENSIONS[view.kind]:
        view.by = next(iter(OWN_DIMENSIONS[view.kind]))
    return view


def build(user_id: int, view: View, f: Filters) -> dict:
    """Your view, with the practice total beside each headline figure."""
    if not user_id:
        raise ValueError('My usage needs a signed-in person')
    view = own_view(view)
    mine = lock(f, user_id)
    out = reports.build(view, mine, show_names=True)
    out['dimensions'] = OWN_DIMENSIONS[view.kind]

    practice = {c['label']: c['value'] for c in _cards(view, practice_filters(f))}
    cards = []
    for card in out['cards']:
        if card['label'] in _DROP_CARDS:
            continue
        go = dict(card['go'])
        if go.get('by') in ('user_id', 'role'):
            go['by'] = _OWN_GO[go.get('measure', 'runs') if view.tab == 'ai' else 'nonai']
        card.update(go=go, practice=practice.get(card['label'], '—'),
                    hint=card['hint'].replace(', by person', ''),
                    active=(go.get('measure', view.measure) == view.measure and go['by'] == view.by
                            and all(getattr(mine, k, None) == v for k, v in go.items()
                                    if k not in ('by', 'measure'))))
        cards.append(card)
    out['cards'] = cards
    out['notes'] = _notes(view, f) + [n for n in out['notes'] if 'figures above all count' not in n
                                      and 'access log' not in n]
    out['filters'] = describe(mine, view)
    return out


def _cards(view: View, f: Filters) -> list[dict]:
    """Headline figures only: no chart, no breakdown, no rows."""
    began = reports.checks_began() if view.tab == 'ai' else None
    out = {'cards': [], 'total': 0}
    if view.tab == 'ai':
        cte, p = reports._base('runs', f, began)
        reports._ai_cards(f, View(tab='ai', measure='runs', by='feature'), cte, p, began, out)
    else:
        cte, p = reports._base('nonai', f)
        reports._nonai_cards(cte, p, out)
    return out['cards']


def _notes(view: View, f: Filters) -> list[str]:
    notes = ['"Practice" is everyone\'s total for the same period, including yours. It is a total '
             'only: it is never broken down, and your filters do not narrow it.']
    if view.tab == 'nonai':
        notes.append('Tasks from the web server log (May – September 2026) have no person, so they '
                     'are in neither figure.')
    return notes


def describe(f: Filters, view: View) -> list[str]:
    out = [f'{f.start:%d %b %Y} – {f.end:%d %b %Y}', reports.TABS[view.tab]]
    if view.tab == 'ai':
        out.append(reports.MEASURES[view.measure])
    for n in reports.tab_filters(view.tab):
        value = getattr(f, n)
        if value:
            out.append(f'{reports.FILTER_LABELS[n]}: {reports.value_label(n, value)}')
    return out


def drill(view: View, f: Filters, value) -> dict:
    return reports.drill(view, f, value)
