"""The practice's own name (core ADR-121) runs in each of MedUI's three sequences, before the
patient's identifiers, as in the core's own profiles. Source checks, like test_escape_boundaries."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text()


def _before(text, first, then):
    assert first in text and then in text
    assert text.index(first) < text.index(then), f'{first!r} should come before {then!r}'


def test_record_pass_takes_the_practice_name_before_the_patient():
    da = _src('app/services/pipeline/nodes/data_assembly.py')
    _before(da, 'redact_identifier_labels(redacted)', 'redact_practice_name(redacted, self._vault)')
    _before(da, 'redact_practice_name(redacted, self._vault)', 'redacted = RedactionService.redact(\n')


def test_prompt_pass_takes_the_practice_name_before_the_patient():
    inf = _src('app/services/pipeline/nodes/inference.py')
    _before(inf, 'redact_identifier_labels(redacted)', 'redact_practice_name(redacted, vault)')
    _before(inf, 'redact_practice_name(redacted, vault)', 'RedactionService.redact(redacted, identifiers')


def test_input_pass_takes_the_practice_name_before_the_patient():
    eng = _src('app/services/pipeline/engine.py')
    _before(eng, 'value = mask(value)', 'redact_practice_name(value, vault)')
    _before(eng, 'redact_practice_name(value, vault)', 'RedactionService.redact(value, identifiers')


def test_the_pinned_core_has_the_pass():
    from bps_redaction.redaction import RedactionService
    assert hasattr(RedactionService, 'redact_practice_name')
    req = _src('requirements.txt')
    wheels = [p.name for p in (ROOT / 'vendor' / 'wheels').glob('bps_redaction-*.whl')]
    pin = re.search(r'^bps-redaction==(\S+)$', req, re.M).group(1)
    assert wheels == [f'bps_redaction-{pin}-py3-none-any.whl']
