"""The public repository's issue forms: every form makes the reporter confirm there are no patient
details, blank issues are off, and security problems are sent to private reporting."""
import pathlib
import re

FORMS = pathlib.Path(__file__).resolve().parents[1] / '.github' / 'ISSUE_TEMPLATE'


def test_every_form_has_the_required_privacy_tick():
    forms = sorted(FORMS.glob('*.yml'))
    forms = [f for f in forms if f.name != 'config.yml']
    assert len(forms) >= 3
    for f in forms:
        text = f.read_text()
        assert re.search(r'id: privacy\n(.*\n){3,5}\s+- label: .*no patient details.*\n\s+required: true', text), f.name
        assert 'public' in text.lower(), f.name


def test_chooser_has_no_blank_issues_and_sends_security_privately():
    text = (FORMS / 'config.yml').read_text()
    assert 'blank_issues_enabled: false' in text
    assert '/security/advisories/new' in text
    assert '/discussions' in text
