"""ResultsRollupService — full unredacted pathology/radiology report text, rolled up.

get_candidates() lists a patient's investigations (filed + inbox, de-duplicated) with a
best-guess default selection (the most recent REQUESTDATE among pathology/radiology providers).
generate_rollup() renders + extracts text for a chosen set of reports and concatenates them —
intended for copying to the clipboard, not for AI/redacted contexts.
"""

from flask import current_app

from app.sql.query_loader import ReadOnlySession, load_query

# Provider-name substrings (case-insensitive) identifying pathology labs and radiology/imaging
# providers, built from real PROVIDERNAME values observed in BPSDB. Used only to pick a sensible
# default selection — every investigation is still listed and can be manually selected regardless.
_PATHOLOGY_RADIOLOGY_PATTERNS = [
    'QML', 'SULLIVAN NICOLAIDES', 'SNP', 'QUEENSLAND MEDICAL LABORATORY',
    'MATER LABORATORY', 'PATHOLOGY QUEENSLAND', 'ENVOI PATHOLOGY', 'SONIC HEALTHCARE',
    'NATIONAL BOWEL CANCER SCREENING',
    'I-MED RADIOLOGY', 'EXACT RADIOLOGY', 'SOUTHERNEX IMAGING', 'QUEENSLAND XRAY',
    'RADIOLOGY REPORTS', 'BREASTSCREEN', 'BREAST CLINIC',
]


def _is_pathology_or_radiology(provider: str | None) -> bool:
    if not provider:
        return False
    upper = provider.upper()
    return any(p in upper for p in _PATHOLOGY_RADIOLOGY_PATTERNS)


class ResultsRollupService:

    @staticmethod
    def get_candidates(patient_id: int) -> list[dict]:
        uri = current_app.config.get('BPSDB_URI')
        with ReadOnlySession(uri) as sess:
            rows = sess.execute(load_query('patient_investigations_full'), [patient_id, patient_id])

        # The same result can appear once filed (INVESTIGATIONS, IsInBox=0) and once still in
        # the inbox (INCOMINGREPORTS, IsInBox=1) with different ReportIDs. Keep one row per
        # underlying result, preferring the filed copy when both exist.
        by_key: dict[tuple, dict] = {}
        for r in rows:
            key = (r.get('ProviderName'), r.get('TestName'), r.get('CollectionDate'))
            existing = by_key.get(key)
            if existing is None or (existing.get('IsInBox') == 1 and r.get('IsInBox') == 0):
                by_key[key] = r
        deduped = list(by_key.values())

        request_dates = [
            r['RequestDate'] for r in deduped
            if r.get('RequestDate') and _is_pathology_or_radiology(r.get('ProviderName'))
        ]
        max_request_date = max(request_dates) if request_dates else None

        candidates = []
        for r in deduped:
            is_pr = _is_pathology_or_radiology(r.get('ProviderName'))
            candidates.append({
                'report_id':       r['ReportID'],
                'is_inbox':        bool(r.get('IsInBox')),
                'collection_date': r.get('CollectionDate'),
                'report_date':     r.get('ReportDate'),
                'provider':        r.get('ProviderName'),
                'test_name':       r.get('TestName'),
                'is_default':      bool(is_pr and max_request_date is not None
                                         and r.get('RequestDate') == max_request_date),
            })
        return candidates

    @staticmethod
    def generate_rollup(patient_id: int, selections: list[dict]) -> str:
        from app.services import document_service
        from app.services.inbox_service import InboxService
        from app.services.viewer_service import ViewerService

        sections = []
        for sel in selections:
            report_id = sel.get('report_id')
            is_inbox = sel.get('is_inbox')
            if not report_id:
                continue

            try:
                if is_inbox:
                    report = InboxService.get_report(report_id)
                    if not report:
                        continue
                    binary = report.get('CONTENT')
                    if binary:
                        binary = bytes(binary)
                else:
                    report = ViewerService.get_path_filed(report_id)
                    if not report:
                        continue
                    binary = None
                    stored = report.get('STORED') or 0
                    page_id = report.get('INVESTIGATIONPAGEID')
                    if stored > 0 and page_id:
                        binary = ViewerService.get_path_binary(page_id, stored)

                result = document_service.render_path_report(
                    report.get('REPORTHEADER'), report.get('REPORTBODY'), binary=binary,
                )
                text = document_service.extract_text(result)
            except Exception as exc:
                current_app.logger.warning('generate_rollup: failed report %s: %s', report_id, exc)
                continue

            header = ' | '.join(
                str(p) for p in [sel.get('report_date'), sel.get('provider'), sel.get('test_name')]
                if p
            )
            sections.append(f'{header}\n{"-" * len(header)}\n{text}' if header else text)

        return '\n\n'.join(sections)
