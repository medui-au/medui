"""Protocol governance (ADR-176): the generated decision record, targets to review, the policy
paragraph. Invented data only."""
import os
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import protocol_service as svc


def test_rules_in_words():
    assert svc.rule_text({'any': ['isIHD', 'isCVA']}) == 'any of IHD, stroke/TIA coded'
    assert svc.rule_text({'always': True}) == 'the default for everyone else'
    assert svc.rule_text(None).startswith('never preselected')
    assert svc.rule_text({'any': ['isDiabetes'], 'none': ['isIHD']}) == 'any of diabetes coded; none of IHD coded'
    assert svc.prevention_rule_text({'sex': 'F', 'age_min': 50, 'age_max': 74}) == 'women, aged 50–74'
    assert svc.prevention_rule_text({'age_min': 50, 'age_max': 70, 'needs': 'smoking_history'}) == \
        'aged 50–70, with a recorded smoking history'
    assert svc.prevention_rule_text({'age_min': 45, 'flags_none': ['isColonCaPolyps']}) == \
        'aged 45+, without colon cancer or polyps coded'


def test_the_policy_template_has_the_practice_protocol_paragraph():
    text = (Path(__file__).resolve().parent.parent / 'app' / 'templates' / 'governance' / 'ai_policy'
            / 'policy_template.md').read_text()
    assert '**Practice protocols for care plans.**' in text
    assert 'the doctor confirms or changes\nevery target' in text and 'it does not choose targets' in text


DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')
PID = 4242


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
        users = dict(doc=User(username='dr_a', display_name='Dr A', security_level=5, password_hash='x'),
                     manager=User(username='mgr', display_name='Manager', security_level=7, password_hash='x'),
                     admin=User(username='adm', display_name='Admin', security_level=9, password_hash='x'))
        db.session.add_all(users.values())
        db.session.commit()
        from app.commands.protocol import seed_v1
        seed_v1(users['admin'].id)
        svc.approve(users['admin'], date.today() + timedelta(days=365))
        yield SimpleNamespace(app=app, db=db, **users)
        db.session.remove()
        db.drop_all()


def _client(ctx, user):
    from flask import g
    g.pop('_login_user', None)
    client = ctx.app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return client


@needs_db
def test_decision_record_is_built_from_the_version(ctx):
    assert _client(ctx, ctx.doc).get('/admin/protocols/record').status_code == 403
    body = _client(ctx, ctx.manager).get('/admin/protocols/record').get_data(as_text=True)
    assert 'Practice protocol, version 1: decision record' in body
    assert 'any of IHD, stroke/TIA, vasculopathy, revascularisation coded' in body
    assert 'Australian clinical guideline for diagnosing and managing acute coronary syndromes' in body
    assert 'women, aged 50–74' in body and 'Condition modules' in body


def _target(ctx, code, flags):
    from app.services import patient_target_service
    opt = next(o for o in svc.live_version().options if o.code == code)
    patient_target_service.confirm(PID, ctx.doc, [{'measure_id': opt.measure_id, 'option_id': opt.id}], flags)
    return opt


@needs_db
def test_targets_to_review_after_a_change_or_a_superseded_guideline(ctx):
    _target(ctx, 'ldl_ascvd', {'isIHD': 1})
    _target(ctx, 'bp_general', {})
    assert svc.targets_to_review() == []                          # nothing has changed
    # v2 rewords one option and drops another.
    v2 = svc.start_draft(ctx.admin, 'invented change')
    ldl2 = next(o for o in v2.options if o.code == 'ldl_ascvd')
    svc.update_option(ldl2, {'label': '< 1.2 mmol/L (invented)'})
    svc.delete_option(next(o for o in v2.options if o.code == 'bp_general'))
    svc.approve(ctx.admin, date.today() + timedelta(days=30))
    items = svc.targets_to_review()
    reasons = {it['target'].measure.key: ' '.join(it['reasons']) for it in items}
    assert 'now reads "< 1.2 mmol/L (invented)"' in reasons['ldl'] and 'no longer in protocol v2' in reasons['bp']
    # A cited guideline is superseded.
    opt = next(o for o in svc.live_version().options if o.code == 'hba1c_general')
    _target(ctx, 'hba1c_general', {'isDiabetes': 1})
    g = opt.citations[0].guideline
    new = svc.save_guideline(ctx.admin, {'title': 'Invented newer handbook'})
    svc.save_guideline(ctx.admin, {'superseded_by_id': str(new.id)}, g)
    reasons = {it['target'].measure.key: ' '.join(it['reasons']) for it in svc.targets_to_review()}
    assert 'marked superseded' in reasons['hba1c']
    body = _client(ctx, ctx.manager).get('/admin/protocols/review').get_data(as_text=True)
    assert f'/gpccmp/patient/{PID}/targets' in body and 'marked superseded' in body
