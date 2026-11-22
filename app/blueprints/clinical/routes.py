import re as _re

from flask import render_template, request, abort, current_app, jsonify
from flask_login import login_required, current_user
from . import bp
from app.services.clinical_service import ClinicalService
from app.utils.access import ai_required


def _strip_rtf(text: str) -> str:
    """Strip RTF markup using striprtf; fall back to regex for non-RTF text."""
    if not text:
        return ''
    s = str(text)
    if s.strip().startswith('{\\rtf'):
        try:
            from striprtf.striprtf import rtf_to_text
            s = rtf_to_text(s)
            s = _re.sub(r'\n{3,}', '\n\n', s)
            return s.strip()
        except Exception:
            pass
    # Regex fallback
    s = _re.sub(r'\{\\[^}]*\}', '', s)
    s = _re.sub(r'\\[a-z]+\-?\d*\s?', '', s)
    s = _re.sub(r'[{}]', '', s)
    s = _re.sub(r'<[^>]+>', '', s)
    s = _re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def _fmt_start_time(seconds) -> str:
    """Convert BPSDB StartTime (seconds since midnight) to HH:MM string."""
    if not seconds:
        return ''
    try:
        s = int(seconds)
        return f'{s // 3600:02d}:{(s % 3600) // 60:02d}'
    except (ValueError, TypeError):
        return ''


@bp.get('/')
@login_required
def search():
    return render_template('clinical/search.html')


@bp.get('/search')
@login_required
def search_results():
    q = request.args.get('q', '').strip()
    if not q:
        return ''
    try:
        patients = ClinicalService.search_patients(q)
    except Exception as e:
        current_app.logger.error('BPSDB search error: %s', e)
        return '<tr><td colspan="4" class="search-empty">Could not connect to patient database.</td></tr>'
    # ?then=comms: choosing the patient for content handed to Comms (ADR-093).
    row_endpoint = _SEARCH_THEN.get(request.args.get('then', ''), 'clinical.patient')
    return render_template('clinical/_search_results.html', patients=patients,
                           row_endpoint=row_endpoint)


_SEARCH_THEN = {'comms': 'clinical_comms.patient_comms'}


@bp.get('/patient/<int:patient_id>')
@login_required
def patient(patient_id: int):
    try:
        demographics = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:
        current_app.logger.error('BPSDB demographics error for %d: %s', patient_id, e)
        demographics = None
    if not demographics:
        abort(404)
    return render_template('clinical/patient.html', patient=demographics)



@bp.get('/patient/<int:patient_id>/api/disease_profile')
@login_required
def api_disease_profile(patient_id: int):
    # The results badges are rules the viewing user chose to display (ADR-166).
    from app.services import egfr_criterion, hba1c_criterion, user_settings_service
    try:
        profile = ClinicalService.get_disease_profile(
            patient_id,
            show_hba1c_rule=bool(user_settings_service.get(current_user, hba1c_criterion.BADGE_PREF_KEY)),
            show_egfr_rule=bool(user_settings_service.get(current_user, egfr_criterion.BADGE_PREF_KEY)))
    except Exception as e:
        current_app.logger.error('disease_profile error for %d: %s', patient_id, e)
        profile = {}
    return render_template('clinical/_panels/disease_profile.html', profile=profile)


@bp.get('/patient/<int:patient_id>/api/history')
@login_required
def api_history(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'history')
    except Exception as e:
        current_app.logger.error('history error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/history.html', rows=rows)


@bp.get('/patient/<int:patient_id>/api/medications')
@login_required
def api_medications(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'medications')
    except Exception as e:
        current_app.logger.error('medications error for %d: %s', patient_id, e)
        rows = []
    is_admin = current_user.is_authenticated and current_user.has_level(7)
    mapped = {}
    if is_admin and rows:
        from app.services.drug_mapping_service import batch_status
        mapped = batch_status([r['PRODUCTID'] for r in rows if r.get('PRODUCTID')])
    return render_template('clinical/_sections/medications.html',
                           rows=rows, mapped_pids=mapped,
                           patient_id=patient_id, is_admin=is_admin)


@bp.get('/patient/<int:patient_id>/api/med-mapping/<int:product_id>')
@login_required
def med_mapping_popup(patient_id: int, product_id: int):
    if not current_user.has_level(7):
        abort(403)
    from app.services.drug_mapping_service import get_mapping
    existing   = get_mapping(product_id)
    brand_name = request.args.get('name', '')
    # If there's an approved mapping with no ATC code, try to fetch one via
    # the generic name — this succeeds where the original brand lookup missed it.
    suggested_atc = None
    if existing and not existing.atc_code:
        from app.services.pbs_api_service import pbs_atc_by_generic
        suggested_atc = pbs_atc_by_generic(existing.generic_name, mims_name=brand_name)
    return render_template(
        'clinical/_sections/drug_mapping_popup.html',
        patient_id=patient_id, product_id=product_id,
        brand_name=brand_name, existing=existing,
        suggested_atc=suggested_atc,
    )


@bp.get('/api/pbs-suggest')
@login_required
def pbs_suggest():
    if not current_user.has_level(7):
        abort(403)
    from app.services.pbs_api_service import pbs_suggest as _suggest
    brand = request.args.get('brand', '')
    return jsonify(_suggest(brand))


@bp.post('/patient/<int:patient_id>/api/med-mapping')
@login_required
def med_mapping_approve(patient_id: int):
    if not current_user.has_level(7):
        abort(403)
    from app.services.drug_mapping_service import approve
    product_id = request.form.get('product_id', type=int)
    brand      = request.form.get('brand_name', '').strip()
    generic    = request.form.get('generic_name', '').strip()
    atc        = request.form.get('atc_code', '').strip()
    if product_id and generic:
        approve(product_id, brand, generic, atc, current_user.id)
    return render_template('clinical/_sections/drug_mapping_saved.html',
                           brand_name=brand, generic_name=generic)


@bp.get('/patient/<int:patient_id>/api/immunizations')
@login_required
def api_immunizations(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'immunisations')
    except Exception as e:
        current_app.logger.error('immunizations error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Date', 'VacDate'), ('Vaccine', 'VACCINENAME'), ('Seq', 'SEQUENCE')],
                           empty_msg='No immunizations recorded.')


@bp.get('/patient/<int:patient_id>/api/immunizations/eligibility-flags')
@login_required
def api_immunizations_eligibility_flags(patient_id: int):
    from app.services.patient_json_service import PatientJsonService
    try:
        rows = PatientJsonService().get_atomic_block('vaccine_eligibility', patient_id)
        due = [r for r in rows if r.get('eligible_for_funded_dose') and r.get('dose_due_now')]
    except Exception as e:
        current_app.logger.error('immunizations eligibility flags error for %d: %s', patient_id, e)
        due = []
    from app.services.vaccine_eligibility_service import SCHEDULE_TEXT
    return render_template('clinical/_panels/immunization_eligibility_flags.html', vaccines=due,
                           schedule=SCHEDULE_TEXT)


@bp.get('/patient/<int:patient_id>/api/allergies')
@login_required
def api_allergies(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'allergies')
    except Exception as e:
        current_app.logger.error('allergies error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Item', 'ItemName'), ('Reaction', 'Reaction'), ('Severity', 'Severity')],
                           empty_msg='No allergies recorded.')


@bp.get('/patient/<int:patient_id>/api/family_history')
@login_required
def api_family_history(patient_id: int):
    try:
        fh_data = ClinicalService.get_family_history(patient_id)
    except Exception as e:
        current_app.logger.error('family_history error for %d: %s', patient_id, e)
        fh_data = {'detail': [], 'overview': None}
    return render_template('clinical/_panels/family_history.html', data=fh_data)


@bp.get('/patient/<int:patient_id>/api/social_history')
@login_required
def api_social_history(patient_id: int):
    try:
        profile = ClinicalService.get_social_history(patient_id)
    except Exception as e:
        current_app.logger.error('social_history error for %d: %s', patient_id, e)
        profile = None
    return render_template('clinical/_panels/social_history.html', profile=profile)


@bp.get('/patient/<int:patient_id>/api/recalls')
@login_required
def api_recalls(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'recalls')
    except Exception as e:
        current_app.logger.error('recalls error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Due', 'REMINDERDUE'), ('Reason', 'REASONTEXT')],
                           strikethrough_key='IS_STRUCK',
                           empty_msg='No recalls due.')


@bp.get('/patient/<int:patient_id>/api/actions')
@login_required
def api_actions(patient_id: int):
    try:
        rows = ClinicalService.get_actions(patient_id)
    except Exception as e:
        current_app.logger.error('actions error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Due', 'DUEDATE'), ('Action', 'ACTIONTEXT')],
                           strikethrough_key='PERFCODE',
                           empty_msg='No actions due.')


@bp.get('/patient/<int:patient_id>/api/pathology_trends')
@login_required
def api_pathology_trends(patient_id: int):
    try:
        rows = ClinicalService.get_pathology_trends(patient_id)
    except Exception as e:
        current_app.logger.error('pathology_trends error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Date', 'PerformedDate'), ('Test', 'ResultName'), ('Result', 'ResultValue')],
                           empty_msg='No recent tracked pathology.')


@bp.get('/patient/<int:patient_id>/api/letters')
@login_required
def api_letters(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'letters')
    except Exception as e:
        current_app.logger.error('letters error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/letters.html', rows=rows, patient_id=patient_id)


@bp.get('/patient/<int:patient_id>/api/scans')
@login_required
def api_scans(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'scans')
    except Exception as e:
        current_app.logger.error('scans error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/scans.html', rows=rows, patient_id=patient_id)


@bp.get('/patient/<int:patient_id>/api/pathsummary')
@login_required
def api_pathsummary(patient_id: int):
    try:
        rows = ClinicalService.get_patient_section(patient_id, 'pathology')
    except Exception as e:
        current_app.logger.error('pathsummary error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/pathsummary.html', rows=rows, patient_id=patient_id)


@bp.get('/patient/<int:patient_id>/api/last_items')
@login_required
def api_last_items(patient_id: int):
    try:
        rows = ClinicalService.get_last_items(patient_id)
    except Exception as e:
        current_app.logger.error('last_items error for %d: %s', patient_id, e)
        rows = []
    return render_template('clinical/_panels/clinical_table.html', rows=rows,
                           columns=[('Date', 'MaxOfServiceDate'), ('Dr', 'UserInitials'),
                                    ('Item', 'MBSItem'), ('Desc', 'Description')],
                           empty_msg='No services recorded.')


# ── Progress Notes full-page viewer ───────────────────────────────────────────

@bp.get('/patient/<int:patient_id>/progress-notes')
@login_required
def progress_notes(patient_id: int):
    try:
        demographics = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:
        current_app.logger.error('demographics error for %d: %s', patient_id, e)
        demographics = None
    if not demographics:
        abort(404)

    try:
        raw_notes = ClinicalService.get_patient_section(patient_id, 'progress_notes')
    except Exception as e:
        current_app.logger.error('progress_notes error for %d: %s', patient_id, e)
        raw_notes = []

    notes = []
    for n in raw_notes:
        text = _strip_rtf(n.get('VisitNotes') or '')
        raw_date = n.get('VisitDateRaw')
        year = raw_date.year if raw_date and hasattr(raw_date, 'year') else (
            str(n.get('VisitDateFormatted', ''))[-4:] or '?'
        )
        notes.append({
            **n,
            'VisitNotes_Text':    text,
            'StartTimeFormatted': _fmt_start_time(n.get('StartTime')),
            'VisitYear':          str(year),
        })

    return render_template(
        'clinical/progress_notes.html',
        patient=demographics,
        notes=notes,
        note_count=len(notes),
    )


# ── PatientJSON dashboard ─────────────────────────────────────────────────────

@bp.get('/patient/<int:patient_id>/patient-json')
@login_required
def patient_json_dashboard(patient_id: int):
    from app.services.patient_json_service import BLOCK_META
    from app.models.data_bundle import DataBundle

    try:
        patient = ClinicalService.get_patient_demographics(patient_id)
        if patient:
            patient['patient_id'] = patient_id
    except Exception as e:
        current_app.logger.error('patient_json_dashboard(%d): %s', patient_id, e)
        patient = None

    if not patient:
        abort(404)

    bundles = DataBundle.query.filter_by(is_active=True).order_by(DataBundle.name).all()

    return render_template(
        'clinical/patient_json.html',
        patient=patient,
        block_meta=BLOCK_META,
        bundles=bundles,
    )


@bp.get('/patient/<int:patient_id>/api/patient-json/block/<block_name>')
@login_required
def api_patient_json_block(patient_id: int, block_name: str):
    """HTMX: render a single atomic block as an HTML fragment."""
    from app.services.patient_json_service import PatientJsonService
    from app.services.bundle_render_service import _block_as_text, _block_as_markdown
    import json
    from decimal import Decimal
    from datetime import datetime, date

    fmt        = request.args.get('fmt', 'text')
    deidentify = request.args.get('deidentify', '0') == '1'

    def _json_default(o):
        if isinstance(o, Decimal): return float(o)
        if isinstance(o, (datetime, date)): return o.isoformat()
        return str(o)

    try:
        data = PatientJsonService().get_atomic_block(block_name, patient_id, deidentify=deidentify)
    except ValueError as exc:
        return render_template('clinical/partials/pj_block_error.html', message=str(exc)), 400
    except Exception as exc:
        current_app.logger.error('api_patient_json_block(%s, %s): %s', patient_id, block_name, exc)
        return render_template('clinical/partials/pj_block_error.html',
                               message='Could not load data — database error.'), 500

    if fmt == 'json':
        rendered = json.dumps(data, indent=2, default=_json_default, ensure_ascii=False)
    elif fmt == 'markdown':
        rendered = _block_as_markdown(data)
    else:
        rendered = _block_as_text(data)

    return render_template('clinical/partials/pj_block_content.html',
                           rendered=rendered, fmt=fmt)


@bp.get('/patient/<int:patient_id>/api/patient-json/bundle/<bundle_name>')
@login_required
def api_patient_json_bundle(patient_id: int, bundle_name: str):
    """HTMX: render a full bundle as an HTML fragment."""
    from app.services.bundle_render_service import BundleRenderService

    fmt        = request.args.get('fmt', 'text')
    deidentify = request.args.get('deidentify', '0') == '1'

    try:
        rendered = BundleRenderService().render(bundle_name, patient_id,
                                                fmt=fmt, deidentify=deidentify)
    except ValueError as exc:
        return render_template('clinical/partials/pj_block_error.html', message=str(exc)), 404
    except Exception as exc:
        current_app.logger.error('api_patient_json_bundle(%s, %s): %s', patient_id, bundle_name, exc)
        return render_template('clinical/partials/pj_block_error.html',
                               message='Bundle render failed — database error.'), 500

    return render_template('clinical/partials/pj_block_content.html',
                           rendered=rendered, fmt=fmt)


# ── Stub pages (built later) ──────────────────────────────────────────────────

@bp.get('/patient/<int:patient_id>/charts')
@login_required
def patient_charts(patient_id: int):
    import json as _json
    from app.services.chart_service import ChartService, DecimalEncoder

    patient = ClinicalService.get_patient_demographics(patient_id)
    if not patient:
        abort(404)
    patient['patient_id'] = patient_id

    svc = ChartService(current_app.config['BPSDB_URI'])
    try:
        chart_data = svc.get_chart_data(patient_id)
    except Exception as exc:
        current_app.logger.error('patient_charts(%d): %s', patient_id, exc)
        chart_data = {}

    def _sort_key(name: str) -> tuple:
        if name == 'Blood Pressure': return (3, name)
        if name == 'Weight':         return (2, name)
        if name == 'FIB4':           return (1, name)
        return (0, name)

    result_names = sorted(chart_data.keys(), key=_sort_key)

    # Build 2-column grid HTML server-side (preserves Gen4 pattern exactly)
    html_content = ''
    if result_names:
        rows = (len(result_names) + 1) // 2
        for i in range(rows):
            page_break = ' page-break-after' if (i + 1) % 3 == 0 and (i + 1) < rows else ''
            html_content += f'<div class="charts-row{page_break}">'
            for j in range(2):
                idx = i * 2 + j
                if idx < len(result_names):
                    rn = result_names[idx]
                    safe_id = rn.replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')
                    html_content += (
                        f'<div class="chart-col">'
                        f'<h4 id="title-{safe_id}" class="chart-title"></h4>'
                        f'<canvas id="chart-{safe_id}"></canvas>'
                        f'</div>'
                    )
            html_content += '</div>'
    else:
        html_content = '<p class="charts-empty">No chart data available for this patient.</p>'

    return render_template(
        'clinical/patient_charts.html',
        patient=patient,
        patient_id=patient_id,
        html_content=html_content,
        chart_data=_json.dumps(chart_data, cls=DecimalEncoder),
    )


@bp.get('/patient/<int:patient_id>/pathatom')
@login_required
def pathatom_dashboard(patient_id: int):
    """Atomized pathology chart — one chart per test, selectable via dropdown. Supports ?loinccode= deep-link."""
    import json as _json
    from app.services.chart_service import ChartService, DecimalEncoder

    patient = ClinicalService.get_patient_demographics(patient_id)
    if not patient:
        abort(404)
    patient['patient_id'] = patient_id

    svc = ChartService(current_app.config['BPSDB_URI'])
    try:
        chart_data = svc.get_pathatom_chart_data(patient_id)
    except Exception as exc:
        current_app.logger.error('pathatom_dashboard(%d): %s', patient_id, exc)
        chart_data = {}

    loinc_to_name: dict = {}
    try:
        from app.services.chart_service import chart_name, names_with_percent_and_count
        raw_rows = svc.get_pathatom_raw_rows(patient_id)
        mixed = names_with_percent_and_count(raw_rows)
        for row in raw_rows:
            lc = str(row.get('LoincCode') or '').strip()
            rn = chart_name(row, mixed)
            if lc and rn and lc not in loinc_to_name:
                loinc_to_name[lc] = rn
    except Exception:
        pass

    def _sort_key(name: str) -> tuple:
        if name == 'Blood Pressure': return (3, name)
        if name == 'Weight':         return (2, name)
        if name == 'FIB4':           return (1, name)
        return (0, name)

    sorted_tests = sorted(chart_data.keys(), key=_sort_key)

    requested_loinc = request.args.get('loinccode', '').strip()
    if requested_loinc and requested_loinc in loinc_to_name:
        initial_test = loinc_to_name[requested_loinc]
        if initial_test not in chart_data:
            initial_test = sorted_tests[0] if sorted_tests else ''
    else:
        initial_test = sorted_tests[0] if sorted_tests else ''

    try:
        path_summary = ClinicalService.get_patient_section(patient_id, 'pathology')
    except Exception:
        path_summary = []

    return render_template(
        'clinical/pathatom_dashboard.html',
        patient=patient,
        patient_id=patient_id,
        chart_data_json=_json.dumps(chart_data, cls=DecimalEncoder),
        sorted_tests=sorted_tests,
        initial_test=initial_test,
        path_summary=path_summary,
    )


@bp.get('/patient/<int:patient_id>/results-rollup/candidates')
@login_required
def results_rollup_candidates(patient_id: int):
    from app.services.results_rollup_service import ResultsRollupService
    try:
        candidates = ResultsRollupService.get_candidates(patient_id)
    except Exception as e:
        current_app.logger.error('results_rollup_candidates(%d): %s', patient_id, e)
        return jsonify({'error': 'Failed to load investigations for this patient.'}), 500
    return jsonify({'candidates': candidates})


@bp.post('/patient/<int:patient_id>/results-rollup/generate')
@login_required
def results_rollup_generate(patient_id: int):
    from app.services.results_rollup_service import ResultsRollupService
    data = request.get_json(silent=True) or {}
    selections = data.get('selections') or []
    if not selections:
        return jsonify({'error': 'No reports selected.'}), 400
    try:
        text = ResultsRollupService.generate_rollup(patient_id, selections)
    except Exception as e:
        current_app.logger.error('results_rollup_generate(%d): %s', patient_id, e)
        return jsonify({'error': 'Failed to generate rollup.'}), 500
    return jsonify({'text': text})


@bp.get('/patient/<int:patient_id>/ai')
@login_required
@ai_required
def ai_panel(patient_id: int):
    import json as _json
    from sqlalchemy import or_, func
    from app.models.pipeline import Pipeline, PipelineStatus
    from app.models.ai_provider import AIModel
    from app.services import user_settings_service as user_settings

    try:
        patient = ClinicalService.get_patient_demographics(patient_id)
        if patient:
            patient['patient_id'] = patient_id
    except Exception:
        patient = None

    if not patient:
        abort(404)

    pipelines = (Pipeline.query
                 .filter(
                     or_(
                         func.lower(Pipeline.classifier) == 'ai_panel',
                         func.lower(Pipeline.classifier) == '[ai_panel]',
                     ),
                     Pipeline.status == PipelineStatus.active,
                 )
                 .order_by(Pipeline.is_default.desc(), Pipeline.name)
                 .all())

    # ── Handle document badge links (?auto=sum|exp|txt&doc_type=…&doc_id=…) ──────
    auto = request.args.get('auto', '').strip().lower()
    if auto == 'exp' and not current_app.config.get('EXP_LINKS_ENABLED'):
        auto = ''          # [EXP] is hidden (ADR-185): a typed or saved link starts nothing
    auto_run = None
    doc_load = None

    if auto in ('sum', 'exp'):
        # Find the matching classifier pipeline and auto-run it
        auto_classifier = f'[{auto.upper()}]'
        auto_pipeline = (Pipeline.query
                         .filter(
                             or_(
                                 func.lower(Pipeline.classifier) == auto_classifier.lower(),
                                 func.lower(Pipeline.classifier) == auto_classifier.lower().strip('[]'),
                             ),
                             Pipeline.status == PipelineStatus.active,
                         )
                         .order_by(Pipeline.is_default.desc(), Pipeline.name)
                         .first())
        if auto_pipeline:
            if not any(p.id == auto_pipeline.id for p in pipelines):
                pipelines = [auto_pipeline] + list(pipelines)
            auto_run = {
                'pipeline_id': auto_pipeline.id,
                'classifier':  auto,
                'doc_type':    request.args.get('doc_type', ''),
                'doc_id':      request.args.get('doc_id', type=int),
                'inbox':       request.args.get('inbox', '0'),
                'label':       request.args.get('label', ''),
            }

    elif auto == 'txt':
        # Load document text into the textarea — no pipeline selected, no auto-run
        doc_load = {
            'doc_type': request.args.get('doc_type', ''),
            'doc_id':   request.args.get('doc_id', type=int),
            'inbox':    request.args.get('inbox', '0'),
            'label':    request.args.get('label', ''),
        }

    elif request.args.get('run_pipeline'):
        # Direct pipeline link from topnav (?run_pipeline=<id>) — no document, auto-run immediately
        rp_id = request.args.get('run_pipeline', type=int)
        if rp_id:
            from app.extensions import db
            direct_pipeline = db.session.get(Pipeline, rp_id)
            if direct_pipeline and direct_pipeline.status == PipelineStatus.active:
                if not any(p.id == direct_pipeline.id for p in pipelines):
                    pipelines = [direct_pipeline] + list(pipelines)
                auto_run = {
                    'pipeline_id': direct_pipeline.id,
                    'classifier':  'direct',
                    'doc_type':    '',
                    'doc_id':      None,
                    'inbox':       '0',
                    'label':       direct_pipeline.name,
                }

    # Build {pipeline_id: {model_id, display_name, is_local}} from each pipeline's inference step
    pipeline_models = {}
    for p in pipelines:
        for step in p.steps:
            if step.node_type == 'inference':
                try:
                    cfg = _json.loads(step.config_json or '{}')
                except ValueError:
                    continue
                mid = cfg.get('model_id')
                if mid:
                    m = AIModel.query.get(int(mid))
                    if m and m.provider:
                        pipeline_models[p.id] = {
                            'model_id': m.id,
                            'display_name': m.display_name or m.model_id,
                            'is_local': m.provider.is_local,
                        }
                break

    default_pipeline_id = next(
        (p.id for p in pipelines if p.is_default),
        pipelines[0].id if pipelines else None,
    )

    ai_models = (AIModel.query
                 .filter_by(is_enabled=True, show_in_ai_assist=True, is_asr=False)
                 .order_by(AIModel.display_name)
                 .all())

    from app.models.system_setting import SystemSetting
    practice_name = SystemSetting.get('general.practice_name', 'The Practice')

    text_clean_pipeline = (Pipeline.query
                           .filter(func.lower(Pipeline.classifier) == '[text_clean]',
                                   Pipeline.status == PipelineStatus.active)
                           .first())
    text_clean_pipeline_id = text_clean_pipeline.id if text_clean_pipeline else None

    return render_template(
        'clinical/partials/ai_assist_panel.html',
        patient=patient,
        patient_id=patient_id,
        pipelines=pipelines,
        pipeline_models=pipeline_models,
        default_pipeline_id=default_pipeline_id,
        ai_models=ai_models,
        auto_run=auto_run,
        doc_load=doc_load,
        practice_name=practice_name,
        text_clean_pipeline_id=text_clean_pipeline_id,
        show_instructions_expanded=user_settings.get(current_user, 'ai.show_instructions_expanded'),
    )


@bp.get('/patient/<int:patient_id>/ai/pipeline/<int:pipeline_id>/prompt-text')
@login_required
def ai_pipeline_prompt_text(patient_id: int, pipeline_id: int):
    """Return the raw UserPrompt.prompt_text for the prompt_assembly step of a pipeline,
    and the system prompt that step would send (read-only, for the
    "Instructions given to the AI" strip — ADR-086)."""
    import json as _json
    from app.models.pipeline import Pipeline
    from app.models.prompt import UserPrompt
    from app.services.pipeline.nodes.prompt_assembly import assemble_system_prompt, resolve_system_prompt

    empty = {'prompt_text': '', 'prompt_name': '', 'system_prompt': None}
    pipeline = Pipeline.query.get(pipeline_id)
    if not pipeline:
        return jsonify(empty)

    for step in sorted(pipeline.steps, key=lambda s: s.step_order):
        if step.node_type == 'prompt_assembly':
            cfg = _json.loads(step.config_json or '{}')
            up_id = cfg.get('user_prompt_id')
            if up_id:
                up = UserPrompt.query.get(int(up_id))
                if up and up.is_active:
                    sp = resolve_system_prompt(cfg, up)
                    text, _, scope = assemble_system_prompt(cfg, up)
                    from app.services import scope_service
                    return jsonify({
                        'prompt_text': up.prompt_text,
                        'prompt_name': up.name,
                        'notice': scope_service.notice_text(
                            scope_service.pipeline_notice_key(pipeline_id, 'draft')),
                        # As sent: the scope instruction (ADR-087) in front of the prompt.
                        'system_prompt': ({'name': sp.name if sp else '',
                                           'version': sp.version if sp else None,
                                           'text': text,
                                           'scope': (scope.get('label') if scope.get('applied')
                                                     else None)} if text else None),
                    })
            break

    return jsonify(empty)


@bp.post('/patient/<int:patient_id>/ai/export-pit')
@login_required
def ai_export_pit(patient_id: int):
    """Export AI panel output as a PIT file to the BP shared folder."""
    from datetime import datetime as _dt
    from app.utils.pit_utils import send_as_pit

    data    = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'No content to export.'}), 400

    label = (data.get('label') or '').strip()
    if not label:
        label = f'[AI PANEL] {_dt.now().strftime("%d-%m-%Y")}'

    try:
        patient = ClinicalService.get_patient_demographics(patient_id)
    except Exception:
        patient = None

    # Provenance footer, when the practice has it on (Setup → Messaging).
    from app.services.ai_provenance_service import footer_for_run
    content += footer_for_run(data.get('run_id'), current_user)

    try:
        ok = send_as_pit(patient=patient, pit_label=label, body=content, user=current_user)
    except Exception as exc:
        current_app.logger.error('AI Panel PIT export failed patient=%s: %s', patient_id, exc)
        return jsonify({'error': str(exc)}), 500

    if ok:
        # The AI output behind this export was used — for the usage record.
        from app.services import usage_service
        usage_service.mark_run_output_used(data.get('run_id'))
        return jsonify({'ok': True})
    return jsonify({'error': 'PIT export failed — check pit_export_path in Setup → Messaging.'}), 500


@bp.post('/patient/<int:patient_id>/ai/send-sms')
@login_required
def ai_send_sms(patient_id: int):
    """Stub — SMS sending not yet implemented."""
    return jsonify({'error': 'SMS sending not yet implemented.'}), 501


@bp.post('/patient/<int:patient_id>/ai/send-email')
@login_required
def ai_send_email(patient_id: int):
    """Stub — Email sending not yet implemented."""
    return jsonify({'error': 'Email sending not yet implemented.'}), 501


# ── Legacy section endpoint (kept for backward compatibility) ──────────────────

@bp.get('/patient/<int:patient_id>/section/<section>')
@login_required
def patient_section(patient_id: int, section: str):
    if section not in ClinicalService._SECTIONS:
        abort(404)
    try:
        rows = ClinicalService.get_patient_section(patient_id, section)
    except Exception as e:
        current_app.logger.error('BPSDB section %s error for %d: %s', section, patient_id, e)
        rows = []
        return render_template(f'clinical/_sections/{section}.html', rows=rows,
                               patient_id=patient_id, error='Could not load data.')
    return render_template(f'clinical/_sections/{section}.html', rows=rows,
                           patient_id=patient_id)
