from datetime import datetime, timezone

from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user

from app.services.doc_library_service import DocLibraryService
from . import bp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(dt) -> str:
    if not dt:
        return ''
    return dt.strftime('%-d %b %Y')


def _doc_to_dict(doc, user_id: int) -> dict:
    return {
        'id':          doc.id,
        'title':       doc.title,
        'keywords':    doc.keywords or '',
        'visibility':  doc.visibility.value,
        'patient_id':  doc.patient_id,
        'is_owner':    doc.created_by_id == user_id,
        'author':      doc.created_by.username if doc.created_by else '',
        'updated_at':  _fmt_date(doc.updated_at or doc.created_at),
    }


# The Library is not linked to patients (ADR-093): documents are general, its AI
# runs with no patient, and patient-specific sending (email, SMS, filing to
# Best Practice) happens in Comms, where the patient is chosen.

# ── List / Search ─────────────────────────────────────────────────────────────

@bp.get('/')
@login_required
def index():
    filter_key = request.args.get('filter', '').strip() or None
    docs = DocLibraryService.list_documents_filtered(current_user, filter_key)
    lib_pipeline_id = DocLibraryService.get_lib_pipeline_id()
    return render_template(
        'doc_library/index.html',
        docs=docs,
        lib_pipeline_id=lib_pipeline_id,
        patient=None,
        patient_id=None,
        current_patient_id=None,
        active_filter=filter_key or '',
    )


@bp.get('/search')
@login_required
def search():
    term       = request.args.get('q', '').strip()
    filter_key = request.args.get('filter', '').strip() or None
    if term:
        docs = DocLibraryService.search_documents_filtered(term, current_user, filter_key)
    else:
        docs = DocLibraryService.list_documents_filtered(current_user, filter_key)
    return render_template(
        'doc_library/partials/card_grid.html',
        docs=docs,
        patient_id=None,
        active_filter=filter_key or '',
    )


# ── Editor pages ──────────────────────────────────────────────────────────────

def _ai_models():
    from app.models.ai_provider import AIModel
    return (AIModel.query
            .filter_by(is_enabled=True, show_in_ai_assist=True, is_asr=False)
            .order_by(AIModel.display_name)
            .all())


def _lib_default_model(lib_pipeline_id):
    """Resolve the model pinned on the [LIB] pipeline's inference step, if any.

    Mirrors the same lookup used for clinical/partials/ai_assist_panel.html's
    per-pipeline model hint — a step without a pinned model_id falls back to
    the InferenceNode's SystemSetting default at run time, which isn't
    resolved here (matches the existing ai_assist_panel behaviour).
    """
    if not lib_pipeline_id:
        return None
    import json as _json
    from app.models.ai_provider import AIModel
    from app.models.pipeline import Pipeline
    pipeline = Pipeline.query.get(lib_pipeline_id)
    if not pipeline:
        return None
    for step in pipeline.steps:
        if step.node_type == 'inference':
            try:
                cfg = _json.loads(step.config_json or '{}')
            except ValueError:
                continue
            mid = cfg.get('model_id')
            if mid:
                m = AIModel.query.get(int(mid))
                if m and m.provider:
                    return {
                        'model_id': m.id,
                        'display_name': m.display_name or m.model_id,
                        'is_local': m.provider.is_local,
                    }
            break
    return None


@bp.get('/new')
@login_required
def editor_new():
    lib_pipeline_id = DocLibraryService.get_lib_pipeline_id()
    return render_template(
        'doc_library/editor.html',
        doc=None,
        lib_pipeline_id=lib_pipeline_id,
        patient_id=None,
        patient=None,
        current_patient_id=None,
        ai_models=_ai_models(),
        lib_default_model=_lib_default_model(lib_pipeline_id),
    )


@bp.get('/<int:doc_id>/edit')
@login_required
def editor_edit(doc_id: int):
    doc = DocLibraryService.get_document(doc_id, current_user)
    if not doc:
        abort(404)
    lib_pipeline_id = DocLibraryService.get_lib_pipeline_id()
    return render_template(
        'doc_library/editor.html',
        doc=doc,
        lib_pipeline_id=lib_pipeline_id,
        patient_id=None,
        patient=None,
        current_patient_id=None,
        ai_models=_ai_models(),
        lib_default_model=_lib_default_model(lib_pipeline_id),
    )


# ── Save / Save As ────────────────────────────────────────────────────────────

@bp.post('/save')
@login_required
def save_new():
    data = request.get_json(silent=True) or {}
    try:
        doc = DocLibraryService.create_document(data, current_user)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ok': True, 'doc_id': doc.id})


@bp.post('/<int:doc_id>/save')
@login_required
def save_existing(doc_id: int):
    data = request.get_json(silent=True) or {}
    doc, _error = DocLibraryService.update_document(doc_id, data, current_user)
    if doc is None:
        return jsonify({'error': 'Document not found or access denied.'}), 404
    return jsonify({'ok': True, 'doc_id': doc.id})


@bp.post('/<int:doc_id>/save-as')
@login_required
def save_as(doc_id: int):
    data = request.get_json(silent=True) or {}
    doc = DocLibraryService.clone_document(doc_id, data, current_user)
    if doc is None:
        return jsonify({'error': 'Source document not found.'}), 404
    return jsonify({'ok': True, 'doc_id': doc.id})


# ── Delete / Hide ─────────────────────────────────────────────────────────────

@bp.post('/<int:doc_id>/delete')
@login_required
def delete(doc_id: int):
    ok = DocLibraryService.delete_document(doc_id, current_user)
    if not ok:
        return jsonify({'error': 'Delete failed — document not found or access denied.'}), 403
    return jsonify({'ok': True})


@bp.post('/<int:doc_id>/hide')
@login_required
def hide(doc_id: int):
    hidden = DocLibraryService.toggle_hide(doc_id, current_user)
    return jsonify({'ok': True, 'hidden': hidden})


# ── Render (Raw → sanitized HTML) ────────────────────────────────────────────

@bp.post('/render-markdown')
@login_required
def render_markdown():
    """Markdown/plain-text -> sanitized HTML. Used by Print and the Rendered tab
    (for non-HTML-document content)."""
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    from app.services.email_body_renderer import render
    result = render(text)
    return jsonify({'html': result.html})
