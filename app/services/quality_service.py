"""Chart.js payload builder for the Quality indicators page.

Ported from the BMC Monitor prototype's chart_service.py, but emitting
Chart.js {type, labels, datasets} data instead of CSS bar-height percentages
(MedUI already loads Chart.js via CDN elsewhere — see doctor/billing_analysis.html,
clinical/patient_charts.html). Colors are NOT baked in here: each dataset
carries a 0-based `series` index that the template maps to a CSS custom
property (--q-series-N), so light/dark theming lives in CSS, matching how
billing_analysis.html already reads --accent-primary for its own chart.
"""

from app.indicators.base import CHART_BAR, CHART_CATEGORY_TOTALS, CHART_STACKED_BAR, ChartSpec, Indicator

# Matches the dataviz skill's validated 8-slot categorical palette — beyond
# 8 series, adjacent-pair colorblind-safety is no longer guaranteed, so
# stacked charts with more segments than this get capped (see
# _build_stacked_bar) rather than growing a 9th hue.
MAX_STACK_SEGMENTS = 8
OTHER_SEGMENT_KEY = '__other__'
OTHER_SEGMENT_LABEL = 'Other (grouped)'


def build_totals_row(indicator: Indicator, rows: list[dict]) -> dict | None:
    """A synthetic 'Total' row for the admin All-Doctors table: each
    Column.summable column gets the sum across every doctor; non-summable
    columns (percentages — see Column.summable) get None, which the
    template renders as a dash rather than a misleading naive sum of
    percentages. Returns None when there's nothing to total.
    """
    if not rows:
        return None
    return {
        'doctor_name': 'Total',
        **{
            col.key: (sum(r.get(col.key, 0) or 0 for r in rows) if col.summable else None)
            for col in indicator.columns
        },
    }


def build_chart(
    spec: ChartSpec, rows: list[dict], *, anonymize: bool = False, mine_userid: int | None = None
) -> dict:
    """Dispatch to the right builder for a ChartSpec's kind.

    `anonymize`=True hides every doctor's name from the chart payload
    entirely (not just visually — the label strings themselves are blanked
    before the dict is serialised to the page) except the viewer's own bar,
    which is still positionally identified via `mine_index` so the template
    can highlight it. Used for the single-doctor view (a non-admin, or an
    admin who has drilled into one doctor) so a doctor can see how their own
    numbers compare to the practice without seeing colleagues' names — the
    same practice-wide-but-anonymised comparison the BMC Monitor prototype
    offered (see plans/decisions.md ADR-010/ADR-011), just Chart.js-rendered.
    `CHART_CATEGORY_TOTALS` is practice-wide by construction (no per-doctor
    identity in the first place), so it ignores both arguments.
    """
    if spec.kind == CHART_BAR:
        return _build_bar(spec, rows, anonymize, mine_userid)
    if spec.kind == CHART_STACKED_BAR:
        return _build_stacked_bar(spec, rows, anonymize, mine_userid)
    if spec.kind == CHART_CATEGORY_TOTALS:
        return _build_category_totals(spec, rows)
    raise ValueError(f'Unknown chart kind: {spec.kind!r}')


def _mine_index(ordered_rows: list[dict], mine_userid: int | None) -> int | None:
    if mine_userid is None:
        return None
    for i, r in enumerate(ordered_rows):
        if r.get('bpsdb_userid') == mine_userid:
            return i
    return None


def _anon_labels(n: int, mine_index: int | None) -> list[str]:
    """Blank every label except the viewer's own bar, which reads 'You' —
    the outline alone wasn't enough to pick "mine" out of a stack of
    otherwise-identically-styled segment colours, so the x-axis tick itself
    now names it too."""
    return ['You' if i == mine_index else '' for i in range(n)]


def _build_bar(spec: ChartSpec, rows: list[dict], anonymize: bool, mine_userid: int | None) -> dict:
    ordered = sorted(rows, key=lambda r: r.get(spec.metric, 0) or 0, reverse=True)
    mine_index = _mine_index(ordered, mine_userid)
    return {
        'type': 'bar',
        'stacked': False,
        'indexAxis': 'x',
        'anonymize': anonymize,
        'mine_index': mine_index,
        'labels': _anon_labels(len(ordered), mine_index) if anonymize else [r['doctor_name'] for r in ordered],
        'datasets': [{
            'label': spec.label,
            'series': 0,
            'data': [r.get(spec.metric, 0) or 0 for r in ordered],
        }],
    }


def _build_stacked_bar(
    spec: ChartSpec, rows: list[dict], anonymize: bool, mine_userid: int | None
) -> dict:
    segments = spec.segments
    dropped_keys: set[str] = set()

    if len(segments) > MAX_STACK_SEGMENTS:
        totals = {key: sum(r.get(key, 0) or 0 for r in rows) for key, _ in segments}
        kept = sorted(segments, key=lambda kv: totals[kv[0]], reverse=True)[:MAX_STACK_SEGMENTS - 1]
        kept_keys = {key for key, _ in kept}
        dropped_keys = {key for key, _ in segments if key not in kept_keys}
        segments = kept + [(OTHER_SEGMENT_KEY, OTHER_SEGMENT_LABEL)]

    def seg_value(row: dict, key: str):
        if key == OTHER_SEGMENT_KEY:
            return sum(row.get(k, 0) or 0 for k in dropped_keys)
        return row.get(key, 0) or 0

    ordered = sorted(
        rows,
        key=lambda r: sum(seg_value(r, key) for key, _ in segments),
        reverse=True,
    )
    mine_index = _mine_index(ordered, mine_userid)
    return {
        'type': 'bar',
        'stacked': True,
        'indexAxis': 'x',
        'anonymize': anonymize,
        'mine_index': mine_index,
        'labels': _anon_labels(len(ordered), mine_index) if anonymize else [r['doctor_name'] for r in ordered],
        'datasets': [
            {'label': label, 'series': i, 'data': [seg_value(r, key) for r in ordered]}
            for i, (key, label) in enumerate(segments)
        ],
    }


def _build_category_totals(spec: ChartSpec, rows: list[dict]) -> dict:
    """Practice-wide totals: one bar per category, summed across every row —
    not per-doctor, so a single series colour is enough (position + label
    already carry identity, same convention as any ranked bar list). No
    per-doctor identity is present at all, so this is safe to show to every
    viewer regardless of admin status."""
    totals = [(label, sum(r.get(key, 0) or 0 for r in rows)) for key, label in spec.segments]
    totals = [t for t in totals if t[1] > 0]
    totals.sort(key=lambda t: t[1], reverse=True)
    return {
        'type': 'bar',
        'stacked': False,
        'indexAxis': 'y',
        'anonymize': False,
        'mine_index': None,
        'labels': [label for label, _ in totals],
        'datasets': [{
            'label': spec.label,
            'series': 0,
            'data': [value for _, value in totals],
        }],
    }
