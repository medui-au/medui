"""Care plan builder (ADR-129): the patient's plan screen and the doctor's recipe library."""
from functools import wraps

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from app.models.careplan import Careplan, CareplanRecipe, CareplanResultToken, CareplanStatus
from app.services import careplan_service as svc
from app.services.clinical_service import ClinicalService
from app.utils.access import ai_required


def doctor_required(f):
    """Care plans are for doctors (level 5 and above)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.has_level(5):
            if request.is_json:
                return jsonify({'error': 'Care plans are for doctors.'}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _patient(patient_id: int) -> dict:
    try:
        demographics = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:
        current_app.logger.error('careplan demographics error: %s', type(e).__name__)
        demographics = None
    if not demographics:
        abort(404)
    return demographics


def _plan(plan_id: int) -> Careplan:
    return Careplan.query.get_or_404(plan_id)


def _error(e: Exception, status: int = 400):
    return jsonify({'error': str(e)}), status


# ── Patient screen ────────────────────────────────────────────────────────────

@bp.get('/patient/<int:patient_id>')
@login_required
@doctor_required
def patient_plan(patient_id: int):
    patient = _patient(patient_id)
    draft = svc.open_draft(patient_id)
    current = svc.last_filed(patient_id)
    return render_template('careplan/patient.html', patient=patient, draft=draft, current=current,
                           history=svc.plan_history(patient_id))


@bp.post('/patient/<int:patient_id>/start')
@login_required
@doctor_required
def start(patient_id: int):
    _patient(patient_id)
    draft = svc.open_draft(patient_id) or svc.start_draft(patient_id, current_user)
    return redirect(url_for('careplan.edit', plan_id=draft.id))


@bp.get('/plan/<int:plan_id>/edit')
@login_required
@doctor_required
def edit(plan_id: int):
    plan = _plan(plan_id)
    if plan.status != CareplanStatus.draft:
        return redirect(url_for('careplan.view', plan_id=plan.id))
    patient = _patient(plan.patient_id)
    svc.ensure_fact_tokens()
    try:
        coded = svc.coded_history(plan.patient_id)
    except Exception as e:
        current_app.logger.warning('careplan coded history failed: %s', type(e).__name__)
        coded = []
    prev = Careplan.query.get(plan.previous_careplan_id) if plan.previous_careplan_id else None
    asset = {
        'plan_id': plan.id, 'revision': plan.draft_revision, 'draft': svc.draft_data(plan),
        'coded': coded,
        'recipes': [svc.recipe_payload(r) for r in svc.visible_recipes(current_user)
                    if r.current_version_id],
        'tokens': {t.key: {'label': t.label, 'unit': t.expected_unit}
                   for t in svc.active_tokens().values()},
        'previous_values': svc.filed_values(prev) if prev else {},
        'patient_facts': {'age': patient.get('CLINICAL_AGE') or '', 'sex': patient.get('GENDER') or ''},
        'urls': {
            'save': url_for('careplan.save', plan_id=plan.id),
            'preview': url_for('careplan.values_preview', plan_id=plan.id),
            'confirm': url_for('careplan.values_confirm', plan_id=plan.id),
            'check': url_for('careplan.check', plan_id=plan.id),
            'file': url_for('careplan.file', plan_id=plan.id),
            'print': url_for('careplan.print_plan', plan_id=plan.id),
            'export': url_for('careplan.export', plan_id=plan.id),
            'void': url_for('careplan.void', plan_id=plan.id),
            'row_recipe': url_for('careplan.row_to_recipe'),
            'view': url_for('careplan.view', plan_id=plan.id),
            'recipes': url_for('careplan.recipes'),
        },
    }
    return render_template('careplan/edit.html', patient=patient, plan=plan, asset=asset)


@bp.post('/plan/<int:plan_id>/draft')
@login_required
@doctor_required
def save(plan_id: int):
    plan = _plan(plan_id)
    body = request.get_json(silent=True) or {}
    try:
        rev = svc.save_draft(plan, current_user, int(body.get('revision', -1)), body.get('draft') or {})
    except svc.DraftConflict:
        return jsonify({'error': 'This plan was saved from another window. Reload to see the latest.',
                        'conflict': True}), 409
    except (svc.CareplanError, ValueError) as e:
        return _error(e)
    return jsonify({'revision': rev})


@bp.post('/plan/<int:plan_id>/values/preview')
@login_required
@doctor_required
def values_preview(plan_id: int):
    plan = _plan(plan_id)
    keys = [k for k in (request.get_json(silent=True) or {}).get('keys', []) if isinstance(k, str)][:50]
    try:
        values = svc.fetch_values(plan.patient_id, keys)
    except Exception as e:
        current_app.logger.error('careplan values preview failed: %s', type(e).__name__)
        return _error('Best Practice could not be read.', 502)
    return jsonify({'values': values})


@bp.post('/plan/<int:plan_id>/values/confirm')
@login_required
@doctor_required
def values_confirm(plan_id: int):
    plan = _plan(plan_id)
    body = request.get_json(silent=True) or {}
    keys = [k for k in body.get('keys', []) if isinstance(k, str)][:50]
    manual = {k: v for k, v in (body.get('manual') or {}).items() if isinstance(v, str)}
    try:
        return jsonify(svc.confirm_values(plan, current_user, keys, manual))
    except svc.CareplanError as e:
        return _error(e)


@bp.post('/plan/<int:plan_id>/check')
@login_required
@doctor_required
def check(plan_id: int):
    plan = _plan(plan_id)
    return jsonify({'notes': svc.completeness(svc.draft_data(plan))})


@bp.post('/plan/<int:plan_id>/file')
@login_required
@doctor_required
def file(plan_id: int):
    plan = _plan(plan_id)
    try:
        svc.file_plan(plan, current_user, _patient(plan.patient_id))
    except svc.CareplanError as e:
        return _error(e)
    return jsonify({'url': url_for('careplan.view', plan_id=plan.id)})


@bp.post('/plan/<int:plan_id>/void')
@login_required
@doctor_required
def void(plan_id: int):
    plan = _plan(plan_id)
    reason = (request.get_json(silent=True) or request.form).get('reason', '')
    try:
        svc.void_plan(plan, current_user, reason)
    except svc.CareplanError as e:
        return _error(e)
    return jsonify({'url': url_for('careplan.patient_plan', patient_id=plan.patient_id)})


@bp.get('/plan/<int:plan_id>')
@login_required
@doctor_required
def view(plan_id: int):
    plan = _plan(plan_id)
    if plan.status == CareplanStatus.draft:
        return redirect(url_for('careplan.edit', plan_id=plan.id))
    return render_template('careplan/view.html', patient=_patient(plan.patient_id), plan=plan)


@bp.get('/plan/<int:plan_id>/print')
@login_required
@doctor_required
def print_plan(plan_id: int):
    plan = _plan(plan_id)
    if plan.status == CareplanStatus.draft:
        document = svc.draft_document(plan, current_user, _patient(plan.patient_id))
        return render_template('careplan/print.html', document=document, draft=True)
    if not plan.filed_document:
        abort(404)
    return render_template('careplan/print.html', document=plan.filed_document, draft=False)


@bp.post('/plan/<int:plan_id>/export')
@login_required
@doctor_required
def export(plan_id: int):
    plan = _plan(plan_id)
    channel = (request.get_json(silent=True) or {}).get('channel', '')
    try:
        out = svc.export_plan(plan, current_user, _patient(plan.patient_id), channel)
    except svc.CareplanError as e:
        return _error(e)
    out['comms_url'] = url_for('clinical_comms.patient_comms', patient_id=plan.patient_id)
    return jsonify(out)


@bp.post('/plan/<int:plan_id>/export-bp')
@login_required
@doctor_required
def export_bp(plan_id: int):
    """BP →: the plan to Best Practice as a PIT file, in place (ADR-174)."""
    plan = _plan(plan_id)
    try:
        out = svc.export_plan_to_bp(plan, current_user, _patient(plan.patient_id))
    except svc.CareplanError as e:
        return _error(e)
    except Exception as e:  # the PIT share boundary
        current_app.logger.error('care plan PIT export failed plan=%s: %s', plan_id, type(e).__name__)
        return _error(RuntimeError('Sending to Best Practice failed. Check the PIT folder in Setup → Messaging.'), 500)
    return jsonify(out)


@bp.post('/row-to-recipe')
@login_required
@doctor_required
def row_to_recipe():
    row = (request.get_json(silent=True) or {}).get('row') or {}
    try:
        recipe = svc.row_to_recipe(current_user, row)
    except svc.CareplanError as e:
        return _error(e)
    return jsonify({'url': url_for('careplan.recipe_edit', recipe_id=recipe.id)})


# ── Recipe library (Doctor Data) ──────────────────────────────────────────────

def _models():
    from app.services import model_choice
    return model_choice.available_models()


def _assist_pipelines():
    from app.models.pipeline import Pipeline, PipelineStatus
    return [p for p in Pipeline.query.filter_by(status=PipelineStatus.active).order_by(Pipeline.name).all()
            if '[recipe]' in (p.classifier or '').lower()]


@bp.get('/recipes')
@login_required
@doctor_required
def recipes():
    svc.ensure_fact_tokens()
    tokens = CareplanResultToken.query.order_by(CareplanResultToken.key).all()
    facts = [t for t in tokens if t.key in svc.FACT_TOKENS]
    results = [t for t in tokens if t.key not in svc.FACT_TOKENS]
    return render_template('careplan/recipes.html', recipes=svc.visible_recipes(current_user),
                           tokens=results, fact_tokens=facts,
                           shared={t.key: svc.shared_codes(t) for t in results},
                           can_practice=svc.can_publish_practice(current_user))


@bp.get('/recipes/new')
@bp.get('/recipes/<int:recipe_id>')
@login_required
@doctor_required
def recipe_edit(recipe_id: int | None = None):
    recipe = CareplanRecipe.query.get_or_404(recipe_id) if recipe_id else None
    payload = svc.recipe_payload(recipe) if recipe else None
    editable = recipe is None or recipe.owner_id == current_user.id or (
        recipe.scope.value == 'practice' and svc.can_publish_practice(current_user))
    targets = []
    if recipe and recipe.current_version:
        for t in recipe.current_version.targets:
            c = t.citation
            targets.append({'token': t.token.key, 'target': t.target_text,
                            'guideline': c.guideline.title if c else '', 'edition': c.guideline.edition if c else '',
                            'url': c.guideline.url if c else '', 'section': c.section_ref if c else '',
                            'quote': c.quote if c else ''})
    return render_template('careplan/recipe_edit.html', recipe=recipe, payload=payload, targets=targets,
                           editable=editable, can_practice=svc.can_publish_practice(current_user),
                           token_labels={k: t.label for k, t in svc.active_tokens().items()},
                           pipelines=_assist_pipelines() if current_user.can_use_ai else [],
                           models=_models() if current_user.can_use_ai else [])


@bp.post('/recipes/save')
@login_required
@doctor_required
def recipe_save():
    body = request.get_json(silent=True) or {}
    recipe = CareplanRecipe.query.get_or_404(body['id']) if body.get('id') else None
    try:
        recipe = svc.save_recipe(current_user, body, recipe)
    except svc.CareplanError as e:
        return _error(e)
    return jsonify({'id': recipe.id, 'url': url_for('careplan.recipe_edit', recipe_id=recipe.id)})


@bp.post('/recipes/<int:recipe_id>/<action>')
@login_required
@doctor_required
def recipe_action(recipe_id: int, action: str):
    recipe = CareplanRecipe.query.get_or_404(recipe_id)
    try:
        if action == 'approve':
            svc.approve_recipe(current_user, recipe)
        elif action == 'copy':
            recipe = svc.copy_recipe(current_user, recipe)
        elif action == 'retire':
            svc.retire_recipe(current_user, recipe)
            return jsonify({'url': url_for('careplan.recipes')})
        else:
            abort(404)
    except svc.CareplanError as e:
        return _error(e)
    return jsonify({'url': url_for('careplan.recipe_edit', recipe_id=recipe.id)})


@bp.post('/recipes/assist')
@login_required
@doctor_required
@ai_required
def recipe_assist():
    """Run the practice's recipe pipeline on the doctor's text. No patient: the recipe screen has none."""
    from app.services.pipeline.engine import PipelineEngine
    body = request.get_json(silent=True) or {}
    text = (body.get('text') or '').strip()[:8000]
    allowed = {p.id for p in _assist_pipelines()}
    pipeline_id = body.get('pipeline_id')
    if not text:
        return _error('Type a description or paste guideline wording first.')
    if pipeline_id not in allowed:
        return _error('Choose a recipe assistant pipeline.')
    from app.services import model_choice
    try:
        model = model_choice.chosen(body.get('model_id'))      # ADR-178: the doctor's choice for this run
    except ValueError as e:
        return _error(e)
    inputs = {'user_prompt': text}
    if model is not None:
        inputs['model_id_override'] = model.id
    try:
        run_id = PipelineEngine.run(pipeline_id=pipeline_id, patient_id=None, user_id=current_user.id,
                                    input_data=inputs, model_is_local=False)
    except ValueError as e:
        return _error(e)
    return jsonify({'run_id': run_id, 'stream_url': url_for('pipeline_run.run_stream', run_id=run_id)})


@bp.get('/loinc')
@login_required
@doctor_required
def loinc_catalogue():
    """The practice's LOINC codes for the token editor (names, units, counts; no patients)."""
    if not current_user.is_admin:
        return _error('Result tokens are set up by an administrator.', 403)
    try:
        codes = svc.loinc_catalogue(refresh=request.args.get('refresh') == '1')
    except Exception as e:
        current_app.logger.error('careplan loinc catalogue failed: %s', type(e).__name__)
        return _error('Best Practice could not be read.', 502)
    return jsonify({'codes': codes})


@bp.post('/tokens')
@login_required
@doctor_required
def token_save():
    if not current_user.is_admin:
        return _error('Result tokens are set up by an administrator.', 403)
    body = request.get_json(silent=True) or {}
    token = CareplanResultToken.query.get_or_404(body['id']) if body.get('id') else None
    try:
        token = svc.save_token(body, token)
    except svc.CareplanError as e:
        return _error(e)
    shared = svc.shared_codes(token)
    warnings = [f'{", ".join(codes)} is also in token "{key}".' for key, codes in shared.items()]
    return jsonify({'ok': True, 'warnings': warnings})
