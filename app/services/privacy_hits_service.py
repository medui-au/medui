"""Turn a run's privacy-check hits into future redactions (ADR-049).

The pre-send check (ADR-084, ADR-111) records where each finding sits in the
prompt as sent — offsets, never text. Here an administrator sees each hit in context and
can add it to a list, so the same leak is redacted from then on:

  - a shortened name -> the name-variant list, for every patient with the
    name it is short for (practice_nickname_service.LIST_TABLE);
  - another person's name or a recurring string -> the always-redact list
    (ADR-030), for everyone.

The word is always read here, from the run's stored prompt, never taken from
the browser: an entry can only be made from text that was actually flagged.
"""
import json
import re
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db

# Which list a hit can go to, by the check's finding type.
_TO_NAME_VARIANTS = frozenset({'patient_name_variant'})
_TO_ALWAYS_REDACT = frozenset({
    'practice_contact_name', 'practice_contact_detail', 'titled_name',
    'street_address', 'email_address', 'landline_number', 'mobile_number',
})
ALWAYS_LABELS = ('Name', 'HCP', 'Place', 'Org', 'Contact')
_CONTEXT = 60
_FORM_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{2,}")


def _run_and_prompt(run_id: int):
    from app.models.pipeline import PipelineRun
    from app.services.pipeline.engine import extract_debug_info
    run = db.session.get(PipelineRun, run_id)
    if not run:
        return None, '', {}
    debug = extract_debug_info(run)
    verdict = debug.get('privacy_check') or {}
    if 'hits' not in verdict:
        # A request stopped at the pre-send review never got its card, so read the
        # check's own result (ADR-120): the same hits, positions and types.
        try:
            output = json.loads(run.output_json or '{}')
        except ValueError:
            output = {}
        precheck = output.get('precheck')
        if isinstance(precheck, dict) and 'hits' in precheck:
            verdict = precheck
    return run, debug.get('current_prompt') or '', verdict


def _given_names(patient_id: int) -> list[dict]:
    """The patient's first- and middle-name words, each with how many patients share it."""
    from app.services.redaction_service import RedactionService
    demographics = (RedactionService._get_demographics(patient_id) or {}) if patient_id else {}
    names: list[dict] = []
    for field, role in (('FIRSTNAME', 'first name'), ('MIDDLENAME', 'middle name')):
        for i, word in enumerate(re.split(r'[\s-]+', (demographics.get(field) or '').strip())):
            if len(word) < 2 or any(n['name'] == word.lower() for n in names):
                continue
            names.append({'name': word.lower(), 'display': word.capitalize(),
                          'role': role if i == 0 else 'middle name', 'patients': _patients_with(word)})
    return names


def _patients_with(name: str) -> int | None:
    from app.sql.query_loader import ReadOnlySession, load_query
    try:
        with ReadOnlySession(current_app.config['BPSDB_URI']) as session:
            rows = session.execute(load_query('patients_with_given_name'), [f'% {name.lower()} %'])
        return rows[0]['n'] if rows else 0
    except Exception as exc:  # BPSDB boundary: the count is a courtesy, not a gate
        current_app.logger.warning('patients_with_given_name failed: %s', exc)
        return None


def load(run_id: int) -> dict | None:
    """The run's hits with their words and context, or None if there is no such run."""
    run, prompt, verdict = _run_and_prompt(run_id)
    if not run:
        return None
    hits = []
    for i, h in enumerate(verdict.get('hits') or []):
        start, end = h.get('start'), h.get('end')
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(prompt):
            continue
        action = ('name_variant' if h.get('type') in _TO_NAME_VARIANTS
                  else 'always_redact' if h.get('type') in _TO_ALWAYS_REDACT else None)
        hits.append({
            'index': i, 'tier': h.get('tier'), 'type': h.get('type'), 'kind': h.get('kind'),
            'word': prompt[start:end],
            'before': prompt[max(0, start - _CONTEXT):start], 'after': prompt[end:end + _CONTEXT],
            'action': action,
        })
    from app.services import privacy_reports_service
    reports = privacy_reports_service.for_run(run, prompt)          # users' reports (ADR-115)
    wants_names = (any(h['action'] == 'name_variant' for h in hits)
                   or any(r['single_word'] and r['status'] == 'open' for r in reports))
    return {
        'run': run, 'hits': hits, 'checked': bool(verdict), 'reports': reports,
        'given_names': _given_names(run.patient_id) if wants_names and run.patient_id else [],
    }


def _hit(run_id: int, index: int):
    run, prompt, verdict = _run_and_prompt(run_id)
    hits = (verdict.get('hits') or []) if run else []
    if not 0 <= index < len(hits):
        return run, None, ''
    h = hits[index]
    start, end = h.get('start'), h.get('end')
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(prompt):
        return run, None, ''
    return run, h, prompt[start:end]


def _ensure_list_table() -> None:
    from app.services import mapping_service
    from app.services.practice_nickname_service import LIST_TABLE, LIST_COLUMNS
    if mapping_service.get_table(LIST_TABLE):
        return
    mapping_service.create_table(
        LIST_TABLE, 'Name variants (future redactions)',
        'Short forms of given names, redacted for every patient with that first or middle '
        'name (ADR-049). Added from privacy-check hits on a run, or typed here. Set active '
        'to false to switch an entry off.')
    for col, col_type in LIST_COLUMNS:
        mapping_service.column_add(LIST_TABLE, col, col_type)


def add_name_variant(run_id: int, index: int, name: str, user: str, confirmed: bool) -> dict:
    """Add the hit's word as a short form of one of the patient's given names."""
    run, hit, word = _hit(run_id, index)
    if not hit or hit.get('type') not in _TO_NAME_VARIANTS:
        return {'ok': False, 'message': 'That hit is not a shortened name.'}
    return name_variant_from_text(run, word, name, user, confirmed,
                                  f'From privacy-check hit on run #{run.id}')


def name_variant_from_text(run, word: str, name: str, user: str, confirmed: bool, note: str) -> dict:
    """Add a word from the run's prompt as a short form of one of the patient's given names
    (a checker hit, or a user's report, ADR-115)."""
    from app.services import mapping_service
    from app.services.practice_nickname_service import LIST_TABLE, forget_listed_forms
    from app.services.redaction_service import _lowercase_words
    form = word.strip()
    if not _FORM_RE.fullmatch(form):
        return {'ok': False, 'message': 'Only a single word of three or more letters can be added.'}
    names = {n['name']: n for n in _given_names(run.patient_id)}
    name = (name or '').strip().lower()
    if name not in names:
        return {'ok': False, 'message': "Choose one of the patient's own first or middle names."}
    if form.lower() == name:
        return {'ok': False, 'message': 'That is the name itself, already redacted.'}
    if form.lower() in _lowercase_words() and not confirmed:
        return {'ok': False, 'confirm': True,
                'message': f'"{form.capitalize()}" is also an ordinary word. It will only be '
                           f'redacted when capitalised — so also at the start of a sentence. Add anyway?'}
    _ensure_list_table()
    rows, _ = mapping_service.get_rows(LIST_TABLE, page=1, per_page=5000)
    if any(str(r.get('name') or '').lower() == name and str(r.get('form') or '').lower() == form.lower()
           for r in rows):
        return {'ok': False, 'message': f'"{form.capitalize()}" for {name.capitalize()} is already listed.'}
    mapping_service.row_insert(LIST_TABLE, {
        'name': name, 'form': form.lower(), 'active': True, 'added_by': user,
        'added_at': datetime.now(timezone.utc).isoformat(), 'source_run': run.id,
        'note': note,
    })
    forget_listed_forms()
    current_app.logger.info('name-variant list: entry added by %s from run %s', user, run.id)
    reach = names[name]['patients']
    return {'ok': True, 'message': f'Added: "{form.capitalize()}" will be redacted for every patient '
                                   f'whose first or middle name is {name.capitalize()}'
                                   + (f' ({reach} patients).' if reach is not None else '.')}


def add_always_redact(run_id: int, index: int, label: str, user: str) -> dict:
    """Add the hit's text to the always-redact list (ADR-030), for every patient."""
    run, hit, text = _hit(run_id, index)
    if not hit or hit.get('type') not in _TO_ALWAYS_REDACT:
        return {'ok': False, 'message': 'That hit cannot go on the always-redact list.'}
    return always_redact_from_text(run, text, label, user, f'From privacy-check hit on run #{run.id}')


def always_redact_from_text(run, text: str, label: str, user: str, source: str) -> dict:
    """Add text from the run's prompt to the always-redact list (ADR-030): a checker hit,
    or a user's report (ADR-115)."""
    from app.services import mapping_service
    from app.services import redaction_service
    text = ' '.join(text.split())
    if len(text) < redaction_service._ALWAYS_MIN_LENGTH:
        return {'ok': False, 'message': 'Too short to redact safely everywhere.'}
    if label not in ALWAYS_LABELS:
        return {'ok': False, 'message': 'Choose a label.'}
    try:
        rows, _ = mapping_service.get_rows(redaction_service._ALWAYS_TABLE, page=1, per_page=5000)
    except ValueError:
        return {'ok': False, 'message': 'The always-redact table does not exist.'}
    if any(str(r.get('string') or '').strip().lower() == text.lower() for r in rows):
        return {'ok': False, 'message': 'Already on the always-redact list.'}
    mapping_service.row_insert(redaction_service._ALWAYS_TABLE, {
        'string': text, 'label': label, 'active': True,
        'note': f'{source}, added by {user}, {datetime.now(timezone.utc):%Y-%m-%d}',
    })
    from app.services import redaction_core
    redaction_core.forget()                       # applies to the next run
    current_app.logger.info('always-redact list: entry added by %s from run %s', user, run.id)
    return {'ok': True, 'message': 'Added to the always-redact list: it will be redacted for every patient.'}
