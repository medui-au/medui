"""The AI-drafted GPCCMP (ADR-174). Invented data only; no AI is called.

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

from app.services import gpccmp_draft_service as drafts
from app.services import gpccmp_decision_service as dec

DECISIONS = {
    'plan_type': 'prepare',
    'issues': [
        {'key': 'hypertension', 'label': 'Hypertension', 'source': 'protocol', 'goal': '',
         'directions': 'Continue current medicines; home BP for 1 week', 'services': [{'name': 'Dietitian', 'purpose': 'salt'}]},
        {'key': 'free_0', 'label': 'Left knee pain', 'source': 'gp', 'goal': '', 'directions': 'Physio referral',
         'services': [{'name': 'Physiotherapist', 'purpose': 'strength'}]},
    ],
    'modifiers': {'frail': False, 'palliative': False, 'cognitive': False, 'carer': '', 'adherence': '', 'declined': ''},
    'review_interval': '3 months',
    'consent': {'agrees': True, 'share': False, 'copy_offered': False, 'mhr': False, 'withheld': ''},
    'notes': '', 'format': 'tabular',
}


def good_reply():
    return {
        'issues': [
            {'issue_key': 'hypertension', 'issue_label': 'Hypertension',
             'goal': 'My goal is to keep my blood pressure at my target [Protocol]',
             'measure': 'I will measure this by home blood pressure readings [Discussed]',
             'patient_actions': ['Check my blood pressure at home for one week [Discussed]'],
             'team_actions': ['Continue current medicines [Discussed]', 'Blood pressure each visit [Protocol]'],
             'services': [{'name': 'Dietitian', 'purpose': 'salt'}],
             'review_aim': 'On review I am aiming to look at my home readings [Discussed]'},
            {'issue_key': 'free_0', 'issue_label': 'Left knee pain',
             'goal': 'My goal is to walk further with less pain [Discussed]',
             'measure': 'I will measure this by how far I can walk [Discussed]',
             'patient_actions': ['Do the exercises the physiotherapist gives me [Discussed]'],
             'team_actions': ['Refer to physiotherapy [Discussed]'],
             'services': [{'name': 'Physiotherapist', 'purpose': 'strength'}],
             'review_aim': 'On review I am aiming to talk about my walking [Discussed]'},
        ],
        'safety_netting': ['See your GP sooner if you feel dizzy or faint [Protocol]'],
    }


# ── No database ───────────────────────────────────────────────────────────────

def test_parse_output_tolerates_fences_and_text():
    raw = json.dumps(good_reply())
    assert drafts.parse_output(raw)['issues'][0]['issue_key'] == 'hypertension'
    assert drafts.parse_output('```json\n' + raw + '\n```')['safety_netting']
    assert drafts.parse_output('Here is the plan:\n' + raw + '\nThanks')['issues'][1]['issue_key'] == 'free_0'
    assert drafts.parse_output('not json') is None and drafts.parse_output('{"issues": 3}') is None


def test_a_good_reply_passes_every_check():
    checks = drafts.run_checks(drafts.parse_output(json.dumps(good_reply())), DECISIONS)
    assert all(c['ok'] for c in checks), [c for c in checks if not c['ok']]
    assert {c['key'] for c in checks} == {'issues', 'services', 'targets', 'wording', 'consent', 'doses', 'tags', 'complete'}


def test_the_checks_catch_each_kind_of_overreach():
    bad = good_reply()
    h = bad['issues'][0]
    h['team_actions'].append('Aim for blood pressure below 120/70 [Protocol]')          # a target of its own
    h['patient_actions'].append('Your last reading was too high [Record]')             # a judgement
    h['patient_actions'].append('You agreed to this plan [Discussed]')                 # consent
    h['team_actions'].append('Start amlodipine 5 mg daily [Protocol]')                 # a dose not in directions
    h['services'].append({'name': 'Cardiologist', 'purpose': ''})                     # a service not chosen
    h['measure'] = 'I will measure this by readings'                                  # no tag
    bad['issues'].append({'issue_key': 'diabetes_glucose', 'issue_label': 'Diabetes', 'goal': '', 'measure': '',
                          'patient_actions': [], 'team_actions': [], 'services': [], 'review_aim': ''})
    del bad['issues'][1]                                                               # an issue dropped
    checks = {c['key']: c for c in drafts.run_checks(drafts.parse_output(json.dumps(bad)), DECISIONS)}
    for key in ('issues', 'services', 'targets', 'wording', 'consent', 'doses', 'tags', 'complete'):
        assert not checks[key]['ok'], key
    assert any('diabetes_glucose' in x for x in checks['issues']['details'])
    assert any('Left knee pain' in x for x in checks['issues']['details'])
    assert any('cardiologist' in x for x in checks['services']['details'])


def test_words_from_the_gps_own_directions_are_not_flagged():
    d = json.loads(json.dumps(DECISIONS))
    d['issues'][0]['directions'] = 'Amlodipine 5 mg daily; BP below 140/90 at home'
    r = good_reply()
    r['issues'][0]['team_actions'] = ['Amlodipine 5 mg daily [Discussed]', 'BP below 140/90 at home [Discussed]']
    checks = {c['key']: c for c in drafts.run_checks(drafts.parse_output(json.dumps(r)), d)}
    assert checks['doses']['ok'] and checks['targets']['ok']


def _rule(key, **rule):
    return SimpleNamespace(key=key, label=key, wording=f'{key} wording', rule=rule)


def test_prevention_lines_are_worked_out_by_medui():
    v = SimpleNamespace(prevention=[
        _rule('bowel', age_min=45, age_max=74, flags_none=['isColonCaPolyps']),
        _rule('breast', sex='F', age_min=50, age_max=74),
        _rule('lung', age_min=50, age_max=70, needs='smoking_history'),
        _rule('skin', needs='skin_cancer_history'),
        _rule('diabetes_risk', age_min=40, flags_none=['isDiabetes'])])
    keys = lambda *a, **k: [p['key'] for p in drafts.prevention_lines(v, *a, **k)]
    assert keys(60, 'F', {}, 'Non smoker') == ['bowel', 'breast', 'diabetes_risk']
    assert keys(60, 'M', {'isDiabetes': 1, 'isColonCaPolyps': 1}, 'Ex smoker (2019)') == ['lung']
    assert keys(60, 'F', {}, 'Smoker', palliative=True) == []
    assert keys(None, None, {}, None) == []                       # no age: no age-based line
    assert 'skin' not in keys(60, 'M', {}, None)                  # a fact MedUI doesn't have


def test_smoking_history_and_review_dates():
    assert drafts.has_smoking_history('Ex smoker (2015)') and drafts.has_smoking_history('Smoker')
    assert not drafts.has_smoking_history('Non smoker') and not drafts.has_smoking_history('Never smoked')
    assert not drafts.has_smoking_history('')
    assert drafts.review_due('3 months', date(2026, 11, 30)) == date(2027, 2, 28)
    assert drafts.review_due('12 months', date(2028, 2, 29)) == date(2029, 2, 28)
    assert drafts.review_due('soon') is None


def test_modules_block_holds_only_issues_in_scope():
    v = SimpleNamespace(modules=[SimpleNamespace(condition_key='hypertension', label='Hypertension', goals='Keep my BP',
                                                 measures_text='', monitoring='Each visit', patient_info='', safety_netting='',
                                                 services=['Dietitian']),
                                 SimpleNamespace(condition_key='gout', label='Gout', goals='No flares', measures_text='',
                                                 monitoring='', patient_info='', safety_netting='', services=[])])
    text = drafts.modules_block(v, ['hypertension', 'free_0'])
    assert 'Module hypertension: Hypertension' in text and 'Gout' not in text and 'Standard services: Dietitian' in text


def test_the_system_prompt_forbids_arithmetic_and_judgement():
    from app.services import gpccmp_prompt_seed as seed
    p = seed.SYSTEM_PROMPT
    for phrase in ('DO NO ARITHMETIC', 'Do not compare a value with a range or a target',
                   "laboratory's own flag", 'Never state, choose or change a target', 'OVERRIDES everything else',
                   'Never state that the patient agreed or consented'):
        assert phrase in p, phrase
    assert '{{input.gp_decisions}}' in seed.USER_PROMPT and '{{data.blocks}}' in seed.USER_PROMPT


# ── Database ──────────────────────────────────────────────────────────────────

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')
PID = 4242
PATIENT = {'patient_id': PID, 'INTERNALID': PID, 'SURNAME': 'Example', 'FIRSTNAME': 'Ivy', 'AGE': 61,
           'CCMP_Eligibility': '965'}


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
        monkeypatch.setattr(ClinicalService, 'get_disease_profile', staticmethod(lambda pid, **kw: {'isHT': 1}))
        monkeypatch.setattr(patient_target_service, 'latest_values', lambda pid, measures: {})
        monkeypatch.setattr(careplan_service, 'default_header', lambda pid: 'History: Hypertension (invented)')
        monkeypatch.setattr(careplan_service, 'fetch_values', lambda pid, keys: [
            {'key': 'age', 'value': '61'}, {'key': 'sex', 'value': 'Female'}, {'key': 'smoking', 'value': 'Non smoker'}])
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
def test_seed_adds_new_rows_only_and_runs_once(ctx):
    from app.commands.gpccmp import seed_pipeline
    from app.models.pipeline import Pipeline, PipelineStep
    from app.models.prompt import SystemPrompt, UserPrompt
    existing = SystemPrompt(name='Default Info Sheet Prompt', prompt_text='invented existing text', is_active=True)
    ctx.db.session.add(existing)
    ctx.db.session.commit()
    out = seed_pipeline()
    assert out['made'] == ['system prompt', 'user prompt', 'pipeline']
    assert seed_pipeline()['made'] == []
    assert SystemPrompt.query.filter_by(name='Default Info Sheet Prompt').first().prompt_text == 'invented existing text'
    pl = ctx.db.session.get(Pipeline, out['pipeline_id'])
    assert pl.status.value == 'draft' and pl.redaction_policy.value == 'redact_all' and not pl.show_in_topnav
    steps = PipelineStep.query.filter_by(pipeline_id=pl.id).order_by(PipelineStep.step_order).all()
    assert [s.node_type for s in steps] == ['data_assembly', 'prompt_assembly', 'inference', 'deredaction']
    assert json.loads(steps[0].config_json)['blocks'][0] == 'demographics'
    assert UserPrompt.query.get(out['user_prompt_id']).system_prompt_name == SystemPrompt.query.get(out['system_prompt_id']).name


def _ready_session(ctx):
    from app.services import protocol_service
    s = dec.open_session(PID, ctx.doc, {'isHT': 1})
    form = MultiDict([('issue', 'hypertension'), ('svc_hypertension_1', 'on'), ('svcp_hypertension_1', 'salt'),
                      ('dir_hypertension', 'Continue current medicines; home BP for 1 week'), ('free_label_0', 'Left knee pain'),
                      ('free_dir_0', 'Physio referral'), ('free_svc_0', 'Physiotherapist'), ('free_svcp_0', 'strength'),
                      ('consent_agrees', 'on'), ('review_interval', '3 months')])
    dec.save(s, dec.parse_form(form, protocol_service.live_version()), proceed=True)
    return s


@needs_db
def test_start_refuses_until_everything_is_in_place(ctx, monkeypatch):
    from app.commands.gpccmp import seed_pipeline
    from app.services import careplan_service
    s = dec.open_session(PID, ctx.doc, {})
    with pytest.raises(drafts.DraftError, match='Confirm the plan decisions'):
        drafts.start(s, ctx.doc)
    s = _ready_session(ctx)
    with pytest.raises(drafts.DraftError, match='not set up'):
        drafts.start(s, ctx.doc)
    seed_pipeline()
    with pytest.raises(drafts.DraftError, match='no model yet'):
        drafts.start(s, ctx.doc)
    from app.models.pipeline import Pipeline, PipelineStatus
    from app.models.system_setting import SystemSetting
    pl = ctx.db.session.get(Pipeline, int(SystemSetting.get('gpccmp.pipeline_id')))
    pl.status = PipelineStatus.active
    ctx.db.session.commit()
    plan = careplan_service.start_draft(PID, ctx.doc)                 # a hand-written draft is open
    with pytest.raises(drafts.DraftError, match='already has a care plan draft'):
        drafts.start(s, ctx.doc)
    careplan_service.void_plan(plan, ctx.doc, 'invented')
    ctx.db.session.commit()
    captured = {}
    from app.services.pipeline.engine import PipelineEngine
    monkeypatch.setattr(PipelineEngine, 'run', staticmethod(lambda **kw: captured.update(kw) or 'run-invented'))
    assert drafts.start(s, ctx.doc) == 'run-invented'
    assert '[GP DECISIONS]' in captured['input_data']['gp_decisions']
    assert '(key: hypertension)' in captured['input_data']['gp_decisions']
    assert 'Module hypertension' in captured['input_data']['protocol_modules']
    assert 'Example' not in captured['input_data']['gp_decisions']   # no name in what the AI gets


def _complete_run(ctx, session, reply_text):
    from app.models.pipeline import PipelineRun, RunStatus
    from app.models.system_setting import SystemSetting
    run_uuid = str(uuid.uuid4())
    cols = {c.name for c in PipelineRun.__table__.columns}
    run = PipelineRun(**{k: v for k, v in dict(run_uuid=run_uuid, pipeline_id=int(SystemSetting.get('gpccmp.pipeline_id')),
                                                patient_id=PID, initiated_by_id=ctx.doc.id, status=RunStatus.completed,
                                                redaction_policy='redact_all', is_redacted=True, is_hcp_redacted=True,
                                                model_is_local=False,
                                                output_json=json.dumps({'final_output': reply_text})).items() if k in cols})
    ctx.db.session.add(run)
    session.check_results = {'run_uuid': run_uuid}
    ctx.db.session.commit()
    return run


@needs_db
def test_a_completed_run_becomes_a_checked_care_plan_draft(ctx):
    from app.commands.gpccmp import seed_pipeline
    from app.models.careplan import Careplan
    from app.services import patient_target_service, protocol_service
    seed_pipeline()
    bp = next(o for o in protocol_service.live_version().options if o.code == 'bp_high_risk')
    patient_target_service.confirm(PID, ctx.doc, [{'measure_id': bp.measure_id, 'option_id': bp.id}], {'isHT': 1})
    s = _ready_session(ctx)
    _complete_run(ctx, s, '```json\n' + json.dumps(good_reply()) + '\n```')
    out = drafts.poll(s, ctx.doc, PATIENT, {'isHT': 1}, {'age': '61', 'sex': 'Female', 'smoking': 'Non smoker'})
    assert out == {'state': 'done', 'careplan_id': s.careplan_id} and s.status.value == 'drafted'
    assert all(c['ok'] for c in s.check_results['checks'])
    plan = ctx.db.session.get(Careplan, s.careplan_id)
    data = json.loads(plan.draft_json)
    assert data['header'].startswith('DRAFT GP Chronic Condition Management Plan')
    assert 'Blood pressure: < 130/80 mmHg' in data['header'] and 'History: Hypertension (invented)' in data['header']
    labels = [r['issue_label'] for r in data['rows']]
    assert labels[:2] == ['Hypertension', 'Left knee pain']
    assert 'Preventive health (for information)' in labels and 'Review arrangements' in labels
    consent = next(r for r in data['rows'] if r['issue_label'].startswith('Consent'))['management']
    assert 'agrees to the plan: yes' in consent and 'My Health Record: not recorded (GP to complete)' in consent
    prev = next(r for r in data['rows'] if r['issue_label'].startswith('Preventive'))['management']
    assert 'Bowel cancer screening' in prev and 'Breast screening' in prev and 'Prostate' not in prev
    assert plan.review_due_on == drafts.review_due('3 months')
    assert drafts.poll(s, ctx.doc, PATIENT, {}, {})['state'] == 'done'      # idempotent
    # Draft again voids the draft and returns the decisions to confirmed.
    drafts.redraft(s, ctx.doc)
    ctx.db.session.refresh(plan)
    assert plan.status.value == 'void' and s.status.value == 'ready' and s.careplan_id is None


@needs_db
def test_an_unreadable_reply_fails_without_a_draft(ctx):
    from app.commands.gpccmp import seed_pipeline
    seed_pipeline()
    s = _ready_session(ctx)
    _complete_run(ctx, s, 'Sorry, I cannot help with that.')
    out = drafts.poll(s, ctx.doc, PATIENT, {}, {})
    assert out['state'] == 'failed' and s.careplan_id is None and s.status.value == 'ready'


@needs_db
def test_bp_button_sends_the_plan_in_place(ctx, monkeypatch):
    from app.services import careplan_service
    sent = {}
    import app.utils.pit_utils as pit
    monkeypatch.setattr(pit, 'send_as_pit', lambda **kw: sent.update(kw) or True)
    plan = careplan_service.start_draft(PID, ctx.doc)
    data = careplan_service.draft_data(plan)
    data['rows'][0]['issue_label'] = 'Hypertension'
    careplan_service.save_draft(plan, ctx.doc, plan.draft_revision, data)
    r = _client(ctx, ctx.doc).post(f'/careplan/plan/{plan.id}/export-bp')
    assert r.status_code == 200 and r.get_json() == {'ok': True}
    assert 'Hypertension' in sent['body'] and sent['patient']['INTERNALID'] == PID
    body = _client(ctx, ctx.doc).get(f'/careplan/plan/{plan.id}/edit').get_data(as_text=True)
    assert 'data-bp-url' in body and 'cp-bp-tick' in body


def test_blank_lines_are_dropped_from_the_printed_plan_only():
    from app.services import careplan_service as cps
    assert cps.no_blank_lines('History:\n\n  \nHypertension  \n\n\nMedicines: none\n') == 'History:\nHypertension\nMedicines: none'
    assert cps.no_blank_lines(None) == '' and cps.no_blank_lines('one line') == 'one line'
    data = {'header': 'A\n\n\nB', 'rows': [{'issue_label': 'Gout', 'goals': 'x\n\ny', 'management': '\n- a\n\n- b\n',
                                            'providers': 'Physio\n\n'}], 'values': {}}
    out = cps.compact(data)
    assert out['header'] == 'A\nB' and out['rows'][0]['goals'] == 'x\ny'
    assert out['rows'][0]['management'] == '- a\n- b' and out['rows'][0]['providers'] == 'Physio'
    assert data['header'] == 'A\n\n\nB'                      # the draft itself is unchanged


@needs_db
def test_print_preview_and_export_have_no_blank_lines(ctx):
    from app.services import careplan_service as cps
    plan = cps.start_draft(PID, ctx.doc)
    data = cps.draft_data(plan)
    data['header'] = 'Past history:\n\n\nHypertension\n\n'
    data['rows'][0].update(issue_label='Hypertension', goals='Goal one\n\n\nGoal two', management='- a\n\n- b')
    cps.save_draft(plan, ctx.doc, plan.draft_revision, data)
    html = cps.render_document(plan, cps.draft_data(plan), PATIENT, 'Dr A', None)
    assert 'Hypertension\n\n' not in html.split('</strong>', 1)[-1].split('</div>', 1)[0]
    assert 'Goal one\nGoal two' in html
    md = cps.plan_markdown(plan, cps.draft_data(plan), PATIENT, 'Dr A', None)
    assert '- Goal one\n- Goal two' in md
    assert '\n\n' in cps.draft_data(plan)['header']                  # the draft keeps what was typed


def _models(ctx):
    from app.models.ai_provider import AIModel, AIProviderConfig
    prov = AIProviderConfig(name='Invented cloud', provider_key='invented_cloud', base_url='http://127.0.0.1:1', is_local=False)
    ctx.db.session.add(prov)
    ctx.db.session.flush()
    shown = AIModel(provider_id=prov.id, model_id='invented-a', display_name='Invented A', show_in_ai_assist=True)
    hidden = AIModel(provider_id=prov.id, model_id='invented-b', display_name='Invented B', show_in_ai_assist=False)
    ctx.db.session.add_all([shown, hidden])
    ctx.db.session.commit()
    return shown, hidden


@needs_db
def test_the_gp_can_choose_the_model_for_a_draft(ctx, monkeypatch):
    from app.commands.gpccmp import seed_pipeline
    shown, hidden = _models(ctx)
    seed_pipeline(model_id=hidden.id)                       # the pipeline's own model
    assert [m.id for m in drafts.available_models()] == [shown.id]
    assert drafts.default_model().id == hidden.id and drafts.model_label(hidden) == 'Invented B (cloud)'
    captured = {}
    from app.services.pipeline.engine import PipelineEngine
    monkeypatch.setattr(PipelineEngine, 'run', staticmethod(lambda **kw: captured.update(kw) or 'run-x'))
    s = _ready_session(ctx)
    drafts.start(s, ctx.doc)                                # no choice: the pipeline default, no override
    assert 'model_id_override' not in captured['input_data']
    assert s.check_results['model_id'] == hidden.id and not s.check_results['model_chosen']
    drafts.start(s, ctx.doc, shown.id)                      # the GP's choice goes to the engine
    assert captured['input_data']['model_id_override'] == shown.id
    assert s.check_results['model'] == 'Invented A (cloud)' and s.check_results['model_chosen']
    with pytest.raises(drafts.DraftError):                  # only models the AI Assistant offers
        drafts.start(s, ctx.doc, hidden.id)
    body = _client(ctx, ctx.doc).get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'Pipeline default: Invented B (cloud)' in body and 'Invented A (cloud)' in body


def test_printed_plan_has_no_source_tags_or_draft_line():
    from app.services import careplan_service as cps
    assert drafts.DRAFT_LINE.startswith(cps._DRAFT_LINE_PREFIX)
    header = drafts.DRAFT_LINE + '\n\nPlan: Prepare\nTARGETS FOR THIS PLAN (set by the GP)\n- Blood pressure: < 130/80 mmHg'
    out = cps.compact({'header': header, 'rows': [{
        'issue_label': 'Hypertension', 'goals': 'My goal is to keep my BP at target [Protocol]\nI will measure this by home readings [Discussed]',
        'management': 'I will achieve this by:\n- Check my BP at home [Discussed]\n- Bring readings  [Record]',
        'providers': 'Dietitian: salt'}]})
    assert 'DRAFT' not in out['header'] and out['header'].startswith('Plan: Prepare')
    r = out['rows'][0]
    assert '[' not in r['goals'] + r['management']
    assert r['goals'] == 'My goal is to keep my BP at target\nI will measure this by home readings'
    assert r['management'] == 'I will achieve this by:\n- Check my BP at home\n- Bring readings'
    assert cps.for_document('A [Other] tag stays') == 'A [Other] tag stays'


@needs_db
def test_the_draft_keeps_its_tags_and_the_document_does_not(ctx):
    from app.commands.gpccmp import seed_pipeline
    from app.models.careplan import Careplan
    from app.services import careplan_service as cps
    seed_pipeline()
    s = _ready_session(ctx)
    _complete_run(ctx, s, json.dumps(good_reply()))
    drafts.poll(s, ctx.doc, PATIENT, {'isHT': 1}, {'age': '61', 'sex': 'Female', 'smoking': 'Non smoker'})
    plan = ctx.db.session.get(Careplan, s.careplan_id)
    data = cps.draft_data(plan)
    assert '[Protocol]' in data['rows'][0]['goals'] and data['header'].startswith('DRAFT')    # the editor keeps them
    html = cps.render_document(plan, data, PATIENT, 'Dr A', None)
    md = cps.plan_markdown(plan, data, PATIENT, 'Dr A', None)
    for text in (html, md):
        assert '[Protocol]' not in text and '[Discussed]' not in text and '[Record]' not in text
        assert 'DRAFT GP Chronic' not in text


@needs_db
def test_the_decisions_page_links_an_open_draft(ctx):
    from app.services import careplan_service as cps
    _ready_session(ctx)
    plan = cps.start_draft(PID, ctx.doc)
    body = _client(ctx, ctx.doc).get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'A care plan draft is already open' in body and f'/careplan/plan/{plan.id}/edit' in body


@needs_db
def test_buttons_save_before_moving_on(ctx, monkeypatch):
    """Save and continue saves the targets; Proceed with GPCCMP saves and confirms exactly what is on the
    page, then drafts from it (ADR-177)."""
    from app.commands.gpccmp import seed_pipeline
    from app.models.pipeline import Pipeline, PipelineStatus
    from app.models.system_setting import SystemSetting
    from app.services import patient_target_service, protocol_service
    from app.services.pipeline.engine import PipelineEngine
    seed_pipeline()
    pl = ctx.db.session.get(Pipeline, int(SystemSetting.get('gpccmp.pipeline_id')))
    pl.status = PipelineStatus.active
    ctx.db.session.commit()
    captured = {}
    monkeypatch.setattr(PipelineEngine, 'run', staticmethod(lambda **kw: captured.update(kw) or 'run-y'))
    doc = _client(ctx, ctx.doc)
    bp = next(o for o in protocol_service.live_version().options if o.code == 'bp_high_risk')
    r = doc.post(f'/gpccmp/patient/{PID}/targets',
                 data={'action': 'continue', 'measure': [str(bp.measure_id)], f'choice_{bp.measure_id}': str(bp.id)})
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/gpccmp/patient/{PID}/plan')
    assert patient_target_service.current_targets(PID)[bp.measure_id].option_id == bp.id
    r = doc.post(f'/gpccmp/patient/{PID}/plan', data=MultiDict([
        ('action', 'draft'), ('plan_type', 'prepare'), ('issue', 'hypertension'),
        ('dir_hypertension', 'A direction typed just before drafting'), ('review_interval', '3 months'), ('format', 'tabular')]))
    assert r.status_code == 302 and '/gpccmp/session/' in r.headers['Location']
    s = dec.open_session(PID, ctx.doc)
    assert s.status.value == 'ready' and dec.decisions(s)['issues'][0]['directions'] == 'A direction typed just before drafting'
    assert 'A direction typed just before drafting' in captured['input_data']['gp_decisions']
    page = doc.get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'data-unsaved-guard' in page and 'unsaved_guard.js' in page and 'Proceed with GPCCMP →' in page
    assert 'value="proceed"' not in page                      # two buttons only: Save decisions, Proceed with GPCCMP


@needs_db
def test_recipe_assist_offers_and_passes_a_model_choice(ctx, monkeypatch):
    """ADR-178: the recipe page's AI assist takes a model for the run, from the same list."""
    from app.models.pipeline import Pipeline, PipelineStatus, RedactionPolicy
    from app.services.pipeline.engine import PipelineEngine
    shown, hidden = _models(ctx)
    pl = Pipeline(name='Invented recipe assistant', classifier='[RECIPE]', status=PipelineStatus.active,
                  redaction_policy=RedactionPolicy.redact_all)
    ctx.db.session.add(pl)
    ctx.db.session.commit()
    captured = {}
    monkeypatch.setattr(PipelineEngine, 'run', staticmethod(lambda **kw: captured.update(kw) or 'run-r'))
    doc = _client(ctx, ctx.doc)
    page = doc.get('/careplan/recipes/new').get_data(as_text=True)
    assert 'id="rc-model"' in page and "The pipeline's own model" in page and 'Invented A (cloud)' in page
    assert 'Invented B' not in page                                    # not offered in AI Assist
    r = doc.post('/careplan/recipes/assist', json={'text': 'Gout (invented)', 'pipeline_id': pl.id, 'model_id': shown.id})
    assert r.status_code == 200 and captured['input_data']['model_id_override'] == shown.id
    r = doc.post('/careplan/recipes/assist', json={'text': 'Gout (invented)', 'pipeline_id': pl.id})
    assert r.status_code == 200 and 'model_id_override' not in captured['input_data']
    r = doc.post('/careplan/recipes/assist', json={'text': 'Gout (invented)', 'pipeline_id': pl.id, 'model_id': hidden.id})
    assert r.status_code == 400


@needs_db
def test_with_ai_off_the_draft_step_is_closed(ctx):
    """This edition: targets, protocols and decisions work with AI off; the draft doesn't."""
    ctx.app.config['AI_ENABLED'] = False
    _ready_session(ctx)
    doc = _client(ctx, ctx.doc)
    page = doc.get(f'/gpccmp/patient/{PID}/plan').get_data(as_text=True)
    assert 'value="draft"' not in page and 'needs AI switched on' in page
    assert doc.get(f'/gpccmp/patient/{PID}/targets').status_code == 200
    r = doc.post(f'/gpccmp/patient/{PID}/plan', data=MultiDict([('action', 'draft'), ('issue', 'hypertension')]))
    assert r.status_code == 403


def test_install_seeds_adds_the_drafting_workflow_as_a_draft():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / 'app' / 'commands' / 'install.py').read_text()
    assert text.count('        _seed_gpccmp_pipeline()') == 2   # called by install seeds and by resync-seeds
