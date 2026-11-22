"""Patient targets (ADR-172). Invented data only.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway PostgreSQL database ending in _test (schema created with db.create_all()).
"""
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import patient_target_service as svc

REAL_LATEST = svc.latest_values     # the fixture replaces it; one test needs the real one


# ── No database ───────────────────────────────────────────────────────────────

def test_why_text_names_the_coded_conditions():
    v = SimpleNamespace(version=3)
    o = SimpleNamespace(default_rule={'any': ['isIHD', 'isCVA', 'isDiabetes']})
    assert svc.why_text(o, {'isIHD': 1, 'isDiabetes': 1, 'isCVA': 0}, v) == 'Practice protocol v3: diabetes, IHD coded'
    assert svc.why_text(SimpleNamespace(default_rule={'always': True}), {}, v) == \
        'Practice protocol v3: the default for everyone else'
    assert svc.why_text(None, {}, v) == ''


def test_every_profile_flag_has_a_label():
    from app.services.condition_codes import FLAGS
    assert set(FLAGS) <= set(svc.FLAG_LABELS)


def test_token_check_rules():
    from app.services import protocol_service as ps
    tok = lambda key, codes, unit: SimpleNamespace(key=key, loinc_codes=codes, expected_unit=unit)
    ldl = SimpleNamespace(key='ldl', unit='mmol/L')
    assert ps.token_check(ldl, tok('ldl_c', ['22748-8', '39469-2'], 'mmol/L')) == ps.LINK_OK
    assert ps.token_check(ldl, tok('mix', ['22748-8', '14647-2'], 'mmol/L')) == ps.LINK_MISMATCH   # one code is TC
    assert ps.token_check(ldl, tok('ldl_mg', ['22748-8'], 'mg/dL')) == ps.LINK_MISMATCH
    assert ps.token_check(ldl, tok('bp', [], 'mmHg')) == ps.LINK_MISMATCH
    bp = SimpleNamespace(key='bp', unit='mmHg')
    assert ps.token_check(bp, tok('bp', [], 'mmHg')) == ps.LINK_OK
    assert ps.token_check(bp, tok('ldl_c', ['22748-8'], 'mmol/L')) == ps.LINK_MISMATCH
    urate = SimpleNamespace(key='urate', unit='mmol/L')
    assert ps.token_check(urate, tok('urate_x', ['14933-6'], 'mmol/L')) == ps.LINK_OK
    assert ps.token_check(urate, tok('chol', ['14647-2'], 'mmol/L')) == ps.LINK_MISMATCH    # same unit, wrong test
    assert ps.token_check(urate, tok('weight', [], 'kg')) == ps.LINK_MISMATCH
    glucose = SimpleNamespace(key='home_bgl', unit='mmol/L')                                # no codes defined
    assert ps.token_check(glucose, tok('chol', ['14647-2'], 'mmol/L')) == ps.LINK_MISMATCH
    hba1c = SimpleNamespace(key='hba1c', unit='%')
    assert ps.token_check(hba1c, tok('hba1c_ngsp', ['4548-4', '17856-6'], '%')) == ps.LINK_OK
    assert ps.token_check(hba1c, tok('hba1c_ifcc', ['59261-8'], 'mmol/mol')) == ps.LINK_MISMATCH


# ── Database ──────────────────────────────────────────────────────────────────

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')

PID = 4242
PATIENT = {'patient_id': PID, 'SURNAME': 'Example', 'FIRSTNAME': 'Ivy', 'AGE': 61}


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
                     nurse=User(username='rn_a', display_name='Nurse A', security_level=3, password_hash='x'),
                     clerk=User(username='rc_a', display_name='Reception A', security_level=2, password_hash='x'),
                     admin=User(username='adm', display_name='Admin', security_level=9, password_hash='x'))
        db.session.add_all(users.values())
        db.session.commit()
        from app.commands.protocol import seed_v1
        from app.services import protocol_service
        seed_v1(users['admin'].id)
        protocol_service.approve(users['admin'], date.today() + timedelta(days=365))
        from app.services.clinical_service import ClinicalService
        monkeypatch.setattr(ClinicalService, 'get_patient_demographics', staticmethod(lambda pid: dict(PATIENT)))
        monkeypatch.setattr(ClinicalService, 'get_disease_profile',
                            staticmethod(lambda pid, **kw: {'isDiabetes': 1, 'isIHD': 1, 'isHT': 0}))
        monkeypatch.setattr(svc, 'latest_values', lambda pid, measures: {
            'ldl_c': {'key': 'ldl_c', 'value': '1.9', 'unit': 'mmol/L', 'date': '2026-10-03', 'status': 'found'}})
        yield SimpleNamespace(app=app, db=db, **users)
        db.session.remove()
        db.drop_all()


def _measure(key):
    from app.models.protocol import ProtocolMeasure
    return ProtocolMeasure.query.filter_by(key=key).first()


def _option(code):
    from app.services import protocol_service
    return next(o for o in protocol_service.live_version().options if o.code == code)


def _client(ctx, user):
    from flask import g
    g.pop('_login_user', None)
    client = ctx.app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return client


FLAGS = {'isDiabetes': 1, 'isIHD': 1}


@needs_db
def test_rows_show_relevant_measures_with_the_preselected_option(ctx):
    data = svc.build_rows(PID, FLAGS)
    rows = {r['measure'].key: r for r in data['rows']}
    assert rows['ldl']['default'].code == 'ldl_ascvd' and 'IHD' in rows['ldl']['why']
    assert rows['bp']['default'].code == 'bp_high_risk'
    assert rows['hba1c']['default'].code == 'hba1c_general'
    assert {'uacr', 'urate', 'waist', 'weight', 'home_bgl'} <= {r['measure'].key for r in data['addable']}
    no_dm = {r['measure'].key for r in svc.build_rows(PID, {})['rows']}
    assert 'hba1c' not in no_dm and 'bp' in no_dm          # BP and LDL have an "everyone else" default


@needs_db
def test_confirm_records_the_basis_and_keeps_history(ctx):
    bp, ldl, uacr = _measure('bp'), _measure('ldl'), _measure('uacr')
    saved = svc.confirm(PID, ctx.doc, [
        {'measure_id': ldl.id, 'option_id': _option('ldl_ascvd').id},           # the preselected one
        {'measure_id': bp.id, 'option_id': _option('bp_general').id},           # another option
        {'measure_id': uacr.id, 'option_id': None, 'value_text': '< 3.0 mg/mmol', 'reason': 'invented reason'},
    ], FLAGS)
    by = {t.measure.key: t for t in saved}
    assert by['ldl'].basis.value == 'default' and by['ldl'].value_text == _option('ldl_ascvd').label
    assert by['bp'].basis.value == 'option'
    assert by['uacr'].basis.value == 'individual' and by['uacr'].reason == 'invented reason'
    assert all(t.protocol_version.version == 1 for t in saved)
    # The same choice again changes nothing.
    assert svc.confirm(PID, ctx.doc, [{'measure_id': ldl.id, 'option_id': _option('ldl_ascvd').id}], FLAGS) == []
    # A change closes the old row and keeps it.
    new = svc.confirm(PID, ctx.doc, [{'measure_id': ldl.id, 'option_id': None, 'value_text': '< 1.8 mmol/L'}], FLAGS)
    assert len(new) == 1
    hist = svc.history(PID)[ldl.id]
    assert len(hist) == 2 and hist[1].superseded_by_id == hist[0].id and hist[1].superseded_at is not None
    assert svc.current_targets(PID)[ldl.id].value_text == '< 1.8 mmol/L'


@needs_db
def test_confirm_refuses_bad_choices_and_stores_none(ctx):
    bp, hba1c = _measure('bp'), _measure('hba1c')
    with pytest.raises(svc.TargetError):          # a GP-sets option needs a value
        svc.confirm(PID, ctx.doc, [{'measure_id': bp.id, 'option_id': _option('bp_general').id},
                                   {'measure_id': hba1c.id, 'option_id': _option('hba1c_individual').id}], FLAGS)
    assert svc.current_targets(PID) == {}         # all or nothing
    with pytest.raises(svc.TargetError):          # an option from another measure
        svc.confirm(PID, ctx.doc, [{'measure_id': bp.id, 'option_id': _option('ldl_high').id}], FLAGS)
    with pytest.raises(svc.TargetError):
        svc.confirm(PID, ctx.nurse, [{'measure_id': bp.id, 'option_id': _option('bp_general').id}], FLAGS)


@needs_db
def test_screen_nurse_reads_doctor_sets(ctx):
    url = f'/gpccmp/patient/{PID}/targets'
    assert _client(ctx, ctx.clerk).get(url).status_code == 403
    nurse = _client(ctx, ctx.nurse)
    body = nurse.get(url).get_data(as_text=True)
    assert 'Only a doctor can change them' in body and 'Save targets' not in body
    assert nurse.post(url, data={}).status_code == 403
    doc = _client(ctx, ctx.doc)
    body = doc.get(url).get_data(as_text=True)
    assert 'Save targets' in body and 'Save and continue to plan decisions' in body and 'Preselected' in body and 'IHD' in body and 'Latest: 1.9' in body
    ldl = _measure('ldl')
    r = doc.post(url, data={'measure': [str(ldl.id)], f'choice_{ldl.id}': str(_option('ldl_ascvd').id)})
    assert r.status_code == 302
    assert svc.current_targets(PID)[ldl.id].basis.value == 'default'
    body = nurse.get(url).get_data(as_text=True)
    from markupsafe import escape
    assert str(escape(_option('ldl_ascvd').label)) in body and 'protocol default' in body


@needs_db
def test_admin_relinks_a_measure_token(ctx):
    from app.models.careplan import CareplanResultToken
    from app.services import protocol_service
    ctx.db.session.add_all([
        CareplanResultToken(key='uacr_x', label='Invented ACR', loinc_codes=['32294-1'], expected_unit='mg/mmol', active=True),
        CareplanResultToken(key='tc_x', label='Invented TC', loinc_codes=['14647-2'], expected_unit='mmol/L', active=True),
        CareplanResultToken(key='ldl_x', label='Invented LDL', loinc_codes=['22748-8 '], expected_unit='mmol/L', active=True),
        CareplanResultToken(key='bp', label='Blood pressure', loinc_codes=[], expected_unit='mmHg', active=True)])
    ctx.db.session.commit()
    m = _measure('uacr')
    protocol_service.update_measure(m, {'label': m.label, 'unit': 'mg/mmol', 'token_key': 'uacr_x'})
    assert m.token_key == 'uacr_x'
    for bad in ('not_a_token', 'tc_x'):                   # missing, or the wrong unit
        with pytest.raises(protocol_service.ProtocolError):
            protocol_service.update_measure(m, {'label': m.label, 'unit': 'mg/mmol', 'token_key': bad})
    ldl = _measure('ldl')
    with pytest.raises(protocol_service.ProtocolError):   # total cholesterol is not LDL
        protocol_service.update_measure(ldl, {'label': ldl.label, 'unit': 'mmol/L', 'token_key': 'tc_x'})
    protocol_service.update_measure(ldl, {'label': ldl.label, 'unit': 'mmol/L', 'token_key': 'ldl_x'})
    bp = _measure('bp')
    with pytest.raises(protocol_service.ProtocolError):   # BP takes only its own record value
        protocol_service.update_measure(bp, {'label': bp.label, 'unit': 'mmHg', 'token_key': 'ldl_x'})
    # The screen offers only what passes.
    body = _client(ctx, ctx.admin).get('/admin/protocols/?tab=measures').get_data(as_text=True)
    ldl_card = body.split(f'id="m-{ldl.id}"')[1].split('id="m-')[0]
    assert 'value="ldl_x"' in ldl_card and 'value="tc_x"' not in ldl_card and 'value="bp"' not in ldl_card


@needs_db
def test_a_bad_link_shows_no_latest_value(ctx, monkeypatch):
    from app.models.careplan import CareplanResultToken
    from app.services import careplan_service
    ctx.db.session.add(CareplanResultToken(key='ldl_c', label='Total chol by mistake', loinc_codes=['14647-2'],
                                           expected_unit='mmol/L', active=True))
    ctx.db.session.commit()
    asked = []
    monkeypatch.setattr(careplan_service, 'fetch_values', lambda pid, keys: asked.extend(keys) or [])
    from app.services import protocol_service
    REAL_LATEST(PID, protocol_service.measures())
    assert 'ldl_c' not in asked                         # its codes are total cholesterol's


def test_link_status_tells_missing_from_mismatch():
    from app.services import protocol_service as ps
    m = SimpleNamespace(key='urate', unit='mmol/L', token_key='urate')
    assert ps.link_status(m, {}) == ps.LINK_MISSING
    assert ps.link_status(SimpleNamespace(key='urate', unit='mmol/L', token_key=None), {}) == ps.LINK_NONE
    t = SimpleNamespace(key='urate', loinc_codes=['0000-0'], expected_unit='kg')
    assert ps.link_status(m, {'urate': t}) == ps.LINK_MISMATCH
