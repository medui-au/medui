"""Care plan builder (ADR-129). Invented data only.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway PostgreSQL database ending in _test (schema created with db.create_all()).
"""
import json
import os
from datetime import date
from types import SimpleNamespace

import pytest

from app.services import careplan_service as svc


# ── No database ───────────────────────────────────────────────────────────────

def test_issue_key_matches_coded_history_to_recipes():
    assert svc.issue_key('TYPE 2 DIABETES') == 'type_2_diabetes'
    assert svc.issue_key('Osteoarthritis knee (L)') == 'osteoarthritis_knee'
    assert svc.issue_key('  Gout ') == 'gout'


def test_tokens_in_finds_each_key_once():
    assert svc.tokens_in('Urate {urate.last} on {urate.date}', 'aim {urate.target}; LDL {ldl.last}') == ['urate', 'ldl']
    assert svc.tokens_in('no tokens {here}', None) == []


def _token(**kw):
    base = dict(key='urate', label='Uric acid', loinc_codes=['1111-1', '2222-2'], expected_unit='mmol/L',
                max_age_days=None)
    base.update(kw)
    return SimpleNamespace(**base)


ROWS = [
    {'ReportDate': '2026-01-10', 'LoincCode': '1111-1   ', 'ResultValue': '0.52', 'Units': 'mmol/L'},
    {'ReportDate': '2026-09-01', 'LoincCode': '2222-2', 'ResultValue': '0.41', 'Units': 'mmol/L'},
    {'ReportDate': '2026-10-01', 'LoincCode': '9999-9', 'ResultValue': '7.0', 'Units': '%'},
]


def test_pick_latest_takes_the_newest_matching_result_with_padded_codes():
    v = svc.pick_latest(ROWS, _token(), date(2026, 10, 31))
    assert (v['value'], v['date'], v['loinc'], v['status']) == ('0.41', '2026-09-01', '2222-2', 'found')


def test_pick_latest_reports_a_different_unit_without_converting():
    rows = [{'ReportDate': '2026-09-01', 'LoincCode': '1111-1', 'ResultValue': '410', 'Units': 'umol/L'}]
    v = svc.pick_latest(rows, _token(), date(2026, 10, 31))
    assert v['status'] == 'unit_mismatch' and v['value'] == '410' and v['unit'] == 'umol/L'


def test_pick_latest_marks_old_results_and_missing_ones():
    assert svc.pick_latest(ROWS, _token(max_age_days=30), date(2026, 10, 31))['status'] == 'stale'
    assert svc.pick_latest(ROWS, _token(loinc_codes=['0000-0']), date(2026, 10, 31))['status'] == 'not_found'


def test_pick_latest_keeps_the_laboratory_wording():
    rows = [{'ReportDate': '2026-09-01', 'LoincCode': '1111-1', 'ResultValue': '<0.10', 'Units': 'mmol/L'}]
    assert svc.pick_latest(rows, _token(), date(2026, 10, 31))['value'] == '<0.10'


def test_pick_latest_treats_a_blank_unit_as_unknown_and_lab_spellings_as_equal():
    blank = [{'ReportDate': '2026-09-01', 'LoincCode': '1111-1', 'ResultValue': '0.41', 'Units': ''}]
    assert svc.pick_latest(blank, _token(), date(2026, 10, 31))['status'] == 'found'
    sqm = [{'ReportDate': '2026-09-01', 'LoincCode': '1111-1', 'ResultValue': '72', 'Units': 'mL/min/1.73 sqm'}]
    assert svc.pick_latest(sqm, _token(expected_unit='mL/min/1.73m2'), date(2026, 10, 31))['status'] == 'found'
    assert svc.norm_unit('mL/min/1.73m*2') == svc.norm_unit('ml/min/1.73 m2')
    assert svc.norm_unit('mg/mmol creat') == svc.norm_unit('mg/mmol') != svc.norm_unit('mmol/mol')


def _cat(code, name, unit, n):
    return {'LoincCode': code + '  ', 'ResultName': name, 'Units': unit, 'Results': n, 'LastDate': '2026-09-01'}


def test_catalogue_suggests_codes_sharing_a_name_and_unit_without_chaining():
    rows = [
        _cat('1001-1', 'Widget level', 'mmol/L', 900), _cat('1001-1', 'Widget', 'mmol/L', 100),
        _cat('1002-2', 'Widget', 'mmol/L', 40),                  # same name, same unit: suggested
        _cat('1003-3', 'Widget', 'umol/L', 30),                  # same name, other unit: not
        _cat('1003-3', 'Gadget', 'umol/L', 30),
        _cat('1004-4', 'Gadget', 'umol/L', 20),                  # linked to 1003-3 only, never chained to 1001-1
        _cat('1005-5', 'Widget level', 'mmol/L', 1), _cat('1005-5', 'Other', '', 99),
    ]
    cat = {c['code']: c for c in svc.build_catalogue(rows)}
    assert cat['1001-1']['n'] == 1000 and cat['1001-1']['names'][0] == 'Widget level'
    assert cat['1001-1']['related'] == ['1002-2']
    assert cat['1003-3']['related'] == ['1004-4']
    assert '1001-1' not in cat['1004-4']['related']
    # 1005-5's only mmol/L results are a stray 1%: no shared main unit, so not suggested.
    assert '1005-5' not in cat['1001-1']['related']
    assert [c['code'] for c in svc.build_catalogue(rows)][0] == '1001-1'


DEMO = {'WEIGHTVALUE': 92, 'WEIGHT_DATE': '2026-08-01', 'HEIGHTVALUE': '1.75', 'HEIGHT_DATE': '2025-02-01',
        'CLINICAL_AGE': '67y', 'GENDER': 'Male'}
BP_ROWS = [{'ReportDate': '2026-06-01', 'Systolic': 150, 'Diastolic': 90},
           {'ReportDate': '2026-09-15', 'Systolic': 128, 'Diastolic': 76}]


def test_record_facts_are_as_recorded_or_arithmetic():
    f = svc.facts_from(DEMO, BP_ROWS, {'ALCOHOLPERWEEK': '10 (over 5 days)', 'SMOKING': 'Ex smoker (2015)'},
                       date(2026, 10, 31))
    assert f['bp'] == ('128/76', 'mmHg', '2026-09-15')           # systolic and diastolic from one reading
    assert f['weight'] == ('92', 'kg', '2026-08-01') and f['height'] == ('1.75', 'm', '2025-02-01')
    assert f['bmi'] == ('30.0', 'kg/m2', '2026-08-01')
    assert f['weight_excess'] == ('+15', 'kg', '2026-08-01')     # 92 - 25 x 1.75^2
    assert f['age'] == ('67', 'years', '2026-10-31') and f['sex'] == ('Male', '', None)
    assert f['alcohol'][0] == '10 (over 5 days)' and f['smoking'][0] == 'Ex smoker (2015)'
    light = svc.facts_from({**DEMO, 'WEIGHTVALUE': 55}, [], {'ALCOHOLPERWEEK': 'No Data'}, date(2026, 10, 31))
    assert light['weight_excess'][0] == '-6' and 'bp' not in light and 'alcohol' not in light
    assert svc.facts_from({'GENDER': 'Unknown', 'CLINICAL_AGE': '7m'}, None, None, date(2026, 10, 31)) == \
        {'age': ('7m', '', '2026-10-31')}


def test_fact_value_marks_old_dated_facts_only():
    f = svc.facts_from(DEMO, BP_ROWS, None, date(2026, 10, 31))
    assert svc.fact_value(_token(key='bp', max_age_days=30), f, date(2026, 10, 31))['status'] == 'stale'
    assert svc.fact_value(_token(key='sex', max_age_days=1), f, date(2026, 10, 31))['status'] == 'found'
    assert svc.fact_value(_token(key='smoking'), f, date(2026, 10, 31))['status'] == 'not_found'


def test_render_text_fills_values_targets_and_dashes():
    values = {'urate': {'value': '0.41', 'unit': 'mmol/L', 'date': '2026-09-01'}}
    out = svc.render_text('Urate {urate.last} ({urate.date}), target {urate.target}; LDL {ldl.last}',
                          values, {'urate': '< 0.36 mmol/L'})
    assert out == 'Urate 0.41 mmol/L (01/09/2026), target < 0.36 mmol/L; LDL —'


def test_validate_draft_cleans_shape_and_drops_page_supplied_values():
    clean = svc.validate_draft({'header': 'h', 'rows': [
        {'issue_label': 'Gout', 'issue_source': 'evil', 'goals': 'g', 'recipe_id': '7',
         'targets': {'urate': '< 0.36', 'BAD KEY': 'x'}}], 'values': {'urate': {'value': '1'}}})
    row = clean['rows'][0]
    assert row['issue_source'] == 'free_text' and row['recipe_id'] is None
    assert row['targets'] == {'urate': '< 0.36'}
    with pytest.raises(svc.CareplanError):
        svc.validate_draft({'rows': 'nope'})


def test_header_headings_are_bold_and_text_escaped():
    html = str(svc.header_html('History: Gout (2020)\nMedications: Allopurinol <b>\n  not a heading: x\nno colon'))
    assert html.startswith('<strong>History:</strong> Gout (2020)')
    assert '<strong>Medications:</strong> Allopurinol &lt;b&gt;' in html
    assert '<strong>  not' not in html and html.endswith('no colon')
    assert str(svc.header_html('<i>Bad</i>: x')) == '&lt;i&gt;Bad&lt;/i&gt;: x'


def test_completeness_checks_the_document_not_the_patient():
    data = {'rows': [
        {'issue_label': 'Gout', 'goals': 'g', 'management': 'Urate {urate.last}', 'providers': '',
         'targets': {'urate': '< 0.36'}},
        {'issue_label': 'CKD', 'goals': 'g', 'management': 'm', 'providers': 'p', 'targets': {'urate': '< 0.30'}},
        {'issue_label': '', 'goals': '', 'management': '', 'providers': ''}], 'values': {}}
    notes = svc.completeness(data)
    assert 'Row 1 (Gout): no providers.' in notes
    assert 'Row 1 (Gout): no value fetched for urate.' in notes
    assert 'urate has different targets in rows 1 and 2.' in notes
    assert not any('met' in n or 'abnormal' in n.lower() for n in notes)
    assert svc.completeness({'rows': [], 'values': {}}) == ['No issues entered.']


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
    # The test database must be in place before the app is built: .env (loaded with override)
    # names the live database, and this fixture drops every table.
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
        monkeypatch.setattr(svc, 'default_header', lambda pid: 'History: Gout')
        yield SimpleNamespace(app=app, db=db, doc=doc, lead=lead)
        db.session.remove()
        db.drop_all()
        # Leave the database empty for the migration-based tests (test_distribution runs
        # `db upgrade`, which would trust a leftover alembic_version and create nothing).
        with db.engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS alembic_version')


def _urate_token():
    return svc.save_token({'key': 'urate', 'label': 'Uric acid', 'loinc_codes': '1111-1, 2222-2',
                           'expected_unit': 'mmol/L'})


@needs_db
def test_recipe_versions_are_fixed_once_approved(ctx):
    _urate_token()
    r = svc.save_recipe(ctx.doc, {'issue_label': 'Gout', 'goals': 'Fewer flares',
                                  'management': 'Urate {urate.last}',
                                  'targets': [{'token': 'urate', 'target': '< 0.36 mmol/L', 'guideline': 'Invented Gout Guide',
                                               'edition': '2026', 'section': '3.1', 'quote': 'aim below 0.36'}]})
    assert r.current_version.version == 1 and r.status.value == 'draft'
    svc.approve_recipe(ctx.doc, r)
    v1 = r.current_version
    assert v1.is_approved and all(c.verified_at for c in v1.citations)
    svc.save_recipe(ctx.doc, {'issue_label': 'Gout', 'goals': 'No flares', 'management': 'm'}, r)
    assert r.current_version.version == 2 and v1.goals_text == 'Fewer flares'


@needs_db
def test_one_target_per_token_and_practice_scope_needs_an_admin(ctx):
    _urate_token()
    with pytest.raises(svc.CareplanError, match='two targets'):
        svc.save_recipe(ctx.doc, {'issue_label': 'Gout', 'targets': [
            {'token': 'urate', 'target': '< 0.36'}, {'token': 'urate', 'target': '< 0.30'}]})
    ctx.db.session.rollback()
    with pytest.raises(svc.CareplanError, match='administrator'):
        svc.save_recipe(ctx.doc, {'issue_label': 'Gout', 'scope': 'practice'})
    assert svc.save_recipe(ctx.lead, {'issue_label': 'Gout', 'scope': 'practice'}).scope.value == 'practice'


@needs_db
def test_draft_conflict_values_and_filing_freeze(ctx, monkeypatch):
    _urate_token()
    with ctx.app.test_request_context():
        plan = svc.start_draft(4242, ctx.doc)
        data = svc.draft_data(plan)
        data['rows'][0].update(issue_label='Gout', goals='Fewer flares', management='Urate {urate.last}',
                               providers='GP', targets={'urate': '< 0.36 mmol/L'})
        data['values'] = {'urate': {'value': '9.99'}}          # ignored: values only come from a fetch
        rev = svc.save_draft(plan, ctx.doc, plan.draft_revision, data)
        with pytest.raises(svc.DraftConflict):
            svc.save_draft(plan, ctx.doc, rev - 1, data)
        assert svc.draft_data(plan)['values'] == {}

        monkeypatch.setattr(svc, '_bp_section', lambda pid, q, n=1: [
            {'ReportDate': '2026-09-01', 'LoincCode': '2222-2', 'ResultValue': '0.41', 'Units': 'mmol/L'}])
        svc.confirm_values(plan, ctx.doc, ['urate'])
        svc.file_plan(plan, ctx.doc, {'FIRSTNAME': 'Ann', 'SURNAME': 'Example'})
        assert plan.status.value == 'filed' and plan.draft_json is None
        assert '0.41 mmol/L' in plan.filed_document and len(plan.filed_sha256) == 64
        assert plan.rows[0].management_text == 'Urate {urate.last}'     # tokens kept for the next plan
        assert plan.values[0].value_text == '0.41' and plan.values[0].loinc_code == '2222-2'
        with pytest.raises(svc.CareplanError):
            svc.save_draft(plan, ctx.doc, plan.draft_revision, data)

        nxt = svc.start_draft(4242, ctx.doc)
        assert svc.draft_data(nxt)['rows'][0]['management'] == 'Urate {urate.last}'
        assert svc.draft_data(nxt)['values'] == {}
        svc.save_draft(nxt, ctx.doc, nxt.draft_revision, svc.draft_data(nxt))
        svc.file_plan(nxt, ctx.doc, {'FIRSTNAME': 'Ann', 'SURNAME': 'Example'})
        assert plan.status.value == 'superseded'
        svc.void_plan(nxt, ctx.doc, 'filed in error')
        assert nxt.status.value == 'void' and plan.status.value == 'filed'


@needs_db
def test_row_saved_as_recipe_keeps_tokens_not_values(ctx):
    _urate_token()
    r = svc.row_to_recipe(ctx.doc, {'issue_label': 'Gout', 'goals': 'g', 'management': 'Urate {urate.last}',
                                    'providers': 'GP', 'targets': {'urate': '< 0.36'}})
    assert r.scope.value == 'personal' and r.status.value == 'draft'
    assert r.current_version.management_text == 'Urate {urate.last}'
    assert [t.target_text for t in r.current_version.targets] == ['< 0.36']


@needs_db
def test_token_validation(ctx):
    with pytest.raises(svc.CareplanError):
        svc.save_token({'key': 'Bad Key', 'label': 'x', 'loinc_codes': '1'})
    with pytest.raises(svc.CareplanError):
        svc.save_token({'key': 'ok', 'label': 'x', 'loinc_codes': ''})
    t = svc.save_token({'key': 'ldl', 'label': 'LDL', 'loinc_codes': '3333-3 4444-4'})
    assert t.loinc_codes == ['3333-3', '4444-4']


@needs_db
def test_pages_render_for_a_doctor(ctx, monkeypatch):
    from app.services.clinical_service import ClinicalService
    patient = {'patient_id': 4242, 'FIRSTNAME': 'Ann', 'SURNAME': 'Example', 'DOB': '1950-01-01',
               'CLINICAL_AGE': '76y', 'GENDER': 'Female'}
    monkeypatch.setattr(ClinicalService, 'get_patient_demographics', staticmethod(lambda pid: patient))
    monkeypatch.setattr(svc, 'coded_history', lambda pid: [{'label': 'Gout', 'year': '2020', 'key': 'gout'}])
    _urate_token()
    recipe = svc.save_recipe(ctx.doc, {'issue_label': 'Gout', 'management': 'Urate {urate.last}',
                                       'targets': [{'token': 'urate', 'target': '< 0.36'}]})
    client = ctx.app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(ctx.doc.id)
        s['_fresh'] = True
    pages = {'/careplan/patient/4242': 'New plan', '/careplan/recipes': 'Result tokens',
             f'/careplan/recipes/{recipe.id}': 'Targets', '/careplan/recipes/new': 'New recipe'}
    for url, text in pages.items():
        r = client.get(url)
        assert r.status_code == 200 and text in r.get_data(as_text=True), url
    plan = svc.start_draft(4242, ctx.doc)
    body = client.get(f'/careplan/plan/{plan.id}/edit').get_data(as_text=True)
    asset = json.loads(body.split('<script id="cp-asset" type="application/json">')[1].split('</script>')[0])
    assert asset['coded'][0]['label'] == 'Gout' and asset['recipes'][0]['targets'] == {'urate': '< 0.36'}
    assert client.get('/careplan/plan/999/edit').status_code == 404
    assert 'data-dictate-for="@focus"' in body and 'Print preview' in body

    data = svc.draft_data(plan)
    data['rows'][0].update(issue_label='Gout', goals='Fewer flares', management='Urate {urate.last}',
                           providers='GP')
    svc.save_draft(plan, ctx.doc, plan.draft_revision, data)
    r = client.get(f'/careplan/plan/{plan.id}/print')
    text = r.get_data(as_text=True)
    assert r.status_code == 200 and 'not filed yet' in text and 'Fewer flares' in text
    assert 'cp-screen-only' in text.split('not filed yet')[0]          # the note doesn't print
    assert plan.status.value == 'draft' and plan.filed_document is None and not plan.rows
    from app.models.careplan import CareplanEvent
    ev = CareplanEvent.query.filter_by(careplan_id=plan.id, action='draft_printed').one()
    assert ev.detail['revision'] == plan.draft_revision and len(ev.detail['sha256']) == 64
    r = client.post(f'/careplan/plan/{plan.id}/export', json={'channel': 'bp'})
    d = r.get_json()
    assert r.status_code == 200 and d['comms_url'].endswith('/clinical/comms/patient/4242')
    assert '## Gout' in d['markdown'] and '**Goals**' in d['markdown'] and '- Fewer flares' in d['markdown']
    assert '**History:** Gout' in d['markdown'] and '**' not in d['text'] and 'Fewer flares' in d['html']
    assert d['label'].startswith('GP Chronic Condition Management Plan ')
    assert client.post(f'/careplan/plan/{plan.id}/export', json={'channel': 'fax'}).status_code == 400
    ev = CareplanEvent.query.filter_by(careplan_id=plan.id, action='exported').one()
    assert ev.detail['channel'] == 'bp' and ev.detail['status'] == 'draft'
    svc.file_plan(plan, ctx.doc, patient)
    text = client.get(f'/careplan/plan/{plan.id}/print').get_data(as_text=True)
    d = client.post(f'/careplan/plan/{plan.id}/export', json={'channel': 'email'}).get_json()
    assert '- Fewer flares' in d['markdown'] and 'Prepared by Dr A · ' in d['markdown']
    assert d['html'] == plan.filed_document
    assert 'not filed yet' not in text and 'Fewer flares' in text


@needs_db
def test_fact_tokens_are_created_once_keep_their_key_and_fetch_from_the_record(ctx, monkeypatch):
    svc.ensure_fact_tokens()
    svc.ensure_fact_tokens()
    from app.models.careplan import CareplanResultToken
    bp = CareplanResultToken.query.filter_by(key='bp').one()
    assert bp.loinc_codes == [] and bp.expected_unit == 'mmHg'
    svc.save_token({'key': 'renamed', 'label': 'Last BP', 'max_age_days': '90', 'loinc_codes': '1111-1'}, bp)
    assert (bp.key, bp.label, bp.max_age_days, bp.loinc_codes) == ('bp', 'Last BP', 90, [])
    with pytest.raises(svc.CareplanError):
        svc.save_token({'key': 'weight', 'label': 'x', 'loinc_codes': '1111-1'})
    monkeypatch.setattr(svc, '_record_facts', lambda pid, keys, today: svc.facts_from(DEMO, BP_ROWS, None, today))
    monkeypatch.setattr(svc, '_bp_section', lambda *a: [])
    got = {v['key']: v for v in svc.fetch_values(4242, ['bp', 'bmi', 'nope'], date(2026, 10, 31))}
    assert got['bp']['value'] == '128/76' and got['bmi']['value'] == '30.0' and got['nope']['status'] == 'unknown_token'


@needs_db
def test_a_code_in_two_tokens_is_reported(ctx):
    a = svc.save_token({'key': 'chol', 'label': 'Cholesterol', 'loinc_codes': '1111-1'})
    b = svc.save_token({'key': 'ldl', 'label': 'LDL', 'loinc_codes': '2222-2, 1111-1'})
    assert svc.shared_codes(b) == {'chol': ['1111-1']} and svc.shared_codes(a) == {'ldl': ['1111-1']}


@needs_db
def test_loinc_catalogue_is_for_administrators(ctx, monkeypatch):
    monkeypatch.setattr(svc, 'loinc_catalogue', lambda refresh=False: [{'code': '1001-1', 'related': []}])
    from flask import g
    for user, status in ((ctx.doc, 403), (ctx.lead, 200)):
        g.pop('_login_user', None)   # the fixture's app context outlives each request, and so would g
        client = ctx.app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(user.id)
            s['_fresh'] = True
        r = client.get("/careplan/loinc"); assert r.status_code == status, r.get_data(as_text=True)[:300]


@needs_db
def test_care_plans_are_for_doctors(ctx):
    from app.models.user import User
    nurse = User(username='nurse', display_name='Nurse', security_level=3, password_hash='x')
    ctx.db.session.add(nurse)
    ctx.db.session.commit()
    client = ctx.app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(nurse.id)
        s['_fresh'] = True
    assert client.get('/careplan/recipes').status_code == 403


def test_contact_line_prefers_the_emergency_contact():
    """ADR-180: one contact in the header, the Emergency Contact else the Next of Kin. The query
    orders them; the line is built from the first row. Invented people."""
    ec = {'FIRSTNAME': 'Jo', 'SURNAME': 'Example', 'RELATIONSHIP': 'Daughter', 'PHONE1': '0400 000 001',
          'PHONE2': '0400 000 001', 'TYPE': 2}
    assert svc.contact_line([ec]) == 'Emergency contact: Jo Example (Daughter), 0400 000 001'
    nok = {'FIRSTNAME': 'Sam', 'SURNAME': 'Example', 'RELATIONSHIP': '', 'PHONE1': '', 'PHONE2': '07 0000 0002', 'TYPE': 1}
    assert svc.contact_line([nok]) == 'Next of kin: Sam Example, 07 0000 0002'
    assert svc.contact_line([]) == '' and svc.contact_line([{'FIRSTNAME': ' ', 'SURNAME': '', 'TYPE': 2}]) == ''


def test_header_adds_the_contact_after_allergies(monkeypatch):
    sections = {'patient_medications': [], 'patient_allergies': [],
                'patient_careplan_contact': [{'FIRSTNAME': 'Jo', 'SURNAME': 'Example', 'RELATIONSHIP': 'Son',
                                              'PHONE1': '0400 000 003', 'PHONE2': '', 'TYPE': 2}]}
    monkeypatch.setattr(svc, 'coded_history', lambda pid: [{'label': 'Gout', 'year': '2020', 'key': 'gout'}])
    monkeypatch.setattr(svc, '_bp_section', lambda pid, name, params=1: sections[name])
    assert svc.default_header(1) == ('History: Gout (2020)\nAllergies: none recorded\n'
                                     'Emergency contact: Jo Example (Son), 0400 000 003')


def test_the_contact_query_puts_the_emergency_contact_first():
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / 'app' / 'sql' / 'patient_careplan_contact.sql').read_text()
    assert 'TOP 1' in sql and 'ORDER BY TYPE DESC, NextofKinid DESC' in sql and 'recordstatus = 1' in sql
