"""The in-app guide (Setup → Administrator setup guide): every page it shows, and every link
in them, stays inside the app (medui_os 0.50.2)."""
import re
from pathlib import Path

import pytest
from flask import Flask

from app.services import guide_docs

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app():
    app = Flask(__name__, root_path=str(ROOT / 'app'))
    app.add_url_rule('/setup/guide/<path:name>', endpoint='setup.guide', view_func=lambda name: '')
    with app.test_request_context('/'):
        yield app


def _pages():
    names = [str(p.relative_to(ROOT / 'docs'))[:-3] for p in (ROOT / 'docs').rglob('*.md')]
    return sorted(names) + [guide_docs.guide_name(t) for t in guide_docs.TOP_LEVEL]


@pytest.mark.parametrize('name', ['../wsgi', 'repo/CLAUDE', 'repo/../README', '/etc/passwd',
                                  'install/../../README', 'install\\README', '', 'repo/app/x'])
def test_only_documentation_is_served(app, name):
    assert guide_docs.render(name) is None


def test_every_top_level_page_is_in_the_image():
    dockerfile = (ROOT / 'Dockerfile').read_text()
    ignore = (ROOT / '.dockerignore').read_text().split()
    for rel in guide_docs.TOP_LEVEL:
        assert rel in dockerfile and f'!{rel}' in ignore, rel


def test_every_link_in_every_page_works(app):
    """A link to another page opens it, at a heading it has; nothing is left pointing at a .md
    file the browser can't open."""
    rendered = {}
    for name in _pages():
        page = guide_docs.render(name)
        assert page is not None, name
        rendered[name] = str(page[1])
    for name, html in rendered.items():
        for href in re.findall(r'href="([^"]*)"', html):
            if href.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            assert href.startswith('/setup/guide/'), (name, href)
            target, _, anchor = href[len('/setup/guide/'):].partition('#')
            assert target in rendered, (name, href)
            if anchor:
                assert f'id="{anchor}"' in rendered[target], (name, href)


def test_a_link_to_a_script_becomes_its_file_name(app):
    html = str(guide_docs.render('redaction-lists')[1])
    assert 'docs/identifier_labels_seed.csv</code> in the MedUI folder' in html
    assert 'href="identifier_labels_seed.csv"' not in html


def test_install_readme_link_from_the_setup_guide(app):
    html = str(guide_docs.render('setup-guide')[1])
    assert 'href="/setup/guide/install/README"' in html
    assert guide_docs.render('install/README')[0]


# ── the AI-use policy's Appendix A (needs the throwaway test database) ───────

import os
from types import SimpleNamespace

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')


@pytest.fixture
def db_app(monkeypatch):
    from app import create_app
    from app import config as app_config
    from app.extensions import db
    for name in dir(app_config):
        cls = getattr(app_config, name)
        if isinstance(cls, type) and hasattr(cls, 'SQLALCHEMY_DATABASE_URI'):
            monkeypatch.setattr(cls, 'SQLALCHEMY_DATABASE_URI', DB_URL)
    app = create_app('dev')
    app.config.update(TESTING=True, SERVER_NAME='test.local', AI_ENABLED=True)
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        with app.test_request_context('/'):
            yield SimpleNamespace(app=app, db=db)
        db.session.remove()
        db.drop_all()


def _policy():
    return str(guide_docs.render('templates/practice-ai-use-policy')[1])


@needs_db
def test_policy_lists_what_is_enabled_now(db_app):
    from app.models.ai_provider import AIProviderConfig, AIModel
    from app.models.system_setting import SystemSetting
    local = AIProviderConfig(name='Invented Local', provider_key='inv_local',
                             base_url='http://ollama.example:11434', is_local=True)
    cloud = AIProviderConfig(name='Invented Cloud', provider_key='inv_cloud',
                             base_url='https://api.cloud.example', is_local=False)
    off = AIProviderConfig(name='Switched Off Co', provider_key='inv_off',
                           base_url='https://off.example', is_enabled=False)
    db_app.db.session.add_all([local, cloud, off])
    db_app.db.session.flush()
    asr = AIModel(provider_id=local.id, model_id='whisper-invented', is_asr=True)
    db_app.db.session.add_all([
        asr,
        AIModel(provider_id=cloud.id, model_id='cloud-model-1', display_name='Cloud One',
                is_recommended=True, show_in_ai_assist=True),
        AIModel(provider_id=cloud.id, model_id='cloud-model-2', is_enabled=False),
        AIModel(provider_id=off.id, model_id='never-shown')])
    db_app.db.session.flush()
    SystemSetting.set('active_asr_model_id', asr.id)
    SystemSetting.set('general.practice_name', 'Invented Street Clinic')
    html = _policy()
    assert 'medui:enabled-ai' not in html and 'Filled in by MedUI' not in html
    assert 'Invented Local' in html and "On the practice&#39;s computers" in html
    assert 'Invented Cloud' in html and 'Cloud: receives redacted requests only' in html
    assert 'Cloud One' in html and 'recommended, AI assistant' in html
    assert 'voice (scribe)' in html
    assert 'cloud-model-2' not in html and 'Switched Off Co' not in html and 'never-shown' not in html
    assert 'Invented Street Clinic' in html and 'Listed ' in html


@needs_db
def test_policy_says_when_ai_is_off(db_app):
    db_app.app.config['AI_ENABLED'] = False
    html = _policy()
    assert 'AI is switched off in this installation' in html and 'No AI provider is enabled' in html


def test_policy_outside_the_app_points_to_it():
    text = (ROOT / 'docs/templates/practice-ai-use-policy.md').read_text()
    assert '<!-- medui:enabled-ai -->' in text and 'Governance → AI-use policy' in text
    assert 'governance register' not in text
    assert 'No unredacted or identifiable patient information goes to a cloud AI service' in text
    assert 'train on' in text


def test_docs_template_is_the_apps_template():
    """The docs copy (for reading outside MedUI) is the text Governance → AI-use Policy starts
    from; a change to one is made to both."""
    docs = (ROOT / 'docs/templates/practice-ai-use-policy.md').read_text()
    app_copy = (ROOT / 'app/templates/governance/ai_policy/policy_template.md').read_text()
    assert docs == app_copy
