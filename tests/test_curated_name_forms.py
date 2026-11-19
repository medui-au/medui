"""Common short forms are redacted without a practice list entry (core 0.2.14, ADR-148).

A patient called Mick, whose first name is Michael, kept "Mick" in the text when the
practice had no preferred-name entries or listed form for it. Invented names only.
"""
import bps_redaction


def _redactor(first):
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': first, 'MIDDLENAME': '', 'SURNAME': 'Quillfeather',
        'NAME': f'Mr {first} Quillfeather', 'PREFERREDNAME': ''}}}}
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0214():
    assert bps_redaction.__version__ >= '0.2.14' and bps_redaction.RULESET.startswith('medui-adr')


def test_a_common_short_form_is_redacted_with_no_list_entry():
    r = _redactor('Michael')
    v = r.vault('k')
    out = r.prompt('Mick rang about his bloods.', 1001, v)
    assert 'Mick' not in out and '[Redacted Name:' in out
    assert r.deredact(out, v.get_reverse_map()).text == 'Mick rang about his bloods.'


def test_an_everyday_word_is_not_on_the_list():
    r = _redactor('William')
    assert 'Will review' in r.prompt('Will review in two weeks.', 1001, r.vault('k'))
