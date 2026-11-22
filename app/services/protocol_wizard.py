"""The protocol setup wizard (ADR-182): a practice builds its first protocol by answering one question
per measure and patient group from the option catalogue (protocol_catalogue). The answers become a
DRAFT version, which an administrator reviews on the Practice Protocols screen and approves. The
wizard never approves anything and never pre-chooses an answer.
"""
from app.extensions import db
from app.models.careplan import CareplanGuideline
from app.models.protocol import (MeasureScope, ProtocolMeasure, ProtocolModule, ProtocolOption,
                                 ProtocolOptionCitation, ProtocolPreventionRule, ProtocolStatus,
                                 ProtocolVersion)
from app.services import protocol_catalogue as cat
from app.services import protocol_service as svc

GP_SETS = 'gp'          # answer: the GP sets this group's target individually
LEAVE = 'leave'         # answer: the measure is left out of the protocol
KEEP, DROP = 'keep', 'drop'


def seed_guidelines(user_id: int | None = None) -> tuple[int, int]:
    """Add the catalogue's guidelines to the library. Insert-only, matched by title: an existing row
    (perhaps edited by the practice) is never changed. Returns (added, already there)."""
    added = existing = 0
    for row in cat.GUIDELINES.values():
        if CareplanGuideline.query.filter_by(title=row['title']).first():
            existing += 1
            continue
        db.session.add(CareplanGuideline(accessed_on=cat.ACCESSED, created_by_id=user_id, **row))
        added += 1
    db.session.commit()
    return added, existing


def _guidelines() -> dict[str, CareplanGuideline]:
    by_title = {g.title: g for g in CareplanGuideline.query.all()}
    return {k: by_title.get(row['title']) for k, row in cat.GUIDELINES.items()}


def _measures() -> dict[str, ProtocolMeasure]:
    """The catalogue's measures, adding any the practice doesn't have (matched by key; existing ones
    are left as the practice has them)."""
    out = {}
    for key, label, unit, token, scope, order in cat.MEASURES:
        m = ProtocolMeasure.query.filter_by(key=key).first()
        if m is None:
            m = ProtocolMeasure(key=key, label=label, unit=unit, token_key=token,
                                scope=MeasureScope(scope), display_order=order, active=True)
            db.session.add(m)
            db.session.flush()
        out[key] = m
    return out


def _label(key: str) -> str:
    return next(m[1] for m in cat.MEASURES if m[0] == key)


def questions() -> dict:
    """What the wizard page shows. Citations carry the guideline rows (None if not yet seeded)."""
    gl = _guidelines()

    def opts(mkey):
        return [dict(o, cites=[(gl.get(g), cat.GUIDELINES[g], sec, q) for g, sec, q in o['citations']])
                for o in cat.OPTIONS.get(mkey, [])]
    protocol = [dict(key=k, label=_label(k), groups=cat.GROUPS[k], options=opts(k)) for k in cat.GROUPS]
    individual = [dict(key=m[0], label=m[1], options=opts(m[0])) for m in cat.MEASURES if m[4] == 'individual']
    modules = [dict(key=k, label=l, rule=svc.rule_text(a), fields=f) for k, l, a, f in cat.MODULES]
    prevention = [dict(key=k, label=l, wording=w, source=s) for k, l, r, w, s in cat.PREVENTION]
    return dict(protocol=protocol, individual=individual, modules=modules, prevention=prevention,
                missing_guidelines=sum(1 for g in gl.values() if g is None))


def read_answers(form) -> tuple[dict, list[str]]:
    """The wizard's answers from a submitted form, and the questions left unanswered."""
    answers = {'measures': {}, 'individual': {}, 'modules': {}, 'prevention': {}}
    missing = []
    for mkey, groups in cat.GROUPS.items():
        codes = {o['code'] for o in cat.OPTIONS[mkey]}
        if form.get(f'm_{mkey}') == LEAVE:
            answers['measures'][mkey] = LEAVE
            continue
        if form.get(f'm_{mkey}') != 'use':
            missing.append(_label(mkey))
            continue
        per = {}
        for g in groups:
            a = form.get(f'g_{mkey}_{g["key"]}')
            if a in codes or (a == GP_SETS and g['rule'] is not None):
                per[g['key']] = a
            else:
                missing.append(f'{_label(mkey)}: {g["label"]}')
        answers['measures'][mkey] = per
    for kind, items, field in (('individual', [m[0] for m in cat.MEASURES if m[4] == 'individual'], 'i_'),
                               ('modules', [m[0] for m in cat.MODULES], 'mod_'),
                               ('prevention', [p[0] for p in cat.PREVENTION], 'prev_')):
        for key in items:
            a = form.get(field + key)
            if a in (KEEP, DROP):
                answers[kind][key] = a
            else:
                missing.append({'individual': 'Individual measure', 'modules': 'Condition module',
                                'prevention': 'Prevention line'}[kind] + f': {key}')
    return answers, missing


def build_draft(user, answers: dict, note: str = '') -> ProtocolVersion:
    """A new draft version from complete wizard answers."""
    if svc.draft_version():
        raise svc.ProtocolError('There is already a draft version. Approve or discard it before running the wizard.')
    seed_guidelines(user.id)
    gl = _guidelines()
    ms = _measures()
    version = ProtocolVersion(version=svc._next_number(), status=ProtocolStatus.draft, created_by_id=user.id,
                              copied_from_id=None,
                              change_note=note or 'Built with the setup wizard from the option catalogue; '
                                                  'reviewed and edited by the practice before approval.')
    db.session.add(version)
    db.session.flush()
    n_options = 0

    def add(mkey, spec, code, rule, priority, group_label, gp_sets=False):
        o = ProtocolOption(version_id=version.id, measure_id=ms[mkey].id, code=code, label=spec['label'],
                           plan_wording=spec.get('plan_wording'), patient_group=group_label,
                           default_rule=svc.validate_rule(rule), priority=priority, gp_sets=gp_sets,
                           rationale='Chosen by the practice in the setup wizard.' if rule else None)
        nonlocal n_options
        n_options += 1
        db.session.add(o)
        db.session.flush()
        for g, sec, q in spec.get('citations', []):
            if gl.get(g):
                db.session.add(ProtocolOptionCitation(option_id=o.id, guideline_id=gl[g].id, section_ref=sec, quote=q))

    gp_spec = lambda mkey: dict(label=cat.GP_SETS_LABEL, plan_wording=f'Your GP has set your {_label(mkey).lower()} target.')
    for mkey, groups in cat.GROUPS.items():
        per = answers['measures'].get(mkey, LEAVE)
        if per == LEAVE:
            continue
        specs = {o['code']: o for o in cat.OPTIONS[mkey]}
        gp_preselected = False
        for i, g in enumerate(groups):
            a, pr = per[g['key']], (i + 1) * 10
            if a == GP_SETS:
                add(mkey, gp_spec(mkey), f'{mkey}_gp__{g["key"]}', g['rule'], pr, g['label'], gp_sets=True)
                gp_preselected = True
            else:
                add(mkey, specs[a], f'{a}__{g["key"]}', g['rule'], pr, g['label'])
        if not gp_preselected:   # always offered, never preselected
            add(mkey, gp_spec(mkey), f'{mkey}_gp', None, 100, None, gp_sets=True)

    for mkey, a in answers['individual'].items():
        if a == KEEP:
            for o in cat.OPTIONS[mkey]:
                add(mkey, o, o['code'], None, 10, 'Individual patients (set by the GP)')

    for i, (ckey, label, applies, fields) in enumerate(cat.MODULES):
        if answers['modules'].get(ckey) == KEEP:
            db.session.add(ProtocolModule(version_id=version.id, condition_key=ckey, label=label,
                                          applies_when=svc.validate_rule(applies), display_order=(i + 1) * 10, **fields))
    for i, (pkey, label, rule, wording, source) in enumerate(cat.PREVENTION):
        if answers['prevention'].get(pkey) == KEEP:
            db.session.add(ProtocolPreventionRule(version_id=version.id, key=pkey, label=label, rule=rule,
                                                  wording=wording, source=source, display_order=(i + 1) * 10))
    if not n_options:
        db.session.rollback()
        raise svc.ProtocolError('Every measure was left out: a protocol needs at least one target option.')
    db.session.commit()
    return version
