"""The patient's own phone number with its groups in columns (core 0.2.17, ADR-152).

Column-aligned text spreads a number's groups with runs of spaces ('5550        1234'); the
any-spacing rule allowed up to three, so the whole number went to the cloud. Invented numbers.
"""
import bps_redaction


def _redactor():
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': 'Marigold', 'MIDDLENAME': '', 'SURNAME': 'Quillfeather',
        'NAME': 'Mrs Marigold Quillfeather', 'PREFERREDNAME': '',
        'PHONE_HOME': '55501234', 'PHONE_MOBILE': '0491570156'}}}}
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0217():
    assert tuple(int(p) for p in bps_redaction.__version__.split('.')) >= (0, 2, 17)
    assert bps_redaction.RULESET.startswith('medui-adr')


def test_column_spaced_numbers_are_redacted_and_restored():
    r = _redactor()
    text = 'H: 5550     1234    Mob 0491 570        156'
    v = r.vault('k')
    out = r.prompt(text, 1001, v)
    assert '5550' not in out and '1234' not in out and '570' not in out
    assert r.deredact(out, v.get_reverse_map()).text == text


def test_a_line_break_still_ends_the_number():
    r = _redactor()
    assert r.prompt('5550\n1234', 1001, r.vault('k')) == '5550\n1234'
