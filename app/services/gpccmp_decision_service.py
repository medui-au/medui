"""GPCCMP plan decisions (ADR-173): what the GP decides for one plan, stored as data.

Every item here is the GP's: the plan type, the issues in scope, the modifiers, the directions,
services and goal wording per issue, the review interval and the consent ticks. Coded conditions
only decide which issues are offered ticked; the GP confirms or changes them. Phase 4 gives
`decisions_block` to the AI as data it may not contradict or add to.
"""
import json
from datetime import datetime, timezone

from app.extensions import db
from app.models.gpccmp import GpccmpSession, SessionStatus
from app.services import protocol_service as protocols

PLAN_TYPES = {'prepare': 'Prepare a new plan (MBS 965)', 'review': 'Review the current plan (MBS 967)'}
REVIEW_INTERVALS = ('1 month', '2 months', '3 months', '6 months', '12 months')
DEFAULT_REVIEW = '3 months'          # decision 5
FORMATS = {'tabular': 'Tabular'}
MAX_TEXT = 2000
MAX_FREE_ISSUES = 5

MODIFIERS = {
    'frail': 'Aged 80+ or frail',
    'palliative': 'Palliative / terminal illness',
    'cognitive': 'Cognitive impairment or limited capacity',
}
CONSENT = {
    'agrees': 'The patient took part in setting the goals and agrees to the plan',
    'share': 'The patient consents to relevant parts being shared with the care team',
    'copy_offered': 'A copy was offered to the patient (and carer)',
    'mhr': 'The patient consents to upload to My Health Record',
}


class DecisionError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _text(v, limit: int = MAX_TEXT) -> str:
    v = (v or '').strip()
    if len(v) > limit:
        raise DecisionError(f'A text field is longer than {limit} characters.')
    return v


def plan_type_from_eligibility(code) -> str:
    """The billing record's CCMP eligibility, as a starting point only ('967' → review)."""
    return 'review' if str(code or '').strip() == '967' else 'prepare'


# ── Sessions ──────────────────────────────────────────────────────────────────

def open_session(patient_id: int, user, flags: dict | None = None) -> GpccmpSession:
    """This doctor's unfinished session for the patient, or a new one started from the
    patient's last confirmed plan (carry_forward)."""
    s = (GpccmpSession.query.filter_by(patient_id=patient_id, user_id=user.id)
         .filter(GpccmpSession.status.in_([SessionStatus.draft, SessionStatus.ready]))
         .order_by(GpccmpSession.updated_at.desc()).first())
    if s is None:
        live = protocols.live_version()
        s = GpccmpSession(patient_id=patient_id, user_id=user.id, status=SessionStatus.draft,
                          protocol_version_id=live.id if live else None)
        carried = carry_forward(patient_id, live, flags or {})
        if carried:
            s.decisions_json = json.dumps(carried)
        db.session.add(s)
        db.session.commit()
    return s


def last_confirmed(patient_id: int) -> GpccmpSession | None:
    """The patient's most recent confirmed plan decisions, by any doctor."""
    return (GpccmpSession.query.filter_by(patient_id=patient_id)
            .filter(GpccmpSession.status.in_([SessionStatus.ready, SessionStatus.drafted]),
                    GpccmpSession.confirmed_at.isnot(None))
            .order_by(GpccmpSession.confirmed_at.desc()).first())


def carry_forward(patient_id: int, version, flags: dict) -> dict | None:
    """The defaults for a new plan, from the patient's last confirmed plan (ADR-173).

    Carried, all editable: issues, goals, directions, services, modifiers, review interval,
    notes, format. Never carried: consent (recorded afresh for every plan and review) and the
    plan type (it starts from the billing record). An issue whose module is no longer in the
    protocol becomes one of the GP's own issues. A module now matching a coded condition that
    the last plan didn't have is added and marked new."""
    prev = last_confirmed(patient_id)
    if prev is None:
        return None
    old = decisions(prev)
    if not old:
        return None
    modules = {m.condition_key: m for m in (version.modules if version else [])}
    issues, n_free = [], 0
    for iss in old.get('issues', []):
        iss = dict(iss)
        for k in ('new_since_last', 'progress', 'progress_note'):     # progress belongs to one review
            iss.pop(k, None)
        if iss.get('source') == 'protocol' and iss.get('key') not in modules:
            iss['source'] = 'gp'
        if iss.get('source') == 'gp':
            if n_free >= MAX_FREE_ISSUES:
                continue
            iss['key'] = f'free_{n_free}'
            n_free += 1
        issues.append(iss)
    have = {i['key'] for i in issues}
    for key, m in modules.items():
        if key not in have and protocols.rule_matches(m.applies_when, flags):
            issues.append({'key': key, 'label': m.label, 'source': 'protocol', 'goal': '', 'directions': '',
                           'services': [], 'new_since_last': True})
    who = (prev.user.display_name or prev.user.username) if prev.user else ''
    return {
        'issues': issues,
        'modifiers': dict(old.get('modifiers', {})),
        'review_interval': old.get('review_interval', DEFAULT_REVIEW),
        'consent': {**{k: False for k in CONSENT}, 'withheld': ''},
        'notes': old.get('notes', ''),
        'format': old.get('format', 'tabular'),
        'carried_from': {'session_id': prev.id, 'date': prev.confirmed_at.strftime('%d/%m/%Y'), 'by': who},
    }


def decisions(session: GpccmpSession) -> dict:
    try:
        return json.loads(session.decisions_json) if session.decisions_json else {}
    except (TypeError, ValueError):
        return {}


# ── The form ──────────────────────────────────────────────────────────────────

def issue_choices(version, flags: dict) -> list[dict]:
    """The protocol's condition modules, ticked where their rule matches a coded condition."""
    out = []
    for m in (version.modules if version else []):
        coded = protocols.rule_matches(m.applies_when, flags)
        out.append({'key': m.condition_key, 'label': m.label, 'coded': coded, 'module': m,
                    'services': list(m.services or [])})
    return out


def parse_form(form, version, eligibility=None) -> dict:
    """The decisions from the posted form. Only services the module offers, or ones the GP
    typed, are kept."""
    modules = {m.condition_key: m for m in (version.modules if version else [])}
    plan_type = form.get('plan_type') or plan_type_from_eligibility(eligibility)
    if plan_type not in PLAN_TYPES:
        raise DecisionError('Choose the plan type.')
    issues = []
    for key in form.getlist('issue'):
        m = modules.get(key)
        if m is None:
            continue
        offered = list(m.services or [])
        services = []
        for i, name in enumerate(offered):
            if form.get(f'svc_{key}_{i}'):
                services.append({'name': name, 'purpose': _text(form.get(f'svcp_{key}_{i}'), 300)})
        other = _text(form.get(f'svc_other_{key}'), 300)
        if other:
            services.append({'name': other, 'purpose': _text(form.get(f'svcp_other_{key}'), 300)})
        issues.append({'key': key, 'label': m.label, 'source': 'protocol', 'goal': _text(form.get(f'goal_{key}'), 500),
                       'directions': _text(form.get(f'dir_{key}')), 'services': services,
                       **_progress(form, f'progress_{key}', f'progress_note_{key}')})
    for n in range(MAX_FREE_ISSUES):
        label = _text(form.get(f'free_label_{n}'), 150)
        if not label:
            continue
        services = []
        svc = _text(form.get(f'free_svc_{n}'), 300)
        if svc:
            services.append({'name': svc, 'purpose': _text(form.get(f'free_svcp_{n}'), 300)})
        issues.append({'key': f'free_{n}', 'label': label, 'source': 'gp', 'goal': _text(form.get(f'free_goal_{n}'), 500),
                       'directions': _text(form.get(f'free_dir_{n}')), 'services': services,
                       **_progress(form, f'free_progress_{n}', f'free_progress_note_{n}')})
    review = form.get('review_interval') or DEFAULT_REVIEW
    if review not in REVIEW_INTERVALS:
        raise DecisionError('Choose a review interval from the list.')
    fmt = form.get('format') or 'tabular'
    if fmt not in FORMATS:
        raise DecisionError('Choose an output format.')
    return {
        'plan_type': plan_type,
        'issues': issues,
        'modifiers': {**{k: bool(form.get(f'mod_{k}')) for k in MODIFIERS},
                      'carer': _text(form.get('mod_carer'), 200),
                      'adherence': _text(form.get('mod_adherence'), 500),
                      'declined': _text(form.get('mod_declined'), 500)},
        'review_interval': review,
        'consent': {**{k: bool(form.get(f'consent_{k}')) for k in CONSENT},
                    'withheld': _text(form.get('consent_withheld'), 500)},
        'notes': _text(form.get('notes')),
        'format': fmt,
    }


def _progress(form, word_field: str, note_field: str) -> dict:
    """A review's progress for one issue (ADR-175): the GP's word and an optional note."""
    from app.services.gpccmp_review_service import PROGRESS_WORDS
    word = (form.get(word_field) or '').strip()
    if word and word not in PROGRESS_WORDS:
        raise DecisionError('Choose a progress word from the list.')
    out = {}
    if word:
        out['progress'] = word
    note = _text(form.get(note_field), 500)
    if note:
        out['progress_note'] = note
    return out


def problems(d: dict) -> list[str]:
    """What stops 'Proceed with GPCCMP'. Consent is not required here: it is often recorded
    with the patient after the draft, and the AI never states it unless it is ticked."""
    out = []
    if not d.get('issues'):
        out.append('Choose at least one issue for the plan.')
    if d.get('plan_type') == 'review':
        missing = [i['label'] for i in d.get('issues', []) if not i.get('progress')]
        if missing:
            out.append('Record progress for each issue (or "not assessed"): ' + ', '.join(missing) + '.')
    if d.get('modifiers', {}).get('cognitive') and not d['modifiers'].get('carer'):
        out.append('Name the carer or substitute decision-maker (cognitive impairment is ticked).')
    return out


def save(session: GpccmpSession, d: dict, proceed: bool = False) -> GpccmpSession:
    if session.status not in (SessionStatus.draft, SessionStatus.ready):
        raise DecisionError('This plan has already been drafted; start a new one.')
    carried = decisions(session).get('carried_from')
    if carried and 'carried_from' not in d:
        d = {**d, 'carried_from': carried}
    session.decisions_json = json.dumps(d)
    session.plan_type = d['plan_type']
    live = protocols.live_version()
    session.protocol_version_id = live.id if live else None
    if proceed:
        blockers = problems(d)
        if blockers:
            db.session.commit()      # keep what was entered
            raise DecisionError(' '.join(blockers))
        session.status = SessionStatus.ready
        session.confirmed_at = _now()
    else:
        session.status = SessionStatus.draft
        session.confirmed_at = None
    db.session.commit()
    return session


def abandon(session: GpccmpSession) -> None:
    if session.status in (SessionStatus.draft, SessionStatus.ready):
        session.status = SessionStatus.abandoned
        db.session.commit()


# ── The block the AI will receive (phase 4) ──────────────────────────────────

def decisions_block(d: dict, targets: list[dict], version=None) -> str:
    """The GP's decisions as labelled text: what phase 4 gives the AI, which it may not
    contradict or add to. targets: [{'measure', 'target', 'basis'}]. No names or identifiers."""
    lines = ['[GP DECISIONS]']
    lines.append(f"Plan type: {PLAN_TYPES.get(d.get('plan_type'), '')}")
    if version:
        lines.append(f'Practice protocol: version {version.version}')
    lines.append('Targets (set by the GP; use exactly as written):')
    for t in targets or []:
        basis = {'default': 'protocol default', 'option': 'protocol option', 'individual': 'individual'}.get(t['basis'], t['basis'])
        lines.append(f"- {t['measure']}: {t['target']} ({basis})")
    if not targets:
        lines.append('- none set')
    mods = d.get('modifiers', {})
    on = [MODIFIERS[k] for k in MODIFIERS if mods.get(k)]
    lines.append('Modifiers: ' + ('; '.join(on) if on else 'none'))
    if mods.get('carer'):
        lines.append(f"Carer / substitute decision-maker: {mods['carer']}")
    if mods.get('adherence'):
        lines.append(f"Conditions limiting adherence: {mods['adherence']}")
    if mods.get('declined'):
        lines.append(f"Declined by the patient: {mods['declined']}")
    lines.append('Issues in scope (only these):')
    for i, iss in enumerate(d.get('issues', []), 1):
        lines.append(f"{i}. {iss['label']} (key: {iss['key']})" + (' (added by the GP)' if iss.get('source') == 'gp' else ''))
        if iss.get('goal'):
            lines.append(f"   Goal (patient's words): {iss['goal']}")
        if iss.get('directions'):
            lines.append(f"   GP directions: {iss['directions']}")
        for s in iss.get('services', []):
            lines.append(f"   Service / referral: {s['name']}" + (f" (purpose: {s['purpose']})" if s.get('purpose') else ''))
    lines.append(f"Review: in {d.get('review_interval', DEFAULT_REVIEW)}")
    c = d.get('consent', {})
    lines.append('Consent and agreement (as recorded by the GP):')
    for k, label in CONSENT.items():
        lines.append(f"- {label}: {'yes' if c.get(k) else 'not recorded'}")
    if c.get('withheld'):
        lines.append(f"- Information the patient wants withheld: {c['withheld']}")
    if d.get('notes'):
        lines.append(f"Other GP notes: {d['notes']}")
    lines.append(f"Format: {FORMATS.get(d.get('format'), 'Tabular')}")
    lines.append('[/GP DECISIONS]')
    return '\n'.join(lines)


def targets_for_block(patient_id: int) -> list[dict]:
    from app.services import patient_target_service
    rows = patient_target_service.current_targets(patient_id).values()
    return [{'measure': t.measure.label, 'target': t.value_text, 'basis': t.basis.value}
            for t in sorted(rows, key=lambda t: (t.measure.display_order, t.measure.id))]
