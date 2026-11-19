import io

from flask import abort, render_template, request, send_file, current_app
from flask_login import current_user, login_required
from . import bp
from app.services.inbox_service import InboxService
from app.services.clinical_service import ClinicalService
from app.services import document_service


@bp.get('/')
@login_required
def index():
    default_provider = str(current_user.bpsdb_user_id or 'all') \
        if hasattr(current_user, 'bpsdb_user_id') else 'all'
    provider_id = request.args.get('provider_id', default_provider)

    try:
        providers = InboxService.get_providers()
    except Exception as e:
        current_app.logger.error('inbox.get_providers: %s', e)
        providers = []

    try:
        items = InboxService.get_list(provider_id)
    except Exception as e:
        current_app.logger.error('inbox.get_list(%s): %s', provider_id, e)
        items = []

    return render_template(
        'inbox/inbox.html',
        items=items,
        providers=providers,
        provider_id=provider_id,
    )


@bp.get('/demographics/<int:patient_id>')
@login_required
def demographics(patient_id: int):
    try:
        patient = ClinicalService.get_patient_demographics(patient_id)
        if patient:
            patient['patient_id'] = patient_id
    except Exception as e:
        current_app.logger.error('inbox.demographics(%d): %s', patient_id, e)
        patient = None

    return render_template('inbox/partials/demographics_card.html', patient=patient)


@bp.get('/report/<int:report_id>')
@login_required
def report_content(report_id: int):
    """Serve an inbox report as an iframe-embeddable page.

    INCOMINGREPORTS stores RTF text in REPORTHEADER/REPORTBODY (both may be
    ZIP-compressed).  Binary content (PDF/HTML/image) from BPSDOCUMENTSINBOX
    is fetched via the LEFT JOIN in viewer_path_inbox.sql and passed as the
    'binary' argument to render_path_report — which will prefer it if it is a
    PDF or image (matching Gen4 behaviour).
    """
    try:
        report = InboxService.get_report(report_id)
    except Exception as e:
        current_app.logger.error('inbox.report_content(%d): %s', report_id, e)
        report = None

    if not report:
        return _unavailable('Report not found.'), 404, {'Content-Type': 'text/html'}

    # CONTENT from BPSDOCUMENTSINBOX.dbo.INCOMINGREPORTPAGES (may be None)
    content = report.get('CONTENT')
    binary  = bytes(content) if content else None

    result = document_service.render_path_report(
        report.get('REPORTHEADER'),
        report.get('REPORTBODY'),
        binary=binary,
    )

    if result.render_type == 'html':
        return result.content, 200, {'Content-Type': result.mimetype}
    return send_file(io.BytesIO(result.content), mimetype=result.mimetype, as_attachment=False)


@bp.get('/outliers')
@login_required
def outliers():
    """Inbox results outside range, as the laboratory reports them (ADR-097)."""
    from app.services.inbox_outlier_service import analyse

    flagged = analyse(_inbox_outlier_rows(0))
    stats = {
        'total':    len(flagged),
        'patients': len({r['INTERNALID'] for r in flagged}),
    }
    return render_template('inbox/inbox_outliers.html', rows=flagged, stats=stats)


@bp.get('/outliers/patient/<int:patient_id>')
@login_required
def outliers_patient(patient_id: int):
    """One patient's results outside range, each as a chart of every result for that
    test (ADR-097): the clicked test first, then the others outside range in the
    inbox, then tests not in the inbox whose last result was outside range."""
    import json as _json
    from app.services.chart_service import ChartService, DecimalEncoder
    from app.services.inbox_outlier_service import patient_results

    patient = ClinicalService.get_patient_demographics(patient_id)
    if not patient:
        abort(404)
    patient['patient_id'] = patient_id
    loinc = request.args.get('loinc', '').strip() or None

    history = []
    try:
        history = ChartService(current_app.config['BPSDB_URI']).get_result_history(patient_id)
    except Exception as exc:
        current_app.logger.warning('inbox.outliers_patient history failed: %s', exc)
    charts = patient_results(patient_id, _inbox_outlier_rows(patient_id), history, loinc)

    def chart_json(c):
        scale = {'autoScale': True}
        if c['low'] is not None:
            scale['normalMin'] = c['low']
        if c['high'] is not None:
            scale['normalMax'] = c['high']
        return {'title': c['name'], 'units': c['units'], 'subtitle': '',
                'data': c['points'], 'scale': scale}

    chart_data = {f'{group}-{i}': chart_json(c)
                  for group, items in charts.items() for i, c in enumerate(items)}
    return render_template('inbox/outliers_patient.html', patient=patient, patient_id=patient_id,
                           charts=charts, clicked=loinc,
                           chart_data_json=_json.dumps(chart_data, cls=DecimalEncoder))


def _inbox_outlier_rows(patient_id: int) -> list:
    """The inbox_outliers rows for one patient, or for everyone with 0."""
    from app.sql.query_loader import load_query, ReadOnlySession
    try:
        with ReadOnlySession(current_app.config['BPSDB_URI']) as sess:
            return sess.execute(load_query('inbox_outliers'), [patient_id, patient_id])
    except Exception as exc:
        current_app.logger.warning('inbox.outliers query failed: %s', exc)
        return []


def _unavailable(msg: str = 'Document temporarily unavailable.') -> str:
    return (
        '<!DOCTYPE html><html><body style="font-family:sans-serif;padding:1.25rem;">'
        f'<p style="color:#888;">{msg}</p></body></html>'
    )
