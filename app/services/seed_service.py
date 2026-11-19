"""Portable, insert-only seed installation. Never reads the legacy installation."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, Text, inspect, select, func, text
from app.extensions import db
# A seeded inference step names the kind of default model it falls back to,
# never a model: the practice chooses its models in Setup → AI Providers.
from app.services.seed_fingerprint import MODEL_DEFAULTS as _MODEL_DEFAULTS

ASSETS = Path(__file__).resolve().parents[1] / 'seed_assets'

# Step sequences a seeded workflow may have, with the redaction policy each allows.
# The patient workflows read a data bundle; the generic chatbot's two stages take
# only the typed question: a local model removes identifying details unredacted
# (nothing to de-redact), then the chatbot runs redacted and de-redacts.
_PATIENT = ('data_assembly', 'prompt_assembly', 'inference', 'deredaction')
_SEQUENCES = {
    _PATIENT: {'redact_all'},
    ('prompt_assembly', 'inference', 'deredaction'): {'redact_all'},
    ('prompt_assembly', 'inference'): {'redact_none'},
}

# Format 4: the scope instruction a seeded system prompt uses, and the on-screen
# notice a workflow chooses (upstream ADR-087/088). 'none' only for utility prompts.
_SCOPE_KEYS = {'record', 'scribe', 'correspondence', 'general', 'none'}
_NOTICE_KEYS = {'draft', 'chat_patient', 'chat_general', 'summary', 'scribe'}
_STEP_KEYS = {'data_assembly': {'bundle_name'}, 'prompt_assembly': {'user_prompt_name', 'scope_key'},
              'inference': {'model_default', 'ai_notice'}, 'deredaction': set()}

# An admin list's starting rows: labels only, never a pattern a typo could widen.
_SHAPE_CHARS = set('9AX-/. ')


def _manifest():
    manifest = json.loads((ASSETS / 'manifest.json').read_text())
    if manifest['format_version'] != 4:
        raise ValueError('Unsupported seed format')
    return manifest


def load_admin_lists():
    """Starting rows for admin-managed lists (format 3), checked.

    Each list is created at installation only if its table doesn't exist yet;
    after that it belongs to the practice and is never changed by a seed run.
    """
    manifest = _manifest()
    raw = (ASSETS / 'admin_lists.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['files']['admin_lists.json']:
        raise ValueError('Seed checksum mismatch: admin_lists.json')
    lists = json.loads(raw)
    for name, spec in lists.items():
        columns = spec['columns']
        if not columns or len(columns) != len(set(columns)) or 'id' in columns:
            raise ValueError(f'Invalid admin list columns: {name}')
        if any(set(row) != set(columns) for row in spec['rows']):
            raise ValueError(f'Admin list rows do not match columns: {name}')
    labels = [r['label'].strip().lower() for r in lists.get('identifier_labels', {}).get('rows', [])]
    if any(len(l) < 2 for l in labels) or len(labels) != len(set(labels)):
        raise ValueError('Invalid identifier labels')
    if any(set(r['shape']) - _SHAPE_CHARS for r in lists.get('identifier_labels', {}).get('rows', [])):
        raise ValueError('Invalid identifier label shape')
    return lists


def load_package():
    manifest = _manifest()
    packages = []
    for filename in ('starter.json', 'reference.json'):
        raw = (ASSETS / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['files'][filename]:
            raise ValueError(f'Seed checksum mismatch: {filename}')
        packages.append(json.loads(raw))
    starter, reference = packages
    from app.services.patient_json_service import BLOCK_LABELS
    for rows in starter.values():
        names = [r['name'] for r in rows]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate seed names')
    systems = {r['name'] for r in starter['system_prompts']}
    prompts = {r['name'] for r in starter['user_prompts']}
    bundles = {r['name'] for r in starter['data_bundles']}
    for row in starter['system_prompts']:
        if row.get('scope_key') not in _SCOPE_KEYS:
            raise ValueError('Unsupported scope')
    for row in starter['user_prompts']:
        if row['system_prompt_name'] and row['system_prompt_name'] not in systems:
            raise ValueError('Missing system prompt')
    for row in starter['data_bundles']:
        if any(b['block_source'] not in BLOCK_LABELS for b in row['blocks']):
            raise ValueError('Unsupported data block')
    for row in starter['pipelines']:
        sequence = tuple(s['node_type'] for s in row['steps'])
        if sequence not in _SEQUENCES:
            raise ValueError('Unsupported workflow sequence')
        if row.get('redaction_policy', 'redact_all') not in _SEQUENCES[sequence]:
            raise ValueError('Unsupported workflow redaction policy')
        if any(set(s['config']) - _STEP_KEYS[s['node_type']] for s in row['steps']):
            raise ValueError('Unsupported step settings')
        config = {s['node_type']: s['config'] for s in row['steps']}
        if config.get('prompt_assembly', {}).get('scope_key', 'record') not in _SCOPE_KEYS or \
                config['inference'].get('ai_notice', 'draft') not in _NOTICE_KEYS:
            raise ValueError('Unsupported scope or notice')
        if 'data_assembly' in config and config['data_assembly']['bundle_name'] not in bundles:
            raise ValueError('Missing workflow bundle')
        if config['prompt_assembly']['user_prompt_name'] not in prompts:
            raise ValueError('Missing workflow prompt')
        if config['inference'].get('model_default', 'local') not in _MODEL_DEFAULTS:
            raise ValueError('Unsupported inference settings')
    for kind, rows in reference.items():
        key = 'product_id' if kind == 'drug_mappings' else 'bpsdb_vaccine_id'
        ids = [r[key] for r in rows]
        if len(ids) != len(set(ids)) or any(not isinstance(i, int) or i <= 0 for i in ids):
            raise ValueError(f'Invalid reference identifiers: {kind}')
    return starter, reference


def _insert_starter(starter, counts):
    """Insert starter items whose names are missing; existing ones are left as they are."""
    from app.models.prompt import SystemPrompt, UserPrompt
    from app.models.data_bundle import DataBundle, BundleBlock
    from app.models.pipeline import Pipeline, PipelineStep, RedactionPolicy
    from app.models.patient_message import MessageTemplate

    def blocks(bundle, rows):
        for order, row in enumerate(rows):
            db.session.add(BundleBlock(bundle_id=bundle.id, block_order=order, **row))

    def steps(pipeline, rows):
        for order, row in enumerate(rows):
            db.session.add(PipelineStep(pipeline_id=pipeline.id, step_order=order,
                node_type=row['node_type'], config_json=json.dumps(step_config(row['config']))))

    def add(model, rows, category, key='name', children=None):
        added = skipped = 0
        for source in rows:
            row = dict(source)
            if model.query.filter_by(**{key: row[key]}).first():
                skipped += 1
                continue
            nested = row.pop(children[0]) if children else None
            if 'redaction_policy' in row:
                row['redaction_policy'] = RedactionPolicy[row['redaction_policy']]
            obj = model(**row)
            db.session.add(obj)
            db.session.flush()
            if children:
                children[1](obj, nested)
            added += 1
        counts[category] = {'added': added, 'skipped': skipped}

    add(SystemPrompt, starter['system_prompts'], 'system_prompts')
    add(UserPrompt, starter['user_prompts'], 'user_prompts')
    add(DataBundle, starter['data_bundles'], 'data_bundles', children=('blocks', blocks))
    add(Pipeline, starter['pipelines'], 'pipelines', children=('steps', steps))
    add(MessageTemplate, starter['message_templates'], 'message_templates')


def step_config(seed_config):
    """A seed step's config as stored: model kind → setting key, prompt name → id."""
    from app.models.prompt import UserPrompt
    config = dict(seed_config)
    if 'model_default' in config:
        config['default_setting_key'] = _MODEL_DEFAULTS[config.pop('model_default')]
    if 'user_prompt_name' in config:
        name = config.pop('user_prompt_name')
        matches = UserPrompt.query.filter_by(name=name).all()
        if len(matches) != 1:
            raise ValueError(f'Ambiguous existing user prompt: {name}')
        config['user_prompt_id'] = matches[0].id
    return config


def _install_reference(reference, counts):
    from app.models.drug_mapping import DrugMapping
    from app.models.mapping_table import MappingTable
    added = skipped = 0
    for source in reference['drug_mappings']:
        if DrugMapping.query.filter_by(product_id=source['product_id']).first():
            skipped += 1
            continue
        db.session.add(DrugMapping(**source))
        db.session.flush()
        added += 1
    counts['drug_mappings'] = {'added': added, 'skipped': skipped}
    connection = db.session.connection()
    for name in ('vaccine_mapping', 'nip_risk_mapping'):
        rows = reference[name]
        physical = 'mapdata_' + name
        registry = MappingTable.query.filter_by(name=name).first()
        exists = inspect(connection).has_table(physical)
        if exists != bool(registry):
            raise ValueError(f'Inconsistent existing mapping registry: {name}')
        if exists:
            table = Table(physical, MetaData(), autoload_with=connection)
            if not set(rows[0]).issubset(table.c.keys()):
                raise ValueError(f'Incompatible existing mapping columns: {name}')
        else:
            table = Table(physical, MetaData(), Column('id', Integer, primary_key=True),
                *(Column(k, Integer if k == 'bpsdb_vaccine_id' else Text) for k in rows[0]))
            table.create(connection)
            registry = MappingTable(name=name, label=name.replace('_', ' ').title(),
                description='Legacy reference snapshot; review against this practice’s BP dictionary and current guidance.')
            db.session.add(registry)
        existing = {str(v) for v in connection.execute(select(table.c.bpsdb_vaccine_id)).scalars()}
        missing = [r for r in rows if str(r['bpsdb_vaccine_id']) not in existing]
        if missing:
            connection.execute(table.insert(), missing)
        registry.row_count = connection.execute(select(func.count()).select_from(table)).scalar_one()
        counts[name] = {'added': len(missing), 'skipped': len(rows) - len(missing)}


def _create_admin_lists(admin_lists, counts):
    """Admin lists: created with their starting rows only when absent. An
    existing table is the practice's, edited or emptied on purpose."""
    from app.models.mapping_table import MappingTable
    connection = db.session.connection()
    for name, spec in admin_lists.items():
        physical = 'mapdata_' + name
        registry = MappingTable.query.filter_by(name=name).first()
        exists = inspect(connection).has_table(physical)
        if exists != bool(registry):
            raise ValueError(f'Inconsistent existing mapping registry: {name}')
        if exists:
            counts[name] = {'added': 0, 'skipped': len(spec['rows'])}
            continue
        table = Table(physical, MetaData(), Column('id', Integer, primary_key=True),
                      *(Column(c, Text) for c in spec['columns']))
        table.create(connection)
        if spec['rows']:
            connection.execute(table.insert(), spec['rows'])
        db.session.add(MappingTable(name=name, label=spec['label'], description=spec['description'],
                                    row_count=len(spec['rows'])))
        counts[name] = {'added': len(spec['rows']), 'skipped': 0}


def install_seeds(*, dry_run=False, include_reference_data=False):
    """One PostgreSQL transaction, including reference-table DDL; skip existing keys."""
    starter, reference = load_package()
    admin_lists = load_admin_lists()
    counts = {}
    try:
        if db.engine.dialect.name != 'postgresql':
            raise ValueError('Seed installation requires PostgreSQL')
        db.session.execute(text('SELECT pg_advisory_xact_lock(7165012026)'))
        _insert_starter(starter, counts)
        if include_reference_data:
            _install_reference(reference, counts)
        _create_admin_lists(admin_lists, counts)
        db.session.flush()
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return counts
    except Exception:
        db.session.rollback()
        raise
