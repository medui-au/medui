from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from . import bp
from app.extensions import db


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_level(7):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Main page ─────────────────────────────────────────────────────────────────

def _all_classifiers():
    from app.models.prompt import UserPrompt
    from app.models.pipeline import Pipeline
    prompt_cls = {r[0] for r in db.session.query(UserPrompt.classifier).filter(UserPrompt.classifier.isnot(None))}
    pipe_cls   = {r[0] for r in db.session.query(Pipeline.classifier).filter(Pipeline.classifier.isnot(None))}
    return sorted(prompt_cls | pipe_cls)


@bp.get('/')
@login_required
@_require_admin
def index():
    from app.services.prompt_service import SystemPromptService, UserPromptService
    return render_template(
        'prompt_manager/prompt_manager.html',
        system_prompts=SystemPromptService.list_active(),
        user_prompts=UserPromptService.list_all(),
        active_section='system',
        all_classifiers=_all_classifiers(),
    )


# ── System Prompt routes ───────────────────────────────────────────────────────

@bp.get('/system/list')
@login_required
@_require_admin
def system_list():
    from app.services.prompt_service import SystemPromptService
    return render_template('prompt_manager/partials/system_prompt_list.html',
                           system_prompts=SystemPromptService.list_active())


@bp.get('/system/<int:prompt_id>/edit')
@login_required
@_require_admin
def system_edit(prompt_id: int):
    from app.services.prompt_service import SystemPromptService
    sp = SystemPromptService.get(prompt_id)
    if not sp:
        return '<p style="color:var(--danger)">Not found</p>', 404
    from app.services import scope_service
    system_prompts_names = [s.name for s in SystemPromptService.list_active()]
    return render_template('prompt_manager/partials/system_prompt_editor.html',
                           sp=sp, all_names=system_prompts_names,
                           scope_choices=scope_service.choices(),
                           scope_default_key=scope_service.practice_default_key(),
                           scope_enabled=scope_service.is_enabled())


@bp.post('/system/new')
@login_required
@_require_admin
def system_new():
    from app.services.prompt_service import SystemPromptService
    try:
        sp = SystemPromptService.create({
            'name': request.form.get('name', '').strip(),
            'prompt_text': request.form.get('prompt_text', '').strip(),
            'description': request.form.get('description', ''),
            'is_default': request.form.get('is_default') == '1',
        })
    except Exception as exc:
        return f'<div class="alert alert-danger" style="padding:0.5rem;color:var(--danger);font-size:0.8rem;">{exc}</div>', 400
    return render_template('prompt_manager/partials/system_prompt_list.html',
                           system_prompts=SystemPromptService.list_active(),
                           selected_id=sp.id)


@bp.post('/system/<int:prompt_id>/save')
@login_required
@_require_admin
def system_save(prompt_id: int):
    from app.services.prompt_service import SystemPromptService
    try:
        sp = SystemPromptService.edit(prompt_id, {
            'prompt_text': request.form.get('prompt_text', '').strip(),
            'description': request.form.get('description', ''),
            'is_default': request.form.get('is_default') == '1',
            'scope_key': request.form.get('scope_key', ''),
        })
    except Exception as exc:
        return f'<span style="color:var(--danger);font-size:0.75rem;">✗ {exc}</span>', 400
    return (f'<span style="color:var(--success);font-size:0.75rem;">'
            f'✓ Saved as v{sp.version} (ID {sp.id})</span>'
            + _scope_lint_html(sp.prompt_text, 'system prompt', sp.id))


@bp.post('/system/<int:prompt_id>/set-default')
@login_required
@_require_admin
def system_set_default(prompt_id: int):
    from app.services.prompt_service import SystemPromptService
    try:
        SystemPromptService.set_default(prompt_id)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@bp.get('/system/<int:prompt_id>/history')
@login_required
@_require_admin
def system_history(prompt_id: int):
    from app.services.prompt_service import SystemPromptService
    sp = SystemPromptService.get(prompt_id)
    if not sp:
        return '<p style="color:var(--danger)">Not found</p>', 404
    history = SystemPromptService.get_history(sp.name)
    return render_template('prompt_manager/partials/version_history.html',
                           history=history, current_id=prompt_id)


@bp.post('/system/<int:prompt_id>/delete')
@login_required
@_require_admin
def system_delete(prompt_id: int):
    from app.services.prompt_service import SystemPromptService
    try:
        SystemPromptService.delete(prompt_id)
    except Exception as exc:
        return f'<div style="color:var(--danger);font-size:0.8rem;">{exc}</div>', 400
    return render_template('prompt_manager/partials/system_prompt_list.html',
                           system_prompts=SystemPromptService.list_active())


# ── User Prompt routes ─────────────────────────────────────────────────────────

@bp.get('/user/list')
@login_required
@_require_admin
def user_list():
    from app.services.prompt_service import UserPromptService
    return render_template('prompt_manager/partials/user_prompt_list.html',
                           user_prompts=UserPromptService.list_all())


@bp.get('/user/<int:prompt_id>/edit')
@login_required
@_require_admin
def user_edit(prompt_id: int):
    from app.services.prompt_service import SystemPromptService, UserPromptService
    from app.models.ai_provider import AIModel
    up = UserPromptService.get(prompt_id)
    if not up:
        return '<p style="color:var(--danger)">Not found</p>', 404
    system_prompts = SystemPromptService.list_active()
    ai_models = AIModel.query.filter_by(is_enabled=True, is_asr=False).join(AIModel.provider).all()
    return render_template('prompt_manager/partials/user_prompt_editor.html',
                           up=up, system_prompts=system_prompts, ai_models=ai_models,
                           all_classifiers=_all_classifiers())


@bp.post('/user/new')
@login_required
@_require_admin
def user_new():
    from app.services.prompt_service import SystemPromptService, UserPromptService
    try:
        up = UserPromptService.create({
            'name': request.form.get('name', '').strip(),
            'description': request.form.get('description', ''),
            'prompt_text': request.form.get('prompt_text', '').strip(),
            'system_prompt_name': request.form.get('system_prompt_name', ''),
            'classifier': request.form.get('classifier', ''),
            'default_model_id': request.form.get('default_model_id'),
            'show_in_assistant': request.form.get('show_in_assistant') == '1',
            'temperature': request.form.get('temperature'),
            'max_tokens': request.form.get('max_tokens'),
        })
    except Exception as exc:
        return f'<div style="color:var(--danger);font-size:0.8rem;padding:0.5rem;">{exc}</div>', 400
    return render_template('prompt_manager/partials/user_prompt_list.html',
                           user_prompts=UserPromptService.list_all(),
                           selected_id=up.id)


@bp.post('/user/<int:prompt_id>/save')
@login_required
@_require_admin
def user_save(prompt_id: int):
    from app.services.prompt_service import UserPromptService
    try:
        UserPromptService.edit(prompt_id, {
            'name': request.form.get('name', '').strip(),
            'description': request.form.get('description', ''),
            'prompt_text': request.form.get('prompt_text', '').strip(),
            'system_prompt_name': request.form.get('system_prompt_name', ''),
            'classifier': request.form.get('classifier', ''),
            'default_model_id': request.form.get('default_model_id'),
            'show_in_assistant': request.form.get('show_in_assistant') == '1',
            'temperature': request.form.get('temperature'),
            'max_tokens': request.form.get('max_tokens'),
        })
    except Exception as exc:
        return f'<span style="color:var(--danger);font-size:0.75rem;">✗ {exc}</span>', 400
    return ('<span style="color:var(--success);font-size:0.75rem;">✓ Saved</span>'
            + _scope_lint_html(request.form.get('prompt_text', ''), 'user prompt', prompt_id))


@bp.post('/user/<int:prompt_id>/toggle-assistant')
@login_required
@_require_admin
def user_toggle_assistant(prompt_id: int):
    from app.services.prompt_service import UserPromptService
    try:
        up = UserPromptService.toggle_assistant(prompt_id)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'show_in_assistant': up.show_in_assistant})


@bp.post('/user/<int:prompt_id>/delete')
@login_required
@_require_admin
def user_delete(prompt_id: int):
    from app.services.prompt_service import UserPromptService
    try:
        UserPromptService.delete(prompt_id)
    except Exception as exc:
        return f'<div style="color:var(--danger);font-size:0.8rem;">{exc}</div>', 400
    return render_template('prompt_manager/partials/user_prompt_list.html',
                           user_prompts=UserPromptService.list_all())


def _scope_lint_html(text: str, kind: str, prompt_id: int) -> str:
    """A warning after saving a prompt that asks the AI for device-like output (ADR-089).

    Saved regardless — a nudge, not a block — and the warning is logged so it is
    on record that it was shown.
    """
    from html import escape
    from flask import current_app
    from app.services.checker import scope as scope_check
    hits = scope_check.scan_prompt(text or '')
    if not hits:
        return ''
    asks = sorted({scope_check.LABELS[h['pattern']] for h in hits})
    current_app.logger.info('prompt editor scope warning: %s %s by user %s: %s',
                            kind, prompt_id, current_user.id,
                            ', '.join(sorted({h['pattern'] for h in hits})))
    return ('<div style="margin-top:0.4rem; color:var(--warning, #b45309); font-size:0.75rem;">'
            '⚠ This prompt ' + escape('; '.join(asks)) + '. That goes beyond what MedUI is '
            'intended for: consider rewording it to organise or summarise what the record says.</div>')
