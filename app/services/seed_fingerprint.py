"""Fingerprints of seeded prompts and workflows, for the seed resync.

A fingerprint covers only what a release defines. What each practice chooses —
a workflow's model, data bundle, status and other step settings, a prompt's
model, active flag and assistant listing — is left out, so changing those never
makes an item look customised, and the resync never replaces them.

No app imports: `scripts/build_seed_history.py` uses this outside the app.
"""
import hashlib
import json

SYSTEM_FIELDS = ('prompt_text', 'description')
USER_FIELDS = ('description', 'prompt_text', 'system_prompt_name', 'classifier',
               'temperature', 'max_tokens')
PIPELINE_FIELDS = ('description', 'classifier', 'redaction_policy')

# Seed `model_default` → the setting an inference step falls back to.
MODEL_DEFAULTS = {
    'local': 'default_local_model_id',
    'chatbot': 'default_chatbot_model_id',
}


def _norm(value):
    """Prompt Manager strips text and saves empty fields as None; compare the same way."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def system_prompt(row) -> str:
    return _digest({f: _norm(row.get(f)) for f in SYSTEM_FIELDS})


def user_prompt(row) -> str:
    return _digest({f: _norm(row.get(f)) for f in USER_FIELDS})


def pipeline(fields, steps) -> str:
    """`steps`: [(node_type, user_prompt_name or None, default_setting_key or None)]."""
    data = {f: _norm(fields.get(f)) for f in PIPELINE_FIELDS}
    data['redaction_policy'] = data['redaction_policy'] or 'redact_all'
    data['steps'] = [[n, _norm(p), _norm(k)] for n, p, k in steps]
    return _digest(data)


def seed_steps(row):
    """A seed workflow's steps in fingerprint form."""
    out = []
    for step in row['steps']:
        config = step.get('config') or {}
        key = MODEL_DEFAULTS.get(config['model_default']) if 'model_default' in config else None
        out.append((step['node_type'], config.get('user_prompt_name'), key))
    return out


def seed_pipeline(row) -> str:
    return pipeline(row, seed_steps(row))


def starter_fingerprints(starter) -> dict:
    """{category: {name: fingerprint}} for one release's starter.json."""
    return {
        'system_prompts': {r['name']: system_prompt(r) for r in starter.get('system_prompts', [])},
        'user_prompts': {r['name']: user_prompt(r) for r in starter.get('user_prompts', [])},
        'pipelines': {r['name']: seed_pipeline(r) for r in starter.get('pipelines', [])},
    }
