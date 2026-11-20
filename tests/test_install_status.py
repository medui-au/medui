"""The installation status on an administrator's home page (medui_os).

Users, names, servers and folders here are invented.
"""
import os
from types import SimpleNamespace

import pytest

from app.services import install_status as status


# ── no database needed ────────────────────────────────────────────────────────

def _item(state):
    return status.Item('k', 'Label', state, 'Detail.')


def test_summary_leaves_switched_off_items_out():
    s = status.summary([_item('ok'), _item('off'), _item('off')])
    assert s == {'ready': 1, 'total': 1, 'complete': True, 'blocked': False}


def test_summary_counts_warnings_and_blocks_on_missing():
    s = status.summary([_item('ok'), _item('warn'), _item('missing')])
    assert s['ready'] == 1 and s['total'] == 3 and not s['complete'] and s['blocked']


@pytest.mark.parametrize('value, demo', [('demo', True), (' Demo ', True), ('live', False),
                                         ('', False), (None, False)])
def test_is_demo(monkeypatch, value, demo):
    if value is None:
        monkeypatch.delenv('MEDUI_INSTANCE', raising=False)
    else:
        monkeypatch.setenv('MEDUI_INSTANCE', value)
    assert status.is_demo() is demo


# ── with the throwaway test database ─────────────────────────────────────────

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
    monkeypatch.delenv('MEDUI_INSTANCE', raising=False)
    app = create_app('dev')
    app.config.update(TESTING=True, SERVER_NAME='test.local', WTF_CSRF_ENABLED=False,
                      BPSDB_URI=None, AI_ENABLED=False, MESSAGING_ENABLED=False,
                      PIT_EXPORT_ENABLED=False, SESSION_COOKIE_SECURE=False,
                      OCR_SERVICE_URL='')
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        admin = User(username='localadmin', display_name='Local Admin', security_level=9,
                     is_local_admin=True, password_hash='x')
        admin.set_password('invented-pass-1')
        nurse = User(username='nurse_b', display_name='Nurse B', security_level=3,
                     password_hash='x')
        db.session.add_all([admin, nurse])
        db.session.commit()
        yield SimpleNamespace(app=app, db=db, User=User)
        db.session.remove()
        db.drop_all()


def _items(ctx):
    with ctx.app.test_request_context('/'):
        return {i.key: i for i in status.items()}


def _client(ctx, monkeypatch, username):
    from flask import g
    from app.services.auth_service import AuthService
    user = ctx.User.query.filter_by(username=username).one()
    monkeypatch.setattr(AuthService, 'authenticate', staticmethod(lambda u, p: user))
    g.pop('_login_user', None)
    client = ctx.app.test_client()
    client.post('/auth/login', data={'username': username, 'password': 'x'})
    return client


@pytest.fixture
def bp_connects(monkeypatch):
    import pyodbc
    monkeypatch.setattr(pyodbc, 'connect', lambda *a, **k: SimpleNamespace(close=lambda: None))


@needs_db
def test_fresh_live_installation(ctx):
    found = _items(ctx)
    assert found['database'].state == 'missing'
    assert found['database'].label == 'Best Practice database'
    assert found['practice'].state == 'warn'
    assert found['https'].state == 'warn'
    assert found['ai'].state == 'off' and 'ai_provider' not in found and 'voice' not in found
    assert found['ocr'].state == 'warn'
    assert found['pit'].state == 'warn' and found['messaging'].state == 'warn'   # counted
    assert 'PIT_EXPORT_ENABLED=on' in found['pit'].detail
    assert 'MESSAGING_ENABLED=on' in found['messaging'].detail
    assert found['admins'].state == 'warn'             # one local administrator
    with ctx.app.test_request_context('/'):
        assert status.summary(list(found.values()))['blocked']


@needs_db
def test_links_point_at_setup_tabs_and_the_guide(ctx):
    found = _items(ctx)
    with ctx.app.test_request_context('/'):
        assert found['database'].setup_url.endswith('/setup/?tab=database')
        assert found['database'].guide_url.endswith(
            '/setup/guide/setup-guide#2-best-practice-connection')
        assert found['https'].setup_url is None


@needs_db
def test_every_guide_link_names_a_real_section(ctx, monkeypatch):
    """A guide link must open a page the in-app guide serves, at a heading it has."""
    import re
    import markdown
    from pathlib import Path
    from app.blueprints.setup.routes import _GUIDE_DOCS
    ctx.app.config.update(AI_ENABLED=True, MESSAGING_ENABLED=True, PIT_EXPORT_ENABLED=True)
    guides = {i.guide for i in _items(ctx).values() if i.guide}
    monkeypatch.setenv('MEDUI_INSTANCE', 'demo')
    guides |= {i.guide for i in _items(ctx).values() if i.guide}
    root = Path(__file__).resolve().parent.parent / 'docs'
    for guide in guides:
        name, _, anchor = guide.partition('#')
        assert name in _GUIDE_DOCS, guide
        if anchor:
            html = markdown.markdown((root / f'{name}.md').read_text(), extensions=['toc', 'tables'])
            assert f'id="{anchor}"' in html, guide
    assert re.search(r'#2-best-practice-connection', ' '.join(guides))


@needs_db
def test_connected_bp_and_a_finished_installation(ctx, monkeypatch, bp_connects, tmp_path):
    from app.models.system_setting import SystemSetting
    from app.models.ai_provider import AIProviderConfig
    from app.services import ocr_service, email_service, sms_service
    import requests
    ctx.app.config.update(BPSDB_URI='DRIVER={x};SERVER={sql.example};',
                          SESSION_COOKIE_SECURE=True, PIT_EXPORT_ENABLED=True,
                          MESSAGING_ENABLED=True)
    SystemSetting.set('general.practice_name', 'Invented Street Clinic')
    SystemSetting.set('pit_export_path', str(tmp_path))
    monkeypatch.setattr(email_service, 'is_configured', lambda: True)
    monkeypatch.setattr(sms_service, 'is_configured', lambda: True)
    ctx.db.session.add(ctx.User(username='second_admin', display_name='Second', security_level=9,
                                is_local_admin=True, password_hash='x'))
    ctx.db.session.commit()
    monkeypatch.setattr(ocr_service, '_get_config',
                        lambda: SimpleNamespace(base_url='http://ocr.example:5707'))
    monkeypatch.setattr(requests, 'post', lambda *a, **k: SimpleNamespace(status_code=400))
    found = _items(ctx)
    assert found['database'].state == 'ok'
    assert found['practice'].state == 'ok' and 'Invented Street Clinic' in found['practice'].detail
    assert found['https'].state == 'ok' and found['ocr'].state == 'ok'
    assert found['admins'].state == 'ok'
    with ctx.app.test_request_context('/'):
        assert status.summary(list(found.values()))['complete']
    assert AIProviderConfig.query.count() == 0           # AI off: not counted against it


@needs_db
def test_bp_that_doesnt_connect_is_missing_without_its_message(ctx, monkeypatch):
    import pyodbc

    def refuse(*a, **k):
        raise pyodbc.OperationalError('invented: login failed for user invented_ro')
    monkeypatch.setattr(pyodbc, 'connect', refuse)
    ctx.app.config['BPSDB_URI'] = 'DRIVER={x};SERVER={sql.example};'
    item = _items(ctx)['database']
    assert item.state == 'missing' and 'OperationalError' in item.detail
    assert 'invented_ro' not in item.detail


@needs_db
def test_login_that_can_write_is_a_warning(ctx, monkeypatch, bp_connects):
    from app.services import bp_login_service
    ctx.app.config['BPSDB_URI'] = 'DRIVER={x};SERVER={sql.example};'
    monkeypatch.setattr(bp_login_service, 'cached',
                        lambda: SimpleNamespace(status=bp_login_service.CAN_WRITE))
    assert _items(ctx)['database'].state == 'warn'


@needs_db
def test_ai_on_without_provider_or_voice(ctx):
    ctx.app.config['AI_ENABLED'] = True
    found = _items(ctx)
    assert found['ai'].state == 'ok'
    assert found['ai_provider'].state == 'warn' and found['ai_provider'].setup_tab == 'providers'
    assert found['voice'].state == 'warn'


@needs_db
def test_messaging_on_lists_email_and_sms_separately(ctx):
    ctx.app.config['MESSAGING_ENABLED'] = True
    found = _items(ctx)
    assert 'messaging' not in found
    assert found['email'].state == 'warn' and found['sms'].state == 'warn'


@needs_db
def test_pit_folder(ctx, tmp_path):
    from app.models.system_setting import SystemSetting
    ctx.app.config['PIT_EXPORT_ENABLED'] = True
    assert _items(ctx)['pit'].state == 'warn'
    SystemSetting.set('pit_export_path', str(tmp_path / 'not-there'))
    assert _items(ctx)['pit'].state == 'warn'
    SystemSetting.set('pit_export_path', str(tmp_path))
    assert _items(ctx)['pit'].state == 'ok'


@needs_db
def test_demo_installation(ctx, monkeypatch):
    monkeypatch.setenv('MEDUI_INSTANCE', 'demo')
    found = _items(ctx)
    assert found['database'].label.startswith('Demo data')
    assert found['database'].guide == 'setup-guide#a-demo-installation'
    assert 'pit' not in found and 'messaging' not in found and 'email' not in found


@needs_db
def test_a_failing_check_becomes_a_warning(ctx, monkeypatch):
    monkeypatch.setattr(status, '_ocr', lambda: 1 / 0)
    found = _items(ctx)
    assert found['error'].state == 'warn'
    assert found['database'].state == 'missing'          # the others still ran


@needs_db
def test_home_page_loads_the_panel_for_administrators_only(ctx, monkeypatch):
    admin = _client(ctx, monkeypatch, 'localadmin')
    home = admin.get('/').get_data(as_text=True)
    assert 'hx-get="/install-status"' in home
    panel = admin.get('/install-status')
    assert panel.status_code == 200
    html = panel.get_data(as_text=True)
    assert 'Best Practice database' in html and '/setup/?tab=database' in html
    assert 'Required to connect to your live BP data.' in html and 'role="tooltip"' in html

    nurse = _client(ctx, monkeypatch, 'nurse_b')
    assert 'install-status' not in nurse.get('/').get_data(as_text=True)
    assert nurse.get('/install-status').status_code == 403


@needs_db
def test_every_item_says_what_it_is_needed_for(ctx, monkeypatch):
    ctx.app.config.update(AI_ENABLED=True, MESSAGING_ENABLED=True, PIT_EXPORT_ENABLED=True)
    live = _items(ctx)
    assert all(i.why for i in live.values()), [k for k, i in live.items() if not i.why]
    assert live['database'].why == 'Required to connect to your live BP data.'
    assert live['pit'].why.startswith('Required to save MedUI outputs back to BP')
    monkeypatch.setenv('MEDUI_INSTANCE', 'demo')
    assert 'demo' in _items(ctx)['database'].why


def test_guide_headings_clear_the_fixed_menu_bar():
    """A #section link must stop below the fixed navbar, or the heading is hidden behind it."""
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / 'app/templates/setup/guide.html').read_text()
    assert 'scroll-margin-top:calc(var(--nav-height)' in html


@needs_db
@pytest.mark.parametrize('code, state', [(400, 'ok'), (200, 'warn'), (404, 'warn')])
def test_ocr_is_checked_the_way_liteparse_answers(ctx, monkeypatch, code, state):
    """LiteParse has no /health: a POST to /parse without a file gets 400 when it is up."""
    import requests
    from app.services import ocr_service
    seen = {}
    monkeypatch.setattr(ocr_service, '_get_config', lambda: SimpleNamespace(
        base_url='http://liteparse:5707', api_path='/parse', api_key=None,
        auth_header_name='X-API-KEY'))

    def post(url, **kw):
        seen['url'] = url
        return SimpleNamespace(status_code=code)
    monkeypatch.setattr(requests, 'post', post)
    item = _items(ctx)['ocr']
    assert seen['url'] == 'http://liteparse:5707/parse' and item.state == state
    if state == 'ok':
        assert 'automatically' in item.detail          # no saved entry: the environment's URL


@needs_db
def test_ocr_switched_off_is_grey(ctx):
    ctx.app.config['OCR_ENABLED'] = False
    item = _items(ctx)['ocr']
    assert item.state == 'off' and 'OCR_ENABLED=on' in item.detail


@needs_db
def test_setup_external_tab_says_which_ocr_is_used(ctx, monkeypatch):
    from app.extensions import db
    from app.models.external_service import ExternalServiceConfig, ExternalServiceType
    client = _client(ctx, monkeypatch, 'localadmin')
    html = client.get('/setup/tab/external').get_data(as_text=True)
    assert "own LiteParse automatically" in html
    ctx.app.config['OCR_ENABLED'] = False
    assert 'OCR is switched off' in client.get('/setup/tab/external').get_data(as_text=True)
    ctx.app.config['OCR_ENABLED'] = True
    db.session.add(ExternalServiceConfig(service_type=ExternalServiceType.ocr,
                                         display_name='Other OCR',
                                         base_url='http://ocr.example:5707', is_enabled=True))
    db.session.commit()
    assert 'instead of this installation' in client.get('/setup/tab/external').get_data(as_text=True)


@needs_db
def test_enabled_models_count_without_the_recommended_tick(ctx):
    """"Recommended" is a label: any enabled text model of an enabled provider is enough."""
    from app.models.ai_provider import AIProviderConfig, AIModel
    ctx.app.config['AI_ENABLED'] = True
    p = AIProviderConfig(name='Invented Cloud', provider_key='inv_cloud',
                         base_url='https://api.cloud.example')
    ctx.db.session.add(p)
    ctx.db.session.flush()
    ctx.db.session.add(AIModel(provider_id=p.id, model_id='whisper-invented', is_asr=True))
    ctx.db.session.commit()
    item = _items(ctx)['ai_provider']
    assert item.state == 'warn' and 'no model is enabled' in item.detail   # a voice model only
    ctx.db.session.add(AIModel(provider_id=p.id, model_id='text-model-1', is_recommended=False))
    ctx.db.session.commit()
    item = _items(ctx)['ai_provider']
    assert item.state == 'ok' and item.detail == '1 provider, 1 model enabled.'


@needs_db
def test_only_unfinished_items_show_until_expanded(ctx, monkeypatch, bp_connects):
    import re
    ctx.app.config['BPSDB_URI'] = 'DRIVER={x};SERVER={sql.example};'
    html = _client(ctx, monkeypatch, 'localadmin').get('/install-status').get_data(as_text=True)
    shown, _, folded = html.partition('<details class="inst-more">')
    assert 'HTTPS for the workstations' in shown                   # to do: always shown
    assert 'Best Practice database' in folded and 'Best Practice database' not in shown
    assert re.search(r'Show the \d+ ready item', folded)
