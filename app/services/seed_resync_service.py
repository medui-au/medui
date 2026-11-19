"""Seed resync: bring seeded prompts and workflows up to the installed release.

`flask install seeds` only adds what is missing, so after an upgrade the database
still holds the earlier release's seeded prompts and workflows, including ones the
release has dropped. The resync updates an item only when it is still exactly as
some release seeded it (`seed_history.json`). Anything the practice has edited is
listed and left alone unless named with `replace`. Items the practice created are
never touched. Each workflow keeps its model, data bundle, status and other step
settings. Replaced text is kept so every change can be reverted: user prompts in
`user_prompt_versions`, system prompts as their inactive earlier version. Dropped
items are only listed unless `archive_dropped` is set, and are archived, never
deleted. One transaction; a dry run rolls everything back.
"""
import hashlib
import json

from sqlalchemy import func, text

from app.extensions import db
from app.services import seed_fingerprint as fp
from app.services.seed_service import (ASSETS, _create_admin_lists, _insert_starter, _manifest,
                                       load_admin_lists, load_package, step_config)

_CATEGORIES = ('system_prompts', 'user_prompts', 'pipelines')

# Step settings the release owns; replaced on update. All other settings in an
# existing step (model, data bundle, scope, notice, overrides) are the practice's
# and are kept; a seed's value fills one only where the step has none.
_SEED_STEP_KEYS = {'user_prompt_id', 'default_setting_key'}
# Settings a release may add to an item already installed, filled only where
# empty: a system prompt's scope, a workflow step's scope or notice (format 4).
_FILL_STEP_KEYS = {'scope_key', 'ai_notice'}


def load_history(starter):
    """The fingerprint history, checked against the manifest and the current seeds."""
    manifest = _manifest()
    raw = (ASSETS / 'seed_history.json').read_bytes()
    expected = manifest['files'].get('seed_history.json')
    if not expected or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Seed checksum mismatch: seed_history.json')
    history = json.loads(raw)
    for category, items in fp.starter_fingerprints(starter).items():
        for name, fingerprint in items.items():
            if fingerprint not in history.get(category, {}).get(name, []):
                raise ValueError('Seed history is out of date: run scripts/build_seed_history.py')
    return history


def _classify(current, seed, past, forced):
    if current == seed:
        return 'current'
    if current in past:
        return 'updated'
    return 'replaced' if forced else 'customised'


def _fields(obj, names):
    return {n: getattr(obj, n) for n in names}


def _clean(value):
    return value.strip() or None if isinstance(value, str) else value


def _pipeline_fingerprint(pipeline, steps):
    from app.models.prompt import UserPrompt
    rows = []
    for step in steps:
        config = json.loads(step.config_json or '{}')
        name = key = None
        if step.node_type == 'prompt_assembly' and config.get('user_prompt_id'):
            prompt = db.session.get(UserPrompt, config['user_prompt_id'])
            name = prompt.name if prompt else None
        if step.node_type == 'inference':
            key = config.get('default_setting_key')
        rows.append((step.node_type, name, key))
    fields = _fields(pipeline, fp.PIPELINE_FIELDS)
    fields['redaction_policy'] = pipeline.redaction_policy.value
    return fp.pipeline(fields, rows)


def resync_seeds(*, dry_run=False, archive_dropped=False, replace=()):
    """Returns a list of {category, name, outcome, note}."""
    from app.models.prompt import SystemPrompt, UserPrompt
    from app.models.user_prompt_version import UserPromptVersion
    from app.models.data_bundle import DataBundle
    from app.models.pipeline import Pipeline, PipelineStatus, PipelineStep, RedactionPolicy
    from app.models.patient_message import MessageTemplate
    from app.version import __version__

    starter, _ = load_package()
    admin_lists = load_admin_lists()
    history = load_history(starter)
    replace = set(replace)
    seeded_names = set().union(*(history[c] for c in _CATEGORIES))
    unknown = replace - seeded_names
    if unknown:
        raise ValueError(f'Not a seeded prompt or workflow: {", ".join(sorted(unknown))}')
    seeds = {c: {r['name']: r for r in starter[c]} for c in _CATEGORIES}
    report = []
    reason = f'Seed resync to MedUI {__version__}'

    def note(category, name, outcome, detail=''):
        report.append({'category': category, 'name': name, 'outcome': outcome, 'note': detail})

    def single(rows, category, name):
        if len(rows) > 1:
            note(category, name, 'skipped', f'{len(rows)} items share this name')
            return None
        return rows[0] if rows else None

    def pipeline_steps(pipeline):
        return PipelineStep.query.filter_by(pipeline_id=pipeline.id).order_by(PipelineStep.step_order).all()

    try:
        if db.engine.dialect.name != 'postgresql':
            raise ValueError('Seed resync requires PostgreSQL')
        db.session.execute(text('SELECT pg_advisory_xact_lock(7165012026)'))

        # 1. System prompts: a replaced version stays as the inactive earlier version.
        for name, seed in seeds['system_prompts'].items():
            current = single(SystemPrompt.query.filter_by(name=name, is_active=True).all(),
                             'system_prompts', name)
            if current is None:
                continue
            outcome = _classify(fp.system_prompt(_fields(current, fp.SYSTEM_FIELDS)),
                                fp.system_prompt(seed), history['system_prompts'].get(name, []),
                                name in replace)
            scope = current.scope_key or seed.get('scope_key')
            if outcome in ('updated', 'replaced'):
                was_default = current.is_default
                current.is_active = False
                current.is_default = False
                db.session.flush()
                db.session.add(SystemPrompt(
                    name=name, prompt_text=seed['prompt_text'].strip(),
                    description=_clean(seed.get('description')), version=current.version + 1,
                    is_active=True, is_default=was_default, scope_key=scope))
            elif outcome == 'current' and scope != current.scope_key:
                current.scope_key = scope
                note('system_prompts', name, 'filled', f'scope: {scope}')
            note('system_prompts', name, outcome)

        # 2. User prompts: the replaced text goes to user_prompt_versions.
        for name, seed in seeds['user_prompts'].items():
            prompt = single(UserPrompt.query.filter_by(name=name).all(), 'user_prompts', name)
            if prompt is None:
                continue
            outcome = _classify(fp.user_prompt(_fields(prompt, fp.USER_FIELDS)),
                                fp.user_prompt(seed), history['user_prompts'].get(name, []),
                                name in replace)
            if outcome in ('updated', 'replaced'):
                last = db.session.query(func.max(UserPromptVersion.version)) \
                    .filter_by(user_prompt_id=prompt.id).scalar() or 0
                db.session.add(UserPromptVersion(user_prompt_id=prompt.id, version=last + 1,
                                                 name=prompt.name, reason=reason,
                                                 **_fields(prompt, fp.USER_FIELDS)))
                for field in fp.USER_FIELDS:
                    setattr(prompt, field, _clean(seed.get(field)))
            note('user_prompts', name, outcome)

        # 3. Items new in this release (workflows may need the new prompts).
        existing_pipelines = {p.name for p in Pipeline.query.all()}
        for category, model in (('system_prompts', SystemPrompt), ('user_prompts', UserPrompt),
                                ('data_bundles', DataBundle), ('pipelines', Pipeline),
                                ('message_templates', MessageTemplate)):
            have = {r.name for r in model.query.all()}
            for row in starter[category]:
                if row['name'] not in have:
                    note(category, row['name'], 'added')
        _insert_starter(starter, {})

        # 4. Workflows already installed: model, bundle, status and step settings kept.
        for name, seed in seeds['pipelines'].items():
            if name not in existing_pipelines:
                continue
            pipeline = single(Pipeline.query.filter_by(name=name).all(), 'pipelines', name)
            if pipeline is None:
                continue
            steps = pipeline_steps(pipeline)
            outcome = _classify(_pipeline_fingerprint(pipeline, steps), fp.seed_pipeline(seed),
                                history['pipelines'].get(name, []), name in replace)
            if outcome in ('updated', 'replaced'):
                pipeline.description = _clean(seed.get('description'))
                pipeline.classifier = _clean(seed.get('classifier'))
                pipeline.redaction_policy = RedactionPolicy[seed.get('redaction_policy', 'redact_all')]
                previous = {}
                for step in steps:
                    previous.setdefault(step.node_type, step)
                    db.session.delete(step)
                db.session.flush()
                for order, seed_step in enumerate(seed['steps']):
                    old = previous.get(seed_step['node_type'])
                    config = {k: v for k, v in json.loads(old.config_json or '{}').items()
                              if k not in _SEED_STEP_KEYS} if old else {}
                    for key, value in step_config(seed_step['config']).items():
                        if key in _SEED_STEP_KEYS or key not in config:
                            config[key] = value
                    db.session.add(PipelineStep(pipeline_id=pipeline.id, step_order=order,
                                                node_type=seed_step['node_type'],
                                                label=old.label if old else None,
                                                config_json=json.dumps(config)))
            elif outcome == 'current':
                filled = []
                for seed_step in seed['steps']:
                    wanted = {k: v for k, v in seed_step['config'].items() if k in _FILL_STEP_KEYS}
                    step = next((s for s in steps if s.node_type == seed_step['node_type']), None)
                    if not wanted or step is None:
                        continue
                    config = json.loads(step.config_json or '{}')
                    new = {k: v for k, v in wanted.items() if not config.get(k)}
                    if new:
                        config.update(new)
                        step.config_json = json.dumps(config)
                        filled += [f"{'notice' if k == 'ai_notice' else 'scope'}: {v}" for k, v in new.items()]
                if filled:
                    note('pipelines', name, 'filled', ', '.join(filled))
            note('pipelines', name, outcome)

        # 5. Dropped from this release: archived only on request, and only if unchanged
        #    and nothing still in use relies on them. Workflows first, then prompts.
        def dropped(category):
            return sorted(set(history[category]) - set(seeds[category]))

        going = set()   # dropped workflows archived now, or that would be with archive_dropped
        for name in dropped('pipelines'):
            pipeline = single(Pipeline.query.filter_by(name=name).all(), 'pipelines', name)
            if pipeline is None or pipeline.status == PipelineStatus.archived:
                continue
            if _pipeline_fingerprint(pipeline, pipeline_steps(pipeline)) not in history['pipelines'][name] \
                    and name not in replace:
                note('pipelines', name, 'dropped-customised')
                continue
            going.add(pipeline.id)
            if archive_dropped:
                pipeline.status = PipelineStatus.archived
                note('pipelines', name, 'dropped-archived')
            else:
                note('pipelines', name, 'dropped')
        db.session.flush()

        for name in dropped('user_prompts'):
            prompt = single(UserPrompt.query.filter_by(name=name).all(), 'user_prompts', name)
            if prompt is None or not prompt.is_active:
                continue
            if fp.user_prompt(_fields(prompt, fp.USER_FIELDS)) not in history['user_prompts'][name] \
                    and name not in replace:
                note('user_prompts', name, 'dropped-customised')
                continue
            users = [p.name for p in Pipeline.query.filter(Pipeline.status != PipelineStatus.archived)
                     if p.id not in going and any(s.node_type == 'prompt_assembly'
                            and json.loads(s.config_json or '{}').get('user_prompt_id') == prompt.id
                            for s in pipeline_steps(p))]
            if users:
                note('user_prompts', name, 'dropped-in-use', 'used by ' + ', '.join(sorted(users)))
            elif archive_dropped:
                prompt.is_active = False
                note('user_prompts', name, 'dropped-archived')
            else:
                note('user_prompts', name, 'dropped')
        db.session.flush()

        for name in dropped('system_prompts'):
            current = single(SystemPrompt.query.filter_by(name=name, is_active=True).all(),
                             'system_prompts', name)
            if current is None:
                continue
            if fp.system_prompt(_fields(current, fp.SYSTEM_FIELDS)) not in history['system_prompts'][name] \
                    and name not in replace:
                note('system_prompts', name, 'dropped-customised')
                continue
            users = [p.name for p in UserPrompt.query.filter_by(system_prompt_name=name, is_active=True)]
            if users:
                note('system_prompts', name, 'dropped-in-use', 'used by ' + ', '.join(sorted(users)))
            elif archive_dropped:
                current.is_active = False
                current.is_default = False
                note('system_prompts', name, 'dropped-archived')
            else:
                note('system_prompts', name, 'dropped')

        counts = {}
        _create_admin_lists(admin_lists, counts)
        for name, result in counts.items():
            if result['added']:
                note('admin_lists', name, 'added')

        db.session.flush()
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return report
    except Exception:
        db.session.rollback()
        raise
