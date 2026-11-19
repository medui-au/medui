"""RedactionService: patient identifiers and the record-based redaction passes.

The rules are the bps_redaction core's (ADR-114); this module keeps the import
path MedUI's pipeline and services use. See app/services/redaction_core.py.
"""

from bps_redaction import redaction as _core

from app.services.redaction_core import bound, in_context

RedactionService = bound(_core.RedactionService)

_ALWAYS_TABLE = _core._ALWAYS_TABLE
_ALWAYS_MIN_LENGTH = _core._ALWAYS_MIN_LENGTH
_lowercase_words = in_context(_core._lowercase_words)
