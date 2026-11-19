"""The recording clinician's own first name in a scribe transcript, any case (ADR-133).
Invented names only. Source checks, like test_practice_name_pass."""
from pathlib import Path

from app.services.practitioner_names import first_names_for

ROOT = Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text()


def test_names_from_the_preferred_name_and_the_bp_row():
    rows = [{'user_id': 7, 'first_name': 'Josephine', 'surname': 'Rivers'},
            {'user_id': '7p', 'first_name': 'Jo', 'surname': 'Rivers'},
            {'user_id': 8, 'first_name': 'Alex', 'surname': 'Brook'}]
    assert first_names_for('Dr Jo Rivers', 7, rows) == ['Jo', 'Josephine']
    assert first_names_for(None, 7, rows) == ['Josephine']
    assert first_names_for('Sam', None, rows) == ['Sam']
    assert first_names_for('Dr Jo Anne Rivers', 9, rows) == ['Jo Anne']
    assert first_names_for(None, None, []) == []


def test_bp_initials_are_passed_and_left_to_the_core():
    # A BP first name of initials ("H. A.") gives nothing to match: the core skips one-letter words.
    from bps_redaction.redaction import RedactionService
    assert first_names_for('Sam Pellow', 5, [{'user_id': 5, 'first_name': 'H. A.'}]) == ['Sam', 'H. A.']
    assert RedactionService.redact_clinician_first_names('h a here', ['H. A.'], None) == 'h a here'


def test_the_core_takes_the_name_in_lower_case():
    from bps_redaction.redaction import RedactionService
    from bps_redaction.vault import TokenVault
    out = RedactionService.redact_clinician_first_names('oh hi sam how are you', ['Sam'], TokenVault('t'))
    assert out.startswith('oh hi [Redacted Name: NM-') and 'sam' not in out


def test_only_the_scribe_route_marks_a_transcript():
    voice = _src('app/blueprints/voice/routes.py')
    assert 'transcript_by=current_user.id' in voice
    hits = [p for p in (ROOT / 'app').rglob('*.py') if 'transcript_by=' in p.read_text()]
    assert {p.relative_to(ROOT).as_posix() for p in hits} == {
        'app/blueprints/voice/routes.py', 'app/services/pipeline/engine.py'}


def test_the_input_pass_takes_the_name_last():
    eng = _src('app/services/pipeline/engine.py')
    assert eng.index('HCPRedactionService.redact_hcp(\n            value') < \
        eng.index('redact_clinician_first_names(value, clinician_names, vault)') < \
        eng.index('context.input[key] = unmask(value)')
    assert "context.metadata.get('transcript_by')" in eng
