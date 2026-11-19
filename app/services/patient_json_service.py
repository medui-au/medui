"""PatientJsonService — assembles atomic patient data blocks for the AI pipeline.

Blocks are fetched from BPSDB via PatientJsonRepository, formatted for
downstream consumption, and assembled into named DataBundle records.

Deidentification is handled at two levels:
  - SQL level (_noid.sql variants): strips PII columns from the query itself
  - Post-hoc: blocks without _noid SQL variants receive a single-pass redaction
    applied by the caller (DataAssemblyNode / BundleRenderService)

The _SQL_DEIDENTIFY_BLOCKS frozenset declares which blocks have _noid.sql support.
Callers must not apply additional per-block PII redaction to these blocks.
"""

import re
import time
from datetime import datetime

from flask import current_app

from app.repositories.patient_json_repository import PatientJsonRepository
from app.repositories.patient_repository import _format_clinical_age
from app.sql.query_loader import ReadOnlySession

# Process-level cache for assembled block lists (raw, before redaction).
# Key: (patient_id, tuple(block_names))  Value: (result, fetched_at)
# 10-minute TTL — covers repeated recompose attempts within a consultation.
_BUNDLE_CACHE: dict[tuple, tuple[list, float]] = {}
_BUNDLE_TTL = 600  # seconds

# Per-report extracted text, keyed by ReportID — no TTL, since a filed inbox
# report's content never changes after the fact. Bounded implicitly by how
# many distinct reports get gap-filled over the process's lifetime.
_INBOX_TEXT_CACHE: dict[int, str] = {}
_INBOX_ROLLUP_MAX_DOCS = 8    # cap OCR calls per chat turn / bundle assembly
_INBOX_ROLLUP_MAX_CHARS = 3000  # per-document text cap, keeps bundle size sane

# ── Document exclusion signatures (ADR-029) ──────────────────────────────────
# The practice's own care plans, health assessments and appointment letters
# reach AI context through the document blocks. Care plans in particular are
# earlier AI output fed back in: generated from older data, rarely checked line
# by line, and liable to anchor the next plan on the last. Signatures live in an
# admin mapping table (Admin → Mapping Tables → doc_exclusion_signatures); a
# matching document is left out of the document blocks and listed instead in
# the 'filtered_documents' block.
_EXCLUSION_TABLE = 'doc_exclusion_signatures'
_EXCLUSION_TTL = 60  # seconds — a grid edit applies within a minute (plus _BUNDLE_TTL)
_EXCLUSION_CACHE: dict[str, tuple[list[dict], float]] = {}

# Title and body fields per document block. Signatures match titles by default:
# a title survives summarisation where prose is rewritten, and a document's body
# can mention a care plan without being one.
_DOC_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    'scans':                    (('REPORT_DESCRIPTION',),  ()),
}
# ── Document authors from the practice's own staff ───────────────────────────
# The rollups' Author comes from BP's document records. A doctor's name is
# tokenised by the HCP pass (doctors are in the address book); a receptionist
# or nurse is not, so their full name reached the model — e.g. a recall letter
# (the letters we send are filed under 'referrals'). Non-doctors are named by
# role instead, as the progress notes' author is. Doctors are left alone.
_DOCTOR_GROUPS = frozenset({3, 4, 42})
_ROLE_BY_GROUP = {28: 'Nurse practitioner', 5: 'Nurse', 6: 'Receptionist',
                  7: 'Receptionist', 1: 'Practice manager'}
_STAFF_TTL = 3600
_STAFF_CACHE: dict[str, tuple[list[dict], float]] = {}
_AUTHOR_TITLE = re.compile(r'^(?:dr|prof|professor|a/prof|assoc)\b', re.IGNORECASE)
# The letters we send: always written by one of our own users.
_OWN_LETTER_CATEGORIES = frozenset({'referrals'})


def _staff_users() -> list[dict]:
    """BP users (name + group), cached for an hour. [] if BPSDB is unavailable."""
    from app.services import practitioner_names
    cached = _STAFF_CACHE.get('users')
    if cached and (time.monotonic() - cached[1]) < _STAFF_TTL:
        rows = cached[0]
    else:
        try:
            with _make_session() as session:
                rows = PatientJsonRepository(session).get_staff_users()
        except Exception as exc:  # BPSDB boundary: logged, and authors pass through unchanged
            current_app.logger.warning('staff users unavailable: %s', exc)
            return []
        _STAFF_CACHE['users'] = (rows, time.monotonic())
    # Preferred names (ADR-106) added fresh each call, beside the BP names.
    all_rows = list(rows) + practitioner_names.extra_rows(rows, lower=True)
    return [{'first': (r.get('first_name') or '').strip(), 'surname': (r.get('surname') or '').strip(),
             'group': r.get('group_code')} for r in all_rows]


def _staff_role(author: str, category: str, users: list[dict]) -> str | None:
    """The role to show for an author who is one of our non-doctor staff, or None.

    The name part (before any " - document type") must contain a staff
    member's surname and either their first name or first initial. For our
    own letters a surname alone is enough, since their author is always one
    of our users. Never for a titled author, and never when a doctor matches
    as well — two doctors here share a surname.
    """
    name = re.split(r'\s+-\s+', author, maxsplit=1)[0]
    if _AUTHOR_TITLE.match(name.strip()):
        return None
    words = [w.strip('.,()').lower() for w in name.split() if w.strip('.,()')]

    def matches(u: dict, surname_only: bool) -> bool:
        if not u['surname'] or u['surname'] not in words:
            return False
        if surname_only:
            return True
        first = u['first']
        return bool(first and (first in words
                               or any(len(w) == 1 and w == first[0] for w in words)))

    def decide(candidates: list[dict]) -> str | None:
        if any(u['group'] in _DOCTOR_GROUPS for u in candidates):
            return None
        people = {(u['first'], u['surname']) for u in candidates}
        roles = {_ROLE_BY_GROUP.get(u['group'], 'Staff') for u in candidates}
        return roles.pop() if len(people) == 1 and len(roles) == 1 else None

    # A first name or initial settles who it is, doctors included.
    strict = [u for u in users if matches(u, surname_only=False)]
    if strict:
        return decide(strict)
    # Only our own letters may be matched on a surname alone.
    if (category or '').lower() in _OWN_LETTER_CATEGORIES:
        loose = [u for u in users if matches(u, surname_only=True)]
        if loose:
            return decide(loose)
    return None


def _relabel_staff_authors(rows: list[dict]) -> list[dict]:
    """Replace a non-doctor staff author's name with their role, keeping the
    " - document type" part: "Receptionist - Recall letter"."""
    users = None
    for row in rows:
        author = row.get('Author') if isinstance(row, dict) else None
        if not author or not isinstance(author, str):
            continue
        if users is None:
            users = _staff_users()
            if not users:
                return rows
        role = _staff_role(author, str(row.get('Category') or ''), users)
        if role:
            parts = re.split(r'(\s+-\s+)', author, maxsplit=1)
            row['Author'] = role + ''.join(parts[1:])
    return rows


_MATCH_IN = frozenset({'title', 'summary', 'any'})
_SWITCHED_OFF = frozenset({'false', 'f', 'no', 'n', '0', 'off'})


def _exclusion_signatures() -> list[dict]:
    """Active signatures, cached briefly: [{'signature', 'match_in', 'label'}].

    A missing or unreadable table means no filtering. This is about the quality
    of the context, not privacy: failing open includes a document that might
    have been left out, which is how every bundle behaved before.
    """
    cached = _EXCLUSION_CACHE.get(_EXCLUSION_TABLE)
    if cached and (time.monotonic() - cached[1]) < _EXCLUSION_TTL:
        return cached[0]

    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    from app.services import mapping_service

    try:
        rows, _total = mapping_service.get_rows(_EXCLUSION_TABLE, page=1, per_page=1000)
    except ValueError as exc:                     # table not created
        current_app.logger.warning('document exclusions off: %s', exc)
        rows = []
    except SQLAlchemyError as exc:
        db.session.rollback()                     # don't leave the request's transaction aborted
        current_app.logger.warning('document exclusions unreadable: %s', exc)
        rows = []

    signatures = []
    for row in rows:
        signature = str(row.get('signature') or '').strip()
        # A blank 'active' counts as on, so a row with just a signature works.
        if not signature or str(row.get('active')).strip().lower() in _SWITCHED_OFF:
            continue
        match_in = str(row.get('match_in') or 'title').strip().lower()
        signatures.append({
            'signature': signature.lower(),
            'match_in': match_in if match_in in _MATCH_IN else 'title',
            'label': str(row.get('label') or '').strip() or signature,
        })
    _EXCLUSION_CACHE[_EXCLUSION_TABLE] = (signatures, time.monotonic())
    return signatures


def _is_document(row, block: str) -> bool:
    title_fields, body_fields = _DOC_FIELDS[block]
    return isinstance(row, dict) and any(f in row for f in title_fields + body_fields)


def _excluded_by(row: dict, block: str, signatures: list[dict]) -> str | None:
    """Label of the first signature this document matches, or None."""
    title_fields, body_fields = _DOC_FIELDS[block]
    title = ' '.join(str(row.get(f) or '') for f in title_fields).lower()
    body = ' '.join(str(row.get(f) or '') for f in body_fields).lower()
    for s in signatures:
        text = {'title': title, 'summary': body, 'any': f'{title} {body}'}[s['match_in']]
        if s['signature'] in text:
            return s['label']
    return None


def _partition_documents(rows, block: str) -> tuple[list, list[dict]]:
    """(kept, excluded). Rows that are not documents — errors, status and note
    rows — are always kept. Each excluded row carries 'Filtered by': the
    signature's label. Not 'Excluded by', which a model reading the block
    could take for a clinical judgement rather than a filing rule."""
    signatures = _exclusion_signatures()
    if not signatures or not isinstance(rows, list):
        return rows, []
    kept, excluded = [], []
    for row in rows:
        label = _excluded_by(row, block, signatures) if _is_document(row, block) else None
        if label:
            excluded.append({**row, 'Filtered by': label})
        else:
            kept.append(row)
    return kept, excluded

# Blocks that have a _noid.sql SQL variant for SQL-level PII suppression.
_SQL_DEIDENTIFY_BLOCKS = frozenset({
    'demographics',
    'allergies',
    'medications',
    'ceased_medications',
    'immunizations',
    'social_history',
    'pathology',
    'pathology_compact',
    'recalls',
    'referrals',
})

# Per-block UI metadata: label, icon, short description, whether it has a _noid variant.
BLOCK_META: dict[str, dict] = {
    'demographics':   {'icon': '👤', 'label': 'Demographics',        'desc': 'Age, DOB, address, Medicare, BP, weight', 'deid': True},
    'history':        {'icon': '📋', 'label': 'Medical History',      'desc': 'Past medical and surgical history',        'deid': False},
    'medications':    {'icon': '💊', 'label': 'Medications',          'desc': 'Current prescriptions',                   'deid': True},
    'ceased_medications': {'icon': '💊', 'label': 'Ceased Medications', 'desc': 'Previously discontinued medications, excluding routine cessation reasons', 'deid': True},
    'allergies':      {'icon': '⚠️', 'label': 'Allergies',            'desc': 'Drug and environmental allergies',         'deid': True},
    'fh':             {'icon': '🧬', 'label': 'Family History',       'desc': 'Parents, siblings and relatives',          'deid': True},
    'immunizations':  {'icon': '💉', 'label': 'Immunizations',        'desc': 'Vaccination history',                     'deid': True},
    'vaccine_eligibility': {'icon': '🛡️', 'label': 'Vaccine Eligibility (NIP)', 'desc': 'Funded eligibility for Influenza, COVID-19, Pneumococcal, Varicella Zoster, RSV', 'deid': False},
    'social_history': {'icon': '🏠', 'label': 'Social History',       'desc': 'Occupation, smoking, alcohol, marital',   'deid': True},
    'pathology':         {'icon': '🔬', 'label': 'Pathology',            'desc': 'All results including FIB-4 score',       'deid': True},
    'pathology_compact': {'icon': '🔬', 'label': 'Pathology (compact)', 'desc': 'Last 2–4 results per analyte + FIB-4 (small context)', 'deid': True},
    'progress_notes': {'icon': '📝', 'label': 'Progress Notes',       'desc': 'Recent consultation notes (RTF stripped)', 'deid': False},
    'scans':          {'icon': '📄', 'label': 'Scans & Documents',    'desc': 'Imaging and document list',               'deid': False},
    'referrals':      {'icon': '📨', 'label': 'Referrals',            'desc': 'Outgoing referral letters',               'deid': True},
    'actions':        {'icon': '✅', 'label': 'Actions',              'desc': 'Open clinical actions and tasks',         'deid': False},
    'recalls':        {'icon': '🔔', 'label': 'Recalls',              'desc': 'Scheduled recall items',                  'deid': True},
    'nok':            {'icon': '👥', 'label': 'Next of Kin',          'desc': 'Emergency contacts',                      'deid': False},
    'filtered_documents': {'icon': '🚫', 'label': 'Filtered Documents', 'desc': 'Documents left out of the document blocks by a document filter (Admin → Mapping Tables → doc_exclusion_signatures)', 'deid': False},
}

# Display labels for each semantic block name.
BLOCK_LABELS: dict[str, str] = {
    'demographics':   'Demographics',
    'history':        'Medical History',
    'medications':    'Current Medications',
    'ceased_medications': 'Ceased Medications',
    'allergies':      'Allergies',
    'fh':             'Family History',
    'immunizations':  'Immunizations',
    'vaccine_eligibility': 'Vaccine Eligibility (NIP)',
    'social_history': 'Social History',
    'pathology':         'Pathology',
    'pathology_compact': 'Pathology (compact)',
    'progress_notes': 'Progress Notes',
    'scans':          'Scans & Documents',
    'referrals':      'Referrals',
    'actions':        'Actions',
    'recalls':        'Recalls',
    'nok':            'Next of Kin',
    'scribe':         'Scribe Transcript',
    'scribe_30days':  'Scribe History (30 days)',
    'filtered_documents': 'Filtered Documents',
}

# Preset bundle definitions used as fallback when no DataBundle DB record exists.
_BUNDLE_PRESETS: dict[str, list[str]] = {
    'alldata': [
        'demographics', 'history', 'medications', 'allergies', 'fh',
        'social_history', 'immunizations', 'pathology', 'actions', 'recalls',
    ],
    'deid_context': [
        'demographics', 'history', 'medications', 'allergies', 'fh',
        'social_history', 'immunizations', 'pathology', 'referrals',
        'scans', 'actions', 'recalls', 'progress_notes',
    ],
}


def _make_session() -> ReadOnlySession:
    from flask import current_app
    return ReadOnlySession(current_app.config['BPSDB_URI'])


class PatientJsonService:
    """Semantic block dispatcher and bundle assembler.

    Constructor-injected for testability; defaults to live BPSDB.
    """

    def __init__(self, repo: PatientJsonRepository | None = None):
        self._repo = repo  # lazily built when None (requires app context)

    def _get_repo(self) -> PatientJsonRepository:
        if self._repo is None:
            self._repo = PatientJsonRepository(_make_session())
        return self._repo

    # ── Public API ────────────────────────────────────────────────────────────

    def get_atomic_block(
        self,
        block_name: str,
        patient_id: int,
        deidentify: bool = False,
        user_id: int | None = None,
        q: str | None = None,
    ):
        """Fetch and format a single atomic block.

        Blocks in _SQL_DEIDENTIFY_BLOCKS handle PII suppression via SQL.
        All other blocks return raw data; callers apply a single-pass
        redaction on the assembled prompt string when deidentify=True.
        """
        if block_name == 'scribe':
            return self._get_scribe_transcript(patient_id, user_id=user_id)

        if block_name == 'scribe_30days':
            return self._get_scribe_history(patient_id)

        if block_name == 'filtered_documents':
            return self._get_filtered_documents(patient_id)

        _use_deid = deidentify and block_name in _SQL_DEIDENTIFY_BLOCKS

        dispatch: dict[str, callable] = {
            'demographics':   lambda: self._get_demographics(patient_id, _use_deid),
            'history':        lambda: self._get_repo().get_atomic_history(patient_id),
            'medications':    lambda: self._enrich_medications(
                                  self._get_repo().get_atomic_medications(patient_id, _use_deid)
                              ),
            'ceased_medications': lambda: self._enrich_medications(
                                  self._get_repo().get_atomic_ceased_medications(patient_id, _use_deid)
                              ),
            'allergies':      lambda: self._get_allergies(patient_id, _use_deid),
            'fh':             lambda: self._get_family_history(patient_id),
            'immunizations':  lambda: self._get_repo().get_atomic_immunizations(patient_id, _use_deid),
            'vaccine_eligibility': lambda: self._get_vaccine_eligibility(patient_id),
            'social_history': lambda: self._get_social_history(patient_id, _use_deid),
            'pathology':         lambda: self._get_pathology(patient_id, _use_deid),
            'pathology_compact': lambda: self._get_pathology_compact(patient_id, _use_deid),
            'progress_notes': lambda: self._get_progress_notes(patient_id, q=q),
            'scans':          lambda: self._without_excluded(
                                  self._get_repo().get_atomic_scans(patient_id), 'scans'
                              ),
            'referrals':      lambda: self._get_repo().get_atomic_referrals(patient_id, _use_deid),
            'actions':        lambda: self._get_repo().get_atomic_actions(patient_id),
            'recalls':        lambda: self._get_repo().get_atomic_recalls(patient_id, _use_deid),
            'nok':            lambda: self._get_repo().get_atomic_nok(patient_id),
        }

        if block_name in dispatch:
            result = dispatch[block_name]()
            if _use_deid:
                # The _noid queries use INTERNALID for their joins but also
                # output it — the patient's record number, in "de-identified"
                # data. Dropped here rather than in each multi-statement query
                # (ADR-031).
                from app.services.redaction_service import RedactionService
                result = RedactionService.drop_record_numbers(result)
            return result

        raise ValueError(
            f"Unknown block '{block_name}'. "
            f"Known blocks: {sorted(dispatch)}. "
            "Custom blocks are not yet implemented in Gen5."
        )

    @staticmethod
    def _enrich_medications(rows: list[dict]) -> list[dict]:
        """Inject generic_name / atc_code from approved DrugMapping records."""
        if not rows:
            return rows
        try:
            from app.services.drug_mapping_service import get_mapping
            for r in rows:
                pid = r.get('PRODUCTID')
                if pid:
                    m = get_mapping(pid)
                    if m:
                        r['generic_name'] = m.generic_name
                        if m.atc_code:
                            r['atc_code'] = m.atc_code
        except Exception:
            pass  # enrichment is best-effort; never break the bundle
        return rows

    def _get_vaccine_eligibility(self, patient_id: int) -> list[dict]:
        from app.services import vaccine_eligibility_service
        return vaccine_eligibility_service.get_vaccine_eligibility(patient_id, self._get_repo())

    def get_bundle(
        self,
        bundle_name: str,
        patient_id: int,
        deidentify: bool = True,
    ) -> list[dict]:
        """Assemble a named bundle as a list of {label: data} dicts.

        Looks up the DataBundle DB record first; falls back to _BUNDLE_PRESETS.
        Raw (unredacted) results are cached per patient + block list for 10 minutes
        so repeated recompose attempts within a consultation skip the BPSDB fetch.
        Redaction is always applied fresh by DataAssemblyNode after this returns.
        """
        from app.models.data_bundle import DataBundle

        bundle_def = DataBundle.query.filter_by(name=bundle_name, is_active=True).first()
        if bundle_def:
            blocks = [bb.block_source for bb in bundle_def.blocks]
        else:
            blocks = _BUNDLE_PRESETS.get(bundle_name, _BUNDLE_PRESETS['deid_context'])

        cache_key = (patient_id, tuple(blocks))
        cached = _BUNDLE_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[1]) < _BUNDLE_TTL:
            return list(cached[0])  # shallow copy so callers can't mutate the cache

        result: list[dict] = [{"Today's Date": datetime.now().strftime('%Y-%m-%d')}]

        for block in blocks:
            label = BLOCK_LABELS.get(block, block.replace('_', ' ').title())
            try:
                data = self.get_atomic_block(block, patient_id, deidentify=deidentify)
                result.append({label: data})
            except Exception as exc:
                current_app.logger.error(
                    'PatientJsonService.get_bundle: block=%s patient=%s error=%s',
                    block, patient_id, exc,
                )

        _BUNDLE_CACHE[cache_key] = (result, time.monotonic())
        return result

    # ── Block formatters ──────────────────────────────────────────────────────

    def _get_demographics(self, patient_id: int, deidentify: bool) -> dict:
        data = self._get_repo().get_atomic_demographics(patient_id, deidentify)
        if not data:
            return {'error': 'Patient not found'}

        systolic  = data.get('SYSTOLICBP')
        diastolic = data.get('DIASTOLICBP')
        if systolic and diastolic:
            data['BP']      = f'{systolic}/{diastolic}'
            data['BP_DATE'] = data.get('SYSTOLICBP_DATE')
        for k in ('SYSTOLICBP', 'SYSTOLICBP_DATE', 'DIASTOLICBP', 'DIASTOLICBP_DATE'):
            data.pop(k, None)

        if data.get('DOB'):
            data['AGE'] = _format_clinical_age(str(data['DOB']))

        return data

    def _get_allergies(self, patient_id: int, deidentify: bool) -> list:
        rows = self._get_repo().get_atomic_allergies(patient_id, deidentify)
        return [
            f"{r.get('ItemName')} ({r.get('Reaction')}) - {r.get('Severity')}"
            for r in rows
        ]

    def _get_social_history(self, patient_id: int, deidentify: bool) -> list:
        row = self._get_repo().get_atomic_social_history(patient_id, deidentify)
        if not row:
            return ['No social history recorded']
        return [
            f"Occupation: {row.get('Occupation', 'Not recorded')}",
            f"Alcohol/w: {row.get('ALCOHOLPERWEEK', 'Not recorded')}",
            f"Smoking Status: {row.get('SMOKING', 'Not recorded')}",
            f"Marital Status: {row.get('MaritalStatus', 'Not recorded')}",
        ]

    def _get_pathology(self, patient_id: int, deidentify: bool) -> list:
        path = self._get_repo().get_atomic_pathology_all(patient_id, deidentify)
        fib4 = self._get_repo().get_atomic_fib4(patient_id, deidentify)
        return (path or []) + (fib4 or [])

    def _get_pathology_compact(self, patient_id: int, deidentify: bool) -> list:
        return self._get_repo().get_atomic_pathology_compact(patient_id, deidentify) or []

    def _get_progress_notes(self, patient_id: int, q: str | None = None) -> list:
        from app.services.clinical_synonyms import expand_query

        if q:
            rows = self._get_repo().get_all_progress_notes(patient_id)
            search_terms = expand_query(q)
        else:
            rows = self._get_repo().get_atomic_progress_notes(patient_id)
            search_terms = None

        processed = []
        for row in rows:
            raw = row.get('VisitNotes', '')
            try:
                from striprtf.striprtf import rtf_to_text
                clean = rtf_to_text(raw) if raw else ''
            except ImportError:
                clean = re.sub(r'\\[a-z]{1,32}(-?\d+)? ?', '', raw or '')
                clean = clean.replace('{', '').replace('}', '').strip()

            if search_terms is not None:
                clean_lower = clean.lower()
                matched = [t for t in search_terms if t in clean_lower]
                if not matched:
                    continue
                entry = {
                    'Date':          row.get('VisitDate'),
                    'Doctor':        row.get('Doctor'),
                    'Reason':        row.get('Reason'),
                    'Notes':         clean,
                    'matched_terms': matched,
                }
            else:
                entry = {
                    'Date':   row.get('VisitDate'),
                    'Doctor': row.get('Doctor'),
                    'Reason': row.get('Reason'),
                    'Notes':  clean,
                }

            processed.append(entry)
        return processed

    def _get_family_history(self, patient_id: int) -> list:
        """Build a structured family history list from the clinical panel queries."""
        from app.services.clinical_service import ClinicalService
        try:
            fh_raw = ClinicalService.get_patient_section(patient_id, 'family_history')
        except Exception:
            fh_raw = []

        if not fh_raw:
            return ['No family history recorded']

        return [
            f"{r.get('RELATIONNAME', '')} - {r.get('CONDITION', '')} {r.get('DISEASECOMMENT') or ''}".strip()
            for r in fh_raw
        ]

    # ── External summarisation blocks ────────────────────────────────────────

    def _without_excluded(self, rows, block: str):
        """A document block with signature-matched documents left out (ADR-029).

        Says so in a note row, so neither the model nor a reader mistakes an
        omission for an absence.
        """
        kept, excluded = _partition_documents(rows, block)
        if excluded:
            kept = list(kept) + [{'Note': f'{len(excluded)} document(s) left out by a '
                                          'document filter — see the Filtered '
                                          'Documents block.'}]
        return kept

    def _get_filtered_documents(self, patient_id: int) -> list[dict]:
        """List BP correspondence excluded by configured document signatures."""
        rows = self._get_repo().get_atomic_scans(patient_id)
        _kept, excluded = _partition_documents(rows, 'scans')
        return [{'Source': BLOCK_LABELS['scans'], **row} for row in excluded] or [
            {'Status': 'No documents matched a document filter.'}]

    def _get_scribe_transcript(self, patient_id: int, user_id: int | None) -> dict | None:
        """Return today's scribe session for this patient (live cache then DB)."""
        from app.models.consultation_transcript import ConsultationTranscript
        from datetime import datetime as _dt

        today_midnight = _dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = ConsultationTranscript.query.filter(
            ConsultationTranscript.patient_id == patient_id,
            ConsultationTranscript.updated_at >= today_midnight,
        )
        if user_id:
            q = q.filter(ConsultationTranscript.user_id == user_id)
        record = q.order_by(ConsultationTranscript.updated_at.desc()).first()

        if record and record.transcript_text:
            return {
                'transcript':  record.transcript_text,
                'recorded_at': record.updated_at.strftime('%Y-%m-%d %H:%M'),
                'is_final':    record.is_final,
                'source':      'saved record',
            }
        return None

    def _get_scribe_history(self, patient_id: int) -> dict | None:
        """Return all scribe transcripts for the past 30 days."""
        from app.models.consultation_transcript import ConsultationTranscript
        from datetime import datetime as _dt, timedelta

        cutoff  = _dt.utcnow() - timedelta(days=30)
        records = (
            ConsultationTranscript.query
            .filter(
                ConsultationTranscript.patient_id == patient_id,
                ConsultationTranscript.updated_at >= cutoff,
                ConsultationTranscript.transcript_text.isnot(None),
            )
            .order_by(ConsultationTranscript.updated_at.asc())
            .all()
        )
        if not records:
            return None

        entries = [
            {
                'date':       r.updated_at.strftime('%d %b %Y %H:%M'),
                'status':     'Final' if r.is_final else 'Draft',
                'transcript': r.transcript_text,
            }
            for r in records
        ]
        return {'sessions': entries, 'count': len(entries)}
