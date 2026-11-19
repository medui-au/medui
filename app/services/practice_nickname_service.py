"""The practice's nickname table and the name-variants list (ADR-048, ADR-049).

The rules are the bps_redaction core's (ADR-114); this module keeps the names
the privacy-hits admin uses. See app/services/redaction_core.py.
"""

from bps_redaction import nicknames as _core

from app.services.redaction_core import in_context

LIST_TABLE = _core.LIST_TABLE
LIST_COLUMNS = _core.LIST_COLUMNS
forget_listed_forms = in_context(_core.forget_listed_forms)
