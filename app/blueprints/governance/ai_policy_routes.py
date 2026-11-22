"""Governance → AI-use policy (ADR-158): everyone reads it; administrators edit it.
Every save is a numbered version, kept with its Appendix A; one can be approved (ADR-184)."""
from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required

from . import bp
from app.services import ai_policy_service

NO_SNAPSHOT = ('This version was saved before MedUI kept a copy of Appendix A with each version, '
               'so its list of AI providers and models is not available.')


def _require_admin():
    if not current_user.is_admin:
        abort(403)


def _download(text: str, name: str) -> Response:
    return Response(text, mimetype='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


@bp.get('/ai-policy/')
@login_required
def ai_policy():
    policy = ai_policy_service.get()
    return render_template('governance/ai_policy/view.html', policy=policy,
                           body=ai_policy_service.to_html(policy['markdown']),
                           n_versions=len(ai_policy_service.versions()),
                           default_review=date.today() + timedelta(days=365))


@bp.get('/ai-policy/download')
@login_required
def ai_policy_download():
    text = ai_policy_service.to_markdown(ai_policy_service.get()['markdown'])
    return _download(text, f'ai-use-policy-{datetime.now().strftime("%Y-%m-%d")}.md')


@bp.get('/ai-policy/versions')
@login_required
def ai_policy_versions():
    return render_template('governance/ai_policy/versions.html', versions=ai_policy_service.versions())


def _version_or_404(number: int):
    v = ai_policy_service.version(number)
    if v is None:
        abort(404)
    return v


@bp.get('/ai-policy/version/<int:number>')
@login_required
def ai_policy_version(number: int):
    v = _version_or_404(number)
    saved = ai_policy_service.saved_appendix(v)
    body = ai_policy_service.to_html(v.markdown, saved=saved, missing=None if saved else NO_SNAPSHOT)
    latest = ai_policy_service.latest()
    return render_template('governance/ai_policy/version.html', v=v, body=body,
                           is_latest=latest is not None and latest.id == v.id)


@bp.get('/ai-policy/version/<int:number>/download')
@login_required
def ai_policy_version_download(number: int):
    v = _version_or_404(number)
    saved = ai_policy_service.saved_appendix(v)
    text = ai_policy_service.to_markdown(v.markdown, saved=saved, missing=None if saved else NO_SNAPSHOT)
    return _download(text, f'ai-use-policy-version-{v.number}.md')


@bp.post('/ai-policy/version/<int:number>/approve')
@login_required
def ai_policy_approve(number: int):
    _require_admin()
    try:
        raw = (request.form.get('review_due_on') or '').strip()
        due = date.fromisoformat(raw) if raw else None
        if not request.form.get('attest'):
            raise ValueError('Tick the box to confirm the policy has been read and approved.')
        v = ai_policy_service.approve(number, current_user, due)
        flash(f'Version {v.number} approved. Next review: {v.review_due_on.strftime("%d/%m/%Y")}.', 'success')
    except ValueError as exc:
        flash(str(exc) if 'isoformat' not in str(exc) else 'The review date must be a date.', 'error')
    return redirect(url_for('governance.ai_policy'))


@bp.get('/ai-policy/edit')
@login_required
def ai_policy_edit():
    _require_admin()
    policy = ai_policy_service.get()
    if request.args.get('from') == 'template':
        policy = {**policy, 'markdown': ai_policy_service.template_text(), 'from_template': True}
    return render_template('governance/ai_policy/edit.html', policy=policy,
                           max_length=ai_policy_service.MAX_LENGTH)


@bp.post('/ai-policy/edit')
@login_required
def ai_policy_save():
    _require_admin()
    try:
        v = ai_policy_service.save(request.form.get('markdown', ''), current_user,
                                   request.form.get('note', ''))
    except ValueError as exc:
        flash(str(exc), 'error')
        return render_template('governance/ai_policy/edit.html',
                               policy={**ai_policy_service.get(),
                                       'markdown': request.form.get('markdown', '')},
                               max_length=ai_policy_service.MAX_LENGTH), 400
    if v is None:
        flash('No changes: the policy is the same as the latest version.', 'info')
    else:
        flash(f'Saved as version {v.number}.', 'success')
    return redirect(url_for('governance.ai_policy'))
