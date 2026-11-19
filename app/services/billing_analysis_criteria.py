"""Swappable "worked day" criterion for the Billing Analysis page's averages.

A day with a single stray billed item isn't a day the doctor "worked" in the
throughput sense, and the exact threshold is expected to be revised over
time. To change the rule, edit ACTIVE_DAY_CRITERION (or add a new entry to
WORKED_DAY_CRITERIA and point ACTIVE_DAY_CRITERION at it) — nothing in the
service's aggregation logic, the route, or the template needs to change.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WorkedDayCriterion:
    key: str
    label: str                          # shown to the admin as a footnote on the averages cards
    is_worked: Callable[[dict], bool]   # takes a row shaped like {total_items, total_fees, total_visits, ...}
                                         # — works identically on a per-(day, doctor) row or a practice-wide
                                         # per-day rollup row, since both carry the same three fields


MIN_VISITS_FOR_WORKED_DAY = 3

WORKED_DAY_CRITERIA: dict[str, WorkedDayCriterion] = {
    'min_visits': WorkedDayCriterion(
        key='min_visits',
        label=f'>{MIN_VISITS_FOR_WORKED_DAY} patients billed',
        is_worked=lambda row: row['total_visits'] > MIN_VISITS_FOR_WORKED_DAY,
    ),
    # Add future rules here, e.g.:
    # 'min_fees': WorkedDayCriterion(
    #     key='min_fees', label='> $500 billed',
    #     is_worked=lambda row: row['total_fees'] > 500,
    # ),
}

# Single point of change to revise which rule the averages use.
ACTIVE_DAY_CRITERION: WorkedDayCriterion = WORKED_DAY_CRITERIA['min_visits']
