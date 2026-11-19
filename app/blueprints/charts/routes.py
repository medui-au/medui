import json

from flask import abort, jsonify, render_template, request, url_for, current_app
from flask_login import current_user, login_required

from . import bp
from app.utils.access import ai_required


@bp.get('/scatter')
@login_required
def scatter():
    from app.services.scatter_service import EXPORT_LIMIT
    return render_template('charts/scatter.html', page_title='Patient Scatter',
                           export_limit=EXPORT_LIMIT)


@bp.get('/scatter/data')
@login_required
def scatter_data():
    from app.services.scatter_service import get_patient_data
    return jsonify(get_patient_data())


@bp.post('/scatter/refresh')
@login_required
def scatter_refresh():
    from app.services.scatter_service import bust_cache, get_patient_data
    bust_cache()
    get_patient_data()
    return '', 204


@bp.post('/scatter/export')
@login_required
def scatter_export():
    """Download the chart's patient list (ADR-147): at most EXPORT_LIMIT patients, values
    from the server's cohort, each download recorded as a usage task."""
    from datetime import datetime
    from flask import Response
    from app.services import scatter_service, usage_service

    data = request.get_json(silent=True) or {}
    fmt = data.get('format')
    x_col, y_col = data.get('x'), data.get('y')
    if fmt not in ('csv', 'md') or x_col not in scatter_service.COL_LABELS \
            or y_col not in scatter_service.COL_LABELS:
        return jsonify({'error': 'bad request'}), 400
    try:
        ids = [int(i) for i in data.get('ids') or []]
    except (TypeError, ValueError):
        return jsonify({'error': 'bad request'}), 400
    if not ids or len(ids) > scatter_service.EXPORT_LIMIT:
        return jsonify({'error': f'1 to {scatter_service.EXPORT_LIMIT} patients only'}), 400

    cohort = scatter_service.get_patient_data()
    rows = scatter_service.export_rows(cohort['patients'], ids, x_col, y_col)
    filters = str(data.get('filters') or '')[:500]
    stamp = datetime.now()
    heading = (f'Patient Scatter list, {len(rows)} patients, {stamp:%d %b %Y %H:%M}. '
               f'Filters: {filters or "none"}')

    usage_service.record_task(
        'patient_list.export', 'charts', user_id=current_user.id, patient_linked=True,
        workstation=request.remote_addr,
        detail={'count': len(rows), 'format': fmt, 'x': x_col, 'y': y_col, 'filters': filters})

    if fmt == 'csv':
        body, mimetype = scatter_service.to_csv(rows, heading), 'text/csv'
    else:
        body, mimetype = scatter_service.to_markdown(rows, heading), 'text/markdown'
    name = f'patient_list_{stamp:%Y%m%d_%H%M}.{fmt}'
    return Response(body, mimetype=mimetype,
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


@bp.get('/browse')
@login_required
def browse():
    from app.models.data_source import DataSource
    sources = (DataSource.query
               .filter_by(is_active=True)
               .order_by(DataSource.display_name)
               .all())
    return render_template('charts/browse.html',
                           page_title='Data Sources',
                           page_subtitle='Browse available data sources',
                           sources=sources)


@bp.get('/datasource/<int:source_id>')
@login_required
def datasource_view(source_id: int):
    from app.models.data_source import DataSource
    from app.services import datasource_service
    from app.models.pipeline import Pipeline, PipelineStatus

    source = DataSource.query.get_or_404(source_id)
    if not source.is_active:
        abort(404)

    result = datasource_service.fetch(source)

    chart_config = None
    if source.chart_config_json:
        try:
            chart_config = json.loads(source.chart_config_json)
        except (ValueError, TypeError):
            pass

    # AI analysis is for users who may run AI; no pipelines hides the tab.
    pipelines = (Pipeline.query
                 .filter_by(status=PipelineStatus.active)
                 .filter(Pipeline.name.ilike('%[DATA]%'))
                 .order_by(Pipeline.name)
                 .all()) if current_user.can_use_ai else []

    return render_template(
        'charts/datasource.html',
        page_title=source.display_name,
        page_subtitle=source.description or source.location_type_label,
        source=source,
        result=result,
        chart_config=chart_config,
        chart_config_json=source.chart_config_json or '',
        pipelines=pipelines,
        analyse_url=url_for('charts.datasource_analyse', source_id=source_id),
    )


@bp.post('/datasource/<int:source_id>/analyse')
@login_required
@ai_required
def datasource_analyse(source_id: int):
    """Run a [DATA] pipeline against this source's data. Returns run_id + stream_url."""
    from app.models.data_source import DataSource
    from app.services import datasource_service
    from app.services.pipeline.engine import PipelineEngine

    source = DataSource.query.get_or_404(source_id)
    data        = request.get_json(silent=True) or {}
    pipeline_id = data.get('pipeline_id')
    if not pipeline_id:
        return jsonify({'error': 'pipeline_id required'}), 400

    result = datasource_service.fetch(source)
    if result['error']:
        return jsonify({'error': result['error']}), 502

    csv_text = datasource_service.rows_to_csv_text(result)

    try:
        run_id = PipelineEngine.run(
            pipeline_id=int(pipeline_id),
            patient_id=None,
            user_id=current_user.id,
            input_data={
                'raw_data':   csv_text,
                'source_key': source.key,
                'row_count':  result['row_count'],
            },
            model_is_local=False,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error('datasource_analyse error source=%s: %s', source_id, exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({
        'run_id':     run_id,
        'stream_url': url_for('pipeline_run.run_stream', run_id=run_id),
    })
