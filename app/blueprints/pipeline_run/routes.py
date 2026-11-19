import json
from flask import Response, render_template, request, jsonify, stream_with_context
from flask_login import login_required, current_user
from . import bp
from app.utils.access import ai_required


def _require_clinical(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import abort
            abort(401)
        return f(*args, **kwargs)
    return decorated


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_level(7):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Run endpoints ─────────────────────────────────────────────────────────────

@bp.post('/run/start')
@login_required
@ai_required
@_require_clinical
def run_start():
    """Start a pipeline run. Returns {run_id}."""
    from app.services.pipeline.engine import PipelineEngine

    data = request.get_json(silent=True) or {}
    pipeline_id = data.get('pipeline_id')
    patient_id = data.get('patient_id')
    input_data = data.get('input', {})
    model_is_local = bool(data.get('model_is_local', False))

    if not pipeline_id:
        return jsonify({'error': 'pipeline_id is required'}), 400

    # The privacy gate in app/__init__.py sees only patient ids in the URL;
    # this one arrives in the body, so check it here (staff records).
    if patient_id:
        from werkzeug.exceptions import Forbidden
        from app.services.privacy_service import check_patient_access
        try:
            check_patient_access(int(patient_id))
        except Forbidden:
            return jsonify({'error': 'This record is private.'}), 403

    # Pre-send review (ADR-090): only a page that can show it asks; whether
    # every request pauses is the user's setting, read here, not sent by the page.
    from app.services.pipeline import review as _review
    review = _review.meta_for(current_user, bool(data.get('review_capable')))

    try:
        run_id = PipelineEngine.run(
            pipeline_id=int(pipeline_id),
            patient_id=int(patient_id) if patient_id else None,
            user_id=current_user.id,
            input_data=input_data,
            model_is_local=model_is_local,
            review=review,
        )
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify({'run_id': run_id})


@bp.post('/run/<run_id>/review/check')
@login_required
@ai_required
def run_review_check(run_id: str):
    """Re-check the prompt being reviewed (debounced as the user edits). ADR-090."""
    from app.services.pipeline import review
    entry = review.pending(run_id, current_user.id)
    if not entry:
        return jsonify({'error': 'This review is no longer open.'}), 404
    text = (request.get_json(silent=True) or {}).get('prompt') or ''
    verdict = review.check(text, entry['patient_id'])
    return jsonify({'hits': verdict.get('hits') or [], 'top_tier': verdict.get('top_tier'),
                    'blocking': review.is_blocking(verdict)})


@bp.post('/run/<run_id>/review')
@login_required
@ai_required
def run_review_answer(run_id: str):
    """Send (the reviewed prompt) or cancel. The run checks it again itself. ADR-090."""
    from app.services.pipeline import review
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('send', 'cancel'):
        return jsonify({'error': 'action must be send or cancel'}), 400
    if not review.submit(run_id, current_user.id,
                         {'action': action, 'prompt': data.get('prompt') or ''}):
        return jsonify({'error': 'This review is no longer open.'}), 404
    return jsonify({'ok': True})


@bp.post('/runs/<int:run_db_id>/privacy-report')
@login_required
@ai_required
def run_privacy_report(run_db_id: int):
    """Report text in the prompt as sent that should have been redacted (ADR-115)."""
    from app.services import privacy_reports_service
    data = request.get_json(silent=True) or {}
    result = privacy_reports_service.create(run_db_id, current_user, data.get('start'), data.get('end'),
                                            data.get('note') or '')
    return jsonify(result), (200 if result.get('ok') else 400)


@bp.get('/run/<run_id>/stream')
@login_required
def run_stream(run_id: str):
    """SSE stream for a running pipeline. Client receives JSON event lines."""
    from app.services.pipeline.engine import PipelineEngine

    q = PipelineEngine.get_queue(run_id)
    if q is None:
        return Response(
            _sse_event({'type': 'error', 'message': 'Run not found or already finished'}),
            mimetype='text/event-stream',
        )

    def generate():
        import queue as _queue
        import time as _time
        deadline = _time.monotonic() + 600  # 10-minute hard limit
        try:
            while True:
                try:
                    event = q.get(timeout=15)
                except _queue.Empty:
                    if _time.monotonic() > deadline:
                        yield _sse_event({'type': 'error', 'message': 'Pipeline timed out after 10 minutes'})
                        break
                    yield ': keepalive\n\n'  # SSE comment — keeps connection alive, browser ignores
                    continue
                if event is None:  # sentinel
                    yield _sse_event({'type': 'done'})
                    break
                yield _sse_event(event)
        finally:
            PipelineEngine.cleanup(run_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@bp.get('/run/<run_id>/status')
@login_required
def run_status(run_id: str):
    """Return run status + full context for the debug tab.
    Looks up PipelineRun by run_uuid. step_snapshots (pre-redaction data) for administrators only."""
    from app.services.pipeline.engine import PipelineEngine
    from app.models.pipeline import PipelineRun

    q = PipelineEngine.get_queue(run_id)
    run = PipelineRun.query.filter_by(run_uuid=run_id).first()

    if not run:
        return jsonify({'running': q is not None, 'found': False})

    payload = {
        'running':         q is not None,
        'found':           True,
        'status':          run.status.value,
        'is_redacted':     run.is_redacted,
        'is_hcp_redacted': run.is_hcp_redacted,
        'model_is_local':  run.model_is_local,
        'error_message':   run.error_message,
        'final_output':    None,
    }

    if run.output_json:
        try:
            results = json.loads(run.output_json)
            payload['final_output'] = results.get('final_output')
        except Exception:
            pass

    # Administrators (local or BP level 9), like every debug and privacy view.
    if current_user.is_admin and run.step_snapshots_json:
        try:
            payload['step_snapshots'] = json.loads(run.step_snapshots_json)
        except Exception:
            payload['step_snapshots'] = []

    return jsonify(payload)


# ── History / list ────────────────────────────────────────────────────────────

@bp.get('/')
@login_required
@_require_clinical
def index():
    from app.models.pipeline import PipelineRun
    runs = (PipelineRun.query
            .order_by(PipelineRun.started_at.desc())
            .limit(50)
            .all())
    return render_template('pipeline_run/index.html', runs=runs)


@bp.get('/designer')
@login_required
@_require_admin
def designer():
    from app.models.pipeline import Pipeline
    all_pipelines = Pipeline.query.order_by(Pipeline.name).all()
    existing_classifiers = sorted({
        p.classifier for p in all_pipelines if p.classifier
    })
    show_archived = request.args.get('archived') == '1'
    pipelines = all_pipelines if show_archived else [p for p in all_pipelines if not p.is_archived]
    return render_template('pipeline_run/designer.html',
                           pipelines=pipelines,
                           existing_classifiers=existing_classifiers,
                           show_archived=show_archived,
                           archived_count=sum(1 for p in all_pipelines if p.is_archived))


# ── Pipeline CRUD (designer) ──────────────────────────────────────────────────

@bp.post('/designer/new')
@login_required
@_require_admin
def designer_new():
    from app.extensions import db
    from app.models.pipeline import Pipeline, PipelineStatus, RedactionPolicy

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    p = Pipeline(
        name=name,
        description=request.form.get('description', '').strip() or None,
        status=PipelineStatus.draft,
        redaction_policy=RedactionPolicy(
            request.form.get('redaction_policy', 'redact_all')),
        classifier=request.form.get('classifier', '').strip() or None,
        created_by_id=current_user.id,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'id': p.id, 'name': p.name})


@bp.post('/designer/<int:pipeline_id>/update')
@login_required
@_require_admin
def designer_pipeline_update(pipeline_id: int):
    from app.extensions import db
    from app.models.pipeline import Pipeline, RedactionPolicy

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({'error': 'Not found'}), 404

    rp = request.form.get('redaction_policy')
    if rp:
        try:
            pipeline.redaction_policy = RedactionPolicy(rp)
        except ValueError:
            return jsonify({'error': f'Invalid policy: {rp}'}), 400

    name = request.form.get('name', '').strip()
    if name:
        pipeline.name = name

    if 'classifier' in request.form:
        pipeline.classifier = request.form.get('classifier', '').strip() or None

    if 'show_in_topnav' in request.form:
        pipeline.show_in_topnav = request.form.get('show_in_topnav') == '1'

    db.session.commit()

    # Invalidate topnav cache so the change is reflected immediately
    from app import _TOPNAV_PIPELINE_CACHE
    _TOPNAV_PIPELINE_CACHE['expires'] = 0.0

    return jsonify({'ok': True})


@bp.get('/designer/<int:pipeline_id>')
@login_required
@_require_admin
def designer_edit(pipeline_id: int):
    from app.extensions import db
    from app.models.pipeline import Pipeline
    from app.models.prompt import UserPrompt
    from app.models.ai_provider import AIModel

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        from flask import abort
        abort(404)

    user_prompts = UserPrompt.query.filter_by(is_active=True).order_by(UserPrompt.name).all()
    from app.services import scope_service
    scope_choices = scope_service.choices()
    notice_choices = scope_service.notice_choices()
    models = AIModel.query.filter_by(is_enabled=True).order_by(AIModel.display_name).all()

    cloud_model_ids = {m.id for m in models if not m.provider.is_local}

    steps = list(pipeline.steps)
    inference_model_ids = []
    for s in steps:
        if s.node_type == 'inference':
            cfg = json.loads(s.config_json or '{}')
            mid = cfg.get('model_id')
            if mid:
                inference_model_ids.append(int(mid))

    return render_template('pipeline_run/pipeline_editor.html',
                           pipeline=pipeline,
                           steps=steps,
                           user_prompts=user_prompts,
                           scope_choices=scope_choices,
                           notice_choices=notice_choices,
                           models=models,
                           cloud_model_ids=list(cloud_model_ids),
                           inference_model_ids=inference_model_ids)


@bp.get('/designer/<int:pipeline_id>/step/<int:step_id>/get')
@login_required
@_require_admin
def designer_step_get(pipeline_id: int, step_id: int):
    from app.extensions import db
    from app.models.pipeline import PipelineStep

    step = db.session.get(PipelineStep, step_id)
    if not step or step.pipeline_id != pipeline_id:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'config': json.loads(step.config_json or '{}'), 'label': step.label or ''})


@bp.post('/designer/<int:pipeline_id>/step/add')
@login_required
@_require_admin
def designer_step_add(pipeline_id: int):
    from app.extensions import db
    from app.models.pipeline import Pipeline, PipelineStep

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({'error': 'Not found'}), 404

    node_type = request.form.get('node_type', 'data_assembly')
    max_order = db.session.execute(
        db.select(db.func.max(PipelineStep.step_order))
        .where(PipelineStep.pipeline_id == pipeline_id)
    ).scalar() or -1

    step = PipelineStep(
        pipeline_id=pipeline_id,
        step_order=max_order + 1,
        node_type=node_type,
        label=request.form.get('label', '').strip() or None,
        config_json='{}',
    )
    db.session.add(step)
    db.session.commit()
    return jsonify({'id': step.id, 'step_order': step.step_order})


@bp.post('/designer/<int:pipeline_id>/step/<int:step_id>/config')
@login_required
@_require_admin
def designer_step_config(pipeline_id: int, step_id: int):
    from app.extensions import db
    from app.models.pipeline import PipelineStep

    step = db.session.get(PipelineStep, step_id)
    if not step or step.pipeline_id != pipeline_id:
        return jsonify({'error': 'Not found'}), 404

    config_raw = request.form.get('config_json', '{}')
    try:
        config = json.loads(config_raw)
    except ValueError:
        return jsonify({'error': 'Invalid JSON'}), 400
    if isinstance(config, dict) and 'request_params' in config:
        from app.services import request_params
        try:
            config['request_params'] = request_params.check(config['request_params'], allow_null=True)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        if config['request_params'] is None:
            del config['request_params']
        config_raw = json.dumps(config)

    step.config_json = config_raw
    step.label = request.form.get('label', '').strip() or step.label
    db.session.commit()
    return jsonify({'ok': True})


@bp.post('/designer/<int:pipeline_id>/step/<int:step_id>/move')
@login_required
@_require_admin
def designer_step_move(pipeline_id: int, step_id: int):
    from app.extensions import db
    from app.models.pipeline import PipelineStep

    direction = request.form.get('direction')
    if direction not in ('up', 'down'):
        return jsonify({'error': 'direction must be up or down'}), 400

    steps = (PipelineStep.query
             .filter_by(pipeline_id=pipeline_id)
             .order_by(PipelineStep.step_order, PipelineStep.id)
             .all())

    # Normalise duplicate orders before any swap
    if len({s.step_order for s in steps}) < len(steps):
        for i, s in enumerate(steps):
            s.step_order = i

    idx = next((i for i, s in enumerate(steps) if s.id == step_id), None)
    if idx is None:
        return jsonify({'error': 'Step not found'}), 404

    if direction == 'up' and idx > 0:
        steps[idx].step_order, steps[idx - 1].step_order = (
            steps[idx - 1].step_order, steps[idx].step_order)
    elif direction == 'down' and idx < len(steps) - 1:
        steps[idx].step_order, steps[idx + 1].step_order = (
            steps[idx + 1].step_order, steps[idx].step_order)

    db.session.commit()
    return jsonify({'ok': True})


@bp.post('/designer/<int:pipeline_id>/step/<int:step_id>/delete')
@login_required
@_require_admin
def designer_step_delete(pipeline_id: int, step_id: int):
    from app.extensions import db
    from app.models.pipeline import PipelineStep

    step = db.session.get(PipelineStep, step_id)
    if not step or step.pipeline_id != pipeline_id:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(step)
    db.session.commit()
    return jsonify({'ok': True})


@bp.post('/designer/<int:pipeline_id>/set-default')
@login_required
@_require_admin
def designer_set_default(pipeline_id: int):
    from app.extensions import db
    from app.models.pipeline import Pipeline

    pipeline = db.session.get(Pipeline, pipeline_id)
    if not pipeline:
        return jsonify({'error': 'Pipeline not found'}), 404

    # Clear is_default for all pipelines with the same classifier first
    if pipeline.classifier:
        Pipeline.query.filter_by(classifier=pipeline.classifier).update({'is_default': False})
    else:
        Pipeline.query.filter_by(classifier=None).update({'is_default': False})

    pipeline.is_default = True
    db.session.commit()
    return jsonify({'ok': True, 'pipeline_id': pipeline_id})


@bp.post('/designer/<int:pipeline_id>/activate')
@login_required
@_require_admin
def designer_activate(pipeline_id: int):
    from app.extensions import db
    from app.models.pipeline import Pipeline, PipelineStatus

    p = db.session.get(Pipeline, pipeline_id)
    if not p:
        return jsonify({'error': 'Not found'}), 404
    if p.is_archived:
        return jsonify({'error': 'Unarchive it first.'}), 400
    p.status = PipelineStatus.active
    db.session.commit()
    _refresh_topnav()
    return jsonify({'status': p.status.value})


@bp.post('/designer/<int:pipeline_id>/deactivate')
@login_required
@_require_admin
def designer_deactivate(pipeline_id: int):
    """Back to draft: nothing that looks pipelines up by classifier finds it (ADR-099)."""
    from app.extensions import db
    from app.models.pipeline import Pipeline, PipelineStatus

    p = db.session.get(Pipeline, pipeline_id)
    if not p:
        return jsonify({'error': 'Not found'}), 404
    p.status = PipelineStatus.draft
    db.session.commit()
    _refresh_topnav()
    return jsonify({'status': p.status.value})


@bp.post('/designer/<int:pipeline_id>/archive')
@login_required
@_require_admin
def designer_archive(pipeline_id: int):
    """Hidden from All Pipelines and never run; nothing finds it by classifier."""
    return _set_status(pipeline_id, 'archived')


@bp.post('/designer/<int:pipeline_id>/unarchive')
@login_required
@_require_admin
def designer_unarchive(pipeline_id: int):
    """Back to draft, not active: activating stays a separate step."""
    return _set_status(pipeline_id, 'draft')


def _set_status(pipeline_id: int, status: str):
    from app.extensions import db
    from app.models.pipeline import Pipeline, PipelineStatus

    p = db.session.get(Pipeline, pipeline_id)
    if not p:
        return jsonify({'error': 'Not found'}), 404
    p.status = PipelineStatus(status)
    db.session.commit()
    _refresh_topnav()
    return jsonify({'status': p.status.value})


def _refresh_topnav() -> None:
    """The topnav lists active pipelines; show a status change at once."""
    from app import _TOPNAV_PIPELINE_CACHE
    _TOPNAV_PIPELINE_CACHE['expires'] = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse_event(data: dict) -> str:
    """Emit a named SSE event so addEventListener(type, ...) works in the browser."""
    event_type = data.get('type', 'message')
    return f'event: {event_type}\ndata: {json.dumps(data)}\n\n'
