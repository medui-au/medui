"""MedUI sweeps its own users' first names (core 0.2.9, ADR-134). Source check, like
test_practice_name_pass, plus the core's option on invented rows."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_medui_builds_its_redactor_with_the_option():
    src = (ROOT / 'app/services/redaction_core.py').read_text()
    assert 'practice_first_names=True' in src


def test_the_pinned_core_has_the_option():
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.redaction import RedactionService

    class Source:
        def query(self, name, params=None):
            return {'practice_staff': [{'user_id': 7, 'first_name': 'Zephyrine', 'surname': 'Oakhurst',
                                        'role': 'Receptionist'}]}.get(name, [])

    r = Redactor(Source(), lists=StaticLists({}), practice_first_names=True)
    with r.context():
        out = RedactionService.redact_common_first_names('Thanks, Zephyrine.', r.vault('k'))
    assert 'Zephyrine' not in out and '[Redacted Name: NM-' in out


def test_the_pinned_core_takes_a_four_letter_practice_name_in_lower_case():
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.redaction import RedactionService

    class Source:
        def query(self, name, params=None):
            return {'practice_doctors': [{'user_id': 3, 'first_name': 'Quen', 'surname': 'Harrowgate'}]}.get(name, [])

    r = Redactor(Source(), lists=StaticLists({}), practice_first_names=True)
    with r.context():
        out = RedactionService.redact_common_first_names('how is quen going', r.vault('k'))
    assert 'quen' not in out and '[Redacted Name: NM-' in out
