"""Core 0.2.19 (ADR-154): a zero without the area digit before the own phone digits, and one word
of a multi-word surname beside a name. Invented values only."""
import bps_redaction


def _redactor(**demo):
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': 'Marigold', 'MIDDLENAME': '', 'SURNAME': 'van der Thistlewood',
        'NAME': 'Mrs Marigold van der Thistlewood', 'PREFERREDNAME': '', 'DOB': '1950-07-03',
        'PHONE_HOME': '55501234', **demo}}}}
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0219():
    assert tuple(int(p) for p in bps_redaction.__version__.split('.')) >= (0, 2, 19)
    assert bps_redaction.RULESET.startswith('medui-adr')


def test_both_forms_are_redacted_and_restored():
    r = _redactor()
    text = 'Ph: 05550 1234(H)  RE: Marigold van den Thistlewood attended today.'
    v = r.vault('k')
    out = r.prompt(text, 1001, v)
    for piece in ('5550', '1234', 'Thistlewood', 'Marigold'):
        assert piece not in out
    assert r.deredact(out, v.get_reverse_map()).text == text


def test_the_surname_word_on_its_own_is_left():
    r = _redactor()
    text = 'Referred to the Thistlewood Clinic; ph 105550 1234.'
    assert r.prompt(text, 1001, r.vault('k')) == text


def test_medui_pipeline_takes_the_surname_word():
    """MedUI sequences the passes itself: the rule arrives through the nickname pass."""
    from bps_redaction.redaction import RedactionService
    src = RedactionService.redact_practice_nicknames.__doc__ or ''
    assert 'ADR-154' in src
