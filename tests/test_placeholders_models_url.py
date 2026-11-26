"""Setup placeholders use example domains, and new OpenRouter/Groq providers start with their
models URL (upstream ADR-191). Names and addresses are invented.

The database test runs only when MEDUI_TEST_DATABASE_URL names a throwaway *_test database."""
import os
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_messaging_placeholders_use_example_domains():
    with open(os.path.join(ROOT, 'app/templates/setup/partials/tab_messaging.html'),
              encoding='utf-8') as fh:
        text = fh.read()
    for real in ('fastmail', 'Bayside', 'clinic.com.au', 'sms.provider.com', "'192.168."):
        assert real not in text, real


def test_suggested_models_urls():
    from app.services.ai_provider_service import suggested_models_endpoint, models_endpoint_hint
    assert suggested_models_endpoint('https://openrouter.ai/api/v1') == \
        'https://openrouter.ai/api/v1/endpoints/zdr'
    assert suggested_models_endpoint('https://api.groq.com/openai/v1') == \
        'https://api.groq.com/openai/v1/models'
    assert suggested_models_endpoint('http://ollama.example:11434/v1') is None
    assert models_endpoint_hint('http://ollama.example:11434/v1/') == \
        'http://ollama.example:11434/v1/models'


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
        db.session.add_all([lead] + [AIProviderPreset(
            provider_key=k, display_name=n, provider_type='openai_compatible', base_url_default=u,
            is_local_default=local, supports_model_fetching=True, sort_order=i)
            for i, (k, n, u, local) in enumerate((
                ('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1', False),
                ('groq', 'Groq', 'https://api.groq.com/openai/v1', False),
                ('ollama', 'Ollama', 'http://localhost:11434/v1', True)))])
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(lead.id)
            s['_fresh'] = True
        yield SimpleNamespace(app=app, db=db, client=client)
        db.session.remove()
        db.drop_all()


@needs_db
def test_new_providers_start_with_their_models_url(ctx):
    from app.services import ai_provider_service as svc
    assert svc.create_from_preset('openrouter', {}).models_endpoint == \
        'https://openrouter.ai/api/v1/endpoints/zdr'
    assert svc.create_from_preset('groq', {}).models_endpoint == \
        'https://api.groq.com/openai/v1/models'
    assert svc.create_from_preset('ollama', {}).models_endpoint is None
    ctx.db.session.commit()
    page = ctx.client.get('/setup/tab/providers').get_data(as_text=True)
    assert 'placeholder="http://localhost:11434/v1/models"' in page
