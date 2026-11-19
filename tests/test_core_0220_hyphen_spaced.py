"""Core 0.2.20 (ADR-155): a hyphenated surname written with a space beside the hyphen. Invented values only."""
import bps_redaction


def _redactor(**demo):
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': 'Marigold', 'MIDDLENAME': '', 'SURNAME': 'Quillfeather-Ashgrove',
        'NAME': 'Mrs Marigold Quillfeather-Ashgrove', 'PREFERREDNAME': '', 'DOB': '1950-07-03', **demo}}}}
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0220():
    assert tuple(int(p) for p in bps_redaction.__version__.split('.')) >= (0, 2, 20)


def test_spaced_hyphen_is_redacted_and_restored():
    r = _redactor()
    text = 'RE: Marigold Quillfeather- Ashgrove, and later Mrs QUILLFEATHER - ASHGROVE.'
    v = r.vault('k')
    out = r.prompt(text, 1001, v)
    for piece in ('Quillfeather', 'QUILLFEATHER', 'Ashgrove', 'ASHGROVE', 'Marigold'):
        assert piece not in out
    # Restored with its spacing; a name written in capitals comes back as stored-case, as before.
    assert r.deredact(out, v.get_reverse_map()).text.lower() == text.lower()


def test_one_part_alone_is_left():
    r = _redactor()
    text = 'Seen at the Ashgrove Road clinic.'
    assert r.prompt(text, 1001, r.vault('k')) == text
