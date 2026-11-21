"""Setup → AI Providers: a second server of the same kind can be added from its preset, and a
provider that can't be added says why on the page (ADR-163). Names and addresses are invented.

Runs only when MEDUI_TEST_DATABASE_URL names a throwaway *_test database."""
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
    from app.models.ai_provider import AIProviderPreset
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
        db.session.add_all([lead, AIProviderPreset(
            provider_key='ollama', display_name='Ollama', provider_type='openai_compatible',
            base_url_default='http://localhost:11434/v1', is_local_default=True,
            supports_model_fetching=True, sort_order=1)])
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(lead.id)
            s['_fresh'] = True
        yield SimpleNamespace(app=app, db=db, client=client)
        db.session.remove()
        db.drop_all()


def _post(ctx, url, data):
    from flask import g
    g.pop('_login_user', None)
    r = ctx.client.post(url, data=data)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _keys():
    from app.models.ai_provider import AIProviderConfig
    return sorted(p.provider_key for p in AIProviderConfig.query.all())


@needs_db
def test_a_second_ollama_from_the_preset(ctx):
    _post(ctx, '/setup/providers/add-preset', {'preset_key': 'ollama', 'is_local': '1'})
    html = _post(ctx, '/setup/providers/add-preset', {
        'preset_key': 'ollama', 'name': 'Ollama GPU server', 'is_local': '1',
        'base_url': 'http://gpu-server.example:11434/v1'})
    assert 'role="alert"' not in html
    assert _keys() == ['ollama', 'ollama_2']
    _post(ctx, '/setup/providers/add-preset', {'preset_key': 'ollama', 'name': 'Ollama third', 'is_local': '1'})
    assert _keys() == ['ollama', 'ollama_2', 'ollama_3']


@needs_db
def test_the_same_name_twice_says_so(ctx):
    _post(ctx, '/setup/providers/add-preset', {'preset_key': 'ollama', 'is_local': '1'})
    html = _post(ctx, '/setup/providers/add-preset', {'preset_key': 'ollama', 'is_local': '1'})
    assert 'role="alert"' in html and 'A provider called &#34;Ollama&#34; already exists' in html
    assert _keys() == ['ollama']


@needs_db
def test_a_custom_key_already_used_says_so(ctx):
    _post(ctx, '/setup/providers/add-preset', {'preset_key': 'ollama', 'is_local': '1'})
    html = _post(ctx, '/setup/providers/add-custom', {
        'name': 'Another server', 'provider_key': 'ollama', 'base_url': 'http://other.example:11434/v1'})
    assert 'role="alert"' in html and 'such as ollama_2' in html
    assert _keys() == ['ollama']


@needs_db
def test_no_preset_chosen_says_so(ctx):
    html = _post(ctx, '/setup/providers/add-preset', {'preset_key': ''})
    assert 'Choose a preset first.' in html and _keys() == []
