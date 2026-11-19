import math
import time

from flask import current_app, render_template, render_template_string, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import or_
from . import bp
from app.extensions import db
from app.models.data_bundle import DataBundle, BundleBlock
from app.models.sql_query import SQLQuery


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask_login import current_user
        if not current_user.is_authenticated or not current_user.has_level(7):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


@bp.get('/')
@login_required
@_require_admin
def dashboard():
    return render_template('admin/dashboard.html')


# ── Query Manager ─────────────────────────────────────────────────────────────

_APP_ENABLED_LIMIT = 50  # max queries flagged is_app_enabled simultaneously


@bp.get('/query-manager')
@login_required
@_require_admin
def query_manager():
    queries = SQLQuery.query.order_by(SQLQuery.name).all()
    enabled_count = SQLQuery.query.filter_by(is_app_enabled=True).count()
    return render_template('admin/query_manager.html',
                           queries=queries,
                           enabled_count=enabled_count,
                           app_limit=_APP_ENABLED_LIMIT)


@bp.get('/query-manager/search')
@login_required
@_require_admin
def query_search():
    q = request.args.get('q', '').strip()
    if q:
        queries = SQLQuery.query.filter(
            or_(SQLQuery.name.ilike(f'%{q}%'), SQLQuery.sql_text.ilike(f'%{q}%'))
        ).order_by(SQLQuery.name).all()
    else:
        queries = SQLQuery.query.order_by(SQLQuery.name).all()
    enabled_count = SQLQuery.query.filter_by(is_app_enabled=True).count()
    return render_template('admin/partials/query_list.html',
                           queries=queries,
                           enabled_count=enabled_count,
                           app_limit=_APP_ENABLED_LIMIT)


@bp.post('/query-manager/new')
@login_required
@_require_admin
def query_new():
    base = 'New Query'
    name = base
    n = 1
    while SQLQuery.query.filter_by(name=name).first():
        name = f'{base} {n}'
        n += 1
    q = SQLQuery(name=name, database_target='bpsdb', sql_text='SELECT ')
    db.session.add(q)
    db.session.commit()
    return redirect(url_for('admin.query_edit', query_id=q.id))


@bp.get('/query-manager/edit/<int:query_id>')
@login_required
@_require_admin
def query_edit(query_id: int):
    from app.utils.sql_utils import extract_sql_parameters, extract_system_params_used
    q = SQLQuery.query.get_or_404(query_id)
    return render_template('admin/query_editor.html',
                           query=q,
                           parameters=extract_sql_parameters(q.sql_text),
                           system_params_used=extract_system_params_used(q.sql_text),
                           enabled_count=SQLQuery.query.filter_by(is_app_enabled=True).count(),
                           app_limit=_APP_ENABLED_LIMIT)


@bp.post('/query-manager/save/<int:query_id>')
@login_required
@_require_admin
def query_save(query_id: int):
    q = SQLQuery.query.get_or_404(query_id)
    q.name            = request.form.get('name', q.name).strip() or q.name
    q.description     = request.form.get('description', q.description)
    q.database_target = request.form.get('database_target', q.database_target)
    q.sql_text        = request.form.get('sql_text', q.sql_text)
    q.app_row_limit   = int(request.form.get('app_row_limit', q.app_row_limit) or 200)
    db.session.commit()
    return '<div class="alert alert-success" style="margin:0;">Saved.</div>'


@bp.post('/query-manager/parse-params')
@login_required
@_require_admin
def query_parse_params():
    from app.utils.sql_utils import extract_sql_parameters, extract_system_params_used
    sql_text = request.form.get('sql_text', '')
    return render_template('admin/partials/query_params.html',
                           parameters=extract_sql_parameters(sql_text),
                           system_params_used=extract_system_params_used(sql_text))


@bp.post('/query-manager/execute/<int:query_id>')
@login_required
@_require_admin
def query_execute(query_id: int):
    from flask_login import current_user
    from app.utils.sql_utils import build_system_params, execute_sql_query

    q        = SQLQuery.query.get_or_404(query_id)
    sql_text = request.form.get('sql_text', q.sql_text)
    # Build params dict — system params first, then form overrides
    params = build_system_params(
        patient_id=request.form.get('current_patient_id') or request.form.get('vBPId'),
        user_id=current_user.id,
    )
    for key, value in request.form.items():
        if key.startswith('param_'):
            params[key[6:]] = value    # strip 'param_' prefix

    # Use a temporary SQLQuery-like object with the (possibly unsaved) SQL
    from types import SimpleNamespace
    tmp = SimpleNamespace(database_target=q.database_target, sql_text=sql_text)

    try:
        t0      = time.time()
        rows    = execute_sql_query(tmp, extra_params=params)
        elapsed = (time.time() - t0) * 1000
        columns = list(rows[0].keys()) if rows else []
        return render_template('admin/partials/query_results.html',
                               columns=columns, results=rows,
                               count=len(rows), elapsed=elapsed)
    except Exception as exc:
        return f'<div class="alert alert-danger"><b>Execution error:</b> {exc}</div>'


@bp.post('/query-manager/toggle-app/<int:query_id>')
@login_required
@_require_admin
def query_toggle_app(query_id: int):
    q = SQLQuery.query.get_or_404(query_id)
    if not q.is_app_enabled:
        # Enforce limit
        enabled = SQLQuery.query.filter_by(is_app_enabled=True).count()
        if enabled >= _APP_ENABLED_LIMIT:
            return jsonify({'error': f'Maximum {_APP_ENABLED_LIMIT} app-enabled queries reached.'}), 400
    q.is_app_enabled = not q.is_app_enabled
    db.session.commit()
    return jsonify({'enabled': q.is_app_enabled,
                    'enabled_count': SQLQuery.query.filter_by(is_app_enabled=True).count(),
                    'app_limit': _APP_ENABLED_LIMIT})


@bp.post('/query-manager/delete/<int:query_id>')
@login_required
@_require_admin
def query_delete(query_id: int):
    q = SQLQuery.query.get_or_404(query_id)
    db.session.delete(q)
    db.session.commit()
    return redirect(url_for('admin.query_manager'))


# ── Mapping tables ────────────────────────────────────────────────────────────

@bp.get('/mappings')
@login_required
@_require_admin
def mappings():
    from app.services import mapping_service as ms
    tables = ms.list_tables()
    return render_template('admin/mappings.html', tables=tables)


@bp.get('/mappings/<name>/grid')
@login_required
@_require_admin
def mapping_grid(name):
    from app.services import mapping_service as ms
    try:
        mt = ms._validate_table(name)
        if not ms.physical_table_exists(name):
            return render_template_string(
                '<div style="padding:1rem;">'
                '<div class="alert alert-warning" style="margin-bottom:0.75rem;">'
                '<strong>Physical table missing:</strong> '
                '<code>{{ mt.physical_table }}</code> does not exist in the database. '
                'The registry entry is intact; recreating will produce an empty table.'
                '</div>'
                '<form method="post" action="{{ url_for(\'admin.mapping_recreate\', name=mt.name) }}">'
                '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'
                '<button type="submit" class="btn btn-sm btn-warning">'
                'Recreate Empty Table</button>'
                '</form>'
                '</div>',
                mt=mt,
            )
        schema = ms.get_schema(name)
        page     = max(1, int(request.args.get('page', 1)))
        per_page = int(request.args.get('per_page', 50))
        sort_col = request.args.get('sort_col') or None
        sort_dir = request.args.get('sort_dir', 'asc')
        rows, total = ms.get_rows(name, page, per_page, sort_col, sort_dir)
        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        pages = ms.page_range(page, total_pages)
        return render_template('admin/partials/mapping_grid.html',
                               mt=mt, schema=schema, rows=rows,
                               page=page, per_page=per_page, total=total,
                               total_pages=total_pages, pages=pages,
                               sort_col=sort_col, sort_dir=sort_dir)
    except ValueError as exc:
        return f'<div class="alert alert-danger">{exc}</div>'


@bp.post('/mappings/create')
@login_required
@_require_admin
def mapping_create():
    from app.services import mapping_service as ms
    name  = (request.form.get('name') or '').strip().lower()
    label = (request.form.get('label') or '').strip()
    desc  = (request.form.get('description') or '').strip()
    try:
        ms.create_table(name, label, desc)
        flash(f'Mapping table "{label or name}" created.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('admin.mappings'))


@bp.post('/mappings/<name>/drop')
@login_required
@_require_admin
def mapping_drop(name):
    from app.services import mapping_service as ms
    try:
        ms.drop_table(name)
        flash(f'Mapping table "{name}" dropped.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('admin.mappings'))


@bp.post('/mappings/<name>/recreate')
@login_required
@_require_admin
def mapping_recreate(name):
    from app.services import mapping_service as ms
    try:
        ms.recreate_physical_table(name)
        flash(f'Physical table for "{name}" recreated successfully.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('admin.mappings') + f'?table={name}')


@bp.post('/mappings/<name>/settings')
@login_required
@_require_admin
def mapping_settings(name):
    from app.services import mapping_service as ms
    ttl_raw = request.form.get('cache_ttl_seconds', '').strip()
    try:
        ttl = int(ttl_raw) if ttl_raw else None
    except ValueError:
        ttl = None
    try:
        ms.update_settings(
            name,
            label=request.form.get('label'),
            description=request.form.get('description'),
            refresh_url=request.form.get('refresh_url'),
            cache_ttl_seconds=ttl,
        )
        return '<div class="alert alert-success" style="margin:0;">Settings saved.</div>'
    except ValueError as exc:
        return f'<div class="alert alert-danger" style="margin:0;">{exc}</div>'


@bp.post('/mappings/<name>/cell/<int:row_id>/<col>')
@login_required
@_require_admin
def mapping_cell(name, row_id, col):
    from app.services import mapping_service as ms
    value = request.form.get('value', '')
    try:
        ms.cell_update(name, row_id, col, value)
        return '', 204
    except ValueError as exc:
        return str(exc), 400


@bp.post('/mappings/<name>/row/add')
@login_required
@_require_admin
def mapping_row_add(name):
    import math
    from app.services import mapping_service as ms
    data = {k: v for k, v in request.form.items()
            if k not in ('csrf_token', 'sort_col', 'sort_dir', 'per_page')}
    per_page = int(request.form.get('per_page', 50))
    sort_col = request.form.get('sort_col') or None
    sort_dir = request.form.get('sort_dir', 'asc')
    try:
        ms.row_insert(name, data)
        mt     = ms._validate_table(name)
        schema = ms.get_schema(name)
        total_pages = max(1, math.ceil(mt.row_count / per_page))
        rows, total = ms.get_rows(name, total_pages, per_page, sort_col, sort_dir)
        pages = ms.page_range(total_pages, total_pages)
        return render_template('admin/partials/mapping_grid.html',
                               mt=mt, schema=schema, rows=rows,
                               page=total_pages, per_page=per_page, total=total,
                               total_pages=total_pages, pages=pages,
                               sort_col=sort_col, sort_dir=sort_dir)
    except ValueError as exc:
        return f'<div class="alert alert-danger">{exc}</div>'


@bp.post('/mappings/<name>/row/<int:row_id>/delete')
@login_required
@_require_admin
def mapping_row_delete(name, row_id):
    from app.services import mapping_service as ms
    try:
        ms.row_delete(name, row_id)
        return '', 200
    except ValueError as exc:
        return str(exc), 400


@bp.post('/mappings/<name>/column/add')
@login_required
@_require_admin
def mapping_column_add(name):
    import math
    from app.services import mapping_service as ms
    col_name = (request.form.get('column_name') or '').strip().lower()
    col_type = (request.form.get('column_type') or 'TEXT').strip().upper()
    per_page = int(request.form.get('per_page', 50))
    sort_col = request.form.get('sort_col') or None
    sort_dir = request.form.get('sort_dir', 'asc')
    try:
        ms.column_add(name, col_name, col_type)
        mt     = ms._validate_table(name)
        schema = ms.get_schema(name)
        rows, total = ms.get_rows(name, 1, per_page, sort_col, sort_dir)
        total_pages = max(1, math.ceil(total / per_page))
        pages = ms.page_range(1, total_pages)
        return render_template('admin/partials/mapping_grid.html',
                               mt=mt, schema=schema, rows=rows,
                               page=1, per_page=per_page, total=total,
                               total_pages=total_pages, pages=pages,
                               sort_col=sort_col, sort_dir=sort_dir)
    except ValueError as exc:
        return f'<div class="alert alert-danger">{exc}</div>'


@bp.post('/mappings/<name>/column/<col>/retype')
@login_required
@_require_admin
def mapping_column_retype(name, col):
    from app.services import mapping_service as ms
    new_type = (request.form.get('new_type') or '').strip().upper()
    try:
        ms.column_retype(name, col, new_type)
        return jsonify({'ok': True})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@bp.post('/mappings/<name>/import-csv')
@login_required
@_require_admin
def mapping_import_csv(name):
    from app.services import mapping_service as ms
    f = request.files.get('csv_file')
    if not f or not f.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('admin.mappings'))
    replace = request.form.get('replace') == '1'
    try:
        result = ms.csv_import(name, f.stream, replace)
        errs = result.get('errors', [])
        msg = f'{result["count"]} rows imported.'
        if errs:
            msg += f' {len(errs)} error(s): ' + '; '.join(errs[:3])
        flash(msg, 'success' if not errs else 'warning')
    except Exception as exc:
        flash(f'Import failed: {exc}', 'danger')
    return redirect(url_for('admin.mappings') + f'?table={name}')


@bp.get('/mappings/<name>/export-csv')
@login_required
@_require_admin
def mapping_export_csv(name):
    from flask import Response
    from app.services import mapping_service as ms
    try:
        csv_data = ms.csv_export(name)
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{name}.csv"'},
        )
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('admin.mappings'))


@bp.post('/mappings/<name>/refresh')
@login_required
@_require_admin
def mapping_refresh(name):
    from app.services import mapping_service as ms
    try:
        result = ms.api_refresh(name)
        if result['ok']:
            mt = ms._validate_table(name)
            result['is_stale'] = mt.is_stale
            result['freshness_label'] = mt.freshness_label
            result['row_count'] = mt.row_count
        return jsonify(result)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)})


# ── Bundle management ─────────────────────────────────────────────────────────

@bp.get('/bundles')
@login_required
@_require_admin
def bundles():
    all_bundles = DataBundle.query.order_by(DataBundle.name).all()
    return render_template('admin/bundles.html', bundles=all_bundles)


@bp.get('/bundles/new')
@login_required
@_require_admin
def bundle_new():
    from app.services.patient_json_service import BLOCK_META
    return render_template('admin/bundle_editor.html',
                           bundle=None,
                           block_meta=BLOCK_META,
                           current_blocks=[])


@bp.post('/bundles/new')
@login_required
@_require_admin
def bundle_new_post():
    name        = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    sources     = request.form.getlist('block_source[]')
    labels      = request.form.getlist('block_label[]')

    if not name:
        flash('Bundle name is required.', 'warning')
        return redirect(url_for('admin.bundle_new'))

    if DataBundle.query.filter_by(name=name).first():
        flash(f'A bundle named "{name}" already exists.', 'warning')
        return redirect(url_for('admin.bundle_new'))

    bundle = DataBundle(name=name, description=description, is_active=True)
    db.session.add(bundle)
    db.session.flush()

    for i, src in enumerate(sources):
        if src.strip():
            db.session.add(BundleBlock(
                bundle_id=bundle.id,
                block_order=i,
                block_source=src.strip(),
                label=labels[i].strip() if i < len(labels) and labels[i].strip() else None,
            ))

    db.session.commit()
    flash(f'Bundle "{name}" created.', 'success')
    return redirect(url_for('admin.bundles'))


@bp.get('/bundles/<int:bundle_id>/edit')
@login_required
@_require_admin
def bundle_edit(bundle_id: int):
    from app.services.patient_json_service import BLOCK_META
    bundle = DataBundle.query.get_or_404(bundle_id)
    current_blocks = list(bundle.blocks)
    return render_template('admin/bundle_editor.html',
                           bundle=bundle,
                           block_meta=BLOCK_META,
                           current_blocks=current_blocks)


@bp.post('/bundles/<int:bundle_id>/edit')
@login_required
@_require_admin
def bundle_edit_post(bundle_id: int):
    bundle      = DataBundle.query.get_or_404(bundle_id)
    name        = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    sources     = request.form.getlist('block_source[]')
    labels      = request.form.getlist('block_label[]')
    is_active   = request.form.get('is_active') == '1'

    if not name:
        flash('Bundle name is required.', 'warning')
        return redirect(url_for('admin.bundle_edit', bundle_id=bundle_id))

    bundle.name        = name
    bundle.description = description
    bundle.is_active   = is_active

    # Replace all blocks
    for bb in list(bundle.blocks):
        db.session.delete(bb)
    db.session.flush()

    for i, src in enumerate(sources):
        if src.strip():
            db.session.add(BundleBlock(
                bundle_id=bundle.id,
                block_order=i,
                block_source=src.strip(),
                label=labels[i].strip() if i < len(labels) and labels[i].strip() else None,
            ))

    db.session.commit()
    flash(f'Bundle "{name}" saved.', 'success')
    return redirect(url_for('admin.bundles'))


@bp.post('/bundles/<int:bundle_id>/delete')
@login_required
@_require_admin
def bundle_delete(bundle_id: int):
    bundle = DataBundle.query.get_or_404(bundle_id)
    name   = bundle.name
    db.session.delete(bundle)
    db.session.commit()
    flash(f'Bundle "{name}" deleted.', 'success')
    return redirect(url_for('admin.bundles'))


@bp.post('/bundles/<int:bundle_id>/toggle')
@login_required
@_require_admin
def bundle_toggle(bundle_id: int):
    bundle = DataBundle.query.get_or_404(bundle_id)
    bundle.is_active = not bundle.is_active
    db.session.commit()
    return jsonify({'active': bundle.is_active})


@bp.get('/bundles/<int:bundle_id>/test')
@login_required
@_require_admin
def bundle_test(bundle_id: int):
    bundle = DataBundle.query.get_or_404(bundle_id)
    return render_template('admin/bundle_test.html', bundle=bundle)


@bp.get('/bundles/<int:bundle_id>/test/run')
@login_required
@_require_admin
def bundle_test_run(bundle_id: int):
    """HTMX: run bundle against a patient and return rendered fragment."""
    from app.services.bundle_render_service import BundleRenderService

    bundle     = DataBundle.query.get_or_404(bundle_id)
    patient_id = request.args.get('patient_id', type=int)
    fmt        = request.args.get('fmt', 'text')
    deidentify = request.args.get('deidentify', '0') == '1'

    if not patient_id:
        return '<p style="color:var(--danger);">Enter a patient ID to test.</p>'

    try:
        rendered = BundleRenderService().render(bundle.name, patient_id,
                                                fmt=fmt, deidentify=deidentify)
    except ValueError as exc:
        return f'<p style="color:var(--danger);">{exc}</p>'
    except Exception as exc:
        current_app.logger.error('bundle_test_run(%d, %d): %s', bundle_id, patient_id, exc)
        return '<p style="color:var(--danger);">Error retrieving data — check BPSDB connection.</p>'

    return render_template('clinical/partials/pj_block_content.html',
                           rendered=rendered, fmt=fmt)


# ── Privacy-check hits → future redactions (ADR-049) ────────────────────────────
# Administrators only (security level 9), like the privacy card that links here.

def _require_privacy_admin():
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        from flask import abort
        abort(403)


@bp.get('/privacy-hits/<int:run_id>')
@login_required
def privacy_hits(run_id: int):
    _require_privacy_admin()
    from app.services import privacy_hits_service
    data = privacy_hits_service.load(run_id)
    if data is None:
        from flask import abort
        abort(404)
    # With the Privacy Review page on (ADR-120): the verdict form, and previous / next
    # within the list's filters when the page was opened from it.
    from app.services import privacy_review_service as review_svc
    review = None
    if review_svc.enabled():
        filters = review_svc.parse_filters(request.args) if request.args.get('list') == '1' else None
        review = {'saved': review_svc.get(run_id), 'filters': filters,
                  'args': {'list': '1', **review_svc.query_args(filters)} if filters else {},
                  'around': review_svc.neighbours(run_id, filters) if filters else None,
                  'dispositions': review_svc.DISPOSITION_LABELS, 'severities': review_svc.SEVERITY_LABELS}
    return render_template('admin/privacy_hits.html', labels=privacy_hits_service.ALWAYS_LABELS,
                           review=review, type_label=review_svc.type_label,
                           tier_labels=review_svc.TIER_LABELS, **data)


@bp.post('/privacy-hits/<int:run_id>/review')
@login_required
def privacy_review_save(run_id: int):
    """Record the verdict on a run's hits (ADR-120)."""
    _require_privacy_admin()
    from flask import abort
    from flask_login import current_user
    from app.services import privacy_review_service as svc
    if not svc.enabled():
        abort(404)
    result = svc.save(run_id, request.form.get('disposition', ''), request.form.get('severity'),
                      request.form.get('comment'), current_user.id)
    flash(result['message'], 'success' if result['ok'] else 'danger')
    args = {'list': '1', **svc.query_args(svc.parse_filters(request.args))} \
        if request.args.get('list') == '1' else {}
    return redirect(url_for('admin.privacy_hits', run_id=run_id, **args) + '#review')


# ── Privacy Review: the check's findings across runs (ADR-120) ───────────────

@bp.get('/privacy-review')
@login_required
def privacy_review():
    _require_privacy_admin()
    from flask import abort
    from app.services import privacy_review_service as svc
    if not svc.enabled():
        abort(404)
    filters = svc.parse_filters(request.args)
    return render_template('admin/privacy_review.html', filters=filters,
                           args={'list': '1', **svc.query_args(filters)},
                           tier_labels=svc.TIER_LABELS, dispositions=svc.DISPOSITION_LABELS,
                           severities=svc.SEVERITY_LABELS, **svc.find(filters))


@bp.get('/privacy-review/latest')
@login_required
def privacy_review_latest():
    """The newest run in the list as filtered."""
    _require_privacy_admin()
    from flask import abort
    from app.services import privacy_review_service as svc
    if not svc.enabled():
        abort(404)
    filters = svc.parse_filters(request.args)
    args = {'list': '1', **svc.query_args(filters)}
    run_id = svc.latest(filters)
    if run_id is None:
        flash('No run matches those filters.', 'warning')
        return redirect(url_for('admin.privacy_review', **args))
    return redirect(url_for('admin.privacy_hits', run_id=run_id, **args))


@bp.post('/privacy-hits/<int:run_id>/add')
@login_required
def privacy_hits_add(run_id: int):
    _require_privacy_admin()
    from flask_login import current_user
    from app.services import privacy_hits_service
    index = request.form.get('index', type=int)
    if index is None:
        return jsonify({'ok': False, 'message': 'No hit chosen.'}), 400
    user = current_user.username
    if request.form.get('list') == 'name_variant':
        result = privacy_hits_service.add_name_variant(
            run_id, index, request.form.get('name', ''), user,
            confirmed=request.form.get('confirmed') == '1')
    elif request.form.get('list') == 'always_redact':
        result = privacy_hits_service.add_always_redact(run_id, index, request.form.get('label', ''), user)
    else:
        return jsonify({'ok': False, 'message': 'Unknown list.'}), 400
    return jsonify(result)


@bp.post('/privacy-hits/<int:run_id>/report/<int:report_id>')
@login_required
def privacy_report_handle(run_id: int, report_id: int):
    """A user's report (ADR-115): add it to a list, or dismiss it."""
    _require_privacy_admin()
    from flask_login import current_user
    from app.services import privacy_reports_service
    result = privacy_reports_service.handle(
        run_id, report_id, request.form.get('action', ''), current_user,
        label=request.form.get('label', ''), name=request.form.get('name', ''),
        confirmed=request.form.get('confirmed') == '1')
    return jsonify(result)


# ── Observation anomalies ─────────────────────────────────────────────────────

@bp.get('/observation-anomalies')
@login_required
@_require_admin
def observation_anomalies():
    """Non-numeric values in the measurements BP doesn't check at entry."""
    import pyodbc
    from app.services import observation_anomaly_service
    try:
        data = observation_anomaly_service.load()
        data.update(observation_anomaly_service.load_misfiled())
        error = None
    except pyodbc.Error as exc:                   # BPSDB unreachable: show, don't 500
        from flask import current_app
        current_app.logger.error('observation anomalies: %s', exc)
        data, error = {'rows': [], 'counts': {}, 'patients': 0, 'placeholders': 0,
                       'misfiled': [], 'misfiled_patients': 0, 'misfiled_imported': 0}, str(exc)
    return render_template('admin/observation_anomalies.html', error=error, **data)


# ── Flagged AI requests (ADR-103) ─────────────────────────────────────────────

@bp.get('/flagged-ai')
@login_required
@_require_admin
def flagged_ai():
    """AI requests the scope checks marked, by user, date and workflow, for the practice's oversight."""
    from datetime import date
    from app.services import flagged_requests_service as svc

    def _day(name):
        try:
            return date.fromisoformat(request.args.get(name, ''))
        except ValueError:
            return None

    def _int(name):
        v = request.args.get(name, '')
        return int(v) if v.isdigit() else None

    kind = request.args.get('kind', 'any')
    filters = {'user_id': _int('user'), 'pipeline_id': _int('workflow'),
               'date_from': _day('from'), 'date_to': _day('to'),
               'kind': kind if kind in ('any', 'request', 'reply', 'legality', 'reported') else 'any'}
    data = svc.find(**filters)
    return render_template('admin/flagged_ai.html', filters=filters, **data)


@bp.get('/flagged-ai/<int:run_id>')
@login_required
@_require_admin
def flagged_ai_detail(run_id: int):
    from flask import abort
    from app.services import flagged_requests_service as svc
    d = svc.detail(run_id)
    if not d:
        abort(404)
    return render_template('admin/partials/flagged_ai_detail.html', d=d)
