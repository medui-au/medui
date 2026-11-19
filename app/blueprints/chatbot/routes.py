"""Chatbot blueprint — multi-turn patient AI chat.

Routes
------
GET  /clinical/chatbot/<patient_id>                    Chat page (finds-or-creates the user's active session)
POST /clinical/chatbot/<patient_id>/message             Send a message, start a pipeline run (returns {run_id})
GET  /clinical/chatbot/generic                          Generic (no-patient) chat page — Doctor Data
POST /clinical/chatbot/generic/message                  Send a message on the generic chatbot (stage 1: PII erasure)
POST /clinical/chatbot/generic/message/continue          Stage 2: start the answer run once stage 1's SSE completes
POST /clinical/chatbot/generic/message/direct            No AI erasure step: straight to stage 2, after the user's acknowledgment (ADR-098)
POST /clinical/chatbot/session/<session_id>/complete     Persist the assistant's reply once a run's SSE stream completes
GET  /clinical/chatbot/session/<session_id>/new          Archive the current session, start a fresh one
GET  /clinical/chatbot/generic/sessions                  Sidebar list of previous generic chats (title/content search via ?q=)
GET  /clinical/chatbot/<patient_id>/sessions             Sidebar list of previous chats for this patient (title/content search via ?q=)
GET  /clinical/chatbot/session/<session_id>/resume        Make a previous chat (generic or patient-scoped) active again
POST /clinical/chatbot/session/<session_id>/delete        Soft-delete a chat from the sidebar (see ChatSession.is_deleted)
POST /clinical/chatbot/message/<message_id>/download     Create a downloadable file from an assistant reply
GET  /clinical/chatbot/file/<file_id>/download           Download a previously generated file
POST /clinical/chatbot/render-markdown                    Sanitized markdown/HTML -> HTML, for Print + the Rendered tab
GET  /clinical/chatbot/prompts                            List the current user's saved prompts
POST /clinical/chatbot/prompts                             Save a new prompt
DELETE /clinical/chatbot/prompts/<prompt_id>               Delete a saved prompt
"""

import io
import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import render_template, request, abort, jsonify, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from . import bp
from app.services.pipeline.review import meta_for as review_meta_for
from app.extensions import db
from app.services.clinical_service import ClinicalService
from app.models.pipeline import Pipeline, PipelineStatus, PipelineRun, RunStatus
from app.models.chat import ChatSession, ChatMessage, ChatGeneratedFile, ChatSavedPrompt
from app.utils.access import ai_required

HISTORY_TURNS = 10  # last N messages folded into conversation_history_text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_patient(patient_id: int) -> dict:
    try:
        patient = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:
        current_app.logger.error('chatbot._get_patient(%d): %s', patient_id, e)
        patient = None
    if not patient:
        abort(404)
    patient['patient_id'] = patient_id
    return patient


def _find_pipeline_by_classifier(classifier: str):
    """Active Pipeline authored with the given classifier (bracket-tolerant, matching ai_panel)."""
    return (Pipeline.query
            .filter(
                or_(
                    func.lower(Pipeline.classifier) == classifier,
                    func.lower(Pipeline.classifier) == f'[{classifier}]',
                ),
                Pipeline.status == PipelineStatus.active,
            )
            .order_by(Pipeline.is_default.desc(), Pipeline.name)
            .first())


def _find_chatbot_pipeline():
    return _find_pipeline_by_classifier('chatbot')


def _find_generic_chatbot_pipeline():
    return _find_pipeline_by_classifier('chatbot_generic')


def _find_pii_erasure_pipeline():
    return _find_pipeline_by_classifier('chatbot_generic_pii')


NO_ERASURE_SETTING = 'chatbot.generic_without_erasure'


def _generic_mode() -> str:
    """How the generic chatbot protects what is typed (ADR-098).

    'erasure'   — an active PII Erasure workflow runs first (stage 1). If it fails,
                  the message is refused: a practice that switched erasure on never
                  silently loses it.
    'warn'      — no active erasure workflow, and the practice allows sending with
                  rule-based redaction only, after a warning.
    'off'       — no active erasure workflow, and the practice doesn't allow it.
    """
    if _find_pii_erasure_pipeline():
        return 'erasure'
    from app.models.system_setting import SystemSetting
    return 'off' if SystemSetting.get(NO_ERASURE_SETTING, 'warn') == 'off' else 'warn'


def _get_active_session(patient_id: int | None, create: bool = True) -> ChatSession | None:
    session = (ChatSession.query
               .filter_by(patient_id=patient_id, user_id=current_user.id, is_archived=False, is_deleted=False)
               .order_by(ChatSession.created_at.desc())
               .first())
    if session or not create:
        return session

    pipeline = _find_chatbot_pipeline() if patient_id else _find_generic_chatbot_pipeline()
    if not pipeline:
        return None

    session = ChatSession(
        token_key=secrets.token_hex(32),
        patient_id=patient_id,
        user_id=current_user.id,
        pipeline_id=pipeline.id,
    )
    db.session.add(session)
    db.session.commit()
    return session


_MODEL_PREF = {'patient': 'chatbot.patient_model', 'generic': 'chatbot.generic_model'}


def _remembered_model(kind: str, ai_models, default_model) -> tuple[int | None, bool]:
    """(model to pre-select, show the local→cloud note).

    The model this user last chose, only if it is still in the dropdown
    (enabled, listed for the chatbot, provider on). Otherwise the dropdown
    stays on the default, silently — except a note when the user's last choice
    was a local model and the default is a cloud one.
    """
    from app.models.ai_provider import AIModel
    from app.services import user_settings_service as user_settings
    saved = user_settings.get(current_user, _MODEL_PREF[kind])
    if not saved:
        return None, False
    listed = {m.id: m for m in ai_models if m.provider and m.provider.is_enabled}
    if saved in listed:
        return saved, False
    gone = db.session.get(AIModel, saved)
    was_local = bool(gone and gone.provider and gone.provider.is_local)
    default_cloud = bool(default_model and default_model.provider and not default_model.provider.is_local)
    return None, was_local and default_cloud


def _resolve_default_model(pipeline):
    """Mirror InferenceNode's fallback chain (minus any per-request override) to find
    which model a turn would actually use if the user leaves the dropdown on "Default
    model" — purely for an honest label, never used to decide what's actually sent."""
    if not pipeline:
        return None

    import json as _json
    from app.models.prompt import UserPrompt
    from app.models.system_setting import SystemSetting
    from app.models.ai_provider import AIModel

    inference_cfg = {}
    prompt_default_model_id = None
    for step in sorted(pipeline.steps, key=lambda s: s.step_order):
        try:
            cfg = _json.loads(step.config_json or '{}')
        except ValueError:
            cfg = {}
        if step.node_type == 'prompt_assembly' and cfg.get('user_prompt_id'):
            up = db.session.get(UserPrompt, cfg['user_prompt_id'])
            if up:
                prompt_default_model_id = cfg.get('model_id') or up.default_model_id
        elif step.node_type == 'inference':
            inference_cfg = cfg

    model_id = inference_cfg.get('model_id') or prompt_default_model_id
    if not model_id:
        model_id = SystemSetting.get(inference_cfg.get('default_setting_key', 'default_model_id'))
    return db.session.get(AIModel, int(model_id)) if model_id else None


def _history_text(session: ChatSession) -> str:
    recent = (ChatMessage.query
              .filter_by(session_id=session.id)
              .filter(ChatMessage.role.in_(['user', 'assistant']))
              .order_by(ChatMessage.created_at.desc())
              .limit(HISTORY_TURNS)
              .all())
    recent.reverse()
    lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in recent]
    history = '\n'.join(lines)
    if session.title:
        # chatbot_generic's system prompt instructs the model to keep re-using
        # the same Title across turns unless the conversation's topic shifts —
        # but ChatMessage.content only ever stores the unwrapped Response text
        # (see complete()), never the raw {"Title": ..., "Response": ...}
        # envelope, so without this reminder the model has no way to see what
        # title it previously assigned and would likely reinvent slightly
        # different wording every turn instead of holding it steady.
        history = f'[Current conversation title: "{session.title}"]\n\n{history}'
    return history


def _message_badges(message: ChatMessage) -> dict:
    """Cheap per-message metadata for the cloud/local + redacted badges — direct
    columns on the linked PipelineRun, no JSON parsing, safe for every historical
    message on every page load."""
    run = message.pipeline_run
    if not run:
        return {'is_redacted': None, 'model_is_local': None}
    return {'is_redacted': run.is_redacted, 'model_is_local': run.model_is_local}


def _session_totals(session: ChatSession) -> dict:
    """Sum tokens/cost across every completed turn in this session, from each
    turn's PipelineRun.output_json (already-parsed ai_responses — no need to
    touch the larger step_snapshots_json for this)."""
    import json as _json

    tokens_in = tokens_out = cached_tokens = 0
    cost = 0.0
    have_cost = False

    for m in session.messages:
        if not m.pipeline_run:
            continue
        try:
            output = _json.loads(m.pipeline_run.output_json or '{}')
        except (ValueError, TypeError):
            continue
        for resp in output.get('ai_responses', []):
            tokens_in += resp.get('tokens_input', 0) or 0
            tokens_out += resp.get('tokens_output', 0) or 0
            cached_tokens += resp.get('cached_tokens', 0) or 0
            if resp.get('cost') is not None:
                cost += resp['cost']
                have_cost = True

    return {
        'tokens_input': tokens_in,
        'tokens_output': tokens_out,
        'cached_tokens': cached_tokens,
        'cost': cost if have_cost else None,
    }


# ── Chat page ────────────────────────────────────────────────────────────────

@bp.get('/<int:patient_id>')
@login_required
@ai_required
def index(patient_id: int):
    patient = _get_patient(patient_id)
    session = _get_active_session(patient_id)

    pipeline = _find_chatbot_pipeline()

    from app.models.ai_provider import AIModel
    ai_models = (AIModel.query
                 .filter_by(is_enabled=True, show_in_chatbot=True, is_asr=False)
                 .order_by(AIModel.display_name)
                 .all())

    messages = []
    if session:
        messages = (ChatMessage.query
                    .filter_by(session_id=session.id)
                    .order_by(ChatMessage.created_at.asc())
                    .all())

    default_model = _resolve_default_model(pipeline)
    default_model_label = None
    if default_model:
        default_model_label = default_model.display_name or default_model.model_id
        if default_model.provider:
            default_model_label += ' (local)' if default_model.provider.is_local else ' (cloud)'

    remembered_model_id, model_fallback_note = _remembered_model('patient', ai_models, default_model)
    message_badges = {m.id: _message_badges(m) for m in messages}
    totals = _session_totals(session) if session else None

    from app.models.system_setting import SystemSetting
    practice_name = SystemSetting.get('general.practice_name', 'The Practice')

    return render_template(
        'clinical/chatbot_panel.html',
        patient=patient,
        patient_id=patient_id,
        session=session,
        pipeline=pipeline,
        ai_models=ai_models,
        messages=messages,
        default_model_label=default_model_label,
        remembered_model_id=remembered_model_id,
        model_fallback_note=model_fallback_note,
        message_badges=message_badges,
        practice_name=practice_name,
        totals=totals,
    )


@bp.post('/pref/model')
@login_required
@ai_required
def save_model_pref():
    """Remember the model chosen in a chatbot's dropdown (blank = the default)."""
    from app.models.ai_provider import AIModel
    from app.services import user_settings_service as user_settings
    data = request.get_json(silent=True) or {}
    kind = data.get('kind')
    if kind not in _MODEL_PREF:
        return jsonify({'error': 'kind must be patient or generic'}), 400
    model_id = data.get('model_id') or None
    if model_id is not None:
        try:
            model_id = int(model_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid model_id'}), 400
        if not AIModel.query.filter_by(id=model_id, is_enabled=True, show_in_chatbot=True).first():
            return jsonify({'error': 'Invalid model_id'}), 400
    user_settings.set(current_user, _MODEL_PREF[kind], model_id)
    return jsonify({'ok': True})


# ── Send message ─────────────────────────────────────────────────────────────

@bp.post('/<int:patient_id>/message')
@login_required
@ai_required
def send_message(patient_id: int):
    _get_patient(patient_id)  # 404 if not a valid patient
    session = _get_active_session(patient_id)
    if not session:
        return jsonify({'error': 'No active Chatbot pipeline configured — set one up in Pipeline Designer.'}), 400

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    model_override = data.get('model_id_override')

    history_text = _history_text(session)

    db.session.add(ChatMessage(session_id=session.id, role='user', content=message))
    session.last_activity_at = datetime.now(timezone.utc)
    db.session.commit()

    input_data = {
        'user_prompt': message,
        'conversation_history_text': history_text,
    }
    if model_override:
        try:
            input_data['model_id_override'] = int(model_override)
        except (TypeError, ValueError):
            pass

    from app.services.pipeline.engine import PipelineEngine
    try:
        run_id = PipelineEngine.run(
            pipeline_id=session.pipeline_id,
            patient_id=patient_id,
            user_id=current_user.id,
            input_data=input_data,
            model_is_local=False,
            token_key=session.token_key,
            review=review_meta_for(current_user, bool(data.get('review_capable')),
                                   remember_removed=True),
        )
    except Exception as exc:
        current_app.logger.error('chatbot.send_message run start failed: %s', exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'run_id': run_id, 'session_id': session.id})


# ── Generic (no-patient) chat page ───────────────────────────────────────────

@bp.get('/generic')
@login_required
@ai_required
def generic_index():
    session = _get_active_session(None)
    pipeline = _find_generic_chatbot_pipeline()

    from app.models.ai_provider import AIModel
    ai_models = (AIModel.query
                 .filter_by(is_enabled=True, show_in_chatbot=True, is_asr=False)
                 .order_by(AIModel.display_name)
                 .all())

    messages = []
    if session:
        messages = (ChatMessage.query
                    .filter_by(session_id=session.id)
                    .order_by(ChatMessage.created_at.asc())
                    .all())

    default_model = _resolve_default_model(pipeline)
    default_model_label = None
    if default_model:
        default_model_label = default_model.display_name or default_model.model_id
        if default_model.provider:
            default_model_label += ' (local)' if default_model.provider.is_local else ' (cloud)'

    remembered_model_id, model_fallback_note = _remembered_model('generic', ai_models, default_model)
    message_badges = {m.id: _message_badges(m) for m in messages}
    totals = _session_totals(session) if session else None

    from app.models.system_setting import SystemSetting
    practice_name = SystemSetting.get('general.practice_name', 'The Practice')

    return render_template(
        'clinical/chatbot_generic_panel.html',
        session=session,
        pipeline=pipeline,
        ai_models=ai_models,
        messages=messages,
        default_model_label=default_model_label,
        remembered_model_id=remembered_model_id,
        model_fallback_note=model_fallback_note,
        message_badges=message_badges,
        practice_name=practice_name,
        totals=totals,
        erasure_mode=_generic_mode(),
    )


# ── Generic chat: stage 1 — PII erasure ──────────────────────────────────────
# Two separate Pipelines rather than one 2-step pipeline, run as two
# client-orchestrated SSE runs: WorkflowContext.input is one shared dict per
# run, and InferenceNode's model resolution always lets a client-sent
# model_id_override win — sharing one run between the erasure step and the
# answer step would let a doctor's cloud model choice (meant only for the
# answer) silently redirect the erasure step too. Splitting into two runs
# means the override is only ever included in stage 2's request body, so it
# structurally cannot reach stage 1.

@bp.post('/generic/message')
@login_required
@ai_required
def send_message_generic():
    session = _get_active_session(None)
    if not session:
        return jsonify({'error': 'No active generic Chatbot pipeline configured — set one up in Pipeline Designer.'}), 400

    pii_pipeline = _find_pii_erasure_pipeline()
    if not pii_pipeline:
        return jsonify({'error': 'No active PII Erasure workflow — reload the page.'}), 400

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    # Nothing is persisted here — the raw, pre-erasure message only ever lives
    # in this pipeline run's memory. The user's turn is stored once, by
    # send_message_generic_continue, using the *erased* text once it's known.
    input_data = {'user_prompt': message}

    from app.services.pipeline.engine import PipelineEngine
    try:
        run_id = PipelineEngine.run(
            pipeline_id=pii_pipeline.id,
            patient_id=None,
            user_id=current_user.id,
            input_data=input_data,
            model_is_local=True,  # asserted + engine-enforced: _security_pre_check blocks
            token_key=session.token_key,  # any cloud provider this pipeline's step resolves to
        )
    except Exception as exc:
        current_app.logger.error('chatbot.send_message_generic (stage 1) run start failed: %s', exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'run_id': run_id, 'session_id': session.id})


# ── Generic chat: stage 2 — the actual answer, once stage 1's SSE completes ─

@bp.post('/generic/message/continue')
@login_required
@ai_required
def send_message_generic_continue():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')

    session = (ChatSession.query
               .filter_by(id=session_id, user_id=current_user.id, patient_id=None).first()
               if session_id else None)
    if not session:
        abort(404)
    # The erased text is read from stage 1's own run, never taken from the
    # browser (ADR-053): what goes to the cloud is what the erasure step
    # produced, whatever the page sends.
    erased_text, problem = _stage1_output(data.get('stage1_run_id'))
    if problem:
        return jsonify({'error': problem}), 400
    return _start_generic_answer(session, erased_text, data)


# ── Generic chat without an AI erasure step (ADR-098) ────────────────────────
# For practices with no local model to run the PII Erasure workflow. The typed
# text goes straight to stage 2, which still applies the rule-based redaction
# for runs with no patient (ADR-053) and the pre-send check and review
# (ADR-090). The page warns once per chat and keeps a banner up; the server
# decides the mode, and requires the acknowledgment on every send.

@bp.post('/generic/message/direct')
@login_required
@ai_required
def send_message_generic_direct():
    mode = _generic_mode()
    if mode == 'erasure':
        return jsonify({'error': 'The PII Erasure workflow is active — reload the page.'}), 400
    if mode == 'off':
        return jsonify({'error': 'This practice requires the PII Erasure workflow for the general '
                                 'chatbot, and it is not active. Ask an administrator.'}), 403

    data = request.get_json(silent=True) or {}
    if data.get('acknowledged') is not True:
        return jsonify({'error': 'Please confirm the privacy warning before sending.',
                        'ack_required': True}), 400
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    session = _get_active_session(None)
    if not session:
        return jsonify({'error': 'No active generic Chatbot pipeline configured — set one up in Pipeline Designer.'}), 400
    return _start_generic_answer(session, message, data)


def _start_generic_answer(session: ChatSession, user_text: str, data: dict):
    """Store the user's turn and start the answer run (stage 2) on it.

    With erasure, user_text is stage 1's output: the raw input never reaches the
    database, and every stored user turn (folded into history below) is erased
    text. Without it (ADR-098), user_text is what was typed; stage 2's rule-based
    redaction covers both it and the history, as it would the erased text.
    """
    model_override = data.get('model_id_override')
    history_text = _history_text(session)

    db.session.add(ChatMessage(session_id=session.id, role='user', content=user_text))
    session.last_activity_at = datetime.now(timezone.utc)
    db.session.commit()

    input_data = {
        'user_prompt': user_text,
        'conversation_history_text': history_text,
    }
    if model_override:
        try:
            input_data['model_id_override'] = int(model_override)
        except (TypeError, ValueError):
            pass

    from app.services.pipeline.engine import PipelineEngine
    try:
        run_id = PipelineEngine.run(
            pipeline_id=session.pipeline_id,
            patient_id=None,
            user_id=current_user.id,
            input_data=input_data,
            model_is_local=False,
            token_key=session.token_key,
            # Stage 2 only: stage 1 (PII erasure) is local and never pauses.
            review=review_meta_for(current_user, bool(data.get('review_capable')),
                                   remember_removed=True),
        )
    except Exception as exc:
        current_app.logger.error('chatbot.send_message_generic (stage 2) run start failed: %s', exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'run_id': run_id, 'session_id': session.id})


_STAGE1_MAX_AGE = timedelta(minutes=10)


def _stage1_output(run_uuid) -> tuple[str, str | None]:
    """(erased text, None) from this user's finished PII-erasure run, or ('', why not)."""
    pii_pipeline = _find_pii_erasure_pipeline()
    run = (PipelineRun.query.filter_by(run_uuid=str(run_uuid)).first()
           if run_uuid and pii_pipeline else None)
    if (not run or run.pipeline_id != pii_pipeline.id
            or run.initiated_by_id != current_user.id or run.status != RunStatus.completed):
        return '', 'PII erasure result not found — please send the message again.'
    finished = run.finished_at.replace(tzinfo=timezone.utc) if run.finished_at else None
    if not finished or datetime.now(timezone.utc) - finished > _STAGE1_MAX_AGE:
        return '', 'PII erasure result has expired — please send the message again.'
    try:
        text = (json.loads(run.output_json or '{}').get('final_output') or '').strip()
    except ValueError:
        text = ''
    if not text:
        return '', 'PII erasure step returned no text.'
    return text, None


# ── Generic chat: best-effort model warm-up ──────────────────────────────────
# Ollama unloads a model from VRAM after ~5 minutes idle, and the PII-erasure
# model's cold-load is the slowest part of the two-stage exchange. Pinged by
# the client the moment the generic chat page opens, so it's hopefully
# already resident by the time a doctor finishes typing their first message.
# Purely an optimisation — every failure mode here is swallowed, never
# surfaced to the user, and never blocks the real chat flow.

def _warmup_ollama_model(app, base_url: str, api_key: str | None, model_id: str, keep_alive: str):
    with app.app_context():
        try:
            import requests
            # base_url is the OpenAI-compat root (".../v1") — Ollama's own
            # native API (which supports loading a model with no "prompt",
            # i.e. without generating anything) lives one level up from there.
            native_root = base_url.rstrip('/')
            if native_root.endswith('/v1'):
                native_root = native_root[:-3]
            requests.post(
                f'{native_root}/api/generate',
                json={'model': model_id, 'keep_alive': keep_alive},
                timeout=60,
            )
        except Exception as exc:
            current_app.logger.warning('chatbot generic warmup ping failed (non-fatal): %s', exc)


@bp.post('/generic/warmup')
@login_required
@ai_required
def warmup_generic():
    pii_pipeline = _find_pii_erasure_pipeline()
    if not pii_pipeline:
        return jsonify({'ok': False})

    model = _resolve_default_model(pii_pipeline)
    if not model or not model.provider or not model.provider.is_local \
            or model.provider.provider_type != 'openai_compatible':
        return jsonify({'ok': False})

    import threading
    app = current_app._get_current_object()
    threading.Thread(
        target=_warmup_ollama_model,
        args=(app, model.provider.base_url, model.provider.api_key, model.model_id, '30m'),
        daemon=True,
        name='chatbot-generic-warmup',
    ).start()

    return jsonify({'ok': True})


# ── Persist assistant reply once SSE completes ──────────────────────────────

@bp.post('/session/<int:session_id>/complete')
@login_required
def complete(session_id: int):
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        abort(404)

    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    run_db_id = data.get('run_db_id')
    # Extracted client-side from the model's {"Title": ..., "Response": ...}
    # envelope (chatbot_generic only) — absent/blank on turns where the model
    # judged the topic unchanged, or where its reply didn't parse as JSON at
    # all (older/less-reliable models); either way just leave the title as-is.
    title = (data.get('title') or '').strip()

    if not content:
        return jsonify({'error': 'content is required'}), 400

    run = None
    if run_db_id:
        run = db.session.get(PipelineRun, int(run_db_id))
        if run and (run.pipeline_id != session.pipeline_id or run.initiated_by_id != current_user.id):
            run = None  # not this session's run — don't link a mismatched one

    # Text removed at the pre-send review comes out of the stored copy of the
    # user's message too, so the next turn's history doesn't carry it (ADR-091).
    if run and run.run_uuid:
        from app.services.pipeline import review
        removed = review.pop_removed(run.run_uuid)
        last_user = (ChatMessage.query.filter_by(session_id=session.id, role='user')
                     .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).first())
        if removed and last_user:
            last_user.content = review.redact_segments(last_user.content, removed)

    msg = ChatMessage(
        session_id=session.id,
        role='assistant',
        content=content,
        pipeline_run_id=run.id if run else None,
    )
    db.session.add(msg)
    if title:
        session.title = title[:200]  # column is String(200)
    session.last_activity_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'message_id': msg.id})


# ── New conversation ─────────────────────────────────────────────────────────

@bp.get('/session/<int:session_id>/new')
@login_required
def new_session(session_id: int):
    old = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not old:
        abort(404)
    old.is_archived = True
    db.session.commit()

    from flask import redirect, url_for
    if old.patient_id:
        return redirect(url_for('chatbot.index', patient_id=old.patient_id))
    return redirect(url_for('chatbot.generic_index'))


# ── Previous chats (generic + patient-scoped) ────────────────────────────────

def _session_list_response(patient_id: int | None, q: str):
    """Shared by generic_sessions() and patient_sessions() — identical query
    shape, differing only in which patient_id scopes the list (None = generic).
    A patient-scoped list is deliberately scoped to *that* patient only, not
    every patient-chat this user has ever had — reviewing prior AI
    conversations about the patient currently open is the actual use case."""
    current = _get_active_session(patient_id, create=False)

    query = (ChatSession.query
             .filter_by(user_id=current_user.id, patient_id=patient_id, is_deleted=False)
             .filter(ChatSession.messages.any()))  # hide never-used sessions
    if q:
        like = f'%{q}%'
        query = (query
                 .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
                 .filter(or_(ChatSession.title.ilike(like), ChatMessage.content.ilike(like)))
                 .distinct())
    sessions = query.order_by(ChatSession.last_activity_at.desc()).limit(50).all()

    return render_template(
        'clinical/partials/chatbot_session_list.html',
        sessions=sessions,
        current_session_id=current.id if current else None,
        q=q,
    )


@bp.get('/generic/sessions')
@login_required
def generic_sessions():
    """Sidebar list of the current user's generic chats, newest-active first,
    optionally filtered by a search term across title + message content."""
    return _session_list_response(None, (request.args.get('q') or '').strip())


@bp.get('/<int:patient_id>/sessions')
@login_required
def patient_sessions(patient_id: int):
    """Sidebar list of the current user's chats for this specific patient."""
    _get_patient(patient_id)  # 404 if not a valid patient
    return _session_list_response(patient_id, (request.args.get('q') or '').strip())


@bp.get('/session/<int:session_id>/resume')
@login_required
def resume_session(session_id: int):
    """Make a previous (archived) chat — generic or patient-scoped — the
    active one again, archiving whichever session is currently active for
    that same scope. Mirrors new_session()'s one-active-session-at-a-time
    invariant, just in the other direction."""
    from flask import redirect, url_for

    target = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not target:
        abort(404)

    if target.is_archived:
        current = _get_active_session(target.patient_id, create=False)
        if current and current.id != target.id:
            current.is_archived = True
        target.is_archived = False
        db.session.commit()

    if target.patient_id:
        return redirect(url_for('chatbot.index', patient_id=target.patient_id))
    return redirect(url_for('chatbot.generic_index'))


@bp.post('/session/<int:session_id>/delete')
@login_required
def delete_session(session_id: int):
    """Soft-delete a chat from the sidebar (sets is_deleted — see ChatSession
    for why this isn't a hard delete). If the deleted chat was the currently
    active one, promotes the next most recent surviving chat in that same
    scope to active (falling through to the usual "start a new blank chat"
    behavior if none remain) and tells the browser to navigate there via
    HX-Redirect, since the whole main transcript panel needs to change, not
    just this sidebar list. Otherwise just re-renders the list in place."""
    target = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not target:
        abort(404)

    patient_id = target.patient_id
    was_active = not target.is_archived and not target.is_deleted
    target.is_deleted = True
    target.is_archived = True  # belt-and-suspenders: consistent on both flags,
                                # even though every query already filters is_deleted

    if was_active:
        next_session = (ChatSession.query
                         .filter_by(user_id=current_user.id, patient_id=patient_id, is_deleted=False)
                         .filter(ChatSession.id != target.id)
                         .order_by(ChatSession.last_activity_at.desc())
                         .first())
        if next_session:
            next_session.is_archived = False
        db.session.commit()

        from flask import url_for
        redirect_url = (url_for('chatbot.index', patient_id=patient_id) if patient_id
                         else url_for('chatbot.generic_index'))
        resp = jsonify({'redirect': redirect_url})
        resp.headers['HX-Redirect'] = redirect_url
        return resp

    db.session.commit()
    q = (request.form.get('q') or request.args.get('q') or '').strip()
    return _session_list_response(patient_id, q)


# ── Debug detail (admin-only, lazy) ──────────────────────────────────────────

@bp.post('/session/<int:session_id>/withdraw')
@login_required
def withdraw_last_message(session_id: int):
    """Remove the user's last message when its request was cancelled at review
    (ADR-091): nothing was sent, so it shouldn't stay in the history."""
    session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        abort(404)
    last = (ChatMessage.query.filter_by(session_id=session.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).first())
    if last and last.role == 'user':
        db.session.delete(last)
        db.session.commit()
        return jsonify({'ok': True, 'removed': True})
    return jsonify({'ok': True, 'removed': False})


@bp.get('/message/<int:message_id>/sent')
@login_required
@ai_required
def message_sent(message_id: int):
    """What was sent to the cloud AI for this reply — the redacted prompt and the
    system prompt sent with it, for the reply's Sent tab (ADR-091, ADR-096).
    Pre-redaction text stays in Debug."""
    msg = db.session.get(ChatMessage, message_id)
    if not msg or msg.session.user_id != current_user.id:
        abort(404)
    run = msg.pipeline_run
    if not run or run.model_is_local:
        return jsonify({'error': 'Nothing was sent to a cloud AI for this reply.'})
    from app.services.pipeline.engine import extract_debug_info
    import json as _json
    debug = extract_debug_info(run)
    try:
        review_rec = _json.loads(run.output_json or '{}').get('review')
    except ValueError:
        review_rec = None
    return jsonify({'prompt': debug.get('current_prompt') or '', 'review': review_rec,
                    'system_prompt': debug.get('system_prompt') or ''})


@bp.get('/message/<int:message_id>/debug')
@login_required
def message_debug(message_id: int):
    if not current_user.is_admin:
        abort(403)

    msg = ChatMessage.query.get_or_404(message_id)
    if msg.session.user_id != current_user.id:
        abort(404)
    if not msg.pipeline_run:
        return jsonify({'error': 'No pipeline run linked to this message'}), 404

    from app.services.pipeline.engine import extract_debug_info
    debug = extract_debug_info(msg.pipeline_run)
    debug['is_redacted'] = msg.pipeline_run.is_redacted
    debug['is_hcp_redacted'] = msg.pipeline_run.is_hcp_redacted
    debug['model_is_local'] = msg.pipeline_run.model_is_local
    return jsonify(debug)


# ── File download ────────────────────────────────────────────────────────────

@bp.post('/message/<int:message_id>/download')
@login_required
def create_download(message_id: int):
    msg = ChatMessage.query.get_or_404(message_id)
    if msg.role != 'assistant' or msg.session.user_id != current_user.id:
        abort(404)

    data = request.get_json(silent=True) or {}
    fmt = data.get('format', 'txt')
    if fmt not in ('txt', 'md'):
        fmt = 'txt'

    # Prefer client-supplied content (e.g. the chatbot's Edit tab) over the
    # archived message text, so a presentation-only edit is reflected in the
    # download too — falls back to the stored message when none is sent.
    content = (data.get('content') or '').strip() or msg.content

    filename = f'chat_{message_id}.{fmt}'
    mimetype = 'text/markdown' if fmt == 'md' else 'text/plain'

    file_row = ChatGeneratedFile(
        session_id=msg.session_id,
        message_id=msg.id,
        filename=filename,
        mimetype=mimetype,
        content=content,
        created_by_id=current_user.id,
    )
    db.session.add(file_row)
    db.session.commit()

    return jsonify({'file_id': file_row.id})


@bp.get('/file/<int:file_id>/download')
@login_required
def download_file(file_id: int):
    file_row = ChatGeneratedFile.query.get_or_404(file_id)
    if file_row.session.user_id != current_user.id:
        abort(404)

    return send_file(
        io.BytesIO(file_row.content.encode('utf-8')),
        mimetype=file_row.mimetype,
        as_attachment=True,
        download_name=file_row.filename,
    )


@bp.post('/render-markdown')
@login_required
def render_markdown():
    """Markdown/plain-text -> sanitized HTML (tables, fenced code, bleach-cleaned).
    Used by the chat Print button and the Rendered tab (for non-HTML-document replies)."""
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    from app.services.email_body_renderer import render
    result = render(text)
    return jsonify({'html': result.html})


# ── Saved prompts ─────────────────────────────────────────────────────────────

def _saved_prompt_json(p: ChatSavedPrompt) -> dict:
    return {
        'id': p.id,
        'description': p.description,
        'prompt_text': p.prompt_text,
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


@bp.get('/prompts')
@login_required
def list_saved_prompts():
    prompts = (ChatSavedPrompt.query
               .filter_by(user_id=current_user.id)
               .order_by(ChatSavedPrompt.created_at.desc())
               .all())
    return jsonify({'prompts': [_saved_prompt_json(p) for p in prompts]})


@bp.post('/prompts')
@login_required
def create_saved_prompt():
    data = request.get_json(silent=True) or {}
    description = (data.get('description') or '').strip()
    prompt_text = (data.get('prompt_text') or '').strip()
    if not description or not prompt_text:
        return jsonify({'error': 'description and prompt_text are required'}), 400

    prompt = ChatSavedPrompt(
        user_id=current_user.id,
        description=description,
        prompt_text=prompt_text,
    )
    db.session.add(prompt)
    db.session.commit()
    return jsonify(_saved_prompt_json(prompt))


@bp.delete('/prompts/<int:prompt_id>')
@login_required
def delete_saved_prompt(prompt_id: int):
    prompt = ChatSavedPrompt.query.get_or_404(prompt_id)
    if prompt.user_id != current_user.id:
        abort(404)
    db.session.delete(prompt)
    db.session.commit()
    return jsonify({'ok': True})
