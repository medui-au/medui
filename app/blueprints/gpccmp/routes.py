"""GPCCMP: Targets & Plan (ADR-172, phase 2: patient targets).

Patient Data ▾ → GPCCMP: Targets & Plan, and the Targets link in Patient Tools. Nurses (level 3+)
see a patient's targets; doctors (level 5+) set and change them. Later phases add the plan
decisions form and the AI draft to this blueprint.
"""
from functools import wraps

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from app.services import patient_target_service as targets
from app.services.clinical_service import ClinicalService


def viewer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not targets.can_view(current_user):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _patient(patient_id: int) -> dict:
    try:
        demographics = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:  # BPSDB boundary
        current_app.logger.error('gpccmp demographics error: %s', type(e).__name__)
        demographics = None
    if not demographics:
        abort(404)
    return demographics


def _open_plan(patient_id: int, session):
    """A care-plan draft already open for the patient that isn't this session's own AI draft."""
    from app.services import careplan_service
    plan = careplan_service.open_draft(patient_id)
    return plan if plan is not None and plan.id != session.careplan_id else None


def _drafts():
    from app.services import gpccmp_draft_service
    return gpccmp_draft_service


def _flags(patient_id: int) -> dict:
    """The Disease Profile's coded flags; {} if BP can't be read (nothing is then preselected)."""
    try:
        profile = ClinicalService.get_disease_profile(patient_id) or {}
    except Exception as e:  # BPSDB boundary
        current_app.logger.error('gpccmp disease profile error: %s', type(e).__name__)
        profile = {}
    return {k: v for k, v in profile.items() if k in targets.FLAG_LABELS}


@bp.get('/patient/<int:patient_id>/targets')
@login_required
@viewer_required
def patient_targets(patient_id: int):
    patient = _patient(patient_id)
    flags = _flags(patient_id)
    from app.services import protocol_service as protocols
    latest = targets.latest_values(patient_id, protocols.measures())
    data = targets.build_rows(patient_id, flags, latest)
    coded = [targets.FLAG_LABELS[f] for f, v in flags.items() if v]
    return render_template('gpccmp/targets.html', patient=patient, patient_id=patient_id, coded=coded,
                           can_set=targets.can_set(current_user), **data)


@bp.post('/patient/<int:patient_id>/targets')
@login_required
@viewer_required
def patient_targets_save(patient_id: int):
    if not targets.can_set(current_user):
        abort(403)
    choices = []
    for mid in request.form.getlist('measure'):
        choice = (request.form.get(f'choice_{mid}') or '').strip()
        if not choice:
            continue
        choices.append({'measure_id': int(mid), 'option_id': None if choice == 'individual' else int(choice),
                        'value_text': request.form.get(f'value_{mid}', ''),
                        'reason': request.form.get(f'reason_{mid}', '')})
    try:
        saved = targets.confirm(patient_id, current_user, choices, _flags(patient_id))
    except (targets.TargetError, ValueError) as e:
        flash(str(e) if isinstance(e, targets.TargetError) else 'Something in the form could not be read.', 'error')
        return redirect(url_for('gpccmp.patient_targets', patient_id=patient_id))
    flash(f'{len(saved)} target{"s" if len(saved) != 1 else ""} saved.' if saved else 'No targets changed.',
          'success')
    if request.form.get('action') == 'continue':
        return redirect(url_for('gpccmp.plan_decisions', patient_id=patient_id))
    return redirect(url_for('gpccmp.patient_targets', patient_id=patient_id))


# ── Plan decisions (ADR-173, phase 3) ─────────────────────────────────────────

def doctor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not targets.can_set(current_user):
            abort(403)
        return f(*args, **kwargs)
    return decorated


@bp.get('/patient/<int:patient_id>/plan')
@login_required
@doctor_required
def plan_decisions(patient_id: int):
    from app.services import gpccmp_decision_service as dec
    from app.services import protocol_service as protocols
    patient = _patient(patient_id)
    flags = _flags(patient_id)
    session = dec.open_session(patient_id, current_user, flags)
    d = dec.decisions(session)
    version = protocols.live_version()
    current = targets.current_targets(patient_id)
    preview = dec.decisions_block(d, dec.targets_for_block(patient_id), version) if d else ''
    from app.services import gpccmp_review_service as review
    latest = targets.latest_values(patient_id, protocols.measures())
    module_goals = {m.condition_key: m.goals or '' for m in (version.modules if version else [])}
    filed_goals = review.previous_goals(patient_id)
    prev_goal = {i['key']: review.goal_for(i, filed_goals, module_goals.get(i['key'], '')) for i in d.get('issues', [])}
    return render_template(
        'gpccmp/plan.html', patient=patient, patient_id=patient_id, session=session, d=d, version=version,
        issues=dec.issue_choices(version, flags), chosen={i['key']: i for i in d.get('issues', [])},
        free=[i for i in d.get('issues', []) if i.get('source') == 'gp'], max_free=dec.MAX_FREE_ISSUES,
        plan_types=dec.PLAN_TYPES, default_type=d.get('plan_type') or dec.plan_type_from_eligibility(patient.get('CCMP_Eligibility')),
        eligibility=patient.get('CCMP_Eligibility'), modifiers=dec.MODIFIERS, consent=dec.CONSENT,
        intervals=dec.REVIEW_INTERVALS, default_review=dec.DEFAULT_REVIEW, formats=dec.FORMATS,
        targets_set=list(current.values()), problems=dec.problems(d) if d else [], preview=preview,
        models=_drafts().available_models(), default_label=_drafts().model_label(_drafts().default_model()),
        open_plan=_open_plan(patient_id, session),
        progress_words=review.PROGRESS_WORDS, target_sentences=review.target_sentences(patient_id, latest),
        prev_goal=prev_goal, has_previous=bool(filed_goals or d.get('carried_from')))


@bp.post('/patient/<int:patient_id>/plan')
@login_required
@doctor_required
def plan_decisions_save(patient_id: int):
    from app.services import gpccmp_decision_service as dec
    from app.services import protocol_service as protocols
    patient = _patient(patient_id)
    session = dec.open_session(patient_id, current_user)
    action = request.form.get('action')
    proceed = action in ('proceed', 'draft')
    try:
        d = dec.parse_form(request.form, protocols.live_version(), patient.get('CCMP_Eligibility'))
        dec.save(session, d, proceed=proceed)
    except dec.DecisionError as e:
        flash(str(e), 'error')
        return redirect(url_for('gpccmp.plan_decisions', patient_id=patient_id))
    if action == 'draft':
        # Save, confirm and draft in one step, so the AI works from exactly what the GP sees.
        from app.services import gpccmp_draft_service as drafts
        if not current_user.can_use_ai or not current_app.config.get('AI_ENABLED', True):
            abort(403)
        try:
            drafts.start(session, current_user, request.form.get('model_id', type=int))
        except drafts.DraftError as e:
            flash(f'Decisions saved and confirmed, but the draft could not start: {e}', 'error')
            return redirect(url_for('gpccmp.plan_decisions', patient_id=patient_id))
        return redirect(url_for('gpccmp.draft_page', session_id=session.id))
    flash('Decisions saved and confirmed.' if proceed else 'Decisions saved.', 'success')
    return redirect(url_for('gpccmp.plan_decisions', patient_id=patient_id))


@bp.post('/patient/<int:patient_id>/plan/abandon')
@login_required
@doctor_required
def plan_decisions_abandon(patient_id: int):
    from app.services import gpccmp_decision_service as dec
    dec.abandon(dec.open_session(patient_id, current_user))
    flash('Plan decisions discarded.', 'success')
    return redirect(url_for('gpccmp.patient_targets', patient_id=patient_id))


# ── The AI draft (ADR-174, phase 4) ──────────────────────────────────────────

def _own_session(session_id: int):
    from app.models.gpccmp import GpccmpSession
    from app.extensions import db
    s = db.get_or_404(GpccmpSession, session_id)
    if s.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return s


def _facts(patient_id: int) -> dict:
    """Age, sex and smoking for the prevention lines, from the record (no AI)."""
    from app.services import careplan_service
    try:
        return {v['key']: v.get('value') for v in careplan_service.fetch_values(patient_id, ['age', 'sex', 'smoking'])}
    except Exception as e:  # BPSDB boundary: without them, age/sex-based lines are left out
        current_app.logger.warning('gpccmp facts unavailable: %s', type(e).__name__)
        return {}


@bp.post('/patient/<int:patient_id>/plan/draft')
@login_required
@doctor_required
def plan_draft_start(patient_id: int):
    from app.services import gpccmp_decision_service as dec
    from app.services import gpccmp_draft_service as drafts
    if not current_user.can_use_ai:
        abort(403)
    session = dec.open_session(patient_id, current_user)
    try:
        drafts.start(session, current_user, request.form.get('model_id', type=int))
    except drafts.DraftError as e:
        flash(str(e), 'error')
        return redirect(url_for('gpccmp.plan_decisions', patient_id=patient_id))
    return redirect(url_for('gpccmp.draft_page', session_id=session.id))


@bp.get('/session/<int:session_id>')
@login_required
@doctor_required
def draft_page(session_id: int):
    s = _own_session(session_id)
    patient = _patient(s.patient_id)
    checks = (s.check_results or {}).get('checks') or []
    from app.services import gpccmp_draft_service as drafts
    return render_template('gpccmp/draft.html', session=s, patient=patient, patient_id=s.patient_id, checks=checks,
                           failed=[c for c in checks if not c['ok']], models=drafts.available_models(),
                           default_label=drafts.model_label(drafts.default_model()),
                           used=(s.check_results or {}))


@bp.get('/session/<int:session_id>/status')
@login_required
@doctor_required
def draft_status(session_id: int):
    from flask import jsonify
    from app.services import gpccmp_draft_service as drafts
    s = _own_session(session_id)
    out = drafts.poll(s, current_user, _patient(s.patient_id), _flags(s.patient_id), _facts(s.patient_id))
    if out.get('state') == 'done':
        out['url'] = url_for('gpccmp.draft_page', session_id=s.id)
    return jsonify(out)


@bp.post('/session/<int:session_id>/redraft')
@login_required
@doctor_required
def draft_again(session_id: int):
    from app.services import gpccmp_draft_service as drafts
    s = _own_session(session_id)
    if not current_user.can_use_ai:
        abort(403)
    try:
        drafts.redraft(s, current_user)
        drafts.start(s, current_user, request.form.get('model_id', type=int))
    except drafts.DraftError as e:
        flash(str(e), 'error')
    return redirect(url_for('gpccmp.draft_page', session_id=s.id))
