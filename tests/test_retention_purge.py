"""Setup → Maintenance → Purge keeps AI run records other records still refer to, and the automatic
cleanup switch is gone (upstream ADR-188). All data is invented.

Purge kept failing before: one referenced run rolled back the whole purge.

The database tests run only when MEDUI_TEST_DATABASE_URL names a throwaway *_test database."""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')

OLD = datetime.now(timezone.utc) - timedelta(days=400)


def test_every_blocking_reference_to_a_run_is_found():
    import app.models  # noqa: F401  (registers every table)
    from app.services import retention_service
    found = {(t.name, c.name) for t, c in retention_service._run_references()}
    for ref in (('chat_messages', 'pipeline_run_id'), ('careplan_recipe_versions', 'authoring_run_id'),
                ('gpccmp_sessions', 'pipeline_run_id'),
                ('patient_messages', 'pipeline_run_id'), ('privacy_reports', 'run_id')):
        assert ref in found, ref
    # A privacy review goes with its run (ON DELETE CASCADE), so it doesn't keep the run.
    assert not any(t == 'privacy_reviews' for t, _ in found)


def test_switch_no_code_read_is_gone():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ('app/blueprints/setup/routes.py', 'app/templates/setup/partials/tab_maintenance.html'):
        with open(os.path.join(root, rel), encoding='utf-8') as fh:
            assert 'auto_cleanup' not in fh.read(), rel


@pytest.fixture
def ctx(monkeypatch):
    from app import create_app
    from app import config as app_config
    from app.extensions import db
    from app.models.user import User
    from app.models.pipeline import Pipeline
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
        pipe = Pipeline(name='Invented pipeline')
        db.session.add_all([lead, pipe])
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(lead.id)
            s['_fresh'] = True
        yield SimpleNamespace(app=app, db=db, client=client, user=lead, pipe=pipe)
        db.session.remove()
        db.drop_all()


def _run(ctx, started_at=None):
    from app.models.pipeline import PipelineRun, RedactionPolicy
    run = PipelineRun(pipeline_id=ctx.pipe.id, initiated_by_id=ctx.user.id,
                      redaction_policy=RedactionPolicy.redact_all,
                      **({'started_at': started_at} if started_at else {}))
    ctx.db.session.add(run)
    ctx.db.session.flush()
    return run.id


@needs_db
def test_purge_keeps_a_run_a_chat_refers_to(ctx):
    from app.models.chat import ChatSession, ChatMessage
    from app.models.pipeline import PipelineRun
    linked, unlinked, recent = _run(ctx, OLD), _run(ctx, OLD), _run(ctx)
    chat = ChatSession(token_key='invented-token', user_id=ctx.user.id, pipeline_id=ctx.pipe.id)
    ctx.db.session.add(chat)
    ctx.db.session.flush()
    ctx.db.session.add(ChatMessage(session_id=chat.id, role='assistant', content='Invented reply',
                                   pipeline_run_id=linked, created_at=OLD))
    ctx.db.session.commit()

    preview = ctx.client.get('/setup/tab/maintenance').get_data(as_text=True)
    assert '1 older AI run record(s) are kept' in preview
    assert 'Enable automatic daily cleanup' not in preview

    resp = ctx.client.post('/setup/maintenance/purge')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Purge complete — 1 row(s) deleted' in body
    assert '1 older AI run record(s) kept' in body
    ctx.db.session.remove()
    left = {r.id for r in PipelineRun.query.all()}
    assert left == {linked, recent}, (left, unlinked)


@needs_db
def test_a_run_only_an_expired_message_refers_to_goes_in_the_same_purge(ctx):
    from app.models.patient_message import PatientMessage, MessageChannel, MessageStatus
    from app.models.pipeline import PipelineRun
    from app.services import retention_service
    run_id = _run(ctx, OLD)
    ctx.db.session.add(PatientMessage(patient_id=1, channel=MessageChannel.sms,
                                      status=MessageStatus.sent, pipeline_run_id=run_id,
                                      created_at=OLD))
    ctx.db.session.commit()
    n = retention_service.purge()
    assert (n['messages'], n['runs'], n['runs_kept']) == (1, 1, 0)
    assert PipelineRun.query.count() == 0


@needs_db
def test_saving_maintenance_no_longer_writes_the_switch(ctx):
    from app.models.system_setting import SystemSetting
    resp = ctx.client.post('/setup/maintenance/save', data={
        'retention_transcripts': '30', 'retention_messages': '90', 'retention_runs': '180'})
    assert resp.status_code == 200
    assert SystemSetting.get('data.auto_cleanup') is None


# ── Chat retention (upstream ADR-189) ─────────────────────────────────────────────────

def _chat(ctx, last_activity, **flags):
    from app.models.chat import ChatSession, ChatMessage, ChatGeneratedFile
    run_id = _run(ctx, OLD)
    chat = ChatSession(token_key=f'invented-{run_id}', user_id=ctx.user.id, pipeline_id=ctx.pipe.id,
                       last_activity_at=last_activity, **flags)
    ctx.db.session.add(chat)
    ctx.db.session.flush()
    reply = ChatMessage(session_id=chat.id, role='assistant', content='Invented reply',
                        pipeline_run_id=run_id, created_at=last_activity)
    ctx.db.session.add(reply)
    ctx.db.session.flush()
    ctx.db.session.add(ChatGeneratedFile(session_id=chat.id, message_id=reply.id,
                                         filename='invented.txt', content='Invented file'))
    ctx.db.session.flush()
    return chat.id, run_id


@needs_db
def test_old_chats_go_in_every_state_with_their_runs(ctx):
    from app.models.chat import ChatSession, ChatMessage, ChatGeneratedFile
    from app.models.pipeline import PipelineRun
    current, _ = _chat(ctx, OLD)
    ended, _ = _chat(ctx, OLD, is_archived=True)
    removed, _ = _chat(ctx, OLD, is_archived=True, is_deleted=True)
    recent, recent_run = _chat(ctx, datetime.now(timezone.utc))
    ctx.db.session.commit()

    preview = ctx.client.get('/setup/tab/maintenance').get_data(as_text=True)
    assert 'Chats (days)' in preview

    body = ctx.client.post('/setup/maintenance/purge').get_data(as_text=True)
    assert '3 chats' in body
    ctx.db.session.remove()
    assert {c.id for c in ChatSession.query.all()} == {recent}
    assert ChatMessage.query.count() == 1 and ChatGeneratedFile.query.count() == 1
    # The purged chats' runs went in the same purge; the recent chat's old run is kept.
    assert {r.id for r in PipelineRun.query.all()} == {recent_run}


@needs_db
def test_the_chat_window_is_saved(ctx):
    from app.models.system_setting import SystemSetting
    ctx.client.post('/setup/maintenance/save', data={
        'retention_transcripts': '30', 'retention_messages': '90', 'retention_chats': '45',
        'retention_runs': '180'})
    assert int(SystemSetting.get('data.retention.chats')) == 45


# ── Each Maintenance section saves only its own settings (upstream ADR-190) ──────────

@needs_db
def test_saving_retention_leaves_the_privacy_switches_alone(ctx):
    from app.models.system_setting import SystemSetting
    SystemSetting.set('privacy.hide_staff_records', True)
    SystemSetting.set('privacy.review_page', True)
    resp = ctx.client.post('/setup/maintenance/save', data={
        'section': 'retention', 'retention_transcripts': '20', 'retention_messages': '60',
        'retention_chats': '30', 'retention_runs': '120'})
    assert 'Retention saved.' in resp.get_data(as_text=True)
    assert SystemSetting.get('privacy.hide_staff_records') is True
    assert SystemSetting.get('privacy.review_page') is True
    assert int(SystemSetting.get('data.retention.chats')) == 30


@needs_db
def test_saving_privacy_leaves_the_retention_windows_alone(ctx):
    from app.models.system_setting import SystemSetting
    SystemSetting.set('data.retention.chats', 45)
    resp = ctx.client.post('/setup/maintenance/save', data={
        'section': 'privacy', 'hide_staff_records': 'true'})
    assert 'Privacy settings saved.' in resp.get_data(as_text=True)
    assert int(SystemSetting.get('data.retention.chats')) == 45
    assert SystemSetting.get('privacy.hide_staff_records') is True
    assert SystemSetting.get('privacy.review_page') is False


@needs_db
def test_the_privacy_switches_come_before_retention_and_purge(ctx):
    page = ctx.client.get('/setup/tab/maintenance').get_data(as_text=True)
    order = [page.index(s) for s in ('Staff Privacy', 'Privacy Review', 'Data Retention',
                                     'Save Retention', 'Purge Eligible Data')]
    assert order == sorted(order)
    assert page.count('name="section"') == 2
