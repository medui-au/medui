"""The PIT folder must already exist and be writable; MedUI never creates it (ADR-161).

Before, a UNC path, a typo or an unmounted share made os.makedirs create a local folder, the PIT
file was written there and logged as sent, and Best Practice never saw it."""
import os

import pytest
from flask import Flask

from app.utils import pit_utils


@pytest.mark.parametrize('path, says', [
    ('', 'No PIT folder is set'),
    ('\\\\SERVER\\BPS\\Incoming', 'Windows path'),
    ('//SERVER/BPS/Incoming', 'Windows path'),
    ('C:\\BPS\\Incoming', 'Windows path'),
    ('bps/incoming', 'full path'),
    ('/no/such/folder/for/medui', "doesn't exist"),
])
def test_folder_problem(path, says):
    assert says in pit_utils.folder_problem(path)


def test_a_writable_folder_is_fine(tmp_path):
    assert pit_utils.folder_problem(str(tmp_path)) is None


def test_a_read_only_folder_is_refused(tmp_path):
    ro = tmp_path / 'ro'
    ro.mkdir()
    ro.chmod(0o555)
    try:
        if os.access(ro, os.W_OK):
            pytest.skip('running as a user who can write anywhere')
        assert "can't write" in pit_utils.folder_problem(str(ro))
    finally:
        ro.chmod(0o755)


@pytest.fixture
def app(monkeypatch, tmp_path):
    store = {}
    monkeypatch.setattr(pit_utils.SystemSetting, 'get', staticmethod(lambda k, d=None: store.get(k, d)))
    app = Flask(__name__)
    app.config['PIT_EXPORT_ENABLED'] = True
    with app.app_context():
        yield store


def test_delivery_never_creates_the_folder(app, tmp_path):
    missing = tmp_path / 'not_mounted'
    app['pit_export_path'] = str(missing)
    assert pit_utils.pit_delivery(1, 'invented PIT content', 'Invented_Patient') is False
    assert not missing.exists()


def test_delivery_refuses_a_unc_path(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app['pit_export_path'] = '\\\\SERVER\\BPS\\Incoming'
    assert pit_utils.pit_delivery(1, 'invented PIT content', 'Invented_Patient') is False
    assert list(tmp_path.iterdir()) == []


def test_delivery_writes_into_an_existing_folder(app, tmp_path):
    app['pit_export_path'] = str(tmp_path)
    assert pit_utils.pit_delivery(1, 'invented PIT content', 'Invented_Patient') is True
    files = list(tmp_path.glob('Invented_Patient_COMMS_*.pit'))
    assert len(files) == 1 and files[0].read_text() == 'invented PIT content'
