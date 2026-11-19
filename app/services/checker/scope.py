"""Scope check — layer 2 of the AI scope guardrails (ADR-089).

Looks at the request a user typed for plainly device-like asks: a dose, a
diagnosis, a second opinion, a prognosis, an interpretation of results. It
targets the *ask* ("what dose should I…", "should we start…"), never the nouns
on their own — records are full of "diagnosis", "treatment" and "dose", and
"list the doses" or "summarise the treatment plan" are ordinary work.

Run on the user's own words only, never on workflow templates, record data or
documents (see typed_text()). Also used to warn administrators who save a
prompt that asks for device-like output (Prompt Manager).

Findings are a pattern name and offsets; matched text is never stored.
Not part of AuditFilter's detector (scan.py etc.), which is kept in step with
AuditFilter; this module is MedUI's own.
"""
from __future__ import annotations

import difflib
import re

VERSION = 'scope-v2'

_F = re.IGNORECASE
_SUBJ = r'(?:I|we|you|she|he|they|the\s+patient|(?:my|our)\s+patient)'
_ACT = (r'(?:start|stop|cease|increase|decrease|reduce|double|halve|titrate|prescribe|change|'
        r'switch|add|give|use|treat|refer|order|admit)')

PATTERNS: dict[str, re.Pattern] = {
    # "what dose should I…", "what medication would you…", "which antibiotic to…"
    'dose_or_treatment_ask': re.compile(
        r'\b(?:what|which)\s+(?:dose|dosage|dosing|medication|medicine|treatment|drug|antibiotic)s?\s+'
        r'(?:should|would|could|do\s+you|to|is\s+best|is\s+right)\b', _F),
    # "should I increase…", "should we start…"
    'should_act': re.compile(r'\bshould\s+' + _SUBJ + r'\s+(?:be\s+)?' + _ACT + r'\b', _F),
    # "what is the likely diagnosis", "what could this be"
    'diagnosis_ask': re.compile(
        r'\bwhat\s+is\s+(?:the|her|his|their|my|your)\s+(?:most\s+)?(?:likely\s+|probable\s+)?diagnosis\b'
        r'|\bwhat\s+(?:could|might)\s+(?:this|it|these\s+symptoms)\s+be\b'
        r'|\b(?:can|could|please)\s+you\s+diagnose\b|\bgive\s+(?:me\s+)?a\s+diagnosis\b', _F),
    # An ask for one — not "Differential :" in a blood count or "remains in the differential" in a letter
    'differential': re.compile(
        r'\b(?:give|list|suggest|provide|generate|what(?:\s+is|\s+are|\'s)?(?:\s+the)?|for)\s+'
        r'(?:me\s+)?(?:a\s+|the\s+|some\s+|your\s+)?(?:refined\s+|full\s+|broad\s+)?'
        r'(?:differentials?|ddx)\b(?!\s*:)', _F),
    'second_opinion': re.compile(r'\bsecond\s+opinion\b', _F),
    # "is this normal / serious / cancer"
    'is_this_serious': re.compile(
        r'\bis\s+(?:this|it|that)\s+(?:likely\s+)?(?:normal|abnormal|serious|concerning|worrying|'
        r'dangerous|cancer|malignant|benign)\b', _F),
    'recommend_ask': re.compile(
        r'\bwhat\s+(?:would|do|should)\s+you\s+(?:recommend|suggest|advise)\b'
        r'|\b(?:recommend|suggest|advise)\s+(?:a\s+|the\s+)?(?:treatment|management|dose|dosage|'
        r'medication|plan|next\s+step)', _F),
    # An ask, not "conveys poor prognosis" or a guideline's "if life expectancy is greater than…"
    'prognosis_ask': re.compile(
        r'\bwhat\s+(?:is|\'s)\s+(?:the|her|his|their|my)\s+(?:likely\s+)?(?:prognosis|life\s+expectancy)\b'
        r'|\bprognosis\s*\?'
        r'|\bhow\s+long\s+(?:has|have|does|do)\s+(?:he|she|they|the\s+patient)\s+(?:got|have|left|to\s+live)\b', _F),
    # The user asking — not a lab's "further interpretation of these results is required"
    # or "please interpret the results in the context of clinical findings"
    'interpret_results': re.compile(
        r'\b(?:please|can\s+you|could\s+you|help\s+(?:me\s+)?)\s+interpret\s+'
        r'(?:this|these|the|her|his|their|my)\s+'
        r'(?:results?|bloods?|tests?|ecg|x-?rays?|scans?|pathology|imaging)\b(?!\s+in\s+the\s+context)', _F),
}


# Prompt Manager only: administrators write instructions ("estimate the patient's
# life expectancy"), not questions, so saved prompts are also checked for these.
# A nudge on save, never applied to what users type.
PROMPT_PATTERNS: dict[str, re.Pattern] = {
    'prognosis_ask': re.compile(
        r'\b(?:estimate|predict|calculate|assess)\s+(?:the\s+|their\s+|this\s+patient\'s\s+|expected\s+)*'
        r'(?:life\s+expectancy|survival|prognosis|chance\s+of\s+surviving)\b', _F),
    'diagnosis_ask': re.compile(
        r'\b(?:diagnostic\s+possibilities|possible\s+diagnos[ie]s|missed\s+diagnos[ie]s|'
        r'undiagnosed\s+conditions?|differential\s+diagnos[ie]s)\b', _F),
    'second_opinion': re.compile(
        r'\bsecond\s+(?:opinion|set\s+of\s+eyes)\b'
        r'|\bacting\s+as\s+(?:an?\s+)?(?:expert\s+)?(?:physician|doctor|specialist|clinician|consultant)\b', _F),
    'recommend_ask': re.compile(
        r'\b(?:recommend|suggest|propose)\s+(?:any\s+|further\s+|additional\s+|appropriate\s+)?'
        r'(?:treatments?|management|medications?|investigations?|changes\s+to\s+(?:treatment|medication|management))\b'
        r'|\bmanagement\s+gaps?\b', _F),
}


LABELS = {
    'dose_or_treatment_ask': 'asks which dose or treatment to use',
    'should_act':            'asks whether to start, stop or change something',
    'diagnosis_ask':         'asks for a diagnosis',
    'differential':          'asks for a differential diagnosis',
    'second_opinion':        'asks for a second opinion',
    'is_this_serious':       'asks whether something is normal or serious',
    'recommend_ask':         'asks for a recommendation',
    'prognosis_ask':         'asks for a prognosis',
    'interpret_results':     'asks for results to be interpreted',
}


def scan(text: str) -> list[dict]:
    """[{'pattern': name, 'start': i, 'end': j}, ...] in text order."""
    if not text:
        return []
    hits = []
    for name, rx in PATTERNS.items():
        for m in rx.finditer(text):
            hits.append({'pattern': name, 'start': m.start(), 'end': m.end()})
    return sorted(hits, key=lambda h: h['start'])


def scan_prompt(text: str) -> list[dict]:
    """Prompt Manager's check: the request patterns plus the instruction ones."""
    hits = scan(text)
    for name, rx in PROMPT_PATTERNS.items():
        for m in rx.finditer(text or ''):
            hits.append({'pattern': name, 'start': m.start(), 'end': m.end()})
    return sorted(hits, key=lambda h: h['start'])


def typed_text(user_input: str, template: str | None, is_edited_template: bool) -> str:
    """The part of user_input the user wrote themselves.

    A question typed into the box is all theirs. When the box held the
    workflow's template (possibly edited), only lines the user added or changed
    count — the template's own wording is the administrator's, checked in
    Prompt Manager instead.
    """
    if not user_input:
        return ''
    if not (is_edited_template and template):
        return user_input
    tpl_lines = template.splitlines()
    out = []
    for op in difflib.ndiff(tpl_lines, user_input.splitlines()):
        if op.startswith('+ '):
            out.append(op[2:])
    return '\n'.join(out)


def record(text: str, mode: str) -> dict:
    """The verdict stored on a run: version, mode, hits (no text)."""
    hits = scan(text)
    return {'version': VERSION, 'mode': mode, 'checked_chars': len(text),
            'hits': hits, 'flagged': bool(hits)}
