"""Patient targets (ADR-172): each patient's current target per measure, set by their GP.

The practice protocol (ADR-171) supplies the options and a preselect rule over coded conditions.
The GP confirms the preselected option, chooses another, or sets an individual value; nothing is
stored until they confirm. Rows are append-only: a change closes the current row and adds a new one.
MedUI never sets a target itself and never says whether one is met.
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.protocol import (MeasureScope, PatientTarget, ProtocolMeasure, ProtocolOption,
                                 TargetBasis)
from app.services import protocol_service as protocols

# Disease Profile flag → how a GP reads it in "why preselected".
FLAG_LABELS = {
    'isDiabetes': 'diabetes', 'isIDDM': 'type 1 diabetes', 'isNIDDM': 'type 2 diabetes', 'isIHD': 'IHD',
    'isHT': 'hypertension', 'isAF': 'atrial fibrillation', 'isCVA': 'stroke/TIA', 'isVasculopathy': 'vasculopathy',
    'isColonCaPolyps': 'colon cancer or polyps', 'isFHCaColon': 'family history of colon cancer',
    'isHypercholesterolaemia': 'hypercholesterolaemia', 'isCardiomyopathy': 'cardiomyopathy',
    'isCovid19': 'COVID-19', 'isPacemaker': 'pacemaker', 'isCKDRecorded': 'CKD',
    'isFH': 'familial hypercholesterolaemia', 'isRevascularisation': 'revascularisation',
}

SET_LEVEL = 5      # doctors set and change targets
VIEW_LEVEL = 3     # nurses see them


class TargetError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def can_view(user) -> bool:
    return bool(user.is_authenticated and user.has_level(VIEW_LEVEL))


def can_set(user) -> bool:
    return bool(user.is_authenticated and user.has_level(SET_LEVEL))


def current_targets(patient_id: int) -> dict[int, PatientTarget]:
    rows = PatientTarget.query.filter_by(patient_id=patient_id, superseded_at=None).all()
    return {t.measure_id: t for t in rows}


def history(patient_id: int) -> dict[int, list[PatientTarget]]:
    """Every target ever set for this patient, newest first, by measure."""
    out: dict[int, list] = {}
    for t in (PatientTarget.query.filter_by(patient_id=patient_id)
              .order_by(PatientTarget.set_at.desc(), PatientTarget.id.desc()).all()):
        out.setdefault(t.measure_id, []).append(t)
    return out


def why_text(option, flags: dict, version) -> str:
    """'Practice protocol v1: IHD, diabetes coded', or the fallback wording."""
    if option is None:
        return ''
    rule = option.default_rule or {}
    found = protocols.matching_flags(rule, flags)
    vtag = f'Practice protocol v{version.version}' if version else 'Practice protocol'
    if found:
        return f'{vtag}: {", ".join(FLAG_LABELS.get(f, f) for f in found)} coded'
    if rule.get('always'):
        return f'{vtag}: the default for everyone else'
    return vtag


def one_per_label(options: list, default=None, current=None) -> list:
    """The options a GP chooses between, one per label (ADR-182). A wizard-built protocol has one row per
    patient group, so the same target can appear more than once; the GP sees it once, as the row that
    is preselected for this patient (or holds the current target), else the first by priority."""
    current_id = getattr(current, 'option_id', None)
    default_id = default.id if default else None
    chosen = {}
    for o in sorted(options, key=lambda o: (o.id != current_id, o.id != default_id, o.priority, o.id or 0)):
        chosen.setdefault(o.label.strip().lower(), o)
    picked = {o.id for o in chosen.values()}
    return [o for o in options if o.id in picked]


def build_rows(patient_id: int, flags: dict, latest: dict | None = None) -> dict:
    """What the targets screen shows.

    rows: one per measure that is relevant (a protocol option is preselected for these coded
    conditions) or already has a target. addable: the other active measures, for "Add a measure".
    latest: {token_key: fetch_values row} for the latest value beside each target."""
    version = protocols.live_version()
    by_measure = protocols.options_by_measure(version)
    current = current_targets(patient_id)
    hist = history(patient_id)
    latest = latest or {}
    rows, addable = [], []
    for m in protocols.measures():
        options = by_measure.get(m.id, [])
        default = protocols.default_option(options, flags) if m.scope == MeasureScope.protocol else None
        options = one_per_label(options, default, current.get(m.id))
        row = {
            'measure': m, 'options': options, 'default': default,
            'why': why_text(default, flags, version), 'current': current.get(m.id),
            'history': hist.get(m.id, [])[1:] if current.get(m.id) else hist.get(m.id, []),
            'latest': latest.get(m.token_key) if m.token_key else None,
        }
        (rows if (default or row['current']) else addable).append(row)
    return {'version': version, 'rows': rows, 'addable': addable}


def latest_values(patient_id: int, measures: list[ProtocolMeasure]) -> dict:
    """{token_key: latest value row} from Best Practice through the care-plan tokens (ADR-129).
    Empty if BP can't be read: the screen still works without them."""
    from app.models.careplan import CareplanResultToken
    by_key = {t.key: t for t in CareplanResultToken.query.filter_by(active=True).all()}
    # A link that no longer passes the check shows no value rather than the wrong test's.
    keys = [m.token_key for m in measures
            if m.token_key and protocols.link_status(m, by_key) in (protocols.LINK_OK, protocols.LINK_UNCHECKED)]
    if not keys:
        return {}
    from app.services import careplan_service
    try:
        return {v['key']: v for v in careplan_service.fetch_values(patient_id, keys)}
    except Exception as exc:  # BPSDB boundary: the values are shown for reference only
        current_app.logger.warning('patient targets: latest values unavailable: %s', type(exc).__name__)
        return {}


def confirm(patient_id: int, user, choices: list[dict], flags: dict, context: str = 'standalone') -> list[PatientTarget]:
    """Store the GP's choices. Each choice: {measure_id, option_id | None, value_text, reason}.
    option_id None means an individual value. A choice that repeats the current target is skipped.
    All or nothing: one bad choice stores none."""
    if not can_set(user):
        raise TargetError('Only a doctor can set or change targets.')
    version = protocols.live_version()
    by_measure = protocols.options_by_measure(version)
    current = current_targets(patient_id)
    try:
        new_rows = _apply(patient_id, user, choices, flags, context, version, by_measure, current)
    except TargetError:
        db.session.rollback()
        raise
    db.session.commit()
    return new_rows


def _apply(patient_id, user, choices, flags, context, version, by_measure, current) -> list[PatientTarget]:
    new_rows = []
    for c in choices:
        measure = db.session.get(ProtocolMeasure, int(c['measure_id']))
        if measure is None or not measure.active:
            raise TargetError('Unknown measure.')
        value = (c.get('value_text') or '').strip()
        reason = (c.get('reason') or '').strip() or None
        option = None
        if c.get('option_id'):
            option = db.session.get(ProtocolOption, int(c['option_id']))
            if option is None or option not in by_measure.get(measure.id, []):
                raise TargetError(f'{measure.label}: that option is not in the protocol in use.')
            if option.gp_sets:
                if not value:
                    raise TargetError(f'{measure.label}: enter the target you are setting.')
                basis = TargetBasis.individual
            else:
                value = option.label
                default = protocols.default_option(by_measure.get(measure.id, []), flags)
                basis = TargetBasis.default if default is not None and default.id == option.id else TargetBasis.option
        else:
            if not value:
                raise TargetError(f'{measure.label}: enter the individual target.')
            basis = TargetBasis.individual
        if len(value) > 300:
            raise TargetError(f'{measure.label}: the target is too long.')
        prev = current.get(measure.id)
        if prev and prev.value_text == value and prev.option_id == (option.id if option else None):
            continue
        row = PatientTarget(patient_id=patient_id, measure_id=measure.id, option_id=option.id if option else None,
                            value_text=value, basis=basis, reason=reason, set_by_id=user.id, set_at=_now(),
                            protocol_version_id=version.id if version else None, context=context)
        db.session.add(row)
        db.session.flush()
        if prev:
            prev.superseded_at = row.set_at
            prev.superseded_by_id = row.id
        new_rows.append(row)
    return new_rows
