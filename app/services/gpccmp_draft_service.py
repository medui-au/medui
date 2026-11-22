"""The AI-drafted GPCCMP (ADR-174, phase 4).

MedUI builds everything that is a fact or a decision itself: the medical-history header, the
targets, the prevention lines, the review date, the consent lines and the "For the GP" reference.
The AI writes only the per-issue wording (goal, measure, actions, services, review aim) and the
safety-netting lines, as JSON, from the GP's decisions, the practice protocol's modules and the
redacted record. MedUI then checks the AI's text against the decisions before the GP sees it,
and the result opens as an ordinary care-plan draft (ADR-129).
"""
import json
import re
from datetime import date, datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.careplan import Careplan, CareplanStatus
from app.models.gpccmp import GpccmpSession, SessionStatus
from app.services import gpccmp_decision_service as dec
from app.services import protocol_service as protocols

TAGS = ('[Discussed]', '[Record]', '[Protocol]')
DRAFT_LINE = ("DRAFT GP Chronic Condition Management Plan. Items tagged [Protocol] are proposed and need the "
              "patient's agreement; [Discussed] came from the GP's decisions; [Record] from the patient's record.")


class DraftError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


# ── Inputs ────────────────────────────────────────────────────────────────────

def modules_block(version, issue_keys: list[str]) -> str:
    """The protocol modules for the issues in scope, as [PROTOCOL MODULES] text."""
    by_key = {m.condition_key: m for m in (version.modules if version else [])}
    lines = ['[PROTOCOL MODULES]']
    for key in issue_keys:
        m = by_key.get(key)
        if m is None:
            continue
        lines.append(f'Module {key}: {m.label}')
        for label, value in (('Goal', m.goals), ('Measures', m.measures_text), ('Standard monitoring', m.monitoring),
                             ('Patient information', m.patient_info), ('Safety-netting', m.safety_netting)):
            if value:
                lines.append(f'  {label}: {value}')
        if m.services:
            lines.append('  Standard services: ' + '; '.join(m.services))
    if len(lines) == 1:
        lines.append('(no protocol modules for these issues)')
    lines.append('[/PROTOCOL MODULES]')
    return '\n'.join(lines)


def _age(value) -> int | None:
    m = re.match(r'\s*(\d+)', str(value or ''))
    return int(m.group(1)) if m else None


def _sex(value) -> str | None:
    v = str(value or '').strip().lower()
    return 'F' if v.startswith('f') else 'M' if v.startswith('m') else None


def has_smoking_history(smoking) -> bool:
    v = str(smoking or '').strip().lower()
    return bool(v) and 'non' not in v and 'never' not in v and 'smok' in v


def prevention_lines(version, age, sex, flags: dict, smoking=None, palliative: bool = False) -> list[dict]:
    """The protocol's prevention lines that apply, worked out here (decisions 6 and 8), never by
    the AI. A rule needing a fact MedUI doesn't have (e.g. a skin cancer history flag) is left out."""
    if palliative or version is None:
        return []
    out = []
    for p in version.prevention:
        r = p.rule or {}
        if r.get('sex') and r['sex'] != sex:
            continue
        if ('age_min' in r or 'age_max' in r) and age is None:
            continue
        if 'age_min' in r and age < r['age_min']:
            continue
        if 'age_max' in r and age > r['age_max']:
            continue
        on = {k for k, v in (flags or {}).items() if v}
        if r.get('flags_any') and not (on & set(r['flags_any'])):
            continue
        if r.get('flags_none') and (on & set(r['flags_none'])):
            continue
        need = r.get('needs')
        if need == 'smoking_history' and not has_smoking_history(smoking):
            continue
        if need and need != 'smoking_history':
            continue
        out.append({'key': p.key, 'label': p.label, 'wording': p.wording})
    return out


def available_models() -> list:
    """The models a GP may choose for the draft: the same list the AI Assistant offers."""
    from app.services.model_choice import available_models as _models
    return _models()


def default_model(pid: int | None = None):
    """The drafting pipeline's own model (its inference step), or None."""
    from app.models.ai_provider import AIModel
    from app.models.pipeline import PipelineStep
    try:
        pid = pid or pipeline_id()
    except DraftError:
        return None
    for step in PipelineStep.query.filter_by(pipeline_id=pid, node_type='inference').all():
        try:
            mid = json.loads(step.config_json or '{}').get('model_id')
        except ValueError:
            mid = None
        if mid:
            return db.session.get(AIModel, int(mid))
    return None


def model_label(model) -> str:
    from app.services.model_choice import label
    return label(model)


def pipeline_id() -> int:
    from app.commands.gpccmp import PIPELINE_SETTING
    from app.models.pipeline import Pipeline, PipelineStatus
    from app.models.system_setting import SystemSetting
    pid = SystemSetting.get(PIPELINE_SETTING)
    pl = db.session.get(Pipeline, int(pid)) if pid else None
    if pl is None:
        raise DraftError('The GPCCMP drafting pipeline is not set up yet (flask gpccmp seed-pipeline).')
    if pl.status != PipelineStatus.active:
        raise DraftError('The GPCCMP drafting pipeline has no model yet: an administrator sets it in Admin → '
                         'Pipeline Designer and makes it active.')
    return pl.id


# ── Running ───────────────────────────────────────────────────────────────────

def start(session: GpccmpSession, user, model_id: int | None = None) -> str:
    """Start the AI draft for a confirmed session. Returns the run id. model_id: the GP's
    choice for this draft (one of available_models), otherwise the pipeline's own model."""
    from app.services import careplan_service
    from app.services.pipeline.engine import PipelineEngine
    if session.status != SessionStatus.ready:
        raise DraftError('Confirm the plan decisions first (Proceed with GPCCMP).')
    existing = careplan_service.open_draft(session.patient_id)
    if existing is not None:
        raise DraftError(f'This patient already has a care plan draft open (plan {existing.id}). '
                         'Open it from the notice below, then file or discard it before drafting with AI.')
    d = dec.decisions(session)
    version = protocols.live_version()
    block = dec.decisions_block(d, dec.targets_for_block(session.patient_id), version)
    inputs = {'gp_decisions': block,
              'protocol_modules': modules_block(version, [i['key'] for i in d.get('issues', [])])}
    pid = pipeline_id()
    chosen = None
    if model_id:
        chosen = next((m for m in available_models() if m.id == int(model_id)), None)
        if chosen is None:
            raise DraftError('Choose a model from the list.')
        inputs['model_id_override'] = chosen.id     # the engine's per-run model choice (the AI Assistant's too)
    used = chosen or default_model(pid)
    run_id = PipelineEngine.run(pipeline_id=pid, patient_id=session.patient_id, user_id=user.id,
                                input_data=inputs, model_is_local=False)
    session.check_results = {'run_uuid': run_id, 'started_at': _now().isoformat(),
                             'model_id': used.id if used else None, 'model': model_label(used),
                             'model_chosen': bool(chosen)}
    db.session.commit()
    return run_id


def poll(session: GpccmpSession, user, patient: dict, flags: dict, facts: dict) -> dict:
    """{'state': 'running'|'failed'|'done', ...}. On first 'done' builds the care-plan draft."""
    from app.models.pipeline import PipelineRun, RunStatus
    if session.status == SessionStatus.drafted and session.careplan_id:
        return {'state': 'done', 'careplan_id': session.careplan_id}
    run_uuid = (session.check_results or {}).get('run_uuid')
    if not run_uuid:
        return {'state': 'failed', 'error': 'No draft has been started.'}
    run = PipelineRun.query.filter_by(run_uuid=run_uuid).first()
    if run is None or run.status in (RunStatus.pending, RunStatus.running):
        return {'state': 'running'}
    if run.status != RunStatus.completed:
        return {'state': 'failed', 'error': run.error_message or 'The AI run did not complete.'}
    try:
        output = json.loads(run.output_json or '{}').get('final_output') or ''
    except (TypeError, ValueError):
        output = ''
    parsed = parse_output(output)
    if parsed is None:
        session.check_results = {**(session.check_results or {}), 'error': 'not_json'}
        db.session.commit()
        return {'state': 'failed', 'error': 'The AI reply could not be read as a plan. Try drafting again.'}
    d = dec.decisions(session)
    results = run_checks(parsed, d)
    plan = build_careplan(session, user, parsed, d, flags, facts)
    session.pipeline_run_id = run.id
    session.careplan_id = plan.id
    session.status = SessionStatus.drafted
    prior = session.check_results or {}
    session.check_results = {'run_uuid': run_uuid, 'checks': results, 'model_id': prior.get('model_id'),
                             'model': prior.get('model'), 'model_chosen': prior.get('model_chosen')}
    db.session.commit()
    return {'state': 'done', 'careplan_id': plan.id}


def redraft(session: GpccmpSession, user) -> None:
    """Void this session's AI draft (unfiled) and return the session to confirmed, to draft again."""
    from app.services import careplan_service
    plan = db.session.get(Careplan, session.careplan_id) if session.careplan_id else None
    if plan is not None:
        if plan.status != CareplanStatus.draft:
            raise DraftError('This plan has been filed; start a new plan instead.')
        careplan_service.void_plan(plan, user, 'Replaced by a new AI draft (GPCCMP)')
    session.careplan_id = None
    session.pipeline_run_id = None
    session.status = SessionStatus.ready
    session.check_results = None
    db.session.commit()


# ── Reading the reply ─────────────────────────────────────────────────────────

def parse_output(text: str) -> dict | None:
    """The AI's JSON object, tolerating code fences or text around it. None if unreadable."""
    t = (text or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    start, end = t.find('{'), t.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(t[start:end + 1])
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get('issues'), list):
        return None
    issues = []
    for i in obj['issues']:
        if not isinstance(i, dict):
            continue
        issues.append({
            'issue_key': str(i.get('issue_key') or ''), 'issue_label': str(i.get('issue_label') or ''),
            'goal': str(i.get('goal') or ''), 'measure': str(i.get('measure') or ''),
            'patient_actions': [str(x) for x in i.get('patient_actions') or [] if str(x).strip()],
            'team_actions': [str(x) for x in i.get('team_actions') or [] if str(x).strip()],
            'services': [{'name': str(s.get('name') or ''), 'purpose': str(s.get('purpose') or '')}
                         for s in i.get('services') or [] if isinstance(s, dict)],
            'review_aim': str(i.get('review_aim') or ''),
        })
    safety = [str(x) for x in obj.get('safety_netting') or [] if str(x).strip()]
    return {'issues': issues, 'safety_netting': safety}


# ── MedUI's checks (no AI) ────────────────────────────────────────────────────

_TARGET_RE = re.compile(r'(?:<|>|≤|≥|=<|>=|\bless than|\bbelow|\bunder|\babove|\bover|\bmore than|\bat least|'
                        r'\bat most|\bup to|\bno more than)\s*\d', re.I)
_JUDGE_RE = re.compile(r'\b(abnormal|normal range|within (?:the )?(?:normal )?range|out of range|too high|too low|'
                       r'elevated|well[- ]controlled|poorly controlled|uncontrolled|at target|on target|'
                       r'(?:has|have) (?:been )?(?:met|achieved|reached)|not (?:been )?met|warrants|concerning|'
                       r'suggests|likely)\b', re.I)
_CONSENT_RE = re.compile(r'\b(consent(?:s|ed)?|agree[sd]?|agreement)\b', re.I)
_DOSE_RE = re.compile(r'\b\d+(?:\.\d+)?\s?(?:mg|mcg|microgram|micrograms|units?|ml|mL)\b')


def _ai_lines(parsed: dict) -> list[tuple[str, str]]:
    out = []
    for i in parsed['issues']:
        k = i['issue_key']
        out += [(f'{k}: goal', i['goal']), (f'{k}: measure', i['measure']), (f'{k}: review aim', i['review_aim'])]
        out += [(f'{k}: patient action', a) for a in i['patient_actions']]
        out += [(f'{k}: team action', a) for a in i['team_actions']]
    out += [('safety-netting', s) for s in parsed['safety_netting']]
    return out


def _gp_text(d: dict) -> str:
    parts = [d.get('notes', '')]
    for i in d.get('issues', []):
        parts += [i.get('directions', ''), i.get('goal', '')]
    return '\n'.join(p for p in parts if p)


def _quoted(snippet: str, gp_text: str) -> bool:
    return snippet.lower() in gp_text.lower()


def run_checks(parsed: dict, d: dict) -> list[dict]:
    """Each check: {'key', 'label', 'ok', 'details': [..]}. Deterministic: no AI involved."""
    want = [i['key'] for i in d.get('issues', [])]
    got = [i['issue_key'] for i in parsed['issues']]
    gp_text = _gp_text(d)
    lines = _ai_lines(parsed)
    checks = []

    def add(key, label, details):
        checks.append({'key': key, 'label': label, 'ok': not details, 'details': details})

    det = []
    if set(got) - set(want):
        det.append('Issues not in your decisions: ' + ', '.join(sorted(set(got) - set(want))))
    if set(want) - set(got):
        det.append('Issues missing: ' + ', '.join(i['label'] for i in d['issues'] if i['key'] in set(want) - set(got)))
    if len(got) != len(set(got)):
        det.append('An issue appears more than once.')
    add('issues', 'Exactly the issues you chose', det)

    det = []
    chosen = {i['key']: {s['name'].strip().lower() for s in i.get('services', [])} for i in d.get('issues', [])}
    for i in parsed['issues']:
        named = {s['name'].strip().lower() for s in i['services'] if s['name'].strip()}
        extra = named - chosen.get(i['issue_key'], set())
        missing = chosen.get(i['issue_key'], set()) - named
        if extra:
            det.append(f"{i['issue_key']}: services you didn't choose: " + ', '.join(sorted(extra)))
        if missing:
            det.append(f"{i['issue_key']}: services left out: " + ', '.join(sorted(missing)))
    add('services', 'Only the services and referrals you chose', det)

    det = [f'{where}: "{m.group(0)}…"' for where, text in lines for m in _TARGET_RE.finditer(text)
           if not _quoted(text[max(0, m.start() - 20):m.end() + 10].strip(), gp_text)]
    add('targets', 'No target numbers written by the AI (MedUI prints your targets)', det)

    det = [f'{where}: "{m.group(0)}"' for where, text in lines for m in _JUDGE_RE.finditer(text)
           if not _quoted(m.group(0), gp_text)]
    add('wording', 'No judgement of results or targets', det)

    det = [f'{where}: "{m.group(0)}"' for where, text in lines for m in _CONSENT_RE.finditer(text)]
    add('consent', 'No consent written by the AI (MedUI writes it from your ticks)', det)

    det = [f'{where}: "{m.group(0)}"' for where, text in lines for m in _DOSE_RE.finditer(text)
           if not _quoted(m.group(0), gp_text)]
    add('doses', 'No medicine doses except those in your directions', det)

    det = [f'{where}' for where, text in lines if text.strip() and not text.rstrip().endswith(TAGS)]
    add('tags', 'Every line says where it came from', det)

    det = []
    for i in parsed['issues']:
        missing = [n for n, v in (('goal', i['goal']), ('measure', i['measure']), ('patient actions', i['patient_actions']),
                                  ('team actions', i['team_actions']), ('review aim', i['review_aim'])) if not v]
        if missing:
            det.append(f"{i['issue_key']}: no " + ', '.join(missing))
    add('complete', 'Each issue has a goal, measure, actions and review aim (MBS AN.0.47)', det)
    return checks


# ── The care-plan draft ───────────────────────────────────────────────────────

def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def review_due(interval: str, today: date | None = None) -> date | None:
    m = re.match(r'(\d+)\s+month', interval or '')
    return _add_months(today or date.today(), int(m.group(1))) if m else None


def _bullets(items) -> str:
    return '\n'.join(f'- {x}' for x in items)


def build_careplan(session: GpccmpSession, user, parsed: dict, d: dict, flags: dict, facts: dict) -> Careplan:
    """A care-plan draft (ADR-129) in the existing record: MedUI's header, the AI's issue rows,
    then MedUI's rows for prevention, safety-netting, review, consent and the GP reference."""
    from app.services import careplan_service as cps
    version = protocols.live_version()
    try:
        history = cps.default_header(session.patient_id)
    except Exception as exc:  # BPSDB boundary: the header is a starting point the GP can edit
        current_app.logger.warning('gpccmp: header unavailable: %s', type(exc).__name__)
        history = ''
    targets = dec.targets_for_block(session.patient_id)
    target_lines = [f"{t['measure']}: {t['target']}" for t in targets] or ['GP to set']
    header = '\n\n'.join(x for x in (
        DRAFT_LINE,
        f"Plan: {dec.PLAN_TYPES.get(d.get('plan_type'), '')}" + (f' · practice protocol v{version.version}' if version else ''),
        history,
        'TARGETS FOR THIS PLAN (set by the GP)\n' + _bullets(target_lines),
    ) if x)
    rows = []
    if d.get('plan_type') == 'review':
        # ADR-175: the GP's progress words and the targets beside the last values, written by MedUI.
        from app.services import gpccmp_review_service as review
        from app.services import patient_target_service
        latest = patient_target_service.latest_values(session.patient_id, protocols.measures())
        progress = review.progress_lines(d) + review.target_sentences(session.patient_id, latest)
        rows.append(_row('Progress since the last plan (recorded by the GP)', '', _bullets(progress), '', 'free_text'))
    labels = {i['key']: i['label'] for i in d.get('issues', [])}
    for i in parsed['issues']:
        if i['issue_key'] not in labels:
            continue          # never file an issue the GP didn't choose (also listed by the checks)
        goals = '\n'.join(x for x in (i['goal'], i['measure'], i['review_aim']) if x)
        management = '\n'.join(x for x in (
            'I will achieve this by:\n' + _bullets(i['patient_actions']) if i['patient_actions'] else '',
            'My GP and care team will:\n' + _bullets(i['team_actions']) if i['team_actions'] else '') if x)
        providers = '\n'.join(f"{s['name']}" + (f": {s['purpose']}" if s['purpose'] else '') for s in i['services'])
        rows.append(_row(labels[i['issue_key']], goals, management, providers, 'coded'))
    mods = d.get('modifiers', {})
    age, sex, smoking = (facts.get(k) for k in ('age', 'sex', 'smoking'))
    prev = prevention_lines(version, _age(age), _sex(sex), flags, smoking, palliative=mods.get('palliative'))
    if prev:
        rows.append(_row('Preventive health (for information)', '', _bullets(f"{p['label']}: {p['wording']}" for p in prev),
                         '', 'free_text'))
    if parsed['safety_netting']:
        rows.append(_row('When to seek help sooner', '', _bullets(parsed['safety_netting']), '', 'free_text'))
    due = review_due(d.get('review_interval'))
    rows.append(_row('Review arrangements',
                     f"Next review in {d.get('review_interval', dec.DEFAULT_REVIEW)}" + (f" (by {due.strftime('%d/%m/%Y')})" if due else '')
                     + '. Earlier if things change.', '', '', 'free_text'))
    c = d.get('consent', {})
    consent_lines = [f"{label}: {'yes' if c.get(k) else 'not recorded (GP to complete)'}" for k, label in dec.CONSENT.items()]
    if c.get('withheld'):
        consent_lines.append(f"Information the patient wants withheld: {c['withheld']}")
    rows.append(_row('Consent and agreement (recorded by the GP)', '', _bullets(consent_lines), '', 'free_text'))
    refs = [m for m in (version.modules if version else []) if m.condition_key in labels and m.gp_reference]
    if refs:
        rows.append(_row(f'For the GP: practice protocol v{version.version} reference', '',
                         '\n'.join(f'{m.label}: {m.gp_reference}' for m in refs), '', 'free_text'))
    last = cps.last_filed(session.patient_id)
    plan = Careplan(patient_id=session.patient_id, author_id=user.id, previous_careplan_id=last.id if last else None,
                    status=CareplanStatus.draft, header_text=header, draft_schema=cps.DRAFT_SCHEMA,
                    draft_revision=1, draft_saved_at=_now(), draft_saved_by_id=user.id, review_due_on=due)
    plan.draft_json = json.dumps({'schema': cps.DRAFT_SCHEMA, 'header': header,
                                  'review_due_on': due.isoformat() if due else None, 'rows': rows, 'values': {}})
    db.session.add(plan)
    db.session.flush()
    cps._event('created', user.id, careplan_id=plan.id, copied=False, rows=len(rows), ai_drafted=True,
               gpccmp_session_id=session.id)
    return plan


def _row(label, goals, management, providers, source) -> dict:
    from app.services.careplan_service import _blank_row
    r = _blank_row()
    r.update(issue_label=label[:300], issue_source=source, goals=goals, management=management, providers=providers)
    return r
