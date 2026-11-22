"""Practice Protocols (ADR-171): Admin ▾ → Practice Protocols.

Anyone who sees the Admin menu (level 7+) can read every version. Only an administrator changes a
draft, approves it or edits the guideline library. Approved and retired versions are read-only.
"""
import json
from datetime import date, timedelta
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from app.extensions import db
from app.models.careplan import CareplanGuideline
from app.models.protocol import (ProtocolMeasure, ProtocolModule, ProtocolOption, ProtocolOptionCitation,
                                 ProtocolPreventionRule, ProtocolVersion)
from app.services import protocol_service as svc

TABS = ('measures', 'modules', 'prevention', 'guidelines', 'versions')


def viewer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.has_level(7):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _back(tab: str, version_id: int | None = None, anchor: str = ''):
    url = url_for('protocols.index', tab=tab, v=version_id)
    return redirect(url + (f'#{anchor}' if anchor else ''))


def _json_field(name: str):
    raw = (request.form.get(name) or '').strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise svc.ProtocolError(f'The {name.replace("_", " ")} is not valid JSON ({e.msg}).')


@bp.get('/')
@login_required
@viewer_required
def index():
    tab = request.args.get('tab', 'measures')
    if tab not in TABS:
        tab = 'measures'
    live, draft = svc.live_version(), svc.draft_version()
    vid = request.args.get('v', type=int)
    version = db.session.get(ProtocolVersion, vid) if vid else (draft if current_user.is_admin and draft else live)
    if version is None:
        version = draft or live
    guidelines = CareplanGuideline.query.order_by(CareplanGuideline.title).all()
    from app.models.careplan import CareplanResultToken
    tokens = CareplanResultToken.query.filter_by(active=True).order_by(CareplanResultToken.key).all()
    by_key = {t.key: t for t in tokens}
    token_choices = {m.id: svc.allowed_tokens(m, tokens) for m in svc.measures()}
    link = {m.id: svc.link_status(m, by_key) for m in svc.measures()}
    return render_template(
        'protocols/index.html', tab=tab, version=version, live=live, draft=draft,
        versions=svc.all_versions(), measures=svc.measures(),
        options=svc.options_by_measure(version), guidelines=guidelines,
        flags=svc.flag_labels(), token_choices=token_choices, link=link, can_edit=current_user.is_admin and version is not None
        and version.status.value == 'draft', is_admin=current_user.is_admin,
        scope_label=svc.scope_label, default_review=date.today() + timedelta(days=365))


@bp.get('/record')
@login_required
@viewer_required
def record():
    """The decision record for a version, generated from its data (ADR-176): printable."""
    vid = request.args.get('v', type=int)
    version = db.session.get(ProtocolVersion, vid) if vid else (svc.live_version() or svc.draft_version())
    if version is None:
        abort(404)
    guideline_ids = {c.guideline_id for o in version.options for c in o.citations}
    guidelines = (CareplanGuideline.query.filter(CareplanGuideline.id.in_(guideline_ids))
                  .order_by(CareplanGuideline.title).all() if guideline_ids else [])
    return render_template('protocols/record.html', version=version, measures=svc.measures(),
                           options=svc.options_by_measure(version), guidelines=guidelines,
                           rule_text=svc.rule_text, prevention_rule_text=svc.prevention_rule_text)


@bp.get('/review')
@login_required
@viewer_required
def review_targets():
    """Patients' targets set under options since changed or citing superseded guidelines (ADR-176)."""
    return render_template('protocols/review.html', items=svc.targets_to_review(), live=svc.live_version())


# ── Versions ──────────────────────────────────────────────────────────────────

@bp.post('/draft/start')
@login_required
@admin_required
def draft_start():
    try:
        d = svc.start_draft(current_user, request.form.get('note', ''))
        flash(f'Draft version {d.version} started.', 'success')
        return _back('measures', d.id)
    except svc.ProtocolError as e:
        flash(str(e), 'error')
        return _back('versions')


@bp.post('/draft/discard')
@login_required
@admin_required
def draft_discard():
    try:
        svc.discard_draft()
        flash('Draft discarded.', 'success')
    except svc.ProtocolError as e:
        flash(str(e), 'error')
    return _back('versions')


@bp.post('/draft/approve')
@login_required
@admin_required
def draft_approve():
    try:
        raw = (request.form.get('review_due_on') or '').strip()
        due = date.fromisoformat(raw) if raw else None
        if not request.form.get('attest'):
            raise svc.ProtocolError("Tick the sign-off box: approving says the protocol is the practice's own, reviewed decisions.")
        v = svc.approve(current_user, due, request.form.get('note', ''))
        flash(f'Version {v.version} approved and now in use.', 'success')
        return _back('versions', v.id)
    except ValueError as e:
        flash(str(e) if isinstance(e, svc.ProtocolError) else 'The review date must be a date.', 'error')
        return _back('versions')


@bp.get('/wizard')
@login_required
@admin_required
def wizard():
    """The setup wizard (ADR-182): build a draft protocol from the option catalogue."""
    from app.services import protocol_wizard as wiz
    return render_template('protocols/wizard.html', q=wiz.questions(), draft=svc.draft_version(),
                           live=svc.live_version(), answers=None, missing=[], GP_SETS=wiz.GP_SETS)


@bp.post('/wizard')
@login_required
@admin_required
def wizard_build():
    from app.services import protocol_wizard as wiz
    answers, missing = wiz.read_answers(request.form)
    if missing:
        flash(f'{len(missing)} question(s) still need an answer: they are marked below.', 'error')
        return render_template('protocols/wizard.html', q=wiz.questions(), draft=svc.draft_version(),
                               live=svc.live_version(), answers=request.form, missing=missing, GP_SETS=wiz.GP_SETS), 400
    try:
        v = wiz.build_draft(current_user, answers, request.form.get('note', '').strip())
    except svc.ProtocolError as e:
        flash(str(e), 'error')
        return redirect(url_for('protocols.wizard'))
    flash(f'Draft version {v.version} built from your answers. Read it through, edit what the practice wants '
          f'changed, then approve it on the Versions tab.', 'success')
    return _back('measures', v.id)


@bp.post('/guidelines/seed')
@login_required
@admin_required
def guidelines_seed():
    from app.services.protocol_wizard import seed_guidelines
    added, existing = seed_guidelines(current_user.id)
    flash(f'Guideline library: {added} added, {existing} already there.', 'success')
    return _back('guidelines')


# ── Options ───────────────────────────────────────────────────────────────────

@bp.post('/option/<int:option_id>')
@login_required
@admin_required
def option_save(option_id: int):
    o = db.get_or_404(ProtocolOption, option_id)
    try:
        data = {k: request.form.get(k, '') for k in svc.OPTION_FIELDS}
        data.update(default_rule=_json_field('default_rule'), priority=request.form.get('priority', 100),
                    gp_sets=request.form.get('gp_sets') == 'on')
        svc.update_option(o, data)
        flash('Option saved.', 'success')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return _back('measures', o.version_id, f'opt-{o.id}')


@bp.post('/measure/<int:measure_id>/option/add')
@login_required
@admin_required
def option_add(measure_id: int):
    m = db.get_or_404(ProtocolMeasure, measure_id)
    draft = svc.draft_version()
    if not draft:
        abort(400)
    try:
        o = svc.add_option(draft, m, {'code': request.form.get('code', ''), 'label': request.form.get('label', '')})
        flash('Option added: fill in its wording, rule and guidelines.', 'success')
        return _back('measures', draft.id, f'opt-{o.id}')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return _back('measures', draft.id, f'm-{m.id}')


@bp.post('/option/<int:option_id>/delete')
@login_required
@admin_required
def option_delete(option_id: int):
    o = db.get_or_404(ProtocolOption, option_id)
    vid, mid = o.version_id, o.measure_id
    try:
        svc.delete_option(o)
        flash('Option removed from the draft.', 'success')
    except svc.ProtocolError as e:
        flash(str(e), 'error')
    return _back('measures', vid, f'm-{mid}')


@bp.post('/option/<int:option_id>/citation')
@login_required
@admin_required
def citation_add(option_id: int):
    o = db.get_or_404(ProtocolOption, option_id)
    try:
        svc.add_citation(o, request.form.get('guideline_id', type=int) or 0,
                         request.form.get('section_ref', ''), request.form.get('quote', ''))
        flash('Guideline added to the option.', 'success')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return _back('measures', o.version_id, f'opt-{o.id}')


@bp.post('/citation/<int:citation_id>/delete')
@login_required
@admin_required
def citation_delete(citation_id: int):
    c = db.get_or_404(ProtocolOptionCitation, citation_id)
    o = c.option
    try:
        svc.delete_citation(c)
        flash('Guideline removed from the option.', 'success')
    except svc.ProtocolError as e:
        flash(str(e), 'error')
    return _back('measures', o.version_id, f'opt-{o.id}')


@bp.post('/measure/<int:measure_id>')
@login_required
@admin_required
def measure_save(measure_id: int):
    m = db.get_or_404(ProtocolMeasure, measure_id)
    try:
        svc.update_measure(m, {k: request.form.get(k, '') for k in ('label', 'unit', 'token_key')})
        flash('Measure saved.', 'success')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return _back('measures', request.form.get('v', type=int), f'm-{m.id}')


# ── Modules and prevention lines ──────────────────────────────────────────────

@bp.post('/module/<int:module_id>')
@login_required
@admin_required
def module_save(module_id: int):
    m = db.get_or_404(ProtocolModule, module_id)
    try:
        data = {k: request.form.get(k, '') for k in svc.MODULE_FIELDS}
        data.update(applies_when=_json_field('applies_when'), services=request.form.get('services', ''))
        svc.update_module(m, data)
        flash('Module saved.', 'success')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return _back('modules', m.version_id, f'mod-{m.id}')


@bp.post('/prevention/<int:rule_id>')
@login_required
@admin_required
def prevention_save(rule_id: int):
    p = db.get_or_404(ProtocolPreventionRule, rule_id)
    try:
        data = {k: request.form.get(k, '') for k in svc.PREVENTION_FIELDS}
        data['rule'] = _json_field('rule') or {}
        svc.update_prevention(p, data)
        flash('Prevention line saved.', 'success')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return _back('prevention', p.version_id, f'prev-{p.id}')


# ── Guidelines ────────────────────────────────────────────────────────────────

@bp.post('/guideline')
@bp.post('/guideline/<int:guideline_id>')
@login_required
@admin_required
def guideline_save(guideline_id: int | None = None):
    g = db.get_or_404(CareplanGuideline, guideline_id) if guideline_id else None
    try:
        fields = list(svc.GUIDELINE_FIELDS) + ['published_on', 'accessed_on', 'superseded_by_id']
        g = svc.save_guideline(current_user, {k: request.form.get(k, '') for k in fields}, g)
        flash('Guideline saved.', 'success')
        return _back('guidelines', request.form.get('v', type=int), f'g-{g.id}')
    except svc.ProtocolError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return _back('guidelines', request.form.get('v', type=int))
