"""The privacy card's data: MedUI's own pre-send check, and screening matches.

The pre-send check (app/services/checker/, the bps_redaction core's) runs on the prompt
exactly as it will be sent and is stored in the run. This module shapes what the admin
privacy card shows.
"""
from collections import Counter


def card_from_precheck(precheck: dict | None) -> dict | None:
    """The card's verdict from the stored pre-send check: top tier, hits (offsets), and
    findings counted by tier, type and coverage. None when the check didn't run or failed."""
    if not isinstance(precheck, dict) or 'error' in precheck or 'hits' not in precheck:
        return None
    hits = [h for h in precheck.get('hits') or [] if isinstance(h, dict)]
    counts = Counter((h.get('tier'), h.get('type'), h.get('coverage')) for h in hits)
    findings = [{'tier': t, 'type': ty or 'unknown', 'coverage': c, 'count': n}
                for (t, ty, c), n in sorted(counts.items(), key=lambda kv: (kv[0][0] is None, kv[0][0] or 0, str(kv[0][1])))]
    return {'top_tier': precheck.get('top_tier'), 'hits': hits, 'findings': findings,
            'detector_version': precheck.get('detector_version'), 'scanned_ms': precheck.get('scanned_ms'),
            'patient_identifiers': precheck.get('patient_identifiers')}


_MATCHES_PER_CATEGORY = 20
_MATCH_MAX_CHARS = 120


def screening_matches(answer: str, prompt: str) -> dict[str, list[dict]]:
    """The screening model's suspects, by category, for the privacy card.

    Read from the model's own answer, which the run already stores and the
    debug tab already shows; nothing new leaves MedUI. Each value says whether
    it appears word for word in the prompt, so a reader knows whether a find in
    the page will locate it. Redaction tokens are skipped.
    """
    import json
    import re
    text = re.sub(r'(?s)<think>.*?</think>', '', answer or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
    if not text or text.lower().startswith('no match'):
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        found = re.search(r'(?s)\{.*\}', text)
        try:
            data = json.loads(found.group(0)) if found else {}
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        return {}
    lowered = (prompt or '').lower()
    out: dict[str, list[dict]] = {}
    for category, values in data.items():
        label = re.sub(r'\s+', ' ', str(category).lower().replace('suspected', '')).strip() or 'other'
        items = []
        for value in (values if isinstance(values, list) else [values]):
            value = str(value).strip()
            if not value or '[Redacted' in value:
                continue
            items.append({'value': value[:_MATCH_MAX_CHARS], 'in_prompt': value.lower() in lowered})
            if len(items) >= _MATCHES_PER_CATEGORY:
                break
        if items:
            out[label] = items
    return out

