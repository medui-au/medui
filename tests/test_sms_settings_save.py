"""Setup → Messaging → Save SMS Settings stores what was entered (ADR-159).

The save route imported sms_service._set_secret, which didn't exist, so every save failed with
an ImportError before anything was stored."""
from app.services import sms_service


def test_the_save_routes_helper_exists():
    from app.services.sms_service import _set_secret  # noqa: F401  (the route's own import)


def test_password_is_stored_encrypted_and_read_back(monkeypatch):
    store = {}
    monkeypatch.setattr(sms_service.SystemSetting, 'set', staticmethod(lambda k, v: store.__setitem__(k, v)))
    monkeypatch.setattr(sms_service.SystemSetting, 'get', staticmethod(lambda k, d=None: store.get(k, d)))
    monkeypatch.setattr('app.utils.crypto.encrypt_secret', lambda p: 'enc:' + p)
    monkeypatch.setattr('app.utils.crypto.decrypt_secret', lambda c: c[4:])
    sms_service._set_secret('sms.smtp_password', 'invented-password')
    assert store['sms.smtp_password'] == 'enc:invented-password'
    assert sms_service._get_secret('sms.smtp_password') == 'invented-password'


# ── the save itself, through the Setup page's route (needs the throwaway test database) ──

import os
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')


@pytest.fixture
def ctx(monkeypatch):
    from app import create_app
    from app import config as app_config
    from app.extensions import db
    from app.models.user import User
    for name in dir(app_config):
        cls = getattr(app_config, name)
        if isinstance(cls, type) and hasattr(cls, 'SQLALCHEMY_DATABASE_URI'):
            monkeypatch.setattr(cls, 'SQLALCHEMY_DATABASE_URI', DB_URL)
    app = create_app('dev')
    app.config.update(TESTING=True, SERVER_NAME='test.local', WTF_CSRF_ENABLED=False)
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        lead = User(username='lead', display_name='Lead', security_level=9, password_hash='x')
        db.session.add(lead)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(lead.id)
            s['_fresh'] = True
        yield SimpleNamespace(app=app, db=db, client=client)
        db.session.remove()
        db.drop_all()


@needs_db
def test_save_sms_settings_stores_them(ctx):
    from flask import g
    g.pop('_login_user', None)
    r = ctx.client.post('/setup/messaging/save-sms', data={
        'sms.smtp_host': 'sms-gateway.example', 'sms.smtp_port': '2525',
        'sms.sender_address': 'sms@clinic.example',
        'sms.recipient_template': '{number}@sms.provider.example',
        'sms.requires_auth': 'true', 'sms.smtp_username': 'invented-user',
        'sms.smtp_password': 'invented-password', 'sms.use_tls': 'true'})
    assert r.status_code == 200 and 'SMS settings saved.' in r.get_data(as_text=True)
    from app.models.system_setting import SystemSetting
    assert SystemSetting.get('sms.smtp_host') == 'sms-gateway.example'
    assert SystemSetting.get('sms.smtp_port') == 2525
    assert SystemSetting.get('sms.recipient_template') == '{number}@sms.provider.example'
    assert SystemSetting.get('sms.requires_auth') is True and SystemSetting.get('sms.use_tls') is True
    assert SystemSetting.get('sms.smtp_password') != 'invented-password'
    assert sms_service._get_config()['smtp_password'] == 'invented-password'
    assert sms_service.is_configured() and sms_service.sms_password_is_set()
