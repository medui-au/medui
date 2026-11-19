"""HCPRedactionService: practitioners, staff and the address book.

The rules are the bps_redaction core's (ADR-114); this module keeps the import
path MedUI uses. See app/services/redaction_core.py.
"""

from bps_redaction import hcp as _core

from app.services.redaction_core import bound

HCPRedactionService = bound(_core.HCPRedactionService)
