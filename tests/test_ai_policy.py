"""Governance → AI-use policy (ADR-158). Names and addresses here are invented.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway *_test database.
"""
import os
from types import SimpleNamespace

import pytest
from flask import Flask

from app.services import ai_policy_service as svc

INFO = {'ai_enabled': True, 'practice': 'Invented Street Clinic', 'version': None,
        'listed_at': '20 November 2026, 09:00',
        'providers': [
            {'name': 'Invented Local', 'local': True,
             'models': [{'name': 'whisper-invented', 'model_id': 'whisper-invented',
                         'uses': ['voice (scribe)']}]},
            {'name': 'Invented | Cloud', 'local': False,
             'models': [{'name': 'Cloud One', 'model_id': 'cloud-model-1',
                         'uses': ['recommended', 'AI assistant']}]}]}


@pytest.fixture
def plain_app(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(svc, 'enabled_ai', lambda: INFO)
    with app.app_context():
        yield app


def test_template_has_the_appendix_markers():
    text = svc.template_text()
    assert svc.MARKERS.search(text)
    assert 'governance register' not in text and '](ai-concerns-process.md)' not in text


def test_appendix_goes_between_the_markers(plain_app):
    html = str(svc.to_html('# Policy\n\n## Appendix A\n\n<!-- medui:enabled-ai -->\nold\n'
                           '<!-- /medui:enabled-ai -->\n\nSigned: [name]'))
    assert 'Invented Local' in html and "On the practice&#39;s computers" in html
    assert 'Cloud: receives redacted requests only' in html and 'Cloud One' in html
    assert 'old' not in html and 'Signed' in html
    assert html.index('Invented Local') < html.index('Signed')


def test_without_markers_the_appendix_goes_at_the_end(plain_app):
    html = str(svc.to_html('# Policy\n\nText.'))
    assert html.rstrip().endswith('</table>') and 'Appendix A' in html
    md = svc.to_markdown('# Policy\n\nText.')
    assert md.index('## Appendix A') > md.index('Text.')


def test_the_practices_text_cant_inject_html(plain_app):
    html = str(svc.to_html('<script>alert(1)</script>\n\n[x](javascript:alert(1)) '
                           '[ok](https://example.org/policy) ![i](data:x)'))
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'javascript:' not in html and 'data:x' not in html
    assert 'href="https://example.org/policy"' in html


def test_markdown_download_has_a_table(plain_app):
    md = svc.to_markdown(svc.template_text())
    assert 'medui:enabled-ai' not in md
    assert '| Provider | Runs | Model | Used for |' in md
    assert 'Invented \\| Cloud' in md                       # a | in a name doesn't break the table
    assert 'Listed 20 November 2026, 09:00 from this installation (Invented Street Clinic, MedUI)' in md


def test_ai_off_and_no_providers(plain_app, monkeypatch):
    monkeypatch.setattr(svc, 'enabled_ai', lambda: {**INFO, 'ai_enabled': False, 'providers': []})
    html = str(svc.to_html(svc.template_text()))
    assert 'AI is switched off in this installation' in html and 'No AI provider is enabled' in html


# ── Database ──────────────────────────────────────────────────────────────────

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
        doc = User(username='dr_a', display_name='Dr A', security_level=5, password_hash='x')
        lead = User(username='lead', display_name='Lead', security_level=9, password_hash='x')
        db.session.add_all([doc, lead])
        db.session.commit()
        yield SimpleNamespace(app=app, db=db, doc=doc, lead=lead)
        db.session.remove()
        db.drop_all()


class _As:
    """A test client signed in as one user (flask-login caches the user on g, so clear it)."""
    def __init__(self, ctx, user):
        self.client = ctx.app.test_client()
        with self.client.session_transaction() as s:
            s['_user_id'] = str(user.id)
            s['_fresh'] = True

    def _go(self, method, *a, **kw):
        from flask import g
        g.pop('_login_user', None)
        return getattr(self.client, method)(*a, **kw)

    def get(self, *a, **kw):
        return self._go('get', *a, **kw)

    def post(self, *a, **kw):
        return self._go('post', *a, **kw)


def _client(ctx, user):
    return _As(ctx, user)


@needs_db
def test_template_until_saved_then_the_practices_own(ctx):
    assert svc.get()['is_template']
    svc.save('# Invented Street Clinic AI policy\n\nOur rules.', ctx.lead)
    p = svc.get()
    assert not p['is_template'] and p['updated_by'] == 'Lead' and p['markdown'].startswith('# Invented')
    with pytest.raises(ValueError):
        svc.save('   ', ctx.lead)
    assert svc.get()['version'].number == 1


@needs_db
def test_everyone_reads_only_administrators_edit(ctx):
    doc, lead = _client(ctx, ctx.doc), _client(ctx, ctx.lead)
    page = doc.get('/governance/ai-policy/').get_data(as_text=True)
    assert 'Print or save as PDF' in page and 'Download (.md)' in page
    assert 'ai-policy/edit' not in page
    assert doc.get('/governance/ai-policy/edit').status_code == 403
    assert doc.post('/governance/ai-policy/edit', data={'markdown': '# x'}).status_code == 403
    assert lead.get('/governance/ai-policy/edit').status_code == 200
    r = lead.post('/governance/ai-policy/edit', data={'action': 'save',
                                                     'markdown': '# Our policy\n\nInvented rule.'})
    assert r.status_code == 302
    assert 'Invented rule.' in doc.get('/governance/ai-policy/').get_data(as_text=True)
    dl = doc.get('/governance/ai-policy/download')
    assert dl.mimetype == 'text/markdown' and 'attachment; filename="ai-use-policy-' in dl.headers['Content-Disposition']
    assert dl.get_data(as_text=True).startswith('# Our policy') and '## Appendix A' in dl.get_data(as_text=True)
    page = lead.get('/governance/ai-policy/edit?from=template').get_data(as_text=True)
    assert 'Starting again from the template' in page
    assert not svc.get()['is_template']            # nothing changes until it is saved


@needs_db
def test_governance_menu_links_the_policy(ctx):
    html = _client(ctx, ctx.doc).get('/governance/ai-policy/').get_data(as_text=True)
    assert 'href="/governance/ai-policy/"' in html and 'AI-use Policy' in html


def test_template_carries_the_intended_purpose_paragraphs():
    """ADR-169: questions typed, AI-suggested guideline content, the practice's own prompts and
    recipes, and medicolegally sensitive discussions."""
    text = svc.template_text()
    for phrase in ('**Questions you type.**', '**Guideline content is AI-suggested.**',
                   '**Prompts and care-plan recipes the practice writes**',
                   '**Medicolegally sensitive discussions.**',
                   'governs phrasing only', 'Admin → Flagged AI Requests'):
        assert phrase in text, phrase
    assert text.index('**Questions you type.**') < text.index('## 2. The clinician is responsible') \
        < text.index('**Medicolegally sensitive discussions.**') < text.index('## 3. Patient information')


# ── Versions and approval (ADR-184) ───────────────────────────────────────────

@needs_db
def test_each_save_is_a_new_version_with_its_appendix(ctx, monkeypatch):
    calls = iter(['Invented Local', 'Invented Cloud'])
    def fake_enabled():
        return {'ai_enabled': True, 'practice': 'Invented Clinic', 'version': None,
                'listed_at': '1 January 2026, 09:00',
                'providers': [{'name': next(calls), 'local': True, 'models': []}]}
    monkeypatch.setattr(svc, 'enabled_ai', fake_enabled)
    v1 = svc.save('# Policy\n\n<!-- medui:enabled-ai -->\n<!-- /medui:enabled-ai -->\n', ctx.lead, 'first')
    assert v1.number == 1 and v1.note == 'first' and v1.saved_by_name == 'Lead'
    assert svc.save(v1.markdown, ctx.lead) is None                 # same text: no new version
    v2 = svc.save(v1.markdown + '\nA new rule.', ctx.lead)
    assert v2.number == 2 and [v.number for v in svc.versions()] == [2, 1]
    # Each version keeps the list as it was when it was saved.
    assert 'Invented Local' in svc.to_html(v1.markdown, saved=svc.saved_appendix(v1))
    html2 = svc.to_html(v2.markdown, saved=svc.saved_appendix(v2))
    assert 'Invented Cloud' in html2 and 'when version 2 was saved' in html2
    assert v1.markdown == svc.version(1).markdown                   # never changed


@needs_db
def test_approval_is_once_latest_only_and_needs_the_tick(ctx):
    from datetime import date, timedelta
    svc.save('# Policy one', ctx.lead)
    svc.save('# Policy two', ctx.lead)
    later = date.today() + timedelta(days=300)
    with pytest.raises(ValueError):
        svc.approve(1, ctx.lead, later)                             # not the latest
    with pytest.raises(ValueError):
        svc.approve(2, ctx.lead, date.today())                      # review date must be in the future
    lead, doc = _client(ctx, ctx.lead), _client(ctx, ctx.doc)
    assert doc.post('/governance/ai-policy/version/2/approve', data={'review_due_on': later.isoformat(), 'attest': '1'}).status_code == 403
    lead.post('/governance/ai-policy/version/2/approve', data={'review_due_on': later.isoformat()})
    assert svc.version(2).approved_at is None                       # no tick, no approval
    lead.post('/governance/ai-policy/version/2/approve', data={'review_due_on': later.isoformat(), 'attest': '1'})
    v = svc.version(2)
    assert v.approved_by_name == 'Lead' and v.review_due_on == later
    with pytest.raises(ValueError):
        svc.approve(2, ctx.lead, later)                             # once only
    page = doc.get('/governance/ai-policy/').get_data(as_text=True)
    assert 'Version 2' in page and 'Approved by Lead' in page and 'Versions (2)' in page


@needs_db
def test_everyone_reads_earlier_versions(ctx):
    svc.save('# Old wording\n\nInvented old rule.', ctx.lead)
    svc.save('# New wording', ctx.lead)
    doc = _client(ctx, ctx.doc)
    listing = doc.get('/governance/ai-policy/versions').get_data(as_text=True)
    assert 'Version 1' in listing and 'Version 2' in listing and '(in use)' in listing
    old = doc.get('/governance/ai-policy/version/1').get_data(as_text=True)
    assert 'Invented old rule.' in old and 'an earlier version' in old
    dl = doc.get('/governance/ai-policy/version/1/download')
    assert 'ai-use-policy-version-1.md' in dl.headers['Content-Disposition']
    assert doc.get('/governance/ai-policy/version/9').status_code == 404


@needs_db
def test_a_policy_saved_before_versions_becomes_version_1(ctx):
    from app.models.system_setting import SystemSetting
    SystemSetting.set(svc.SETTING_KEY, {'markdown': '# Invented earlier policy', 'updated_by': 'Lead',
                                        'updated_at': '2026-11-20T10:00:00+00:00'})
    p = svc.get()
    assert p['version'].number == 1 and p['markdown'] == '# Invented earlier policy'
    assert svc.saved_appendix(p['version']) is None
    page = _client(ctx, ctx.doc).get('/governance/ai-policy/version/1').get_data(as_text=True)
    assert 'saved before MedUI kept a copy of Appendix A' in page
    assert len(svc.versions()) == 1                                 # carried over once
