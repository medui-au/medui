"""The protocol setup wizard, guideline seeding and the GP chooser's one-per-label list (ADR-182).
Invented data only. Database tests need MEDUI_TEST_DATABASE_URL (a throwaway *_test database)."""
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import patient_target_service as pts
from app.services import protocol_catalogue as cat
from app.services import protocol_service as svc
from tests.test_practice_protocols import _client, ctx, needs_db  # noqa: F401  (ctx is a fixture)


# ── No database ───────────────────────────────────────────────────────────────

def test_catalogue_cites_known_guidelines_and_valid_rules():
    for mkey, opts in cat.OPTIONS.items():
        for o in opts:
            assert o['citations'], o['code']
            for g, _sec, quote in o['citations']:
                assert g in cat.GUIDELINES, g
                assert len(quote.split()) <= 25, (o['code'], 'quotes stay short')
            assert 'default_rule' not in o and 'priority' not in o, 'the catalogue pre-chooses nothing'
    for mkey, groups in cat.GROUPS.items():
        assert mkey in cat.OPTIONS
        for g in groups:
            svc.validate_rule(g['rule'])
    for _k, _l, applies, _f in cat.MODULES:
        svc.validate_rule(applies)


def test_catalogue_is_de_identified():
    text = repr((cat.GUIDELINES, cat.OPTIONS, cat.MODULES, cat.PREVENTION)).lower()
    assert 'practice library' not in text and 'internal' not in text
    assert not re.search(r'decision \d', text)
    for _k, _l, _a, fields in cat.MODULES:
        for f in ('goals', 'patient_info', 'safety_netting'):
            assert not re.search(r'\d+\s*mg\b|paracetamol|statin|metformin|aspirin', (fields.get(f) or '').lower())


def test_catalogue_guidelines_are_australian_and_dated():
    for row in cat.GUIDELINES.values():
        assert row['title'] and row.get('url', '').startswith('https://')
    assert cat.ACCESSED.year >= 2026


def _o(i, label, priority=10):
    return SimpleNamespace(id=i, label=label, priority=priority)


def test_one_per_label_keeps_the_preselected_or_current_row():
    a1, a2, b = _o(1, '< 130/80 mmHg', 10), _o(2, '< 130/80 mmHg', 20), _o(3, '< 140/90 mmHg', 30)
    assert [o.id for o in pts.one_per_label([a1, a2, b])] == [1, 3]
    assert [o.id for o in pts.one_per_label([a1, a2, b], default=a2)] == [2, 3]
    assert [o.id for o in pts.one_per_label([a1, a2, b], default=a2, current=SimpleNamespace(option_id=1))] == [1, 3]


# ── Database ──────────────────────────────────────────────────────────────────

def _all_answers(choice: dict | None = None) -> dict:
    """A complete form: every measure used, each group given the first option (or the override)."""
    form = {}
    for mkey, groups in cat.GROUPS.items():
        form[f'm_{mkey}'] = 'use'
        for g in groups:
            form[f'g_{mkey}_{g["key"]}'] = cat.OPTIONS[mkey][0]['code']
    for k, *_ in cat.MEASURES:
        if (k, 'individual') in [(m[0], m[4]) for m in cat.MEASURES]:
            form[f'i_{k}'] = 'keep'
    for k, *_ in cat.MODULES:
        form[f'mod_{k}'] = 'keep'
    for k, *_ in cat.PREVENTION:
        form[f'prev_{k}'] = 'drop'
    form.update(choice or {})
    return form


@needs_db
def test_seed_guidelines_is_insert_only(ctx):
    from app.models.careplan import CareplanGuideline
    from app.services.protocol_wizard import seed_guidelines
    title = cat.GUIDELINES['redbook']['title']
    ctx.db.session.add(CareplanGuideline(title=title, edition='edited by the practice'))
    ctx.db.session.commit()
    assert seed_guidelines() == (len(cat.GUIDELINES) - 1, 1)
    assert seed_guidelines() == (0, len(cat.GUIDELINES))
    assert CareplanGuideline.query.filter_by(title=title).one().edition == 'edited by the practice'


@needs_db
def test_wizard_needs_every_answer_and_builds_a_draft(ctx):
    assert _client(ctx, ctx.manager).get('/admin/protocols/wizard').status_code == 403
    adm = _client(ctx, ctx.admin)
    body = adm.get('/admin/protocols/wizard').get_data(as_text=True)
    assert 'Leave out' in body
    assert not re.search(r'<input[^>]*type="radio"[^>]*\bchecked\b', body)   # nothing chosen for the practice
    incomplete = _all_answers()
    del incomplete['g_ldl_ascvd']
    r = adm.post('/admin/protocols/wizard', data=incomplete)
    assert r.status_code == 400 and 'Still to answer' in r.get_data(as_text=True)
    assert svc.draft_version() is None

    form = _all_answers({'g_bp_general': 'bp_130_80', 'g_ldl_ascvd': 'ldl_14_50', 'g_ldl_high_risk': 'ldl_20',
                         'g_ldl_general': 'gp', 'm_activity': 'leave', 'mod_diabetes_glucose': 'drop',
                         'prev_bowel': 'keep'})
    assert adm.post('/admin/protocols/wizard', data=form).status_code == 302
    d = svc.draft_version()
    assert d and d.status.value == 'draft' and svc.live_version() is None
    codes = {o.code: o for o in d.options}
    assert codes['ldl_14_50__ascvd'].default_rule == {'any': cat.ASCVD} and codes['ldl_14_50__ascvd'].citations
    assert codes['ldl_gp__general'].gp_sets and codes['ldl_gp__general'].default_rule == {'always': True}
    assert 'ldl_gp' not in codes and 'bp_gp' in codes and codes['bp_gp'].default_rule is None
    assert not any(c.startswith('activity') for c in codes)
    assert codes['bgl_racgp__monitoring'].default_rule is None
    assert {m.condition_key for m in d.modules} == {m[0] for m in cat.MODULES} - {'diabetes_glucose'}
    assert [p.key for p in d.prevention] == ['bowel']

    # LDL: established disease beats diabetes, which beats GP-sets for everyone else.
    ldl = [o for o in d.options if o.measure.key == 'ldl']
    assert svc.default_option(ldl, {'isDiabetes': 1, 'isIHD': 1}).code == 'ldl_14_50__ascvd'
    assert svc.default_option(ldl, {'isDiabetes': 1}).code == 'ldl_20__high_risk'
    assert svc.default_option(ldl, {}).code == 'ldl_gp__general'
    # BP: the same target chosen for both groups shows once in the GP's list.
    bp = [o for o in d.options if o.measure.key == 'bp']
    assert len(bp) == 3 and len(pts.one_per_label(bp)) == 2

    assert adm.post('/admin/protocols/wizard', data=form).status_code == 302   # refused: a draft exists
    assert len(svc.all_versions()) == 1
    due = (date.today() + timedelta(days=365)).isoformat()
    adm.post('/admin/protocols/draft/approve', data={'review_due_on': due, 'attest': '1'})
    assert svc.live_version().version == 1


@needs_db
def test_wizard_refuses_a_protocol_with_nothing_in_it(ctx):
    from app.services.protocol_wizard import build_draft, read_answers
    form = _all_answers({f'm_{k}': 'leave' for k in cat.GROUPS})
    form.update({k: 'drop' for k in form if k.startswith('i_')})
    answers, missing = read_answers(form)
    assert not missing
    with pytest.raises(svc.ProtocolError):
        build_draft(ctx.admin, answers)
    assert svc.draft_version() is None


@needs_db
def test_guidelines_seed_button(ctx):
    from app.models.careplan import CareplanGuideline
    assert _client(ctx, ctx.manager).post('/admin/protocols/guidelines/seed').status_code == 403
    adm = _client(ctx, ctx.admin)
    assert adm.post('/admin/protocols/guidelines/seed').status_code == 302
    assert CareplanGuideline.query.count() == len(cat.GUIDELINES)


@needs_db
def test_install_seeds_add_the_guidelines_once(ctx):
    from app.commands.install import _seed_gpccmp_pipeline
    from app.models.careplan import CareplanGuideline
    _seed_gpccmp_pipeline()
    _seed_gpccmp_pipeline()
    assert CareplanGuideline.query.count() == len(cat.GUIDELINES)
    assert svc.draft_version() is None and svc.live_version() is None   # still no protocol shipped
