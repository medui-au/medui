"""Voice Blueprint — Voice Scribe routes.

Stage 1 (per chunk): POST /patient/<id>/chunk → VoiceService (ASR stub) → cache
Stage 2 (recompose): POST /patient/<id>/recompose → PipelineEngine → SSE stream

The chunk route is CSRF-exempt because the browser sends binary multipart/form-data.
"""
import json
from datetime import datetime, timezone

from flask import abort, jsonify, render_template, request, url_for, current_app
from flask_login import current_user, login_required

from app.extensions import db, csrf
from app.models.ai_provider import AIModel
from app.models.consultation_transcript import ConsultationTranscript
from app.models.pipeline import Pipeline, PipelineStatus
from app.services import user_settings_service as user_settings
from app.services.pipeline.review import meta_for as review_meta_for
from app.services.scribe_cache import scribe_cache
from app.services.voice_service import VoiceService, speaker_label_status
from . import bp
from app.utils.access import ai_required


# Per-user scribe preferences live in user_preferences (ADR-085).
_ASR_PREF      = 'scribe.asr_model'
_PIPELINE_PREF = 'scribe.pipeline'
_CHUNK_PREF    = 'scribe.chunk_interval_ms'


CHUNK_INTERVALS_MS = (15000, 30000, 45000, 60000)
DEFAULT_CHUNK_INTERVAL_MS = 45000


def _saved_chunk_interval_ms(user) -> int:
    """User's preferred chunk interval, shared by Scribe and Quick Scribe."""
    saved = user_settings.get(user, _CHUNK_PREF)
    return saved if saved in CHUNK_INTERVALS_MS else DEFAULT_CHUNK_INTERVAL_MS


def _get_patient(patient_id: int) -> dict:
    from app.services.clinical_service import ClinicalService
    patient = ClinicalService.get_patient_demographics(patient_id)
    if not patient:
        abort(404)
    return patient


# ── Scribe page ───────────────────────────────────────────────────────────────

@bp.get('/scribe')
@login_required
@ai_required
def scribe():
    """Voice scribe page. Accepts ?patient_id=<int>."""
    patient_id = request.args.get('patient_id', type=int)
    if not patient_id:
        abort(400)
    patient    = _get_patient(patient_id)
    pipelines  = (Pipeline.query
                  .filter_by(status=PipelineStatus.active)
                  .filter(Pipeline.name.ilike('%[SCRIBE]%'))
                  .all())
    has_cached = scribe_cache.has_content(current_user.id, patient_id)
    asr_models = (AIModel.query
                  .filter_by(is_asr=True, is_enabled=True)
                  .join(AIModel.provider)
                  .all())
    saved_asr_id = user_settings.get(current_user, _ASR_PREF)
    saved_pipeline_id = user_settings.get(current_user, _PIPELINE_PREF)
    pipeline_ids = {p.id for p in pipelines}
    selected_pipeline_id = saved_pipeline_id if saved_pipeline_id in pipeline_ids else None
    return render_template(
        'voice/scribe.html',
        speaker_status={m.id: speaker_label_status(m) for m in asr_models},
        patient=patient,
        patient_id=patient_id,
        pipelines=pipelines,
        has_cached_transcript=has_cached,
        asr_models=asr_models,
        selected_asr_model_id=saved_asr_id,
        selected_pipeline_id=selected_pipeline_id,
        chunk_intervals_ms=CHUNK_INTERVALS_MS,
        selected_chunk_interval_ms=_saved_chunk_interval_ms(current_user),
    )


@bp.post('/pref/asr-model')
@login_required
def scribe_set_asr_model():
    """Persist the user's preferred ASR model. JSON body: {model_id: int|null}"""
    data     = request.get_json(silent=True) or {}
    model_id = data.get('model_id')
    if model_id is not None:
        model_id = int(model_id)
        if not AIModel.query.filter_by(id=model_id, is_asr=True).first():
            return jsonify({'error': 'Invalid model_id'}), 400
    user_settings.set(current_user, _ASR_PREF, model_id)
    db.session.commit()
    return jsonify({'ok': True, 'model_id': model_id})


@bp.post('/pref/pipeline')
@login_required
def scribe_set_pipeline():
    """Persist the user's preferred scribe pipeline. JSON body: {pipeline_id: int|null}"""
    data        = request.get_json(silent=True) or {}
    pipeline_id = data.get('pipeline_id')
    if pipeline_id is not None:
        pipeline_id = int(pipeline_id)
        if not Pipeline.query.filter_by(id=pipeline_id, status=PipelineStatus.active).first():
            return jsonify({'error': 'Invalid pipeline_id'}), 400
    user_settings.set(current_user, _PIPELINE_PREF, pipeline_id)
    db.session.commit()
    return jsonify({'ok': True, 'pipeline_id': pipeline_id})


@bp.post('/pref/chunk-interval')
@login_required
def scribe_set_chunk_interval():
    """Persist the user's preferred chunk interval. JSON body: {interval_ms: int}"""
    data = request.get_json(silent=True) or {}
    try:
        interval_ms = int(data.get('interval_ms'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid interval_ms'}), 400
    if interval_ms not in CHUNK_INTERVALS_MS:
        return jsonify({'error': 'Invalid interval_ms'}), 400
    user_settings.set(current_user, _CHUNK_PREF, interval_ms)
    db.session.commit()
    return jsonify({'ok': True, 'interval_ms': interval_ms})


# ── Inline dictation (single-shot, no patient context) ───────────────────────

@bp.post('/dictate')
@login_required
@csrf.exempt
def dictate():
    """Single-shot dictation endpoint for inline mic buttons.

    Uses the user's persisted ASR model preference (scribe.asr_model.<user_id>).
    Returns {transcription} with no DB or cache writes.
    """
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file in request.'}), 400

    audio_bytes = request.files['audio'].read()
    if not audio_bytes:
        return jsonify({'error': 'Empty audio payload.'}), 400

    # Honour an explicit model_id from the client, then fall back to user preference
    model_id = request.form.get('model_id', type=int) or None
    if not model_id:
        saved = user_settings.get(current_user, _ASR_PREF)
        if saved:
            try:
                model_id = int(saved)
            except (TypeError, ValueError):
                pass

    try:
        import uuid
        transcription = VoiceService.process_chunk(
            audio_bytes, 0, model_id=model_id, diarize=False,
            usage_hook=_usage_hook(f'dictate-{uuid.uuid4().hex[:12]}', 'dictation', False))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 503
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify({'transcription': transcription or ''})


# ── Quick Scribe (no patient context) ────────────────────────────────────────

@bp.get('/quick-scribe')
@login_required
@ai_required
def quick_scribe():
    """Patient-free scribe page for phone calls and unscheduled consultations."""
    asr_models   = (AIModel.query
                    .filter_by(is_asr=True, is_enabled=True)
                    .join(AIModel.provider)
                    .all())
    saved_asr_id = user_settings.get(current_user, _ASR_PREF)
    return render_template(
        'voice/quick_scribe.html',
        speaker_status={m.id: speaker_label_status(m) for m in asr_models},
        asr_models=asr_models,
        selected_asr_model_id=saved_asr_id,
        chunk_intervals_ms=CHUNK_INTERVALS_MS,
        selected_chunk_interval_ms=_saved_chunk_interval_ms(current_user),
    )


@bp.post('/quick/chunk')
@login_required
@ai_required
@csrf.exempt
def quick_scribe_chunk():
    """CSRF-exempt chunk endpoint for Quick Scribe — no patient context, no DB or cache writes."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file in request.'}), 400

    audio_bytes = request.files['audio'].read()
    if not audio_bytes:
        return jsonify({'error': 'Empty audio payload.'}), 400

    chunk_index = int(request.form.get('chunk_index', 0))
    session_id  = request.form.get('session_id', '')
    model_id    = request.form.get('model_id', type=int) or None

    try:
        # Resolved here as well so the reply can say which model transcribed
        # this chunk; the page records it with the saved transcript.
        asr_model = VoiceService.resolve_asr_model(model_id)
        transcription = VoiceService.process_chunk(
            audio_bytes, 0, model_id=asr_model.id,
            usage_hook=_usage_hook(session_id, 'scribe.quick', False))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 503
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify({
        'status':        'success',
        'transcription': transcription,
        'session_id':    session_id,
        'chunk_index':   chunk_index,
        'asr_model':     asr_model.model_id,
        'asr_is_local':  bool(asr_model.provider and asr_model.provider.is_local),
    })


# ── Chunk upload ──────────────────────────────────────────────────────────────

@bp.post('/patient/<int:patient_id>/chunk')
@login_required
@ai_required
@csrf.exempt
def scribe_chunk(patient_id: int):
    """Receive a WAV chunk, transcribe (stub), update cache. CSRF-exempt."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file in request.'}), 400

    audio_bytes = request.files['audio'].read()
    if not audio_bytes:
        return jsonify({'error': 'Empty audio payload.'}), 400

    session_id  = request.form.get('session_id', '')
    chunk_index = int(request.form.get('chunk_index', 0))
    model_id    = request.form.get('model_id', type=int) or None

    try:
        # Resolved here as well so the reply can say which model transcribed
        # this chunk; the page records it with the saved transcript.
        asr_model = VoiceService.resolve_asr_model(model_id)
        transcription = VoiceService.process_chunk(
            audio_bytes, patient_id, model_id=asr_model.id,
            usage_hook=_usage_hook(session_id, 'scribe.session', True))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 503
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500

    if transcription:
        scribe_cache.append(current_user.id, patient_id, transcription)

    return jsonify({
        'status':        'success',
        'transcription': transcription,
        'session_id':    session_id,
        'chunk_index':   chunk_index,
        'asr_model':     asr_model.model_id,
        'asr_is_local':  bool(asr_model.provider and asr_model.provider.is_local),
    })


# ── Recompose ─────────────────────────────────────────────────────────────────

@bp.post('/patient/<int:patient_id>/recompose')
@login_required
@ai_required
def scribe_recompose(patient_id: int):
    """Start a pipeline run and return run_id + SSE stream URL.

    JSON body: {pipeline_id, transcript, verbosity}
    """
    from app.services.pipeline.engine import PipelineEngine

    data        = request.get_json(silent=True) or {}
    pipeline_id = data.get('pipeline_id')
    transcript  = (data.get('transcript') or '').strip()
    verbosity   = data.get('verbosity', 'Normal')

    if not pipeline_id:
        return jsonify({'error': 'pipeline_id is required.'}), 400
    if not transcript:
        return jsonify({'error': 'transcript is required.'}), 400

    try:
        run_id = PipelineEngine.run(
            pipeline_id=int(pipeline_id),
            patient_id=patient_id,
            user_id=current_user.id,
            input_data={'raw_transcript': transcript, 'verbosity': verbosity},
            model_is_local=False,
            # The scribe page can show the pre-send review (ADR-094).
            review=review_meta_for(current_user, bool(data.get('review_capable'))),
            # The doctor recording: their own first name, any case (ADR-133).
            transcript_by=current_user.id,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error('scribe_recompose pipeline error: %s', exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({
        'run_id':     run_id,
        'stream_url': url_for('pipeline_run.run_stream', run_id=run_id),
    })


# ── Cache endpoints ───────────────────────────────────────────────────────────

@bp.post('/patient/<int:patient_id>/sync')
@login_required
def scribe_sync(patient_id: int):
    data    = request.get_json(silent=True) or {}
    content = data.get('content', '')
    scribe_cache.set(current_user.id, patient_id, content)
    return jsonify({'status': 'success', 'char_count': len(content)})


@bp.get('/patient/<int:patient_id>/content')
@login_required
def scribe_content(patient_id: int):
    content = scribe_cache.get(current_user.id, patient_id)
    stats   = scribe_cache.get_stats(current_user.id, patient_id)
    return jsonify({'content': content, 'has_content': bool(content), 'stats': stats})


@bp.post('/patient/<int:patient_id>/clear')
@login_required
def scribe_clear(patient_id: int):
    scribe_cache.clear(current_user.id, patient_id)
    return jsonify({'status': 'success'})


# ── Persistence ───────────────────────────────────────────────────────────────

def _usage_hook(session_id: str, task: str, patient_linked: bool):
    """A per-chunk hook that adds each model call to the session's usage record."""
    from functools import partial
    from app.services import usage_service
    return partial(usage_service.record_scribe_call, user_id=current_user.id,
                   session_id=session_id, task=task, patient_linked=patient_linked,
                   workstation=request.remote_addr)


def _record_usage(session_id: str, extra: dict, char_count: int, is_final: bool,
                  now: datetime) -> None:
    """Upsert the session's durable usage row (ScribeUsage) — no text, no patient."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.scribe_usage import ScribeUsage

    tally = extra.get('asr_models') or {}
    local = extra.get('asr_local') or {}
    models = ({name: {'chunks': int(n), 'local': bool(local.get(name))}
               for name, n in tally.items()} if isinstance(tally, dict) else {})
    values = {'chunks': int(extra.get('chunks') or 0), 'char_count': char_count,
              'is_final': is_final, 'last_saved_at': now}
    if models:
        values['asr_models_json'] = json.dumps(models)
    if extra.get('asr_model_first'):
        values['asr_model_first'] = str(extra['asr_model_first'])[:120]
    db.session.execute(
        pg_insert(ScribeUsage)
        .values(user_id=current_user.id, session_id=session_id, started_at=now, **values)
        .on_conflict_do_update(constraint='uq_scribe_usage_session', set_=values))


@bp.post('/patient/<int:patient_id>/save')
@login_required
def scribe_save(patient_id: int):
    """Upsert transcript record (30-day TTL).

    JSON body: {transcript, session_id, is_final, extra_data}
    """
    data            = request.get_json(silent=True) or {}
    transcript_text = (data.get('transcript') or '').strip()
    session_id      = data.get('session_id', '')
    is_final        = bool(data.get('is_final', False))
    extra_data      = data.get('extra_data', {})

    if not transcript_text:
        return jsonify({'error': 'transcript is required.'}), 400
    if not session_id:
        return jsonify({'error': 'session_id is required.'}), 400

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(timezone.utc)
    # Which speech-to-text model(s) transcribed the session. A save that
    # arrives without them — the page reloaded mid-session — keeps the tally
    # already stored instead of wiping it.
    if isinstance(extra_data, dict) and 'asr_models' not in extra_data:
        existing = (ConsultationTranscript.query
                    .filter_by(session_id=session_id, patient_id=patient_id,
                               user_id=current_user.id).first())
        if existing and existing.extra_data_json:
            try:
                previous = json.loads(existing.extra_data_json)
            except ValueError:
                previous = {}
            for key in ('asr_model_first', 'asr_models', 'asr_local'):
                if key in previous:
                    extra_data[key] = previous[key]
    extra_json = json.dumps(extra_data) if extra_data else None

    stmt = (
        pg_insert(ConsultationTranscript)
        .values(
            patient_id=patient_id,
            user_id=current_user.id,
            session_id=session_id,
            transcript_text=transcript_text,
            is_final=is_final,
            extra_data_json=extra_json,
            expires_at=ConsultationTranscript.expiry_date(),
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint='uq_transcript_session',
            set_={
                'transcript_text':  transcript_text,
                'is_final':         is_final,
                'updated_at':       now,
                'extra_data_json':  extra_json,
            },
        )
        .returning(ConsultationTranscript.id, ConsultationTranscript.expires_at)
    )
    result = db.session.execute(stmt)
    _record_usage(session_id, extra_data if isinstance(extra_data, dict) else {},
                  len(transcript_text), is_final, now)
    db.session.commit()
    from app.services import usage_service
    usage_service.record_scribe_saved(user_id=current_user.id, session_id=session_id,
                                      char_count=len(transcript_text), is_final=is_final)
    row = result.fetchone()
    return jsonify({
        'status':        'success',
        'transcript_id': row[0],
        'expires_at':    row[1].isoformat() if row[1] else None,
    })


# ── PIT export ────────────────────────────────────────────────────────────────

@bp.post('/patient/<int:patient_id>/export-pit')
@login_required
def scribe_export_pit(patient_id: int):
    """Export recomposed clinical note as a PIT file to the BP shared folder.

    JSON body: {content, label (optional), run_id (optional: the recompose run, for the provenance footer)}
    """
    from app.utils.pit_utils import send_as_pit

    data    = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'No content to export.'}), 400

    fn       = (getattr(current_user, 'bpsdb_firstname', '') or '').strip()
    sn       = (getattr(current_user, 'bpsdb_surname',   '') or '').strip()
    initials = (fn[:1] + sn[:1]).upper() or current_user.display_name[:2].upper()
    date_str = datetime.now().strftime('%d-%m-%Y')
    label    = (data.get('label') or '').strip() or f'[CONSULT NOTE] {initials} {date_str}'

    patient = _get_patient(patient_id)

    # Provenance footer, when the practice has it on (Setup → Messaging).
    from app.services.ai_provenance_service import footer_for_run
    content += footer_for_run(data.get('run_id'), current_user)

    try:
        ok = send_as_pit(patient=patient, pit_label=label, body=content, user=current_user)
    except Exception as exc:
        current_app.logger.error('Scribe PIT export failed patient=%s: %s', patient_id, exc)
        return jsonify({'error': str(exc)}), 500

    if ok:
        current_app.logger.info('Scribe PIT export OK: patient=%s user=%s', patient_id, current_user.id)
        return jsonify({'ok': True})

    return jsonify({'error': 'PIT export failed — check pit_export_path in Setup → Messaging.'}), 500
