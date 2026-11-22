"""GPCCMP reviews (ADR-175). Invented data only; no AI is called.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway PostgreSQL database ending in _test (schema created with db.create_all()).
"""
import json
import os
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from app.services import gpccmp_decision_service as dec
from app.services import gpccmp_review_service as review


def _version():
    mods = [SimpleNamespace(condition_key='hypertension', label='Hypertension', applies_when={'any': ['isHT']},
                            services=['Dietitian'], goals='Keep my BP at target.')]
    return SimpleNamespace(version=1, modules=mods)


# ── No database ───────────────────────────────────────────────────────────────

def test_progress_is_read_per_issue_and_checked():
    form = MultiDict([('plan_type', 'review'), ('issue', 'hypertension'), ('progress_hypertension', 'improved'),
                      ('progress_note_hypertension', 'home readings lower'), ('free_label_0', 'Left knee pain'),
                      ('free_progress_0', 'stable')])
    d = dec.parse_form(form, _version())
    assert d['issues'][0]['progress'] == 'improved' and d['issues'][0]['progress_note'] == 'home readings lower'
    assert d['issues'][1]['progress'] == 'stable' and 'progress_note' not in d['issues'][1]
    with pytest.raises(dec.DecisionError):
        dec.parse_form(MultiDict([('issue', 'hypertension'), ('progress_hypertension', 'great')]), _version())


def test_a_review_needs_progress_for_every_issue():
    d = dec.parse_form(MultiDict([('plan_type', 'review'), ('issue', 'hypertension')]), _version())
    assert any('Record progress' in p and 'Hypertension' in p for p in dec.problems(d))
    d['issues'][0]['progress'] = 'not assessed'
    assert dec.problems(d) == []
    new_plan = dec.parse_form(MultiDict([('plan_type', 'prepare'), ('issue', 'hypertension')]), _version())
    assert dec.problems(new_plan) == []                      # only a review asks for progress


def test_progress_lines_and_dates():
    d = {'issues': [{'label': 'Hypertension', 'progress': 'improved', 'progress_note': 'readings lower'},
                    {'label': 'Gout'}]}
    assert review.progress_lines(d) == ['Hypertension: improved. readings lower', 'Gout: not recorded (GP to complete)']
    assert review._date('2026-10-03') == '03/10/2026' and review._date('') == ''


# ── Database ──────────────────────────────────────────────────────────────────

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')
PID = 4242
PATIENT = {'patient_id': PID, 'INTERNALID': PID, 'SURNAME': 'Example', 'FIRSTNAME': 'Ivy', 'AGE': 61,
           'CCMP_Eligibility': '967'}
LATEST = {'ldl_c': {'key': 'ldl_c', 'value': '1.9', 'unit': 'mmol/L', 'date': '2026-10-03', 'status': 'found'}}


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
    app.config.update(TESTING=True, SERVER_NAME='test.local', WTF_CSRF_ENABLED=False, AI_ENABLED=True)
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        users = dict(doc=User(username='dr_a', display_name='Dr A', security_level=5, password_hash='x'),
                     admin=User(username='adm', display_name='Admin', security_level=9, password_hash='x'))
        db.session.add_all(users.values())
        db.session.commit()
        from app.commands.protocol import seed_v1
        from app.services import protocol_service, careplan_service, patient_target_service
        seed_v1(users['admin'].id)
        protocol_service.approve(users['admin'], date.today() + timedelta(days=365))
        from app.services.clinical_service import ClinicalService
        monkeypatch.setattr(ClinicalService, 'get_patient_demographics', staticmethod(lambda pid: dict(PATIENT)))
        monkeypatch.setattr(ClinicalService, 'get_disease_profile', staticmethod(lambda pid, **kw: {'isHT': 1, 'isIHD': 1}))
        monkeypatch.setattr(patient_target_service, 'latest_values', lambda pid, measures: dict(LATEST))
        monkeypatch.setattr(careplan_service, 'default_header', lambda pid: 'History: Hypertension (invented)')
        monkeypatch.setattr(careplan_service, 'fetch_values', lambda pid, keys: [])
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


def _set_targets(ctx):
    from app.services import patient_target_service, protocol_service
    v = protocol_service.live_version()
    ldl = next(o for o in v.options if o.code == 'ldl_ascvd')
    bp = next(o for o in v.options if o.code == 'bp_high_risk')
    patient_target_service.confirm(PID, ctx.doc, [{'measure_id': ldl.measure_id, 'option_id': ldl.id},
                                                   {'measure_id': bp.measure_id, 'option_id': bp.id}], {'isIHD': 1})


@needs_db
def test_target_sentences_put_value_beside_target_and_never_judge(ctx):
    _set_targets(ctx)
    lines = review.target_sentences(PID, LATEST)
    assert 'Your target Blood pressure is < 130/80 mmHg; no recent value is recorded.' in lines
    ldl = next(l for l in lines if 'LDL' in l)
    assert ldl.startswith('Your target LDL cholesterol is < 1.4 mmol/L and a reduction of at least 50% from baseline;')
    assert ldl.endswith('your last recorded value was 1.9 mmol/L on 03/10/2026.')
    for word in ('met', 'above', 'below target', 'achieved', 'high', 'low'):
        assert f' {word} ' not in f' {ldl} '.replace('reduction', '')


@needs_db
def test_previous_goals_come_from_the_last_filed_plan(ctx):
    from app.models.careplan import Careplan, CareplanRow, CareplanStatus
    plan = Careplan(patient_id=PID, author_id=ctx.doc.id, status=CareplanStatus.filed, filed_at=dec._now())
    ctx.db.session.add(plan)
    ctx.db.session.flush()
    ctx.db.session.add(CareplanRow(careplan_id=plan.id, position=0, issue_label='Hypertension',
                                   goals_text='My goal is to keep my BP at my target [Protocol]\nI will measure this by home readings'))
    ctx.db.session.commit()
    goals = review.previous_goals(PID)
    assert goals == {'hypertension': 'My goal is to keep my BP at my target'}
    assert review.goal_for({'label': 'Hypertension', 'goal': 'carried'}, goals) == 'My goal is to keep my BP at my target'
    assert review.goal_for({'label': 'Gout', 'goal': ''}, goals, 'No flares') == 'No flares'


@needs_db
def test_progress_is_never_carried_into_the_next_plan(ctx):
    from app.models.user import User
    from app.services import protocol_service
    s = dec.open_session(PID, ctx.doc, {'isHT': 1})
    dec.save(s, dec.parse_form(MultiDict([('plan_type', 'review'), ('issue', 'hypertension'),
                                          ('progress_hypertension', 'improved')]), protocol_service.live_version()), proceed=True)
    other = User(username='dr_b', display_name='Dr B', security_level=5, password_hash='x')
    ctx.db.session.add(other)
    ctx.db.session.commit()
    carried = dec.decisions(dec.open_session(PID, other, {'isHT': 1}))
    assert all('progress' not in i for i in carried['issues'])


@needs_db
def test_review_page_and_draft_carry_the_gps_progress(ctx):
    from app.commands.gpccmp import seed_pipeline
    from app.models.careplan import Careplan
    from app.models.pipeline import PipelineRun, RunStatus
    from app.models.system_setting import SystemSetting
    from app.services import gpccmp_draft_service as drafts, protocol_service
    _set_targets(ctx)
    seed_pipeline()
    doc = _client(ctx, ctx.doc)
    body = doc.get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'Progress since the last plan' in body and 'your last recorded value was 1.9 mmol/L' in body
    s = dec.open_session(PID, ctx.doc, {'isHT': 1})
    dec.save(s, dec.parse_form(MultiDict([('plan_type', 'review'), ('issue', 'hypertension'),
                                          ('progress_hypertension', 'improved'), ('progress_note_hypertension', 'invented note')]),
                               protocol_service.live_version()), proceed=True)
    reply = {'issues': [{'issue_key': 'hypertension', 'issue_label': 'Hypertension',
                         'goal': 'My goal is to keep my BP at my target [Protocol]', 'measure': 'I will measure this by home readings [Discussed]',
                         'patient_actions': ['Check my BP at home [Discussed]'], 'team_actions': ['BP each visit [Protocol]'],
                         'services': [], 'review_aim': 'On review I am aiming to look at my readings [Discussed]'}],
             'safety_netting': []}
    run_uuid = str(uuid.uuid4())
    ctx.db.session.add(PipelineRun(run_uuid=run_uuid, pipeline_id=int(SystemSetting.get('gpccmp.pipeline_id')), patient_id=PID,
                                   initiated_by_id=ctx.doc.id, status=RunStatus.completed, redaction_policy='redact_all',
                                   is_redacted=True, is_hcp_redacted=True, model_is_local=False,
                                   output_json=json.dumps({'final_output': json.dumps(reply)})))
    s.check_results = {'run_uuid': run_uuid}
    ctx.db.session.commit()
    assert drafts.poll(s, ctx.doc, PATIENT, {'isHT': 1}, {})['state'] == 'done'
    rows = json.loads(ctx.db.session.get(Careplan, s.careplan_id).draft_json)['rows']
    assert rows[0]['issue_label'] == 'Progress since the last plan (recorded by the GP)'
    assert 'Hypertension: improved. invented note' in rows[0]['management']
    assert 'your last recorded value was 1.9 mmol/L on 03/10/2026' in rows[0]['management']
    assert rows[1]['issue_label'] == 'Hypertension'
