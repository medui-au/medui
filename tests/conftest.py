"""Test set-up shared by the GPCCMP tests: the open edition ships no practice protocol, so the tests
load an example one (tests/example_protocol.py) through the seed command's data hook."""
import pytest


@pytest.fixture(autouse=True)
def _example_protocol(monkeypatch):
    import example_protocol
    from app.commands import protocol
    monkeypatch.setattr(protocol, 'practice_data', lambda: example_protocol)
