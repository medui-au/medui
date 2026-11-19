"""Where a login lands: Setup → Database for an administrator while Best Practice isn't
configured (ADR-140), and ?next= only ever to a page of this site.

Users and passwords here are invented.
"""
import os
from types import SimpleNamespace

import pytest
from flask import Flask

from app.services.auth_service import AuthService


# ── ?next= is followed only to this site ──────────────────────────────────────

@pytest.mark.parametrize('value', ['/', '/patients?q=1', '/setup/?tab=database'])
def test_safe_next_keeps_own_pages(value):
    assert AuthService.safe_next(value) == value


@pytest.mark.parametrize('value', [
    None, '', 'https://elsewhere.example/', '//elsewhere.example/x', '/\\elsewhere.example',
    'javascript:alert(1)', 'patients', '/x\nSet-Cookie: a=b',
])
def test_safe_next_refuses_other_sites(value):
    assert AuthService.safe_next(value) is None


# ── who is sent to Setup → Database ───────────────────────────────────────────

def _app(bpsdb_uri):
    app = Flask(__name__)
    app.config['BPSDB_URI'] = bpsdb_uri
    return app


ADMIN = SimpleNamespace(is_admin=True)
NURSE = SimpleNamespace(is_admin=False)


def test_admin_without_bp_goes_to_setup():
    with _app(None).app_context():
        assert AuthService.needs_bp_setup(ADMIN, None, '/setup/')
        assert AuthService.needs_bp_setup(ADMIN, '/', '/setup/')          # the bare site address


def test_next_into_setup_is_kept():
    with _app(None).app_context():
        assert not AuthService.needs_bp_setup(ADMIN, '/setup/?tab=providers', '/setup/')


def test_not_for_other_users():
    with _app(None).app_context():
        assert not AuthService.needs_bp_setup(NURSE, None, '/setup/')


def test_not_when_bp_is_configured():
    with _app('DRIVER={x};SERVER={sql.example};').app_context():
        assert not AuthService.needs_bp_setup(ADMIN, None, '/setup/')


# ── the login itself (needs the throwaway test database) ─────────────────────

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
    app.config.update(TESTING=True, SERVER_NAME='test.local', WTF_CSRF_ENABLED=False,
                      BPSDB_URI=None)
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        admin = User(username='localadmin', display_name='Local Admin', security_level=9,
                     is_local_admin=True, password_hash='x')
        admin.set_password('invented-pass-1')
        nurse = User(username='nurse_b', display_name='Nurse B', security_level=3, password_hash='x')
        db.session.add_all([admin, nurse])
        db.session.commit()
        yield SimpleNamespace(app=app, db=db, admin=admin, nurse=nurse)
        db.session.remove()
        db.drop_all()


def _login(ctx, query=''):
    from flask import g
    g.pop('_login_user', None)
    client = ctx.app.test_client()
    r = client.post('/auth/login' + query,
                    data={'username': 'localadmin', 'password': 'invented-pass-1'})
    return client, r


@needs_db
def test_admin_login_without_bp_lands_on_database_tab(ctx):
    client, r = _login(ctx, '?next=/')
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/setup/?tab=database')
    page = client.get('/setup/?tab=database')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'setup-tab active' in html and 'Not configured' in html
    assert "database connection isn&#39;t set" in html or "database connection isn't set" in html


@needs_db
def test_admin_login_with_next_into_setup_keeps_it(ctx):
    _, r = _login(ctx, '?next=/setup/')
    assert r.headers['Location'].endswith('/setup/')


@needs_db
def test_admin_login_with_bp_goes_home(ctx):
    ctx.app.config['BPSDB_URI'] = 'DRIVER={x};SERVER={sql.example};'
    _, r = _login(ctx)
    assert r.headers['Location'] == '/'


@needs_db
def test_off_site_next_is_ignored(ctx):
    ctx.app.config['BPSDB_URI'] = 'DRIVER={x};SERVER={sql.example};'
    _, r = _login(ctx, '?next=https://elsewhere.example/')
    assert r.headers['Location'] == '/'


@needs_db
def test_non_admin_login_without_bp_goes_home(ctx, monkeypatch):
    monkeypatch.setattr(AuthService, 'authenticate', staticmethod(lambda u, p: ctx.nurse))
    from flask import g
    g.pop('_login_user', None)
    r = ctx.app.test_client().post('/auth/login', data={'username': '7', 'password': 'x'})
    assert r.headers['Location'] == '/'


# ── medui_os: when Best Practice counts as configured ────────────────────────

@pytest.mark.parametrize('blank', ['BPSDB_HOST', 'BPSDB_USER', 'BPSDB_PASSWORD'])
def test_bp_not_configured_when_a_setting_is_blank(monkeypatch, blank):
    from app import config
    monkeypatch.delenv('BPSDB_URI', raising=False)
    for name, value in (('BPSDB_HOST', 'sql.example\\BPSINSTANCE'), ('BPSDB_USER', 'invented_ro'),
                        ('BPSDB_PASSWORD', 'invented-pass-2')):
        monkeypatch.setenv(name, value)
    assert 'SERVER={sql.example\\BPSINSTANCE}' in config._build_bpsdb_connection_string()
    monkeypatch.setenv(blank, ' ' if blank != 'BPSDB_PASSWORD' else '')
    assert config._build_bpsdb_connection_string() is None


def test_bp_uri_given_whole_still_counts(monkeypatch):
    from app import config
    monkeypatch.setenv('BPSDB_URI', 'DRIVER={x};SERVER={sql.example};')
    monkeypatch.delenv('BPSDB_USER', raising=False)
    assert config._build_bpsdb_connection_string() == 'DRIVER={x};SERVER={sql.example};'
