"""Core 0.2.18 (ADR-153): the area digit without its zero, the DOB with day and month swapped,
and the patient's own Medicare number in any grouping or cut short. Invented values only."""
import bps_redaction


def _redactor():
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': 'Marigold', 'MIDDLENAME': '', 'SURNAME': 'Quillfeather',
        'NAME': 'Mrs Marigold Quillfeather', 'PREFERREDNAME': '', 'DOB': '1950-07-03',
        'PHONE_HOME': '55501234', 'MEDICARENO_CARD': '2953701561'}}}}
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0218():
    assert tuple(int(p) for p in bps_redaction.__version__.split('.')) >= (0, 2, 18)
    assert bps_redaction.RULESET.startswith('medui-adr')


def test_the_three_forms_are_redacted_and_restored():
    r = _redactor()
    text = 'Ph: 75550 1234(H)  Birthdate:\t07/03/1950  Medicare No.: 2953 7015 61  ref 2953701;'
    v = r.vault('k')
    out = r.prompt(text, 1001, v)
    for piece in ('5550', '1950', '2953', '7015'):
        assert piece not in out
    assert r.deredact(out, v.get_reverse_map()).text == text


def test_other_numbers_and_dates_are_left():
    r = _redactor()
    text = 'seen 07/04/1950, ref 2953702, ph 175550 1234'
    assert r.prompt(text, 1001, r.vault('k')) == text
