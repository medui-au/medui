"""Glucose 14768-6 (usually fasting) goes wherever fasting glucose 14771-0 does (0.53.4)."""
from pathlib import Path

import pytest

SQL = Path(__file__).resolve().parent.parent / 'app' / 'sql'
QUERIES = ['patient_json_pathology_all', 'patient_json_pathology_all_noid',
           'patient_json_pathology_compact', 'patient_json_pathology_compact_noid',
           'patient_pathology_trends']


@pytest.mark.parametrize('name', QUERIES)
def test_14768_6_beside_14771_0(name):
    text = (SQL / f'{name}.sql').read_text()
    assert text.count("'14771-0'") > 0
    assert text.count("'14768-6'") == text.count("'14771-0'")


def test_random_glucose_left_out():
    for name in QUERIES:
        assert "'14749-6'" not in (SQL / f'{name}.sql').read_text()
