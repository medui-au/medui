from dataclasses import dataclass
from datetime import date
from typing import Callable

CHART_BAR = 'bar'
CHART_STACKED_BAR = 'stacked_bar'
CHART_CATEGORY_TOTALS = 'category_totals'


@dataclass(frozen=True)
class Column:
    """One field of a compute() row, shown as a table column (admin, all
    doctors) or a stat tile (a single doctor's own view).

    `always_show_tile` controls the single-doctor stat-tile view only (the
    admin table always shows every column regardless). Set False for columns
    where a zero is uninteresting noise rather than useful context — e.g. a
    long tail of vaccine categories a doctor has never given; a doctor with
    30 zero-value tiles can't see their real numbers at a glance. Total/
    patients/age-band-style columns should stay True.

    `summable` controls the admin table's Total row (see
    quality_service.build_totals_row). Raw counts sum sensibly across
    doctors; a percentage column summed the same way would be meaningless
    (e.g. adding one doctor's 80% to another's 40%), so percentage-style
    columns should set this False — the Total row shows a dash for them
    instead of a naive sum.
    """

    key: str
    label: str
    always_show_tile: bool = True
    summable: bool = True


@dataclass(frozen=True)
class ChartSpec:
    """One chart the Quality page can render for an indicator.

    kind='bar' plots a single numeric field (`metric`) per doctor.
    kind='stacked_bar' plots several fields (`segments`, a list of
    (field_key, segment_label) pairs) stacked within each doctor's bar —
    e.g. an age breakdown. kind='category_totals' also takes `segments`, but
    sums each field across *all* rows into one practice-wide count per
    segment, rendered as a horizontal bar rather than per-doctor bars — for
    breakdowns where "which doctor" isn't the point, just "how many of
    each". See app/services/quality_service.py for the Chart.js payload
    this drives.
    """

    key: str
    label: str
    kind: str
    metric: str | None = None
    segments: list[tuple[str, str]] | None = None


@dataclass(frozen=True)
class Indicator:
    """A single quality indicator: a name plus a function that computes it.

    `compute(start_date, end_date)` returns a list of per-doctor dicts, each
    of which must include `bpsdb_userid` and `doctor_name` alongside
    whatever metric fields the indicator produces (named in `columns` and
    `charts`). Always covers every active doctor, even at all-zero — the
    doctor.quality route filters this down to one doctor's row when needed.

    `columns` drives the admin table / single-doctor stat-tile rendering
    generically — no indicator-specific HTML needed in the template.

    `charts` lists the chart(s) available for this indicator; the page
    shows a toggle when there's more than one. Each is a bar, stacked_bar,
    or category_totals (see ChartSpec).

    `uses_period_filter` — most indicators are period-windowed (compute()
    uses start_date/end_date); a few (e.g. current inbox backlog) are
    point-in-time snapshots where compute() ignores its date args and a
    period selector would just be confusing. Set False for those — the
    page hides the period filter and shows a "live snapshot" note instead.

    `rationale` — a short, honest explanation of what this measure does and
    doesn't tell you (see app/indicators/__init__.py for the drafted text
    per indicator), pre-filled into the editable explanation box on the
    Quality Report (doctor.quality_report). Deliberately not a marketing
    line — several of these indicators are workload-confounded counts, not
    clean quality signals, and the text says so rather than overselling a
    raw number as a performance measure.
    """

    key: str
    label: str
    description: str
    compute: Callable[[date, date], list[dict]]
    columns: list[Column]
    charts: list[ChartSpec]
    uses_period_filter: bool = True
    rationale: str = ''
