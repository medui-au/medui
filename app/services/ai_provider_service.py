"""Service layer for AI provider and model management."""

from __future__ import annotations
import json
import re
import time
from datetime import datetime, timezone

from app.extensions import db
from app.models.ai_provider import AIProviderConfig, AIProviderPreset, AIModel


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------

def get_all_providers() -> list[AIProviderConfig]:
    return AIProviderConfig.query.order_by(AIProviderConfig.name).all()


def get_provider(provider_id: int) -> AIProviderConfig | None:
    return db.session.get(AIProviderConfig, provider_id)


def get_all_presets() -> list[AIProviderPreset]:
    return AIProviderPreset.query.order_by(AIProviderPreset.sort_order).all()


def get_preset(provider_key: str) -> AIProviderPreset | None:
    return AIProviderPreset.query.filter_by(provider_key=provider_key).first()


class ProviderError(ValueError):
    """A provider can't be added as asked; the message is for the administrator."""


def unique_provider_key(base: str) -> str:
    """`base`, or `base_2`, `base_3`… if a provider already has it (ADR-163): a second server of
    the same kind, such as a second Ollama, gets its own key."""
    base = re.sub(r'[^a-z0-9_]+', '_', (base or 'provider').lower()).strip('_')[:50] or 'provider'
    taken = {k for (k,) in db.session.query(AIProviderConfig.provider_key)
             .filter(AIProviderConfig.provider_key.like(f'{base}%')).all()}
    if base not in taken:
        return base
    n = 2
    while f'{base}_{n}' in taken:
        n += 1
    return f'{base}_{n}'


# Models URL to start a new provider with, by its base URL's host (ADR-191). OpenRouter lists
# only its zero-data-retention endpoints, so a practice picks from models that don't keep its
# requests; Groq's own /models list. Any provider can change or clear it in Setup → AI Providers.
SUGGESTED_MODELS_ENDPOINTS = {
    'openrouter.ai': 'https://openrouter.ai/api/v1/endpoints/zdr',
    'api.groq.com':  'https://api.groq.com/openai/v1/models',
}


def suggested_models_endpoint(base_url: str | None) -> str | None:
    """The models URL a provider at this base URL starts with, or None for the default."""
    from urllib.parse import urlparse
    host = (urlparse(base_url or '').hostname or '').lower()
    return SUGGESTED_MODELS_ENDPOINTS.get(host)


def models_endpoint_hint(base_url: str | None) -> str:
    """Placeholder for the Models URL field: the suggested URL, else the default it uses."""
    suggested = suggested_models_endpoint(base_url)
    if suggested:
        return suggested
    return ((base_url or '').rstrip('/') + '/models') if base_url else '/models'


def create_from_preset(provider_key: str, overrides: dict) -> AIProviderConfig:
    """Create a new AIProviderConfig pre-filled from a preset + admin overrides."""
    preset = AIProviderPreset.query.filter_by(provider_key=provider_key).first()
    if preset is None:
        raise ProviderError('Choose a preset first.')
    name = overrides.get('name') or preset.display_name
    if AIProviderConfig.query.filter(db.func.lower(AIProviderConfig.name) == name.lower()).first():
        raise ProviderError(f'A provider called "{name}" already exists: give this one another '
                            'display name, such as the server it runs on.')
    cfg = AIProviderConfig(
        name=name,
        provider_key=unique_provider_key(overrides.get('provider_key') or preset.provider_key),
        provider_type=preset.provider_type,
        base_url=overrides.get('base_url') or preset.base_url_default or '',
        is_local=overrides.get('is_local', preset.is_local_default),
        is_enabled=True,
        supports_model_fetching=preset.supports_model_fetching,
        notes=overrides.get('notes'),
    )
    cfg.models_endpoint = (overrides.get('models_endpoint')
                           or suggested_models_endpoint(cfg.base_url))
    if overrides.get('api_key'):
        cfg.api_key = overrides['api_key']

    # If preset has static models, seed them immediately
    if preset.static_models_json:
        try:
            static = json.loads(preset.static_models_json)
        except (json.JSONDecodeError, TypeError):
            static = []
        db.session.add(cfg)
        db.session.flush()   # get cfg.id
        for m in static:
            db.session.add(AIModel(
                provider_id=cfg.id,
                model_id=m['model_id'],
                display_name=m.get('display_name', m['model_id']),
                is_asr=bool(m.get('is_asr', False)),
                task_tier=m.get('task_tier'),
                is_enabled=True,
            ))
    else:
        db.session.add(cfg)

    db.session.commit()
    return cfg


def create_custom(data: dict) -> AIProviderConfig:
    """Create a fully custom AIProviderConfig."""
    if not data.get('provider_key'):
        raise ProviderError('Give the provider a key.')
    if AIProviderConfig.query.filter_by(provider_key=data['provider_key']).first():
        raise ProviderError(f'The key "{data["provider_key"]}" is used by another provider: choose '
                            f'another, such as {unique_provider_key(data["provider_key"])}.')
    cfg = AIProviderConfig(
        name=data['name'],
        provider_key=data['provider_key'],
        provider_type=data.get('provider_type', 'openai_compatible'),
        base_url=data.get('base_url', ''),
        is_local=bool(data.get('is_local', False)),
        is_enabled=True,
        supports_model_fetching=bool(data.get('supports_model_fetching', False)),
        notes=data.get('notes'),
    )
    if data.get('api_key'):
        cfg.api_key = data['api_key']
    db.session.add(cfg)
    db.session.commit()
    return cfg


def update_provider(provider_id: int, data: dict) -> AIProviderConfig:
    cfg = db.session.get(AIProviderConfig, provider_id)
    if not cfg:
        raise ValueError(f'Provider {provider_id} not found')
    for field in ('name', 'base_url', 'provider_type', 'models_endpoint', 'notes'):
        if field in data:
            setattr(cfg, field, data[field] or None)
    if 'is_local' in data:
        cfg.is_local = bool(data['is_local'])
    if 'is_enabled' in data:
        cfg.is_enabled = bool(data['is_enabled'])
    if 'supports_model_fetching' in data:
        cfg.supports_model_fetching = bool(data['supports_model_fetching'])
    if 'api_key' in data and data['api_key']:
        cfg.api_key = data['api_key']
    db.session.commit()
    return cfg


def delete_provider(provider_id: int) -> None:
    cfg = db.session.get(AIProviderConfig, provider_id)
    if cfg:
        db.session.delete(cfg)
        db.session.commit()


# ---------------------------------------------------------------------------
# Connection testing
# ---------------------------------------------------------------------------

def test_connection(provider_id: int) -> dict:
    """Health-check a provider. Records last_tested_at and last_test_status."""
    cfg = db.session.get(AIProviderConfig, provider_id)
    if not cfg:
        return {'status': 'fail', 'message': 'Provider not found', 'latency_ms': 0}

    # Pick any enabled model, or use a placeholder
    model = cfg.models.filter_by(is_enabled=True).first()
    model_id = model.model_id if model else 'test'

    from .ai_providers.factory import get_provider
    t0 = time.monotonic()
    try:
        provider = get_provider(cfg, model_id)
        ok = provider.health_check()
        latency = int((time.monotonic() - t0) * 1000)
        status = 'ok' if ok else 'fail'
        message = 'Connection successful' if ok else 'Health check returned false'
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        status = 'fail'
        message = str(exc)[:200]

    cfg.last_tested_at = datetime.now(timezone.utc)
    cfg.last_test_status = status
    db.session.commit()
    return {'status': status, 'message': message, 'latency_ms': latency}


# ---------------------------------------------------------------------------
# Model fetching
# ---------------------------------------------------------------------------

def fetch_models(provider_id: int) -> dict:
    """Query the provider's /models endpoint and upsert AIModel rows."""
    cfg = db.session.get(AIProviderConfig, provider_id)
    if not cfg:
        return {'added': 0, 'updated': 0, 'error': 'Provider not found'}
    if not cfg.supports_model_fetching:
        return {'added': 0, 'updated': 0, 'error': 'Provider does not support model fetching'}

    try:
        if cfg.models_endpoint:
            # Use the override URL directly (e.g. OpenRouter ZDR endpoint)
            import requests
            headers = {}
            if cfg.api_key:
                headers['Authorization'] = f'Bearer {cfg.api_key}'
            resp = requests.get(cfg.models_endpoint, headers=headers, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            # Handle multiple response formats:
            #   OpenAI /models  → {"data": [{"id": "..."}]}
            #   Ollama /api/tags → {"models": [{"name": "..."}]}
            #   plain list      → [{"id": "..."} | {"name": "..."}]
            if isinstance(payload, dict):
                items = payload.get('data') or payload.get('models') or []
            else:
                items = payload
            remote_models = []
            for m in items:
                if not isinstance(m, dict):
                    continue
                # Field name varies by endpoint:
                #   OpenAI /models + standard OpenRouter: "id"
                #   OpenRouter /endpoints/zdr:            "model_id"
                #   Ollama /api/tags:                     "name"
                model_id = m.get('id') or m.get('model_id') or m.get('name')
                if model_id:
                    remote_models.append({
                        'model_id': model_id,
                        'display_name': m.get('name', model_id),
                    })
        else:
            from .ai_providers.factory import get_provider
            from .ai_providers.openai_compatible import OpenAICompatibleProvider
            provider = get_provider(cfg, '')
            if not isinstance(provider, OpenAICompatibleProvider):
                return {'added': 0, 'updated': 0, 'error': 'Model fetching only supported for OpenAI-compatible providers'}
            remote_models = provider.list_models()
    except Exception as exc:
        return {'added': 0, 'updated': 0, 'error': str(exc)[:200]}

    added = updated = 0
    for m in remote_models:
        mid = m['model_id']
        existing = AIModel.query.filter_by(provider_id=provider_id, model_id=mid).first()
        if existing:
            existing.display_name = m.get('display_name', mid)
            updated += 1
        else:
            db.session.add(AIModel(
                provider_id=provider_id,
                model_id=mid,
                display_name=m.get('display_name', mid),
                is_enabled=False,  # new fetched models start disabled; admin enables what's needed
            ))
            added += 1

    db.session.commit()
    return {'added': added, 'updated': updated, 'error': None}


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

def disable_all_models(provider_id: int) -> None:
    AIModel.query.filter_by(provider_id=provider_id).update({'is_enabled': False})
    db.session.commit()


def _model_delete_blockers(model_ids: list[int]) -> dict[int, list[str]]:
    """Map model_id -> reasons it can't be deleted. Covers two different kinds
    of reference:
      - Real FK columns with no ON DELETE rule (user_prompts.default_model_id,
        chats.chatbot_model_id_override) — deleting a referenced row raises
        IntegrityError, which previously rolled back the *entire* batch in
        delete_disabled_models, silently leaving every disabled model in
        place rather than just the referenced one.
      - PipelineStep.config_json — a free-form JSON blob that can carry a
        'model_id' key (see pipeline.py) with NO foreign key at all, so it
        can't block the delete at the DB level the way the two columns
        above do. Left unchecked, deleting a model referenced only here
        would succeed silently and only surface later as a runtime "Model
        not found" failure the next time that pipeline runs. Treated the
        same as a hard blocker (skip the delete) since the reference is
        unrecoverable once the underlying model row is gone — a re-fetch
        from the provider creates a new row with a new id, not the old one.
    """
    import json as _json
    from app.models.prompt import UserPrompt
    from app.models.chat import ChatSession
    from app.models.pipeline import Pipeline, PipelineStep

    if not model_ids:
        return {}

    blockers: dict[int, list[str]] = {}
    for p in UserPrompt.query.filter(UserPrompt.default_model_id.in_(model_ids)).all():
        blockers.setdefault(p.default_model_id, []).append(f'prompt "{p.name}"')

    chat_counts = (
        db.session.query(ChatSession.chatbot_model_id_override, db.func.count(ChatSession.id))
        .filter(ChatSession.chatbot_model_id_override.in_(model_ids))
        .group_by(ChatSession.chatbot_model_id_override)
        .all()
    )
    for model_id, count in chat_counts:
        blockers.setdefault(model_id, []).append(f'{count} chat session override(s)')

    model_id_set = set(model_ids)
    pipeline_names: dict[int, str] = {}
    seen_pipeline_per_model: dict[int, set[int]] = {}
    for step in PipelineStep.query.all():
        try:
            cfg = _json.loads(step.config_json or '{}')
        except (ValueError, TypeError):
            continue
        step_model_id = cfg.get('model_id')
        if step_model_id not in model_id_set:
            continue
        if step.pipeline_id not in pipeline_names:
            pl = db.session.get(Pipeline, step.pipeline_id)
            pipeline_names[step.pipeline_id] = pl.name if pl else f'pipeline #{step.pipeline_id}'
        seen = seen_pipeline_per_model.setdefault(step_model_id, set())
        if step.pipeline_id not in seen:
            seen.add(step.pipeline_id)
            blockers.setdefault(step_model_id, []).append(f'pipeline "{pipeline_names[step.pipeline_id]}"')

    return blockers


def delete_disabled_models(provider_id: int) -> dict:
    rows = AIModel.query.filter_by(provider_id=provider_id, is_enabled=False).all()
    blockers = _model_delete_blockers([m.id for m in rows])

    deleted_count = 0
    skipped = []
    for m in rows:
        if m.id in blockers:
            skipped.append({'model': m, 'blockers': blockers[m.id]})
        else:
            db.session.delete(m)
            deleted_count += 1

    db.session.commit()
    return {'deleted_count': deleted_count, 'skipped': skipped}


def delete_model(model_id: int) -> dict:
    m = db.session.get(AIModel, model_id)
    if not m:
        return {'deleted': False, 'blockers': []}

    blockers = _model_delete_blockers([model_id]).get(model_id, [])
    if blockers:
        return {'deleted': False, 'blockers': blockers}

    db.session.delete(m)
    db.session.commit()
    return {'deleted': True, 'blockers': []}


def add_manual_model(data: dict) -> AIModel:
    if not data.get('model_id'):
        raise ValueError('Model ID is required')
    if not data.get('provider_id'):
        raise ValueError('Provider is required')
    ctx = data.get('context_length')
    m = AIModel(
        provider_id=int(data['provider_id']),
        model_id=data['model_id'],
        display_name=data.get('display_name') or data['model_id'],
        task_tier=data.get('task_tier') or None,
        context_length=int(ctx) if ctx else None,
        is_enabled=True,
    )
    db.session.add(m)
    db.session.commit()
    return m


def get_models_for_provider(provider_id: int) -> list[AIModel]:
    return (AIModel.query
            .filter_by(provider_id=provider_id)
            .order_by(AIModel.display_name)
            .all())


def toggle_model(model_id: int) -> AIModel:
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    m.is_enabled = not m.is_enabled
    db.session.commit()
    return m


def set_model_asr(model_id: int, is_asr: bool) -> AIModel:
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    m.is_asr = is_asr
    db.session.commit()
    return m


def set_model_tier(model_id: int, tier: str | None) -> AIModel:
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    m.task_tier = tier if tier in ('fast', 'balanced', 'quality', None) else None
    db.session.commit()
    return m


def set_model_request_params(model_id: int, text: str | None) -> AIModel:
    """Save a model's extra request parameters (ADR-119); raises ValueError if invalid."""
    from app.services import request_params
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    value = request_params.parse(text, asr=bool(m.is_asr))
    m.request_params = json.dumps(value) if value else None
    db.session.commit()
    return m


def set_model_speaker_turns(model_id: int, version: str | None) -> AIModel:
    """Switch Deepgram speaker separation on ('latest', 'v2', 'v1') or off for an ASR model
    (ADR-151); raises ValueError for another value or a model that can't use it."""
    from app.services.ai_providers.asr import DEEPGRAM_SPEAKER_VERSIONS
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    version = (version or '').strip() or None
    if version is not None:
        if version not in DEEPGRAM_SPEAKER_VERSIONS:
            raise ValueError('Speaker turns must be off, latest, v2 or v1')
        if not (m.is_asr and m.provider and m.provider.provider_type == 'asr_deepgram'):
            raise ValueError('Speaker turns are only available on a Deepgram ASR model')
    m.speaker_turns = version
    db.session.commit()
    return m


def set_model_recommended(model_id: int, recommended: bool) -> AIModel:
    m = db.session.get(AIModel, model_id)
    if not m:
        raise ValueError(f'Model {model_id} not found')
    m.is_recommended = recommended
    db.session.commit()
    return m
