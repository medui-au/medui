"""Governance → AI-use policy (ADR-158): everyone reads it; administrators edit it."""
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required

from . import bp
from app.services import ai_policy_service


def _require_admin():
    if not current_user.is_admin:
        abort(403)


@bp.get('/ai-policy/')
@login_required
def ai_policy():
    policy = ai_policy_service.get()
    return render_template('governance/ai_policy/view.html', policy=policy,
                           body=ai_policy_service.to_html(policy['markdown']))


@bp.get('/ai-policy/download')
@login_required
def ai_policy_download():
    text = ai_policy_service.to_markdown(ai_policy_service.get()['markdown'])
    name = f'ai-use-policy-{datetime.now().strftime("%Y-%m-%d")}.md'
    return Response(text, mimetype='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


@bp.get('/ai-policy/edit')
@login_required
def ai_policy_edit():
    _require_admin()
    return render_template('governance/ai_policy/edit.html', policy=ai_policy_service.get(),
                           max_length=ai_policy_service.MAX_LENGTH)


@bp.post('/ai-policy/edit')
@login_required
def ai_policy_save():
    _require_admin()
    if request.form.get('action') == 'reset':
        ai_policy_service.reset()
        flash('The policy is back to the template.', 'info')
        return redirect(url_for('governance.ai_policy'))
    try:
        ai_policy_service.save(request.form.get('markdown', ''), current_user)
    except ValueError as exc:
        flash(str(exc), 'error')
        return render_template('governance/ai_policy/edit.html',
                               policy={**ai_policy_service.get(),
                                       'markdown': request.form.get('markdown', '')},
                               max_length=ai_policy_service.MAX_LENGTH), 400
    flash('Policy saved.', 'success')
    return redirect(url_for('governance.ai_policy'))
