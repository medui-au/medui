"""Practice protocols (ADR-171): versions, rules and editing.

One approved version is live at a time. Changes are made in a draft version: a copy of the live
one (or the first, seeded). Approving a draft retires the version it replaces. Approved and retired
versions are never edited, so a patient's target can always be traced to the exact option and
wording that applied when it was set.

Rules are small JSON objects over the Disease Profile flags (condition_codes.FLAGS):
  {"any": [...]}  at least one flag set
  {"all": [...]}  every flag set
  {"none": [...]} no flag set
  {"always": true} always (a fallback default)
Parts combine with AND. An empty or missing rule never matches.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.extensions import db
from app.models.careplan import CareplanGuideline
from app.models.protocol import (MeasureScope, ProtocolMeasure, ProtocolModule, ProtocolOption,
                                 ProtocolOptionCitation, ProtocolPreventionRule, ProtocolStatus,
                                 ProtocolVersion)
from app.services.condition_codes import FLAGS

RULE_KEYS = ('any', 'all', 'none', 'always')


class ProtocolError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


# ── Rules ─────────────────────────────────────────────────────────────────────

def validate_rule(rule) -> dict | None:
    """The rule, checked: known keys and known flags only. None stays None."""
    if rule in (None, '', {}):
        return None
    if not isinstance(rule, dict):
        raise ProtocolError('A rule must be an object such as {"any": ["isDiabetes"]}.')
    unknown = set(rule) - set(RULE_KEYS)
    if unknown:
        raise ProtocolError(f'Unknown rule part: {", ".join(sorted(unknown))}.')
    for part in ('any', 'all', 'none'):
        flags = rule.get(part)
        if flags is None:
            continue
        if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
            raise ProtocolError(f'"{part}" must be a list of flags.')
        bad = [f for f in flags if f not in FLAGS]
        if bad:
            raise ProtocolError(f'Unknown flag: {", ".join(bad)}. Known: {", ".join(sorted(FLAGS))}.')
    if 'always' in rule and rule['always'] is not True:
        raise ProtocolError('"always" can only be true.')
    return rule


def rule_matches(rule, flags: dict) -> bool:
    """Does the rule hold for these Disease Profile flags ({flag: 0|1})?"""
    if not rule:
        return False
    on = {k for k, v in (flags or {}).items() if v}
    checks = []
    if rule.get('always'):
        checks.append(True)
    if 'any' in rule:
        checks.append(bool(on & set(rule['any'])))
    if 'all' in rule:
        checks.append(set(rule['all']) <= on)
    if 'none' in rule:
        checks.append(not (on & set(rule['none'])))
    return bool(checks) and all(checks)


def matching_flags(rule, flags: dict) -> list[str]:
    """The set flags that made an any/all rule match, for the 'why preselected' line."""
    if not rule:
        return []
    on = {k for k, v in (flags or {}).items() if v}
    wanted = set(rule.get('any', [])) | set(rule.get('all', []))
    return sorted(on & wanted)


def default_option(options: list, flags: dict):
    """The first option, by priority, whose rule matches; None if none does."""
    for opt in sorted(options, key=lambda o: (o.priority, o.id or 0)):
        if rule_matches(opt.default_rule, flags):
            return opt
    return None


# ── Versions ──────────────────────────────────────────────────────────────────

def live_version() -> ProtocolVersion | None:
    return ProtocolVersion.query.filter_by(status=ProtocolStatus.approved).first()


def draft_version() -> ProtocolVersion | None:
    return ProtocolVersion.query.filter_by(status=ProtocolStatus.draft).first()


def all_versions() -> list[ProtocolVersion]:
    return ProtocolVersion.query.order_by(ProtocolVersion.version.desc()).all()


def _next_number() -> int:
    top = db.session.query(db.func.max(ProtocolVersion.version)).scalar()
    return (top or 0) + 1


def start_draft(user, note: str = '') -> ProtocolVersion:
    """A new draft, copied from the live version (or empty if there is none)."""
    if draft_version():
        raise ProtocolError('There is already a draft version. Approve or discard it first.')
    live = live_version()
    draft = ProtocolVersion(version=_next_number(), status=ProtocolStatus.draft, change_note=note or None,
                            copied_from_id=live.id if live else None, created_by_id=user.id)
    db.session.add(draft)
    db.session.flush()
    if live:
        _copy_children(live, draft)
    db.session.commit()
    return draft


def _copy_children(src: ProtocolVersion, dst: ProtocolVersion) -> None:
    for o in src.options:
        new = ProtocolOption(version_id=dst.id, measure_id=o.measure_id, code=o.code, label=o.label,
                             plan_wording=o.plan_wording, patient_group=o.patient_group,
                             default_rule=o.default_rule, priority=o.priority, gp_sets=o.gp_sets,
                             rationale=o.rationale)
        db.session.add(new)
        db.session.flush()
        for c in o.citations:
            db.session.add(ProtocolOptionCitation(option_id=new.id, guideline_id=c.guideline_id,
                                                  section_ref=c.section_ref, quote=c.quote))
    for m in src.modules:
        db.session.add(ProtocolModule(
            version_id=dst.id, condition_key=m.condition_key, label=m.label, applies_when=m.applies_when,
            goals=m.goals, measures_text=m.measures_text, monitoring=m.monitoring, services=m.services,
            patient_info=m.patient_info, safety_netting=m.safety_netting, gp_reference=m.gp_reference,
            source_note=m.source_note, display_order=m.display_order))
    for p in src.prevention:
        db.session.add(ProtocolPreventionRule(version_id=dst.id, key=p.key, label=p.label, rule=p.rule,
                                              wording=p.wording, source=p.source, display_order=p.display_order))


def discard_draft() -> None:
    draft = draft_version()
    if not draft:
        raise ProtocolError('There is no draft to discard.')
    db.session.delete(draft)
    db.session.commit()


def approve(user, review_due_on: date, note: str = '') -> ProtocolVersion:
    """Make the draft live. The version it replaces is retired, never deleted."""
    draft = draft_version()
    if not draft:
        raise ProtocolError('There is no draft to approve.')
    if not review_due_on:
        raise ProtocolError('Give the next review date.')
    if review_due_on <= date.today():
        raise ProtocolError('The next review date must be in the future.')
    if not draft.options:
        raise ProtocolError('A protocol needs at least one target option.')
    live = live_version()
    if live:
        live.status = ProtocolStatus.retired
    draft.status = ProtocolStatus.approved
    draft.approved_by_id = user.id
    draft.approved_at = _now()
    draft.review_due_on = review_due_on
    if note:
        draft.change_note = note
    db.session.commit()
    return draft


def _editable(item) -> ProtocolVersion:
    version = item if isinstance(item, ProtocolVersion) else item.protocol_version
    if version.status != ProtocolStatus.draft:
        raise ProtocolError('Only a draft version can be changed. Start a new draft first.')
    return version


# ── Editing a draft ───────────────────────────────────────────────────────────

OPTION_FIELDS = ('label', 'plan_wording', 'patient_group', 'rationale')
MODULE_FIELDS = ('label', 'goals', 'measures_text', 'monitoring', 'patient_info', 'safety_netting',
                 'gp_reference', 'source_note')
PREVENTION_FIELDS = ('label', 'wording', 'source')


def _clean(text) -> str | None:
    text = (text or '').strip()
    return text or None


def update_option(option: ProtocolOption, data: dict) -> ProtocolOption:
    _editable(option)
    for f in OPTION_FIELDS:
        if f in data:
            setattr(option, f, _clean(data[f]))
    if not option.label:
        raise ProtocolError('An option needs a label.')
    if 'default_rule' in data:
        option.default_rule = validate_rule(data['default_rule'])
    if 'priority' in data:
        try:
            option.priority = int(data['priority'])
        except (TypeError, ValueError):
            raise ProtocolError('Priority must be a whole number.')
    if 'gp_sets' in data:
        option.gp_sets = bool(data['gp_sets'])
    db.session.commit()
    return option


def add_option(version: ProtocolVersion, measure: ProtocolMeasure, data: dict) -> ProtocolOption:
    _editable(version)
    code = _clean(data.get('code')) or ''
    if not code:
        raise ProtocolError('An option needs a short code.')
    if any(o.code == code for o in version.options):
        raise ProtocolError('That code is already used in this version.')
    option = ProtocolOption(version_id=version.id, measure_id=measure.id, code=code,
                            label=_clean(data.get('label')) or code, priority=100)
    db.session.add(option)
    db.session.flush()
    return update_option(option, data)


def delete_option(option: ProtocolOption) -> None:
    _editable(option)
    db.session.delete(option)
    db.session.commit()


def update_module(module: ProtocolModule, data: dict) -> ProtocolModule:
    _editable(module)
    for f in MODULE_FIELDS:
        if f in data:
            setattr(module, f, _clean(data[f]))
    if not module.label:
        raise ProtocolError('A module needs a label.')
    if 'applies_when' in data:
        module.applies_when = validate_rule(data['applies_when'])
    if 'services' in data:
        services = data['services']
        if isinstance(services, str):
            services = [s.strip() for s in services.splitlines() if s.strip()]
        module.services = services or []
    db.session.commit()
    return module


def update_prevention(rule: ProtocolPreventionRule, data: dict) -> ProtocolPreventionRule:
    _editable(rule)
    for f in PREVENTION_FIELDS:
        if f in data:
            setattr(rule, f, _clean(data[f]) or ('' if f == 'wording' else None))
    if 'rule' in data:
        if not isinstance(data['rule'], dict):
            raise ProtocolError('The rule must be an object.')
        rule.rule = data['rule']
    db.session.commit()
    return rule


def add_citation(option: ProtocolOption, guideline_id: int, section_ref: str = '', quote: str = ''):
    _editable(option)
    if not db.session.get(CareplanGuideline, guideline_id):
        raise ProtocolError('Choose a guideline from the library.')
    c = ProtocolOptionCitation(option_id=option.id, guideline_id=guideline_id,
                               section_ref=_clean(section_ref), quote=_clean(quote))
    db.session.add(c)
    db.session.commit()
    return c


def delete_citation(citation: ProtocolOptionCitation) -> None:
    _editable(citation.option)
    db.session.delete(citation)
    db.session.commit()


# Which care-plan result tokens may feed each measure's "latest value" (ADR-172 guard).
# 'fact': only that record-fact token. 'loinc': every LOINC code on the token must be one of
# these, and its unit must match. A measure with no entry takes no token at all: a matching unit
# alone is not enough (cholesterol, glucose and urate are all mmol/L).
MEASURE_SOURCES = {
    'bp':      {'fact': 'bp'},
    'alcohol': {'fact': 'alcohol'},
    'weight':  {'fact': 'weight'},
    'ldl':     {'loinc': {'22748-8', '39469-2'}, 'unit': 'mmol/L'},                 # LDL-C, moles/volume
    'hba1c':   {'loinc': {'4548-4', '17856-6', 'AUSLAB^A1C'}, 'unit': '%'},         # patient_hba1c_series.sql
    # Codes the practice's laboratories send (counted from results since 2024, ADR-172).
    'urate':   {'loinc': {'14933-6'}, 'unit': 'mmol/L'},                            # serum uric acid
    'uacr':    {'loinc': {'32294-1', '14959-1'}, 'unit': 'mg/mmol'},                # urine albumin/creatinine
}

LINK_OK, LINK_UNCHECKED, LINK_MISMATCH, LINK_NONE, LINK_MISSING = 'ok', 'unchecked', 'mismatch', 'none', 'missing'


def _codes(token) -> set[str]:
    return {str(c).strip() for c in (token.loinc_codes or []) if str(c).strip()}


def _same_unit(a, b) -> bool:
    return bool(a) and bool(b) and str(a).strip().lower() == str(b).strip().lower()


def token_check(measure: ProtocolMeasure, token) -> str:
    """LINK_OK or LINK_MISMATCH. (LINK_UNCHECKED is kept for links made before the check.)"""
    from app.services.careplan_service import FACT_TOKENS
    is_fact = token.key in FACT_TOKENS
    rule = MEASURE_SOURCES.get(measure.key)
    if rule and 'fact' in rule:
        return LINK_OK if token.key == rule['fact'] else LINK_MISMATCH
    if rule and 'loinc' in rule:
        codes = _codes(token)
        if is_fact or not codes or not codes <= rule['loinc']:
            return LINK_MISMATCH
        if token.expected_unit and not _same_unit(token.expected_unit, rule['unit']):
            return LINK_MISMATCH
        return LINK_OK
    return LINK_MISMATCH


def allowed_tokens(measure: ProtocolMeasure, tokens: list) -> list:
    """The active tokens that may be linked to this measure, with their check result."""
    out = []
    for t in tokens:
        status = token_check(measure, t)
        if status != LINK_MISMATCH:
            out.append((t, status))
    return out


def link_status(measure: ProtocolMeasure, tokens_by_key: dict) -> str:
    """How the measure's current link stands: none, ok, unchecked, mismatch, or missing (the
    token isn't there or isn't active)."""
    if not measure.token_key:
        return LINK_NONE
    token = tokens_by_key.get(measure.token_key)
    if token is None:
        return LINK_MISSING
    return token_check(measure, token)


def update_measure(measure: ProtocolMeasure, data: dict) -> ProtocolMeasure:
    """A measure's label, unit and the care-plan result token its latest value comes from
    (ADR-172). Measures aren't versioned: this changes the label everywhere, never a target.
    The token must pass token_check for this measure."""
    from app.models.careplan import CareplanResultToken
    label = _clean(data.get('label'))
    if not label:
        raise ProtocolError('A measure needs a label.')
    unit = _clean(data.get('unit'))
    key = _clean(data.get('token_key'))
    if key:
        token = CareplanResultToken.query.filter_by(key=key, active=True).first()
        if token is None:
            raise ProtocolError('Choose an active result token from the care-plan tokens.')
        probe = SimpleNamespace(key=measure.key, unit=unit)
        if token_check(probe, token) == LINK_MISMATCH:
            raise ProtocolError(f'The token "{key}" does not measure {label}: its codes or unit don\'t match.')
    measure.label, measure.unit, measure.token_key = label, unit, key
    db.session.commit()
    return measure


# ── Guidelines (the care-plan library, ADR-129) ──────────────────────────────

GUIDELINE_FIELDS = ('title', 'publisher', 'edition', 'url', 'licence_note')


def save_guideline(user, data: dict, guideline: CareplanGuideline | None = None) -> CareplanGuideline:
    g = guideline or CareplanGuideline(created_by_id=user.id)
    for f in GUIDELINE_FIELDS:
        if f in data:
            setattr(g, f, _clean(data[f]))
    for f in ('published_on', 'accessed_on'):
        if f in data:
            raw = _clean(data[f])
            try:
                setattr(g, f, date.fromisoformat(raw) if raw else None)
            except ValueError:
                raise ProtocolError(f'{f.replace("_", " ").capitalize()} must be a date (YYYY-MM-DD).')
    if 'superseded_by_id' in data:
        sid = data['superseded_by_id']
        sid = int(sid) if str(sid or '').strip() else None
        if sid and (sid == g.id or not db.session.get(CareplanGuideline, sid)):
            raise ProtocolError('Choose another guideline from the library as the replacement.')
        g.superseded_by_id = sid
    if not g.title:
        raise ProtocolError('A guideline needs a title.')
    if guideline is None:
        db.session.add(g)
    db.session.commit()
    return g


def guideline_uses(guideline_id: int) -> list[ProtocolOption]:
    return (ProtocolOption.query.join(ProtocolOptionCitation)
            .filter(ProtocolOptionCitation.guideline_id == guideline_id).all())


# ── For the screen ────────────────────────────────────────────────────────────

def measures() -> list[ProtocolMeasure]:
    return ProtocolMeasure.query.filter_by(active=True).order_by(ProtocolMeasure.display_order,
                                                                 ProtocolMeasure.id).all()


def options_by_measure(version: ProtocolVersion | None) -> dict[int, list[ProtocolOption]]:
    out: dict[int, list] = {}
    for o in (version.options if version else []):
        out.setdefault(o.measure_id, []).append(o)
    return out


def flag_labels() -> list[str]:
    return sorted(FLAGS)


def scope_label(scope: MeasureScope) -> str:
    return 'GPCCMP protocol' if scope == MeasureScope.protocol else 'Individual patients only'


# ── Governance (ADR-176) ──────────────────────────────────────────────────────

def rule_text(rule) -> str:
    """A preselect rule in words, e.g. "any of IHD, stroke/TIA coded"."""
    from app.services.patient_target_service import FLAG_LABELS
    if not rule:
        return 'never preselected (the GP chooses it)'
    if rule.get('always'):
        return 'the default for everyone else'
    name = lambda flags: ', '.join(FLAG_LABELS.get(f, f) for f in flags)
    parts = []
    if rule.get('any'):
        parts.append(f"any of {name(rule['any'])} coded")
    if rule.get('all'):
        parts.append(f"all of {name(rule['all'])} coded")
    if rule.get('none'):
        parts.append(f"none of {name(rule['none'])} coded")
    return '; '.join(parts)


def prevention_rule_text(rule) -> str:
    r = rule or {}
    parts = []
    if r.get('sex'):
        parts.append('women' if r['sex'] == 'F' else 'men')
    if 'age_min' in r and 'age_max' in r:
        parts.append(f"aged {r['age_min']}–{r['age_max']}")
    elif 'age_min' in r:
        parts.append(f"aged {r['age_min']}+")
    elif 'age_max' in r:
        parts.append(f"aged up to {r['age_max']}")
    from app.services.patient_target_service import FLAG_LABELS
    if r.get('flags_any'):
        parts.append('with ' + ' or '.join(FLAG_LABELS.get(f, f) for f in r['flags_any']) + ' coded')
    if r.get('flags_none'):
        parts.append('without ' + ' or '.join(FLAG_LABELS.get(f, f) for f in r['flags_none']) + ' coded')
    if r.get('needs'):
        parts.append({'smoking_history': 'with a recorded smoking history'}.get(r['needs'], f"needing {r['needs']}"))
    return ', '.join(parts) or 'everyone'


def targets_to_review() -> list[dict]:
    """Patients' current targets that need a look at the next plan or review (ADR-176): set under an
    option that the protocol in use no longer has, or has worded differently, or that cites a
    guideline since marked superseded. Individual targets (no option) are the GP's own and aren't
    listed. Newest first."""
    from app.models.protocol import PatientTarget
    live = live_version()
    live_by_code = {o.code: o for o in (live.options if live else [])}
    out = []
    rows = (PatientTarget.query.filter(PatientTarget.superseded_at.is_(None), PatientTarget.option_id.isnot(None))
            .order_by(PatientTarget.set_at.desc()).all())
    for t in rows:
        reasons = []
        opt = t.option
        now = live_by_code.get(opt.code) if opt else None
        if live and opt and opt.version_id != live.id:
            if now is None:
                reasons.append(f'the option "{opt.label}" is no longer in protocol v{live.version}')
            elif now.label != t.value_text:
                reasons.append(f'protocol v{live.version} now reads "{now.label}"')
        for c in (opt.citations if opt else []):
            if c.guideline.superseded_by_id:
                reasons.append(f'cites "{c.guideline.title}", marked superseded')
        if reasons:
            out.append({'target': t, 'reasons': reasons})
    return out
