"""Check a prompt for what survived redaction, before it is sent.

The detector is the bps_redaction core's checker (pattern-v22 at 0.2.x), run in
MedUI's Redactor context (app/services/redaction_core.py). It runs between
redaction and inference with no network call; the verdict is stored with the run.

  tier 0  the patient's own identifiers and their variants
  tier 1  named practitioners (address book, practice users) and the
          practice's own details
  tier 2  shapes that may be anyone's: phones, emails, Medicare numbers,
          addresses, titled names, labelled identifiers

Findings carry offsets into the text and types, never the matched text.
"""
from __future__ import annotations

from bps_redaction.checker.patterns import DETECTOR_VERSION

from app.services.redaction_core import redactor

__all__ = ['DETECTOR_VERSION', 'scan']


def scan(text: str, patient_id: int | None) -> dict:
    """The checker's verdict on text about to be sent.

    Returns {detector_version, lists, scanned_ms, top_tier, hits, patient_identifiers}.
    hits: one per span, by position: {tier, type, kind, coverage, start, end}.
    lists is the fingerprint of the practice's lists in use. patient_identifiers is
    'loaded', 'unavailable' (a patient run whose identifiers couldn't be read: tier 0
    was not searched, so the verdict is not clean), or 'none' (no patient).
    """
    return redactor().verdict(text or '', patient_id)
