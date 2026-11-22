"""flask protocol seed-v1 — load the practice's protocol version 1 as a draft (ADR-171)."""
import click
from flask.cli import AppGroup

protocol_cli = AppGroup('protocol', help='Practice protocols (ADR-171).')


def practice_data():
    """The practice's own protocol data module, if this installation has one (MedUI's open edition
    doesn't: each practice builds its own protocol on the screen)."""
    import importlib
    try:
        return importlib.import_module('app.services.protocol_seed_v1')
    except ImportError:
        return None


def seed_v1(user_id: int | None = None) -> dict:
    """Load version 1 as a draft. Refuses if any version exists. Measures and guidelines are
    matched by key and title, so re-running after a discarded draft reuses them."""
    from app.extensions import db
    from app.models.careplan import CareplanGuideline
    from app.models.protocol import (MeasureScope, ProtocolMeasure, ProtocolModule, ProtocolOption,
                                     ProtocolOptionCitation, ProtocolPreventionRule, ProtocolStatus,
                                     ProtocolVersion)
    from app.services.protocol_service import validate_rule
    data = practice_data()
    if data is None:
        raise click.ClickException('This installation has no practice protocol to load: an administrator builds '
                                   'the protocol on Admin → Practice Protocols (start a draft on the Versions tab).')

    if ProtocolVersion.query.first():
        raise click.ClickException('A protocol version already exists; seed-v1 only loads an empty protocol.')

    guidelines = {}
    for key, row in data.GUIDELINES.items():
        g = CareplanGuideline.query.filter_by(title=row['title']).first()
        if g is None:
            g = CareplanGuideline(accessed_on=data.ACCESSED, created_by_id=user_id, **row)
            db.session.add(g)
            db.session.flush()
        guidelines[key] = g

    measures = {}
    for key, label, unit, token, scope, order in data.MEASURES:
        m = ProtocolMeasure.query.filter_by(key=key).first()
        if m is None:
            m = ProtocolMeasure(key=key, label=label, unit=unit, token_key=token,
                                scope=MeasureScope(scope), display_order=order, active=True)
            db.session.add(m)
            db.session.flush()
        measures[key] = m

    version = ProtocolVersion(version=1, status=ProtocolStatus.draft, created_by_id=user_id,
                              change_note="Version 1: the clinical lead's decisions of 2026-11-22 and the practice GPMP library.")
    db.session.add(version)
    db.session.flush()

    n_opt = n_cit = 0
    for mkey, opts in data.OPTIONS.items():
        for spec in opts:
            spec = dict(spec)
            cites = spec.pop('citations', [])
            o = ProtocolOption(version_id=version.id, measure_id=measures[mkey].id,
                               default_rule=validate_rule(spec.pop('default_rule', None)),
                               gp_sets=spec.pop('gp_sets', False), **spec)
            db.session.add(o)
            db.session.flush()
            n_opt += 1
            for gkey, section, quote in cites:
                db.session.add(ProtocolOptionCitation(option_id=o.id, guideline_id=guidelines[gkey].id,
                                                      section_ref=section, quote=quote))
                n_cit += 1

    for i, (ckey, label, applies, fields) in enumerate(data.MODULES):
        db.session.add(ProtocolModule(version_id=version.id, condition_key=ckey, label=label,
                                      applies_when=validate_rule(applies), display_order=(i + 1) * 10, **fields))

    for i, (pkey, label, rule, wording, source) in enumerate(data.PREVENTION):
        db.session.add(ProtocolPreventionRule(version_id=version.id, key=pkey, label=label, rule=rule,
                                              wording=wording, source=source, display_order=(i + 1) * 10))
    db.session.commit()
    return {'version': version.version, 'measures': len(measures), 'options': n_opt, 'citations': n_cit,
            'guidelines': len(guidelines), 'modules': len(data.MODULES), 'prevention': len(data.PREVENTION)}


@protocol_cli.command('seed-v1')
def seed_v1_command():
    """Load the practice's protocol version 1 as a DRAFT, for an administrator to approve."""
    out = seed_v1()
    click.echo('Loaded protocol version {version} as a draft: {measures} measures, {options} options, '
               '{citations} citations, {guidelines} guidelines, {modules} modules, {prevention} prevention lines.'
               .format(**out))
    click.echo('An administrator approves it on Admin → Practice Protocols → Versions.')
