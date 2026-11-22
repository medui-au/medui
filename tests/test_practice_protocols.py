"""Practice protocols (ADR-171). Invented data only.

The first part needs no database. The second runs only when MEDUI_TEST_DATABASE_URL names a
throwaway PostgreSQL database ending in _test (schema created with db.create_all()).
"""
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import condition_codes as cc
from app.services import protocol_service as svc
import example_protocol as seed


# ── No database ───────────────────────────────────────────────────────────────

def test_new_conditions_have_flags_and_codes():
    assert cc.FLAGS['isFH'] == 'familial_hypercholesterolaemia'
    assert cc.FLAGS['isRevascularisation'] == 'revascularisation'
    for c in cc.ADDED_LATER:
        assert cc.DEFAULTS[c][0], c
    flags = cc.profile_flags([{'ITEMCODE': 3578, 'STATUSCODE': 1}], table=cc._defaults())
    assert flags['isRevascularisation'] == 1 and flags['isFH'] == 0


def test_rules_any_all_none_always():
    on = {'isDiabetes': 1, 'isHT': 1, 'isIHD': 0}
    assert svc.rule_matches({'any': ['isIHD', 'isDiabetes']}, on)
    assert not svc.rule_matches({'any': ['isIHD']}, on)
    assert svc.rule_matches({'all': ['isDiabetes', 'isHT']}, on)
    assert not svc.rule_matches({'all': ['isDiabetes', 'isIHD']}, on)
    assert svc.rule_matches({'none': ['isIHD']}, on)
    assert svc.rule_matches({'any': ['isDiabetes'], 'none': ['isIHD']}, on)
    assert not svc.rule_matches({'any': ['isDiabetes'], 'none': ['isHT']}, on)
    assert svc.rule_matches({'always': True}, {})
    assert not svc.rule_matches(None, on) and not svc.rule_matches({}, on)


def test_rules_are_validated():
    assert svc.validate_rule('') is None and svc.validate_rule({}) is None
    for bad in ({'sometimes': True}, {'any': 'isDiabetes'}, {'any': ['isMadeUp']}, {'always': False}, ['isHT']):
        with pytest.raises(svc.ProtocolError):
            svc.validate_rule(bad)


def _opt(i, rule, priority):
    return SimpleNamespace(id=i, default_rule=rule, priority=priority)


def test_default_option_is_the_first_match_by_priority():
    opts = [_opt(3, {'always': True}, 90), _opt(1, {'any': ['isIHD']}, 10), _opt(2, {'any': ['isDiabetes']}, 20)]
    assert svc.default_option(opts, {'isIHD': 1, 'isDiabetes': 1}).id == 1
    assert svc.default_option(opts, {'isDiabetes': 1}).id == 2
    assert svc.default_option(opts, {}).id == 3
    assert svc.default_option([_opt(1, None, 10)], {'isIHD': 1}) is None
    assert svc.matching_flags({'any': ['isIHD', 'isCVA']}, {'isIHD': 1, 'isCVA': 0, 'isHT': 1}) == ['isIHD']


def test_seed_matches_the_decisions():
    """The v1 data says what the clinical lead decided (decision record, 2026-11-22)."""
    for mkey, opts in seed.OPTIONS.items():
        for o in opts:
            svc.validate_rule(o.get('default_rule'))
            assert o['citations'], o['code']
            for gkey, _section, _quote in o['citations']:
                assert gkey in seed.GUIDELINES, gkey
    labels = {o['code']: o['label'] for opts in seed.OPTIONS.values() for o in opts}
    assert labels['bp_high_risk'].startswith('< 130/80') and labels['bp_general'].startswith('< 140/90')
    assert '1.4' in labels['ldl_ascvd'] and '50%' in labels['ldl_ascvd']
    assert labels['ldl_high'] == '< 2.0 mmol/L' and labels['ldl_aspirational'].startswith('Aspirational')
    assert '7%' in labels['hba1c_general'] and '4.0–7.0' in labels['bgl_racgp']
    assert '10 standard drinks' in labels['alcohol_nhmrc']
    scopes = {k: s for k, _l, _u, _t, s, _o in seed.MEASURES}
    assert {k for k, s in scopes.items() if s == 'individual'} == {'uacr', 'urate', 'waist', 'weight'}
    # ASCVD beats diabetes for LDL; diabetes beats the fallback.
    ldl = [SimpleNamespace(id=i, **{k: o.get(k) for k in ('default_rule', 'priority')}) for i, o in enumerate(seed.OPTIONS['ldl'])]
    assert seed.OPTIONS['ldl'][svc.default_option(ldl, {'isDiabetes': 1, 'isIHD': 1}).id]['code'] == 'ldl_ascvd'
    assert seed.OPTIONS['ldl'][svc.default_option(ldl, {'isDiabetes': 1}).id]['code'] == 'ldl_high'
    assert seed.OPTIONS['ldl'][svc.default_option(ldl, {}).id]['code'] == 'ldl_aspirational'


def test_seed_patient_text_names_no_medicines_or_doses():
    """Decision 7: no named medicines or doses in patient text (reference text may hold them)."""
    import re
    for _k, _l, _a, fields in seed.MODULES:
        for f in ('goals', 'patient_info', 'safety_netting'):
            text = (fields.get(f) or '').lower()
            assert not re.search(r'\d+\s*mg\b|paracetamol|statin|metformin|aspirin', text), (_k, f)


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
        users = dict(doc=User(username='dr_a', display_name='Dr A', security_level=5, password_hash='x'),
                     manager=User(username='mgr', display_name='Manager', security_level=7, password_hash='x'),
                     admin=User(username='adm', display_name='Admin', security_level=9, password_hash='x'))
        db.session.add_all(users.values())
        db.session.commit()
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
def test_seed_loads_a_draft_once(ctx):
    from app.commands.protocol import seed_v1
    import click
    out = seed_v1(ctx.admin.id)
    assert out['options'] == sum(len(v) for v in seed.OPTIONS.values()) and out['modules'] == len(seed.MODULES)
    draft = svc.draft_version()
    assert draft.version == 1 and svc.live_version() is None
    with pytest.raises(click.ClickException):
        seed_v1(ctx.admin.id)


@needs_db
def test_approve_then_draft_copies_and_retires(ctx):
    from app.commands.protocol import seed_v1
    seed_v1(ctx.admin.id)
    with pytest.raises(svc.ProtocolError):
        svc.approve(ctx.admin, date.today())             # the review date must be in the future
    v1 = svc.approve(ctx.admin, date.today() + timedelta(days=365))
    assert v1.status.value == 'approved' and v1.approved_by_id == ctx.admin.id
    opt = v1.options[0]
    with pytest.raises(svc.ProtocolError):
        svc.update_option(opt, {'label': 'Changed'})       # an approved version is read-only
    v2 = svc.start_draft(ctx.admin, 'invented change')
    assert v2.version == 2 and len(v2.options) == len(v1.options) and len(v2.modules) == len(v1.modules)
    assert sum(len(o.citations) for o in v2.options) == sum(len(o.citations) for o in v1.options)
    with pytest.raises(svc.ProtocolError):
        svc.start_draft(ctx.admin)                          # one draft at a time
    changed = next(o for o in v2.options if o.code == opt.code)
    svc.update_option(changed, {'label': 'Invented label', 'default_rule': {'any': ['isHT']}, 'priority': '5'})
    assert changed.label == 'Invented label' and changed.priority == 5 and opt.label != 'Invented label'
    with pytest.raises(svc.ProtocolError):
        svc.update_option(changed, {'default_rule': {'any': ['isMadeUp']}})
    ctx.db.session.rollback()
    svc.approve(ctx.admin, date.today() + timedelta(days=30))
    ctx.db.session.refresh(v1)
    assert v1.status.value == 'retired' and svc.live_version().version == 2


@needs_db
def test_screen_is_read_only_below_admin(ctx):
    from app.commands.protocol import seed_v1
    seed_v1(ctx.admin.id)
    assert _client(ctx, ctx.doc).get('/admin/protocols/').status_code == 403
    mgr = _client(ctx, ctx.manager)
    for tab in ('measures', 'modules', 'prevention', 'guidelines', 'versions'):
        r = mgr.get(f'/admin/protocols/?tab={tab}')
        assert r.status_code == 200, tab
        assert 'Edit option' not in r.get_data(as_text=True)
    opt = svc.draft_version().options[0]
    assert mgr.post(f'/admin/protocols/option/{opt.id}', data={'label': 'x'}).status_code == 403
    assert mgr.post('/admin/protocols/draft/approve', data={}).status_code == 403


@needs_db
def test_admin_edits_and_approves_on_the_screen(ctx):
    from app.commands.protocol import seed_v1
    seed_v1(ctx.admin.id)
    adm = _client(ctx, ctx.admin)
    body = adm.get('/admin/protocols/?tab=measures').get_data(as_text=True)
    assert 'Edit option' in body and '1.4' in body
    opt = svc.draft_version().options[0]
    r = adm.post(f'/admin/protocols/option/{opt.id}', data={
        'label': 'Invented label', 'patient_group': '', 'plan_wording': '', 'rationale': '',
        'default_rule': '{"any": ["isHT"]}', 'priority': '7'})
    assert r.status_code == 302
    ctx.db.session.refresh(opt)
    assert opt.label == 'Invented label' and opt.default_rule == {'any': ['isHT']}
    r = adm.post(f'/admin/protocols/option/{opt.id}', data={'label': 'x', 'default_rule': '{not json'})
    assert r.status_code == 302
    ctx.db.session.refresh(opt)
    assert opt.label == 'Invented label'                     # nothing saved from a bad form
    due = (date.today() + timedelta(days=365)).isoformat()
    assert adm.post('/admin/protocols/draft/approve', data={'review_due_on': due}).status_code == 302
    assert svc.live_version().version == 1


@needs_db
def test_guideline_library_and_supersede(ctx):
    a = svc.save_guideline(ctx.admin, {'title': 'Invented Guide', 'edition': '2020', 'accessed_on': '2026-11-22'})
    b = svc.save_guideline(ctx.admin, {'title': 'Invented Guide', 'edition': '2026'})
    svc.save_guideline(ctx.admin, {'superseded_by_id': str(b.id)}, a)
    assert a.superseded_by_id == b.id
    with pytest.raises(svc.ProtocolError):
        svc.save_guideline(ctx.admin, {'superseded_by_id': str(a.id)}, a)
    with pytest.raises(svc.ProtocolError):
        svc.save_guideline(ctx.admin, {'title': ''})


@needs_db
def test_new_conditions_reach_an_existing_table_once(ctx):
    from app.models.system_setting import SystemSetting
    from sqlalchemy import text
    from app.services import mapping_service as ms
    # The mapping's physical table isn't one of the ORM's, so drop_all leaves it behind.
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()
    assert cc.ensure_table() is True                       # a new table gets every condition
    rows, _ = ms.get_rows(cc.TABLE, page=1, per_page=10000)
    assert {'familial_hypercholesterolaemia', 'revascularisation'} <= {r['condition'] for r in rows}
    # An older table: remove the new rows and forget they were added.
    for r in rows:
        if r['condition'] in cc.ADDED_LATER:
            ms.row_delete(cc.TABLE, r['id'])
    SystemSetting.set(cc._ADDED_KEY, [])
    assert cc.ensure_added_conditions() == list(cc.ADDED_LATER)
    rows, _ = ms.get_rows(cc.TABLE, page=1, per_page=10000)
    revasc = [r for r in rows if r['condition'] == 'revascularisation']
    assert len(revasc) == len(cc.DEFAULTS['revascularisation'][0])
    # An administrator empties it: it is not put back.
    for r in revasc:
        ms.row_delete(cc.TABLE, r['id'])
    ctx.db.session.commit()
    assert cc.ensure_added_conditions() == []
    rows, _ = ms.get_rows(cc.TABLE, page=1, per_page=10000)
    assert not any(r['condition'] == 'revascularisation' for r in rows)
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()


@needs_db
def test_seed_says_so_when_there_is_no_practice_data(ctx, monkeypatch):
    """ADR-181: the open edition ships no practice protocol; the command explains instead of failing."""
    import click
    from app.commands import protocol as cmd
    monkeypatch.setattr(cmd, 'practice_data', lambda: None)
    with pytest.raises(click.ClickException, match='no practice protocol to load'):
        cmd.seed_v1(ctx.admin.id)
    body = _client(ctx, ctx.admin).get('/admin/protocols/').get_data(as_text=True)
    assert 'No protocol yet' in body and 'seed-v1' not in body
