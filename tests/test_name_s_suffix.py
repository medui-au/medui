"""A patient's name with an s straight after it is redacted and checked (core 0.2.11, ADR-141; 0.2.12-0.2.13 streets).

"Marigolds' daughter" and "Marigolds daughter" went to the model with the name in it,
and the pre-send check did not see it. Invented names only.
"""
import bps_redaction
import bps_redaction.checker.patterns


def _fixture_redactor():
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    # The core's own invented practice, shipped in its tests; rebuilt here so the
    # test does not depend on the core's checkout.
    data = {
        'patients': {'1001': {'demographics': {
            'FIRSTNAME': 'Marigold', 'MIDDLENAME': '', 'SURNAME': 'Quillfeather',
            'NAME': 'Mrs Marigold Quillfeather', 'PREFERREDNAME': 'Goldie'}}},
    }
    return Redactor(FixtureSource(data), lists=StaticLists({}))


def test_the_pinned_core_is_0213():
    assert bps_redaction.__version__ >= '0.2.13' and bps_redaction.RULESET.startswith('medui-adr')


def test_the_name_goes_and_the_s_stays():
    r = _fixture_redactor()
    for text in ("Marigolds' daughter rang.", 'Marigolds daughter rang.', "Quillfeathers' address",
                 "Goldies’ bloods"):
        out = r.prompt(text, 1001, r.vault('k'))
        assert 'marigold' not in out.lower() and 'quillfeather' not in out.lower()
        assert 'goldie' not in out.lower() and '[Redacted Patient: PT-' in out


def test_the_check_finds_it_when_left_in():
    r = _fixture_redactor()
    hits = r.verdict("Marigolds' daughter rang.", 1001)['hits']
    assert any(h['tier'] == 0 for h in hits)



def test_a_glued_surname_pauses():
    from bps_redaction.checker.scan import is_blocking
    r = _fixture_redactor()
    assert int(bps_redaction.checker.patterns.DETECTOR_VERSION.split('-v')[1]) >= 29
    assert is_blocking(r.verdict('Seen xQuillfeather today', 1001))


def test_a_street_named_for_the_surname_stays_whole():
    # 0.2.12 (ADR-142): 0.2.11 left "12 [token]s Road". Invented street.
    from bps_redaction import Redactor, StaticLists
    from bps_redaction.adapters.fixture import FixtureSource
    data = {'patients': {'1001': {'demographics': {
        'FIRSTNAME': 'Marigold', 'SURNAME': 'Quillfeather', 'NAME': 'Mrs Marigold Quillfeather',
        'ADDRESS1_PART': '12 Quillfeathers Road', 'ADDRESS': '12 Quillfeathers Road'}}}}
    r = Redactor(FixtureSource(data), lists=StaticLists({}))
    for text in ('12  Quillfeathers Road', 'Quillfeathers Road'):
        out = r.prompt(text, 1001, r.vault('k'))
        assert 'road' not in out.lower() and 'quillfeather' not in out.lower() and '12' not in out


def test_a_road_with_words_before_the_type_stays_whole():
    # 0.2.13 (ADR-143): 0.2.12 left "123 [token]S GULLY CREEK RD". Invented road.
    r = _fixture_redactor()
    for text in ('123 QUILLFEATHERS GULLY CREEK RD', 'Quillfeathers Gully Creek Road'):
        out = r.prompt(text, 1001, r.vault('k'))
        assert ']s ' not in out.lower()
    out = r.prompt("Marigolds wife at St Vincent's", 1001, r.vault('k'))
    assert 'marigold' not in out.lower()
