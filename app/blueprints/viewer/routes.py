"""Viewer blueprint — Letters, Pathology, Scans, and Inbox document viewer.

Routes
------
GET /clinical/viewer/letters/<patient_id>        Full-page letters viewer
GET /clinical/viewer/pathology/<patient_id>      Full-page pathology viewer
GET /clinical/viewer/scans/<patient_id>          Full-page scans viewer

GET /clinical/viewer/content/letter/<record_id>  Iframe content (HTML/PDF/image)
GET /clinical/viewer/content/path/<report_id>    Pathology iframe content (?inbox=0|1)
GET /clinical/viewer/content/scan/<document_id>  Scan/doc iframe content
"""

import io

from flask import render_template, request, abort, send_file, current_app, jsonify
from flask_login import login_required
from . import bp
from app.services.viewer_service import ViewerService
from app.services.clinical_service import ClinicalService
from app.services import document_service


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unavailable_html(detail: str = '') -> str:
    msg = 'Document temporarily unavailable.'
    if detail:
        msg += f' ({detail})'
    return (
        '<!DOCTYPE html><html><body style="font-family:sans-serif;padding:1.25rem;">'
        f'<p style="color:#888;">{msg}</p></body></html>'
    )


def _serve_result(result):
    """Convert a DocumentResult to a Flask response."""
    if result.render_type in ('html',):
        return result.content, 200, {'Content-Type': result.mimetype}
    # pdf or image — send binary
    return send_file(io.BytesIO(result.content), mimetype=result.mimetype, as_attachment=False)


_NOT_THIS_PATIENT = 'This document does not belong to this patient.'


def _owned_by(meta: dict | None, patient_id: int | None) -> bool:
    """True when the document row belongs to patient_id (2026-10-01).

    Every content route takes a document id from the page and a patient id
    alongside it. A document paired with the wrong patient — a bad link, or a
    stale id — is refused, never served under another patient's name.
    """
    return bool(meta and patient_id and meta.get('INTERNALID') == patient_id)


def _get_patient(patient_id: int) -> dict:
    try:
        p = ClinicalService.get_patient_demographics(patient_id)
    except Exception as e:
        current_app.logger.error('viewer._get_patient(%d): %s', patient_id, e)
        p = None
    if not p:
        abort(404)
    p['patient_id'] = patient_id
    return p


# ── Full-page viewers ─────────────────────────────────────────────────────────

@bp.get('/letters/<int:patient_id>')
@login_required
def letters_viewer(patient_id: int):
    patient = _get_patient(patient_id)
    try:
        letters = ClinicalService.get_patient_section(patient_id, 'letters')
    except Exception as e:
        current_app.logger.error('viewer.letters(%d): %s', patient_id, e)
        letters = []
    requested = request.args.get('record_id', type=int)
    return render_template(
        'viewer/letters_viewer.html',
        patient=patient,
        letters=letters,
        initial_record_id=requested,
        document_missing=(requested is not None
                          and requested not in {l.get('RecordId') for l in letters}),
    )


@bp.get('/pathology/<int:patient_id>')
@login_required
def pathology_viewer(patient_id: int):
    patient = _get_patient(patient_id)
    try:
        path_list = ClinicalService.get_patient_section(patient_id, 'pathology')
    except Exception as e:
        current_app.logger.error('viewer.pathology(%d): %s', patient_id, e)
        path_list = []
    requested = request.args.get('report_id', type=int)
    inbox = request.args.get('inbox', '0')
    return render_template(
        'viewer/pathology_viewer.html',
        patient=patient,
        path_list=path_list,
        initial_report_id=requested,
        initial_inbox=inbox,
        # Filed and inbox reports have separate id sequences, so both must match.
        document_missing=(requested is not None
                          and (requested, inbox == '1')
                          not in {(p.get('ReportID'), bool(p.get('IsInBox'))) for p in path_list}),
    )


@bp.get('/scans/<int:patient_id>')
@login_required
def scans_viewer(patient_id: int):
    patient = _get_patient(patient_id)
    try:
        scans = ClinicalService.get_patient_section(patient_id, 'scans')
    except Exception as e:
        current_app.logger.error('viewer.scans(%d): %s', patient_id, e)
        scans = []
    requested = request.args.get('document_id', type=int)
    return render_template(
        'viewer/scans_viewer.html',
        patient=patient,
        scans=scans,
        initial_document_id=requested,
        # A requested document that isn't this patient's is reported, not
        # replaced by the patient's newest one (2026-10-01).
        document_missing=(requested is not None
                          and requested not in {s.get('DocumentId') for s in scans}),
    )


# ── Content endpoints (iframe src) ───────────────────────────────────────────

@bp.get('/content/letter/<int:record_id>')
@login_required
def letter_content(record_id: int):
    """Return the letter as HTML or raw binary for the iframe. ?patient_id= required."""
    patient_id = request.args.get('patient_id', type=int)
    if not patient_id:
        return _unavailable_html('No patient given.'), 400, {'Content-Type': 'text/html'}

    try:
        meta = ViewerService.get_letter_meta(record_id)
    except Exception as e:
        current_app.logger.error('letter_content.meta(%d): %s', record_id, e)
        return _unavailable_html(), 200, {'Content-Type': 'text/html'}

    if not meta:
        return _unavailable_html('Letter not found.'), 404, {'Content-Type': 'text/html'}

    if not _owned_by(meta, patient_id):
        current_app.logger.warning('letter_content: letter %d requested for another patient', record_id)
        return _unavailable_html(_NOT_THIS_PATIENT), 404, {'Content-Type': 'text/html'}

    stored = meta.get('Stored') or 0
    if stored <= 0:
        return _unavailable_html('No binary content stored for this letter.'), 200, {'Content-Type': 'text/html'}

    try:
        binary = ViewerService.get_letter_binary(record_id, stored)
    except Exception as e:
        current_app.logger.error('letter_content.binary(%d, stored=%d): %s', record_id, stored, e)
        binary = None

    result = document_service.render_letter(binary)
    return _serve_result(result)


@bp.get('/content/path/<int:report_id>')
@login_required
def path_content(report_id: int):
    """Return a pathology report as HTML or PDF.  ?inbox=1 for inbox reports.

    ?patient_id= is required and must own the report.
    """
    inbox = request.args.get('inbox', '0') == '1'
    patient_id = request.args.get('patient_id', type=int)
    if not patient_id:
        return _unavailable_html('No patient given.'), 400, {'Content-Type': 'text/html'}

    if inbox:
        # Inbox report: INCOMINGREPORTS + cross-DB LEFT JOIN to BPSDOCUMENTSINBOX
        try:
            from app.services.inbox_service import InboxService
            report = InboxService.get_report(report_id)
        except Exception as e:
            current_app.logger.error('path_content inbox(%d): %s', report_id, e)
            report = None

        if not report:
            return _unavailable_html('Inbox report not found.'), 404, {'Content-Type': 'text/html'}

        if not _owned_by(report, patient_id):
            current_app.logger.warning('path_content: inbox report %d requested for another patient', report_id)
            return _unavailable_html(_NOT_THIS_PATIENT), 404, {'Content-Type': 'text/html'}

        binary = report.get('CONTENT')
        if binary:
            binary = bytes(binary)

        result = document_service.render_path_report(
            report.get('REPORTHEADER'),
            report.get('REPORTBODY'),
            binary=binary,
        )
        return _serve_result(result)

    # Filed pathology report: INVESTIGATIONS + BPSDocuments{N}.dbo.INVESTIGATIONS
    try:
        report = ViewerService.get_path_filed(report_id)
    except Exception as e:
        current_app.logger.error('path_content filed(%d): %s', report_id, e)
        report = None

    if not report:
        return _unavailable_html('Filed report not found.'), 404, {'Content-Type': 'text/html'}

    if not _owned_by(report, patient_id):
        current_app.logger.warning('path_content: filed report %d requested for another patient', report_id)
        return _unavailable_html(_NOT_THIS_PATIENT), 404, {'Content-Type': 'text/html'}

    binary  = None
    stored  = report.get('STORED') or 0
    page_id = report.get('INVESTIGATIONPAGEID')

    if stored > 0 and page_id:
        try:
            binary = ViewerService.get_path_binary(page_id, stored)
        except Exception as e:
            current_app.logger.error('path_content binary(%d, stored=%d): %s', report_id, stored, e)

    result = document_service.render_path_report(
        report.get('REPORTHEADER'),
        report.get('REPORTBODY'),
        binary=binary,
    )
    return _serve_result(result)


@bp.get('/content/scan/<int:document_id>')
@login_required
def scan_content(document_id: int):
    """Return a scan/document as HTML or raw binary for the iframe.

    ?patient_id= is required and must own the document: a document id paired
    with the wrong patient is refused, never served (2026-10-01).
    """
    patient_id = request.args.get('patient_id', type=int)
    if not patient_id:
        return _unavailable_html('No patient given.'), 400, {'Content-Type': 'text/html'}

    try:
        meta = ViewerService.get_scan_meta(document_id)
    except Exception as e:
        current_app.logger.error('scan_content.meta(%d): %s', document_id, e)
        return _unavailable_html(), 200, {'Content-Type': 'text/html'}

    if not meta:
        return _unavailable_html('Document not found.'), 404, {'Content-Type': 'text/html'}

    if not _owned_by(meta, patient_id):
        current_app.logger.warning('scan_content: document %d requested for another patient', document_id)
        return _unavailable_html(_NOT_THIS_PATIENT), 404, {'Content-Type': 'text/html'}

    stored  = meta.get('STORED') or 0
    page_id = meta.get('DOCUMENTPAGEID')

    if not stored or not page_id:
        return _unavailable_html('No binary content stored for this document.'), 200, {'Content-Type': 'text/html'}

    raw = None
    try:
        raw = ViewerService.get_scan_binary(page_id, stored)
    except Exception as e:
        current_app.logger.error('scan_content.binary(%d, stored=%d): %s', document_id, stored, e)

    if raw is None:
        result = document_service.render_scan(None)
    else:
        content_bytes, doctype, compression = raw
        result = document_service.render_scan(content_bytes, doctype, compression)

    return _serve_result(result)


@bp.get('/content/text')
@login_required
def doc_text():
    """Extract plain text from a clinical document for AI pipeline input.

    Uses the same render pipeline as the document viewer (document_service.render_*)
    so ZIP extraction, RTF stripping, CDA transforms, and binary priority all behave
    identically to what the viewer shows.

    Query params
    ------------
    doc_type   : 'path' | 'letter' | 'scan' | 'inbox'
    doc_id     : int
    patient_id : int  — required; the document must belong to this patient.
                 The text becomes AI input for this patient's run, redacted
                 with this patient's identifiers — another patient's document
                 here would go out carrying that patient's details.
    inbox      : '0' | '1'  (path only — '1' means INCOMINGREPORTS source)

    Returns JSON: {text: str, label: str}
    """
    doc_type = request.args.get('doc_type', '').strip()
    doc_id   = request.args.get('doc_id', type=int)
    is_inbox = request.args.get('inbox', '0') == '1'

    patient_id = request.args.get('patient_id', type=int)

    if not doc_type or not doc_id or not patient_id:
        return jsonify({'error': 'doc_type, doc_id and patient_id are required'}), 400

    text  = ''
    label = ''

    try:
        if doc_type == 'path':
            if is_inbox:
                report = ViewerService.get_path_inbox(doc_id)
            else:
                report = ViewerService.get_path_filed(doc_id)

            if report and not _owned_by(report, patient_id):
                current_app.logger.warning('doc_text: %s %d requested for another patient', doc_type, doc_id)
                return jsonify({'error': _NOT_THIS_PATIENT}), 404
            if report:
                label  = (report.get('TESTNAME') or '').strip()
                binary = None
                if is_inbox:
                    # Inbox query returns CONTENT directly from INCOMINGREPORTPAGES
                    raw = report.get('CONTENT')
                    if raw:
                        binary = bytes(raw)
                else:
                    # Filed query uses STORED + INVESTIGATIONPAGEID to fetch from BPSDocuments{N}
                    stored  = report.get('STORED') or 0
                    page_id = report.get('INVESTIGATIONPAGEID')
                    if stored > 0 and page_id:
                        try:
                            binary = ViewerService.get_path_binary(page_id, stored)
                        except Exception as e:
                            current_app.logger.warning('doc_text path binary(%s): %s', doc_id, e)
                result = document_service.render_path_report(
                    report.get('REPORTHEADER'),
                    report.get('REPORTBODY'),
                    binary=binary,
                )
                text = document_service.extract_text(result)

        elif doc_type == 'inbox':
            from app.services.inbox_service import InboxService
            report = InboxService.get_report(doc_id)
            if report and not _owned_by(report, patient_id):
                current_app.logger.warning('doc_text: %s %d requested for another patient', doc_type, doc_id)
                return jsonify({'error': _NOT_THIS_PATIENT}), 404
            if report:
                label  = (report.get('TESTNAME') or '').strip()
                binary = report.get('CONTENT')
                if binary:
                    binary = bytes(binary)
                result = document_service.render_path_report(
                    report.get('REPORTHEADER'),
                    report.get('REPORTBODY'),
                    binary=binary,
                )
                text = document_service.extract_text(result)

        elif doc_type == 'letter':
            meta = ViewerService.get_letter_meta(doc_id)
            if meta and not _owned_by(meta, patient_id):
                current_app.logger.warning('doc_text: %s %d requested for another patient', doc_type, doc_id)
                return jsonify({'error': _NOT_THIS_PATIENT}), 404
            if meta:
                label  = (meta.get('Subject') or '').strip()
                stored = meta.get('Stored') or 0
                if stored > 0:
                    binary = ViewerService.get_letter_binary(doc_id, stored)
                    result = document_service.render_letter(binary)
                    text = document_service.extract_text(result)

        elif doc_type == 'scan':
            meta = ViewerService.get_scan_meta(doc_id)
            if meta and not _owned_by(meta, patient_id):
                current_app.logger.warning('doc_text: %s %d requested for another patient', doc_type, doc_id)
                return jsonify({'error': _NOT_THIS_PATIENT}), 404
            if meta:
                label   = (meta.get('Detail') or meta.get('Subject') or '').strip()
                stored  = meta.get('STORED') or 0
                page_id = meta.get('DOCUMENTPAGEID')
                if stored > 0 and page_id:
                    raw = ViewerService.get_scan_binary(page_id, stored)
                    if raw:
                        content_bytes, doctype, compression = raw
                        result = document_service.render_scan(content_bytes, doctype, compression)
                        text = document_service.extract_text(result)

        else:
            return jsonify({'error': f'Unknown doc_type: {doc_type!r}'}), 400

    except Exception as exc:
        current_app.logger.error('doc_text doc_type=%s doc_id=%s: %s', doc_type, doc_id, exc)
        return jsonify({'error': 'Failed to extract document text', 'detail': str(exc)}), 500

    return jsonify({'text': text, 'label': label})
