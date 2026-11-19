"""A literal \\n, \\t or \\r counts as a word boundary in every redaction pass (ADR-116)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text()


def test_each_pass_masks_and_restores_escapes():
    da = _src('app/services/pipeline/nodes/data_assembly.py')
    assert 'raw_data = mask(raw_data)' in da and da.count("{'blocks': unmask(redacted)}") == 2
    inf = _src('app/services/pipeline/nodes/inference.py')
    assert 'drop_record_numbers(mask(original))' in inf and 'unmask(RedactionService.redact_common_first_names' in inf
    eng = _src('app/services/pipeline/engine.py')
    # Masked at the start of each input field, restored once every pass has run (ADR-133 added one).
    assert 'value = mask(value)' in eng and 'context.input[key] = unmask(value)' in eng


def test_the_core_treats_an_escape_as_a_boundary():
    from bps_redaction.escapes import mask, unmask
    text = 'Seen.\\nGoldie rang.'
    masked = mask(text)
    assert len(masked) == len(text) and 'nGoldie' not in masked and unmask(masked) == text
