"""Extensible filter registry for the Billing Analysis page.

Doctor + period/date-range are "core" filters, handled directly by the route
(they scope every view on the page and reuse the existing /doctor/billings
controls). Anything beyond that is registered here as a BillingFilterDef —
adding a new filter means appending one entry to BILLING_ANALYSIS_FILTERS;
the repository, service, route, and filter-panel template all loop over this
list generically and need no further changes.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BillingFilterDef:
    key: str                              # request-arg name
    label: str                            # UI label
    render: str                           # 'text' | 'select' | 'number' — template render hint
    sql_predicate: str                    # trailing "AND (...)" clause using '?'; must be a no-op
                                           # when its bound values are NULL
    param_count: int
    bind: Callable[[object], list]        # request.args -> list[len == param_count]; all-None => inactive
    options: list[tuple] | None = None    # for render == 'select': (value, label) pairs


# Ordered. Add new filters here only — route/service/template need no further changes.
BILLING_ANALYSIS_FILTERS: list[BillingFilterDef] = []

# Example of how a future filter would be added (not implemented now):
# BillingFilterDef(
#     key='mbs_item', label='MBS Item contains', render='text',
#     sql_predicate='AND (? IS NULL OR s.MBSItem LIKE ?)', param_count=2,
#     bind=lambda args: ([f"%{args['mbs_item']}%"] * 2) if args.get('mbs_item') else [None, None],
# )
