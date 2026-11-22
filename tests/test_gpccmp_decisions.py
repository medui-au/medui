"""GPCCMP plan decisions (ADR-173). Invented data only.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway PostgreSQL database ending in _test (schema created with db.create_all()).
"""
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from app.services import gpccmp_decision_service as dec


def _version():
    mods = [SimpleNamespace(condition_key='hypertension', label='Hypertension', applies_when={'any': ['isHT']},
                            services=['Pharmacist (medicine review)', 'Dietitian'], goals='Keep my BP at target.'),
            SimpleNamespace(condition_key='gout', label='Gout', applies_when=None, services=[], goals='')]
    return SimpleNamespace(version=1, modules=mods)


# ── No database ───────────────────────────────────────────────────────────────

def test_issues_are_ticked_only_by_coded_conditions():
    choices = {c['key']: c['coded'] for c in dec.issue_choices(_version(), {'isHT': 1})}
    assert choices == {'hypertension': True, 'gout': False}


def test_parse_form_keeps_only_offered_services_and_gp_text():
    form = MultiDict([('plan_type', 'prepare'), ('issue', 'hypertension'), ('issue', 'not_a_module'),
                      ('svc_hypertension_1', 'on'), ('svcp_hypertension_1', 'salt and weight'),
                      ('svc_other_hypertension', 'Exercise physiologist'), ('svcp_other_hypertension', 'strength'),
                      ('dir_hypertension', 'Continue current medicines; home BP for 1 week'),
                      ('free_label_0', 'Left knee pain'), ('free_svc_0', 'Physiotherapist'),
                      ('mod_frail', 'on'), ('review_interval', '6 months'), ('consent_share', 'on')])
    d = dec.parse_form(form, _version())
    assert [i['key'] for i in d['issues']] == ['hypertension', 'free_0']
    assert d['issues'][0]['services'] == [{'name': 'Dietitian', 'purpose': 'salt and weight'},
                                         {'name': 'Exercise physiologist', 'purpose': 'strength'}]
    assert d['issues'][1] == {'key': 'free_0', 'label': 'Left knee pain', 'source': 'gp', 'goal': '', 'directions': '',
                              'services': [{'name': 'Physiotherapist', 'purpose': ''}]}
    assert d['modifiers']['frail'] and not d['modifiers']['palliative']
    assert d['review_interval'] == '6 months' and d['consent']['share'] and not d['consent']['agrees']


def test_parse_form_refuses_unknown_choices():
    for bad in ({'plan_type': 'other'}, {'review_interval': '5 weeks'}, {'format': 'poem'}):
        with pytest.raises(dec.DecisionError):
            dec.parse_form(MultiDict(bad), _version())
    with pytest.raises(dec.DecisionError):
        dec.parse_form(MultiDict({'notes': 'x' * (dec.MAX_TEXT + 1)}), _version())


def test_plan_type_starts_from_the_billing_record():
    assert dec.plan_type_from_eligibility('967') == 'review'
    assert dec.plan_type_from_eligibility('965') == 'prepare' and dec.plan_type_from_eligibility(None) == 'prepare'


def test_problems_block_proceed():
    assert dec.problems({'issues': []}) == ['Choose at least one issue for the plan.']
    assert dec.problems({'issues': [{}], 'modifiers': {'cognitive': True, 'carer': ''}})
    assert dec.problems({'issues': [{}], 'modifiers': {'cognitive': True, 'carer': 'daughter'}}) == []


def test_decisions_block_states_everything_and_marks_unrecorded_consent():
    d = dec.parse_form(MultiDict([('issue', 'hypertension'), ('svc_hypertension_0', 'on'),
                                  ('dir_hypertension', 'Recheck in 2 weeks'), ('consent_agrees', 'on'),
                                  ('mod_palliative', 'on')]), _version())
    text = dec.decisions_block(d, [{'measure': 'Blood pressure', 'target': '< 130/80 mmHg', 'basis': 'default'}],
                               _version())
    assert text.startswith('[GP DECISIONS]') and text.endswith('[/GP DECISIONS]')
    assert '- Blood pressure: < 130/80 mmHg (protocol default)' in text
    assert 'Palliative / terminal illness' in text and 'GP directions: Recheck in 2 weeks' in text
    assert 'Service / referral: Pharmacist (medicine review)' in text
    assert 'took part in setting the goals and agrees to the plan: yes' in text
    assert 'consents to upload to My Health Record: not recorded' in text
    assert 'Review: in 3 months' in text
    assert '- none set' in dec.decisions_block(d, [], None)


# ── Database ──────────────────────────────────────────────────────────────────

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')
PID = 4242
PATIENT = {'patient_id': PID, 'SURNAME': 'Example', 'FIRSTNAME': 'Ivy', 'AGE': 61, 'CCMP_Eligibility': '965'}


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
                     nurse=User(username='rn_a', display_name='Nurse A', security_level=3, password_hash='x'),
                     admin=User(username='adm', display_name='Admin', security_level=9, password_hash='x'))
        db.session.add_all(users.values())
        db.session.commit()
        from app.commands.protocol import seed_v1
        from app.services import protocol_service
        seed_v1(users['admin'].id)
        protocol_service.approve(users['admin'], date.today() + timedelta(days=365))
        from app.services.clinical_service import ClinicalService
        from app.services import patient_target_service
        monkeypatch.setattr(ClinicalService, 'get_patient_demographics', staticmethod(lambda pid: dict(PATIENT)))
        monkeypatch.setattr(ClinicalService, 'get_disease_profile',
                            staticmethod(lambda pid, **kw: {'isDiabetes': 1, 'isHT': 1}))
        monkeypatch.setattr(patient_target_service, 'latest_values', lambda pid, measures: {})
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
def test_session_saves_then_proceeds(ctx):
    from app.services import protocol_service
    s = dec.open_session(PID, ctx.doc)
    assert dec.open_session(PID, ctx.doc).id == s.id           # one open session per doctor and patient
    version = protocol_service.live_version()
    with pytest.raises(dec.DecisionError):
        dec.save(s, dec.parse_form(MultiDict({}), version), proceed=True)
    assert s.status.value == 'draft'
    d = dec.parse_form(MultiDict([('issue', 'hypertension'), ('dir_hypertension', 'Invented direction')]), version)
    dec.save(s, d, proceed=True)
    assert s.status.value == 'ready' and s.confirmed_at and dec.decisions(s)['issues'][0]['directions'] == 'Invented direction'
    assert s.protocol_version_id == version.id
    dec.abandon(s)
    assert dec.open_session(PID, ctx.doc).id != s.id


@needs_db
def test_screen_for_doctors_only_with_preview(ctx):
    url = f'/gpccmp/patient/{PID}/plan'
    assert _client(ctx, ctx.nurse).get(url).status_code == 403
    doc = _client(ctx, ctx.doc)
    body = doc.get(url).get_data(as_text=True)
    assert 'Hypertension' in body and 'coded in the record' in body and 'a new plan (965) is due' in body
    assert 'What the AI will be given' not in body              # nothing saved yet
    r = doc.post(url, data=MultiDict([('action', 'proceed'), ('plan_type', 'prepare'), ('issue', 'hypertension'),
                                      ('svc_hypertension_1', 'on'), ('dir_hypertension', 'Invented direction'),
                                      ('review_interval', '3 months'), ('format', 'tabular')]))
    assert r.status_code == 302
    body = doc.get(url).get_data(as_text=True)
    assert 'What the AI will be given' in body and '[GP DECISIONS]' in body and 'Invented direction' in body
    assert 'Example' not in body.split('[GP DECISIONS]')[1].split('[/GP DECISIONS]')[0]   # no name in the block
    targets_page = doc.get(f'/gpccmp/patient/{PID}/targets').get_data(as_text=True)
    assert 'Save and continue to plan decisions' in targets_page


@needs_db
def test_next_plan_carries_forward_but_never_consent(ctx):
    from app.models.user import User
    from app.services import protocol_service
    version = protocol_service.live_version()
    other = User(username='dr_b', display_name='Dr B', security_level=5, password_hash='x')
    ctx.db.session.add(other)
    ctx.db.session.commit()
    first = dec.open_session(PID, ctx.doc, {'isHT': 1})
    assert dec.decisions(first) == {}                                  # nothing to carry yet
    d = dec.parse_form(MultiDict([
        ('issue', 'hypertension'), ('goal_hypertension', 'Invented goal'), ('dir_hypertension', 'Invented direction'),
        ('svc_hypertension_1', 'on'), ('svcp_hypertension_1', 'invented purpose'),
        ('free_label_0', 'Invented issue'), ('free_dir_0', 'Invented free direction'),
        ('mod_frail', 'on'), ('review_interval', '6 months'), ('consent_agrees', 'on'), ('consent_mhr', 'on'),
        ('consent_withheld', 'invented withheld'), ('notes', 'Invented note')]), version)
    dec.save(first, d, proceed=True)
    # A colleague starts the next plan; diabetes has been coded since.
    nxt = dec.open_session(PID, other, {'isHT': 1, 'isDiabetes': 1})
    carried = dec.decisions(nxt)
    assert carried['carried_from']['session_id'] == first.id and carried['carried_from']['by'] == 'Dr A'
    by_key = {i['key']: i for i in carried['issues']}
    ht = by_key['hypertension']
    assert ht['goal'] == 'Invented goal' and ht['directions'] == 'Invented direction'
    assert ht['services'] == [{'name': 'Dietitian', 'purpose': 'invented purpose'}]
    assert by_key['free_0']['label'] == 'Invented issue' and by_key['free_0']['directions'] == 'Invented free direction'
    assert by_key['diabetes_glucose'].get('new_since_last') and by_key['cv_risk'].get('new_since_last')
    assert carried['modifiers']['frail'] and carried['review_interval'] == '6 months' and carried['notes'] == 'Invented note'
    assert not any(carried['consent'][k] for k in dec.CONSENT) and carried['consent']['withheld'] == ''
    assert 'plan_type' not in carried
    # The page says where it came from and marks the new issues.
    body = _client(ctx, other).get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'Started from the plan of' in body and 'new since the last plan' in body and 'Invented direction' in body
    # Saving keeps the record of where it came from.
    dec.save(nxt, dec.parse_form(MultiDict([('issue', 'hypertension')]), version))
    assert dec.decisions(nxt)['carried_from']['session_id'] == first.id


@needs_db
def test_a_retired_module_becomes_the_gps_own_issue(ctx):
    from app.services import protocol_service
    version = protocol_service.live_version()
    s = dec.open_session(PID, ctx.doc, {})
    dec.save(s, dec.parse_form(MultiDict([('issue', 'gout'), ('dir_gout', 'Invented')]), version), proceed=True)
    nv = SimpleNamespace(version=2, modules=[m for m in version.modules if m.condition_key != 'gout'])
    carried = dec.carry_forward(PID, nv, {})
    assert carried['issues'][0]['source'] == 'gp' and carried['issues'][0]['label'] == 'Gout'
    assert carried['issues'][0]['key'] == 'free_0' and carried['issues'][0]['directions'] == 'Invented'
