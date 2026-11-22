"""Care plan builder (ADR-129). Design: plans/careplan_data_model.md.

The doctor composes the plan; this service fills facts and keeps the record. It never infers an
issue, picks a target or variant for a patient, ranks problems, or says whether a target is met.

- Tokens: text holds `{key.last}`, `{key.date}`, `{key.unit}` and `{key.target}`; values come from
  BP results matched by the token's LOINC codes (trimmed: BP pads them); targets from the row's
  recipe. Nothing is converted: a different unit is reported, not changed.
- Drafts: the whole grid is one encrypted JSON document with a revision number; a save carrying an
  older revision is refused.
- Filing writes rows (text with tokens) and the confirmed values, stores the exact HTML and its
  SHA-256, and supersedes the previous filed plan. Filed plans never change; they can be voided.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone

from flask import current_app, render_template
from markupsafe import Markup, escape

from app.extensions import db
from app.utils.bmi import bmi_height
from app.models.careplan import (Careplan, CareplanEvent, CareplanGuideline, CareplanRecipe,
                                 CareplanRecipeCitation, CareplanRecipeTarget, CareplanRecipeVersion,
                                 CareplanResultToken, CareplanRow, CareplanStatus, CareplanValue,
                                 RecipeScope, RecipeStatus)

DRAFT_SCHEMA = 1
DEFAULT_ROWS = 6
MAX_ROWS = 20
MAX_FIELD = 4000
TOKEN_RE = re.compile(r'\{([a-z][a-z0-9_]{0,39})\.(last|date|unit|target)\}')
_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
ROW_FIELDS = ('goals', 'management', 'providers')


class DraftConflict(Exception):
    """The draft was saved elsewhere since this page loaded."""


class CareplanError(ValueError):
    """A request the service refuses, with a message for the user."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(action: str, user_id: int | None, careplan_id: int | None = None,
           recipe_id: int | None = None, **detail) -> None:
    db.session.add(CareplanEvent(careplan_id=careplan_id, recipe_id=recipe_id, action=action,
                                 user_id=user_id, detail=detail or None))


# ── Issue keys and tokens ─────────────────────────────────────────────────────

def issue_key(label: str) -> str:
    """'Type 2 Diabetes (L)' → 'type_2_diabetes': used to match coded history to recipes."""
    s = re.sub(r'\((?:l|r|bilateral)\)\s*$', '', (label or '').strip().lower())
    return re.sub(r'[^a-z0-9]+', '_', s).strip('_')[:80]


def tokens_in(*texts: str) -> list[str]:
    keys: list[str] = []
    for t in texts:
        for key, _part in TOKEN_RE.findall(t or ''):
            if key not in keys:
                keys.append(key)
    return keys


def _trim(code) -> str:
    return str(code or '').strip()


def _as_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def norm_unit(unit: str | None) -> str:
    """A unit's spelling for comparison only: case, spaces and the ways labs write m² ignored."""
    u = re.sub(r'\s+', '', (unit or '').lower()).replace('*', '').replace('^', '')
    u = re.sub(r'(sqm|m2|sq\.m)$', 'm2', u)
    return re.sub(r'creat(inine)?$', '', u)


def pick_latest(rows: list[dict], token, today: date) -> dict:
    """The newest result for a token from patient_result_history rows, as the laboratory wrote it."""
    codes = {_trim(c) for c in (token.loinc_codes or []) if _trim(c)}
    matches = [r for r in rows if _trim(r.get('LoincCode')) in codes and _as_date(r.get('ReportDate'))]
    out = {'key': token.key, 'label': token.label, 'value': None, 'unit': None, 'date': None,
           'loinc': None, 'status': 'not_found'}
    if not matches:
        return out
    r = max(matches, key=lambda r: _as_date(r.get('ReportDate')))
    when = _as_date(r.get('ReportDate'))
    unit = (r.get('Units') or '').strip() or None
    out.update(value=(r.get('ResultValue') or '').strip(), unit=unit, date=when.isoformat(),
               loinc=_trim(r.get('LoincCode')), status='found')
    # A blank unit is unknown, not different: some laboratories leave it out (ADR-129).
    if token.expected_unit and unit and norm_unit(unit) != norm_unit(token.expected_unit):
        out['status'] = 'unit_mismatch'
    elif token.max_age_days and (today - when).days > token.max_age_days:
        out['status'] = 'stale'
    return out


def _fmt_date(iso: str | None) -> str:
    d = _as_date(iso) if iso else None
    return d.strftime('%d/%m/%Y') if d else ''


def render_text(text: str, values: dict, targets: dict, missing: str = '—') -> str:
    """Fill tokens. values: {key: {value, unit, date}}; targets: {key: target_text}."""
    def sub(m):
        key, part = m.group(1), m.group(2)
        if part == 'target':
            return targets.get(key) or missing
        v = values.get(key) or {}
        if part == 'last':
            return f"{v['value']} {v.get('unit') or ''}".strip() if v.get('value') else missing
        if part == 'date':
            return _fmt_date(v.get('date')) or missing
        return v.get('unit') or missing
    return TOKEN_RE.sub(sub, text or '')


def ensure_fact_tokens() -> None:
    """Create the record-fact tokens once (ADR-129 addendum); an administrator may relabel or deactivate them."""
    have = {k for (k,) in db.session.query(CareplanResultToken.key).all()}
    missing = [k for k in FACT_TOKENS if k not in have]
    for k in missing:
        label, unit, _ = FACT_TOKENS[k]
        db.session.add(CareplanResultToken(key=k, label=label, loinc_codes=[], expected_unit=unit or None,
                                           active=True))
    if missing:
        db.session.commit()


def active_tokens() -> dict[str, CareplanResultToken]:
    return {t.key: t for t in CareplanResultToken.query.filter_by(active=True).all()}


def shared_codes(token: CareplanResultToken) -> dict[str, list[str]]:
    """Other tokens that use any of this token's LOINC codes: {other key: [codes]}."""
    mine = {_trim(c) for c in token.loinc_codes or []}
    out = {}
    for t in CareplanResultToken.query.filter(CareplanResultToken.id != token.id).all():
        both = sorted(mine & {_trim(c) for c in t.loinc_codes or []})
        if both:
            out[t.key] = both
    return out


# ── BP data ───────────────────────────────────────────────────────────────────

def _bp_session():
    from app.sql.query_loader import ReadOnlySession
    uri = current_app.config.get('BPSDB_URI')
    if not uri:
        raise RuntimeError('BPSDB_URI not configured')
    return ReadOnlySession(uri)


def _bp_section(patient_id: int, query_name: str, params: int = 1) -> list[dict]:
    from app.repositories.patient_repository import PatientRepository
    with _bp_session() as sess:
        return PatientRepository(sess).get_section(query_name, patient_id, params)


def coded_history(patient_id: int) -> list[dict]:
    """The patient's coded history, newest first, one entry per item text."""
    seen, out = set(), []
    for r in _bp_section(patient_id, 'patient_history'):
        label = (r.get('ItemText') or '').strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        out.append({'label': label.title() if label.isupper() else label,
                    'year': (r.get('YR') or '').strip(), 'key': issue_key(label)})
    return out


def contact_line(rows: list[dict]) -> str:
    """One contact for the plan's header (ADR-180): the Emergency Contact, else the Next of Kin,
    with relationship and phone numbers, as recorded in BP. '' if there is none."""
    if not rows:
        return ''
    r = rows[0]
    name = ' '.join(x for x in ((r.get('FIRSTNAME') or '').strip(), (r.get('SURNAME') or '').strip()) if x)
    if not name:
        return ''
    kind = 'Emergency contact' if str(r.get('TYPE')) == '2' else 'Next of kin'
    rel = (r.get('RELATIONSHIP') or '').strip()
    phones = ', '.join(dict.fromkeys(p for p in ((r.get('PHONE1') or '').strip(), (r.get('PHONE2') or '').strip()) if p))
    return f"{kind}: {name}" + (f" ({rel})" if rel else '') + (f", {phones}" if phones else '')


def default_header(patient_id: int) -> str:
    """A starting medical-history header from BP, for the doctor to edit."""
    parts = []
    try:
        hist = coded_history(patient_id)
        if hist:
            parts.append('History: ' + '; '.join(
                f"{h['label']}{' (' + h['year'] + ')' if h['year'] else ''}" for h in hist))
        meds = _bp_section(patient_id, 'patient_medications')
        if meds:
            parts.append('Medications: ' + '; '.join(
                ' '.join(filter(None, [(m.get('DRUGNAME') or '').strip().title(),
                                       (m.get('DOSESTRING') or '').strip().lower()])) for m in meds))
        allergies = _bp_section(patient_id, 'patient_allergies')
        parts.append('Allergies: ' + ('; '.join(
            ' '.join(filter(None, [a.get('ItemName'), f"({a['Reaction']})" if a.get('Reaction') else None]))
            for a in allergies) if allergies else 'none recorded'))
        contact = contact_line(_bp_section(patient_id, 'patient_careplan_contact'))
        if contact:
            parts.append(contact)
    except Exception as exc:  # BP unreachable: the doctor writes the header
        current_app.logger.warning('careplan header from BP failed: %s', type(exc).__name__)
    return '\n'.join(parts)


# Tokens filled from the record rather than a pathology result: key -> (label, unit, dated).
# Values are as recorded, or arithmetic on recorded values (BMI, weight beside the BMI 20 to 25
# range); none says whether a value is good or bad.
FACT_TOKENS = {
    'bp':            ('Blood pressure', 'mmHg', True),
    'weight':        ('Weight', 'kg', True),
    'height':        ('Height', 'm', True),
    'bmi':           ('BMI', 'kg/m2', True),
    'weight_excess': ('Weight above BMI 25 (+) or below BMI 20 (-)', 'kg', True),
    'age':           ('Age', '', False),
    'sex':           ('Sex', '', False),
    'alcohol':       ('Alcohol (standard drinks per week)', '', False),
    'smoking':       ('Smoking status', '', False),
}
_DEMOGRAPHIC_FACTS = {'weight', 'height', 'bmi', 'weight_excess', 'age', 'sex'}


def _num(v) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _iso(v) -> str | None:
    d = _as_date(v) if v else None
    return d.isoformat() if d else None


def facts_from(demo: dict | None, bp_rows: list[dict] | None, social: dict | None,
               today: date) -> dict[str, tuple]:
    """Record facts as {key: (value, unit, iso date or None)}; a key with nothing recorded is left out."""
    demo, social, out = demo or {}, social or {}, {}
    rows = [r for r in (bp_rows or []) if _as_date(r.get('ReportDate')) and r.get('Systolic') and r.get('Diastolic')]
    if rows:
        r = max(rows, key=lambda r: _as_date(r.get('ReportDate')))
        out['bp'] = (f"{r['Systolic']}/{r['Diastolic']}", 'mmHg', _iso(r.get('ReportDate')))
    w, h = _num(demo.get('WEIGHTVALUE')), _num(demo.get('HEIGHTVALUE'))
    w_date = _iso(demo.get('WEIGHT_DATE'))
    if w:
        out['weight'] = (f'{w:g}', 'kg', w_date)
    if h:
        out['height'] = (f'{h:.2f}', 'm', _iso(demo.get('HEIGHT_DATE')))
    bh = bmi_height(demo)        # not a childhood height for an adult
    if w and bh:
        h = bh
        out['bmi'] = (f'{w / (h * h):.1f}', 'kg/m2', w_date)
        low, high = 20 * h * h, 25 * h * h
        diff = f'+{w - high:.0f}' if w > high else (f'-{low - w:.0f}' if w < low else '0')
        out['weight_excess'] = (diff, 'kg', w_date)
    age = str(demo.get('CLINICAL_AGE') or '').strip()
    if age and age != 'Future':
        out['age'] = (age[:-1], 'years', today.isoformat()) if age.endswith('y') else (age, '', today.isoformat())
    sex = str(demo.get('GENDER') or '').strip()
    if sex and sex != 'Unknown':
        out['sex'] = (sex, '', None)
    alcohol = str(social.get('ALCOHOLPERWEEK') or '').strip()
    if alcohol and alcohol != 'No Data':
        out['alcohol'] = (alcohol, '', None)
    smoking = str(social.get('SMOKING') or '').strip()
    if smoking:
        out['smoking'] = (smoking, '', None)
    return out


def fact_value(token, facts: dict, today: date) -> dict:
    out = {'key': token.key, 'label': token.label, 'value': None, 'unit': None, 'date': None,
           'loinc': None, 'status': 'not_found'}
    if token.key not in facts:
        return out
    value, unit, when = facts[token.key]
    out.update(value=value, unit=unit or None, date=when, status='found')
    dated = FACT_TOKENS.get(token.key, ('', '', False))[2]
    if dated and when and token.max_age_days and (today - _as_date(when)).days > token.max_age_days:
        out['status'] = 'stale'
    return out


def _record_facts(patient_id: int, keys: set, today: date) -> dict:
    from app.services.clinical_service import ClinicalService
    demo = ClinicalService.get_patient_demographics(patient_id) if keys & _DEMOGRAPHIC_FACTS else None
    bp_rows = _bp_section(patient_id, 'patient_charts_bp') if 'bp' in keys else None
    social = ClinicalService.get_social_history(patient_id) if keys & {'alcohol', 'smoking'} else None
    return facts_from(demo, bp_rows, social, today)


def fetch_values(patient_id: int, keys: list[str], today: date | None = None) -> list[dict]:
    tokens = active_tokens()
    known = [tokens[k] for k in keys if k in tokens]
    results = [t for t in known if t.key not in FACT_TOKENS]
    facts = [t for t in known if t.key in FACT_TOKENS]
    today = today or date.today()
    rows = _bp_section(patient_id, 'patient_result_history', 2) if results else []
    record = _record_facts(patient_id, {t.key for t in facts}, today) if facts else {}
    by_key = {t.key: pick_latest(rows, t, today) for t in results}
    by_key.update({t.key: fact_value(t, record, today) for t in facts})
    out = [by_key[t.key] for t in known]
    out += [{'key': k, 'label': k, 'value': None, 'unit': None, 'date': None, 'loinc': None,
             'status': 'unknown_token'} for k in keys if k not in tokens]
    return out


# ── Recipes ───────────────────────────────────────────────────────────────────

def can_publish_practice(user) -> bool:
    """Practice recipes are published by administrators (the practice's clinical lead)."""
    return bool(getattr(user, 'is_admin', False))


def visible_recipes(user) -> list[CareplanRecipe]:
    q = CareplanRecipe.query.filter(CareplanRecipe.status != RecipeStatus.retired)
    out = [r for r in q.all()
           if (r.scope == RecipeScope.practice and r.status == RecipeStatus.approved)
           or r.owner_id == user.id]
    return sorted(out, key=lambda r: (r.issue_label.lower(), (r.variant_label or '').lower(),
                                      r.scope != RecipeScope.practice))


def recipe_payload(recipe: CareplanRecipe) -> dict:
    v = recipe.current_version
    return {
        'id': recipe.id, 'issue_key': recipe.issue_key, 'issue_label': recipe.issue_label,
        'variant': recipe.variant_label, 'modifiers': recipe.modifiers or {},
        'always_offer': recipe.always_offer, 'scope': recipe.scope.value, 'status': recipe.status.value,
        'version_id': v.id if v else None, 'version': v.version if v else None,
        'goals': v.goals_text if v else '', 'management': v.management_text if v else '',
        'providers': v.providers_text if v else '',
        'targets': {t.token.key: t.target_text for t in (v.targets if v else [])},
        'citations': [{'guideline': c.guideline.title, 'edition': c.guideline.edition,
                       'url': c.guideline.url, 'section': c.section_ref, 'quote': c.quote,
                       'applies_to': c.applies_to} for c in (v.citations if v else [])],
    }


def _clean(s, limit=MAX_FIELD) -> str:
    return (s or '').strip()[:limit]


def _guideline(fields: dict, user_id: int) -> CareplanGuideline | None:
    title = _clean(fields.get('guideline'), 300)
    if not title:
        return None
    edition = _clean(fields.get('edition'), 50) or None
    g = CareplanGuideline.query.filter_by(title=title, edition=edition).first()
    if not g:
        g = CareplanGuideline(title=title, edition=edition, url=_clean(fields.get('url'), 500) or None,
                              accessed_on=date.today(), created_by_id=user_id)
        db.session.add(g)
        db.session.flush()
    return g


def save_recipe(user, data: dict, recipe: CareplanRecipe | None = None) -> CareplanRecipe:
    """Create a recipe or save its text. Editing an approved version makes a new draft version."""
    label = _clean(data.get('issue_label'), 150)
    if not label:
        raise CareplanError('Give the issue a name.')
    scope = RecipeScope.practice if data.get('scope') == 'practice' else RecipeScope.personal
    if scope == RecipeScope.practice and not can_publish_practice(user):
        raise CareplanError('Only an administrator can save a practice recipe.')
    if recipe is None:
        recipe = CareplanRecipe(owner_id=user.id, status=RecipeStatus.draft)
        db.session.add(recipe)
    elif recipe.owner_id != user.id and not (recipe.scope == RecipeScope.practice and can_publish_practice(user)):
        raise CareplanError('You can only edit your own recipes; copy this one to change it.')
    recipe.issue_label = label
    recipe.issue_key = issue_key(_clean(data.get('issue_key'), 80) or label)
    recipe.variant_label = _clean(data.get('variant'), 100) or None
    mods = data.get('modifiers') or {}
    recipe.modifiers = {_clean(k, 40): _clean(v, 60) for k, v in mods.items() if _clean(k, 40)} or None
    recipe.always_offer = bool(data.get('always_offer'))
    recipe.scope = scope
    db.session.flush()

    current = recipe.current_version
    if current is None or current.is_approved:
        current = CareplanRecipeVersion(recipe_id=recipe.id, version=(current.version + 1) if current else 1,
                                        created_by_id=user.id)
        db.session.add(current)
        recipe.current_version = current
        recipe.status = RecipeStatus.draft if recipe.status != RecipeStatus.approved else recipe.status
    current.goals_text = _clean(data.get('goals'))
    current.management_text = _clean(data.get('management'))
    current.providers_text = _clean(data.get('providers'), 1000)
    current.change_note = _clean(data.get('change_note'), 1000) or None
    current.ai_assisted = current.ai_assisted or bool(data.get('ai_assisted'))
    run_uuid = _clean(data.get('authoring_run'), 36)
    if run_uuid:
        from app.models.pipeline import PipelineRun
        run = PipelineRun.query.filter_by(run_uuid=run_uuid, initiated_by_id=user.id).first()
        if run:
            current.authoring_run_id, current.ai_assisted = run.id, True
    rd = data.get('review_due_on')
    current.review_due_on = _as_date(rd) if rd else None
    db.session.flush()

    # targets and their citations, replaced as a set (the version is still a draft)
    for t in list(current.targets):
        db.session.delete(t)
    for c in list(current.citations):
        db.session.delete(c)
    db.session.flush()
    tokens = active_tokens()
    seen = set()
    for t in data.get('targets') or []:
        key = _clean(t.get('token'), 40)
        text = _clean(t.get('target'), 60)
        if not key or not text:
            continue
        if key not in tokens:
            raise CareplanError(f'No result token "{key}". Add it under Result tokens first.')
        if key in seen:
            raise CareplanError(f'"{key}" has two targets. A recipe holds one target per result; '
                                'make a variant for a different situation.')
        seen.add(key)
        g = _guideline(t, user.id)
        cit = None
        if g:
            cit = CareplanRecipeCitation(recipe_version_id=current.id, guideline_id=g.id,
                                         section_ref=_clean(t.get('section'), 100) or None,
                                         quote=_clean(t.get('quote'), 2000) or None, applies_to='target')
            db.session.add(cit)
            db.session.flush()
        db.session.add(CareplanRecipeTarget(recipe_version_id=current.id, token_id=tokens[key].id,
                                            target_text=text, citation_id=cit.id if cit else None))
    for c in data.get('citations') or []:
        g = _guideline(c, user.id)
        if g:
            db.session.add(CareplanRecipeCitation(
                recipe_version_id=current.id, guideline_id=g.id,
                section_ref=_clean(c.get('section'), 100) or None, quote=_clean(c.get('quote'), 2000) or None,
                applies_to=c.get('applies_to') if c.get('applies_to') in ('goals', 'management') else 'management'))
    _event('recipe_saved', user.id, recipe_id=recipe.id, version=current.version)
    db.session.commit()
    return recipe


def approve_recipe(user, recipe: CareplanRecipe) -> None:
    v = recipe.current_version
    if not v or v.is_approved:
        raise CareplanError('Nothing to approve.')
    if recipe.owner_id != user.id and not (recipe.scope == RecipeScope.practice and can_publish_practice(user)):
        raise CareplanError('Only the recipe owner can approve it.')
    unverified = [c for c in v.citations if c.quote and not c.verified_at]
    for c in unverified:            # approving confirms the doctor checked each quoted source
        c.verified_by_id, c.verified_at = user.id, _now()
    v.approved_by_id, v.approved_at = user.id, _now()
    recipe.status = RecipeStatus.approved
    _event('recipe_approved', user.id, recipe_id=recipe.id, version=v.version, citations=len(v.citations))
    db.session.commit()


def copy_recipe(user, recipe: CareplanRecipe) -> CareplanRecipe:
    src = recipe.current_version
    data = recipe_payload(recipe)
    data.update(scope='personal', targets=[
        {'token': t.token.key, 'target': t.target_text,
         'guideline': t.citation.guideline.title if t.citation else None,
         'edition': t.citation.guideline.edition if t.citation else None,
         'url': t.citation.guideline.url if t.citation else None,
         'section': t.citation.section_ref if t.citation else None,
         'quote': t.citation.quote if t.citation else None} for t in (src.targets if src else [])],
        citations=[c for c in data['citations'] if c['applies_to'] != 'target'])
    new = save_recipe(user, data)
    new.copied_from_version_id = src.id if src else None
    db.session.commit()
    return new


def retire_recipe(user, recipe: CareplanRecipe) -> None:
    if recipe.owner_id != user.id and not (recipe.scope == RecipeScope.practice and can_publish_practice(user)):
        raise CareplanError('Only the recipe owner can retire it.')
    recipe.status = RecipeStatus.retired
    _event('recipe_retired', user.id, recipe_id=recipe.id)
    db.session.commit()


def row_to_recipe(user, row: dict) -> CareplanRecipe:
    """Save a plan row's text (tokens, not values) as a new personal recipe, for the doctor to approve."""
    return save_recipe(user, {
        'issue_label': row.get('issue_label'), 'goals': row.get('goals'),
        'management': row.get('management'), 'providers': row.get('providers'), 'scope': 'personal',
        'targets': [{'token': k, 'target': v} for k, v in (row.get('targets') or {}).items()],
        'change_note': 'Saved from a care plan row',
    })


def save_token(data: dict, token: CareplanResultToken | None = None) -> CareplanResultToken:
    if token is not None and token.key in FACT_TOKENS:
        # A record fact keeps its key, source and unit; its label, age and Active can change.
        label = _clean(data.get('label'), 100)
        if not label:
            raise CareplanError('Give the token a label.')
        token.label = label
        try:
            token.max_age_days = int(data['max_age_days']) if data.get('max_age_days') else None
        except (TypeError, ValueError):
            raise CareplanError('Maximum age is a number of days.')
        token.active = data.get('active', True) not in (False, 'false', '0', 0)
        db.session.commit()
        return token
    key = _clean(data.get('key'), 40).lower()
    if not _KEY_RE.match(key):
        raise CareplanError('A token key is lower-case letters, digits and _ , starting with a letter.')
    if key in FACT_TOKENS:
        raise CareplanError(f'"{key}" is filled from the record; it is already in the list.')
    label = _clean(data.get('label'), 100)
    codes = [c.strip() for c in re.split(r'[,\s]+', data.get('loinc_codes') or '') if c.strip()]
    if not label or not codes:
        raise CareplanError('Give the token a label and at least one LOINC code.')
    other = CareplanResultToken.query.filter_by(key=key).first()
    if other and other is not token:
        raise CareplanError(f'Token "{key}" already exists.')
    token = token or CareplanResultToken()
    token.key, token.label, token.loinc_codes = key, label, codes
    token.expected_unit = _clean(data.get('expected_unit'), 30) or None
    try:
        token.max_age_days = int(data['max_age_days']) if data.get('max_age_days') else None
    except (TypeError, ValueError):
        raise CareplanError('Maximum age is a number of days.')
    token.active = data.get('active', True) not in (False, 'false', '0', 0)
    db.session.add(token)
    db.session.commit()
    return token


# ── LOINC pick list ───────────────────────────────────────────────────────────

_CATALOGUE: dict = {}
CATALOGUE_TTL = 6 * 3600


def _norm_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def build_catalogue(rows: list[dict]) -> list[dict]:
    """Fold catalogue rows (code, name, unit, count) by code. Each code lists the names and units it
    was reported under and the codes it may be the same test as: a code that shares a result name
    with it AND a unit. Suggestions only, never chained (a shares with b, b with c, does not make a
    and c related), so % and mmol/mol HbA1c or two different ratios are not offered together."""
    codes: dict[str, dict] = {}
    for r in rows:
        code = _trim(r.get('LoincCode'))
        if not code:
            continue
        c = codes.setdefault(code, {'code': code, 'n': 0, 'last': None, 'names': {}, 'units': {}})
        n = int(r.get('Results') or 0)
        c['n'] += n
        name, unit = (r.get('ResultName') or '').strip(), (r.get('Units') or '').strip()
        if name:
            c['names'][name] = c['names'].get(name, 0) + n
        c['units'][unit] = c['units'].get(unit, 0) + n
        last = _as_date(r.get('LastDate'))
        if last and (not c['last'] or last > c['last']):
            c['last'] = last

    def main_units(c):
        # Units on at least 5% of the code's results; a stray few don't make two codes alike.
        return {norm_unit(u) for u, n in c['units'].items() if u and n * 20 >= c['n']}

    by_name: dict[str, set] = {}
    for c in codes.values():
        c['_units'] = main_units(c)
        for name in c['names']:
            by_name.setdefault(_norm_name(name), set()).add(c['code'])
    out = []
    for c in sorted(codes.values(), key=lambda c: -c['n']):
        related = set()
        for name in c['names']:
            for other in by_name.get(_norm_name(name), ()):
                o = codes[other]
                if other != c['code'] and (c['_units'] & o['_units'] or not (c['_units'] or o['_units'])):
                    related.add(other)
        out.append({
            'code': c['code'], 'n': c['n'], 'last': c['last'].isoformat() if c['last'] else None,
            'names': [k for k, _ in sorted(c['names'].items(), key=lambda kv: -kv[1])][:5],
            'units': [{'unit': u, 'n': n} for u, n in sorted(c['units'].items(), key=lambda kv: -kv[1])],
            'related': sorted(related, key=lambda k: -codes[k]['n']),
        })
    return out


def loinc_catalogue(refresh: bool = False) -> list[dict]:
    """The practice's LOINC codes for the token editor, read from Best Practice at most every 6 hours."""
    import time
    from app.repositories.careplan_repository import CareplanRepository
    if refresh or not _CATALOGUE or time.time() - _CATALOGUE['at'] > CATALOGUE_TTL:
        with _bp_session() as sess:
            rows = CareplanRepository(sess).loinc_catalogue()
        _CATALOGUE.update(at=time.time(), codes=build_catalogue(rows))
    return _CATALOGUE['codes']


# ── Plans ─────────────────────────────────────────────────────────────────────

def last_filed(patient_id: int) -> Careplan | None:
    return (Careplan.query.filter_by(patient_id=patient_id, status=CareplanStatus.filed)
            .order_by(Careplan.filed_at.desc()).first())


def open_draft(patient_id: int) -> Careplan | None:
    return Careplan.query.filter_by(patient_id=patient_id, status=CareplanStatus.draft).first()


def _blank_row() -> dict:
    return {'issue_label': '', 'issue_source': 'free_text', 'recipe_id': None, 'recipe_version_id': None,
            'goals': '', 'management': '', 'providers': '', 'targets': {}, 'edited': False}


def filed_values(plan: Careplan) -> dict:
    return {v.token_key: {'value': v.value_text, 'unit': v.unit,
                          'date': v.result_date.isoformat() if v.result_date else None,
                          'status': v.status, 'label': v.label} for v in plan.values}


def start_draft(patient_id: int, user) -> Careplan:
    """A new draft: a copy of the last filed plan's rows (text with tokens), or blank rows."""
    prev = last_filed(patient_id)
    if prev:
        recipe_of = {v.id: v.recipe_id for v in CareplanRecipeVersion.query.filter(
            CareplanRecipeVersion.id.in_([r.recipe_version_id for r in prev.rows if r.recipe_version_id])).all()}
        rows = [{'issue_label': r.issue_label, 'issue_source': r.issue_source,
                 'recipe_id': recipe_of.get(r.recipe_version_id),
                 'recipe_version_id': r.recipe_version_id, 'goals': r.goals_text or '',
                 'management': r.management_text or '', 'providers': r.providers_text or '',
                 'targets': r.targets or {},
                 'edited': r.edited_from_recipe} for r in prev.rows]
        header = prev.header_text or ''
    else:
        rows = [_blank_row() for _ in range(DEFAULT_ROWS)]
        header = default_header(patient_id)
    plan = Careplan(patient_id=patient_id, author_id=user.id, previous_careplan_id=prev.id if prev else None,
                    status=CareplanStatus.draft, header_text=header, draft_schema=DRAFT_SCHEMA,
                    draft_revision=1, draft_saved_at=_now(), draft_saved_by_id=user.id)
    plan.draft_json = json.dumps({'schema': DRAFT_SCHEMA, 'header': header, 'review_due_on': None,
                                  'rows': rows, 'values': {}})
    db.session.add(plan)
    db.session.flush()
    _event('created', user.id, careplan_id=plan.id, copied=bool(prev), rows=len(rows))
    db.session.commit()
    return plan


def draft_data(plan: Careplan) -> dict:
    return json.loads(plan.draft_json or '{}')


def validate_draft(data: dict) -> dict:
    """Shape and size checks on a draft the page sends; returns the cleaned draft."""
    if not isinstance(data, dict) or not isinstance(data.get('rows'), list):
        raise CareplanError('The plan could not be read.')
    rows = data['rows'][:MAX_ROWS]
    clean_rows = []
    for r in rows:
        if not isinstance(r, dict):
            raise CareplanError('The plan could not be read.')
        row = _blank_row()
        row['issue_label'] = _clean(r.get('issue_label'), 300)
        row['issue_source'] = r.get('issue_source') if r.get('issue_source') in ('coded', 'standing', 'free_text') else 'free_text'
        for f in ROW_FIELDS:
            row[f] = _clean(r.get(f))
        for f in ('recipe_id', 'recipe_version_id'):
            row[f] = r.get(f) if isinstance(r.get(f), int) else None
        targets = r.get('targets') if isinstance(r.get('targets'), dict) else {}
        row['targets'] = {k: _clean(v, 60) for k, v in targets.items() if _KEY_RE.match(str(k))}
        row['edited'] = bool(r.get('edited'))
        clean_rows.append(row)
    values = data.get('values') if isinstance(data.get('values'), dict) else {}
    return {'schema': DRAFT_SCHEMA, 'header': _clean(data.get('header'), 8000),
            'review_due_on': data.get('review_due_on') if _as_date(data.get('review_due_on')) else None,
            'rows': clean_rows, 'values': {k: v for k, v in values.items() if _KEY_RE.match(str(k)) and isinstance(v, dict)}}


def save_draft(plan: Careplan, user, revision: int, data: dict) -> int:
    if plan.status != CareplanStatus.draft:
        raise CareplanError('This plan has been filed and can no longer be changed.')
    if revision != plan.draft_revision:
        raise DraftConflict()
    old_values = draft_data(plan).get('values', {})
    clean = validate_draft(data)
    clean['values'] = old_values      # values change only through the confirmed fetch
    plan.draft_json = json.dumps(clean)
    plan.header_text = clean['header']
    plan.draft_revision += 1
    plan.draft_saved_at, plan.draft_saved_by_id = _now(), user.id
    db.session.commit()
    return plan.draft_revision


def confirm_values(plan: Careplan, user, keys: list[str], manual: dict | None = None) -> dict:
    """Store the latest values for the keys the doctor ticked (re-read from BP, never from the page)."""
    if plan.status != CareplanStatus.draft:
        raise CareplanError('This plan has been filed and can no longer be changed.')
    data = draft_data(plan)
    stamp = _now().isoformat()
    for v in fetch_values(plan.patient_id, [k for k in keys if _KEY_RE.match(k)]):
        if v['status'] in ('found', 'stale', 'unit_mismatch'):
            data['values'][v['key']] = {**v, 'fetched_at': stamp}
    for k, text in (manual or {}).items():
        if _KEY_RE.match(k) and _clean(text, 60):
            data['values'][k] = {'key': k, 'label': k, 'value': _clean(text, 60), 'unit': None,
                                 'date': date.today().isoformat(), 'loinc': None, 'status': 'manual',
                                 'fetched_at': stamp}
    plan.draft_json = json.dumps(data)
    plan.draft_revision += 1
    plan.draft_saved_at, plan.draft_saved_by_id = _now(), user.id
    _event('values_fetched', user.id, careplan_id=plan.id, count=len(keys), manual=len(manual or {}))
    db.session.commit()
    return {'values': data['values'], 'revision': plan.draft_revision}


def completeness(data: dict) -> list[str]:
    """What a used row is missing — the document, not the patient."""
    notes = []
    used = [r for r in data.get('rows', []) if r.get('issue_label')]
    if not used:
        notes.append('No issues entered.')
    for i, r in enumerate(used, 1):
        missing = [f for f in ROW_FIELDS if not (r.get(f) or '').strip()]
        if missing:
            notes.append(f"Row {i} ({r['issue_label']}): no {', '.join(missing)}.")
        unfilled = [k for k in tokens_in(r.get('goals'), r.get('management'))
                    if k not in data.get('values', {})]
        if unfilled:
            notes.append(f"Row {i} ({r['issue_label']}): no value fetched for {', '.join(unfilled)}.")
    seen: dict[str, tuple[str, int]] = {}
    for i, r in enumerate(used, 1):
        for k, t in (r.get('targets') or {}).items():
            if k in seen and seen[k][0] != t:
                notes.append(f'{k} has different targets in rows {seen[k][1]} and {i}.')
            seen.setdefault(k, (t, i))
    return notes


# A heading at the start of a line: "History:", "Social history:" (a few words, then a colon).
_HEADING_RE = re.compile(r'^([A-Za-z][A-Za-z /&()-]{0,39}):')


def header_html(text: str) -> Markup:
    """The medical history with each line's leading heading in bold; everything else escaped."""
    lines = []
    for line in (text or '').split('\n'):
        m = _HEADING_RE.match(line)
        lines.append(Markup('<strong>%s:</strong>%s') % (m.group(1), line[m.end():]) if m else escape(line))
    return Markup('\n').join(lines)


def no_blank_lines(text) -> str:
    """The text without empty or whitespace-only lines, so a printed plan takes fewer pages
    (ADR-174 addendum). Only the document is tightened; the draft keeps what was typed."""
    return '\n'.join(line.rstrip() for line in str(text or '').split('\n') if line.strip())


# The GPCCMP draft's source tags and its explanation line (ADR-174) are for the GP reviewing the
# draft; the printed, sent and filed plan leaves them out. The run keeps the tagged AI reply.
_SOURCE_TAG_RE = re.compile(r'[ \t]*\[(?:Discussed|Record|Protocol)\]')
_DRAFT_LINE_PREFIX = 'DRAFT GP Chronic Condition Management Plan.'


def for_document(text) -> str:
    """Text as it appears in the printed and sent plan: no source tags, no draft line, no blank lines."""
    lines = [_SOURCE_TAG_RE.sub('', line) for line in str(text or '').split('\n')
             if not line.strip().startswith(_DRAFT_LINE_PREFIX)]
    return no_blank_lines('\n'.join(lines))


def compact(data: dict) -> dict:
    """A copy of a plan's data for the document: blank lines, source tags and the draft line
    removed from the header and every grid cell. The draft itself is unchanged."""
    rows = [{**r, **{f: for_document(r.get(f)) for f in ('issue_label', 'goals', 'management', 'providers')}}
            for r in data.get('rows', [])]
    return {**data, 'header': for_document(data.get('header')), 'rows': rows}


def render_document(plan: Careplan, data: dict, patient: dict, author_name: str, filed_at: datetime | None) -> str:
    data = compact(data)
    values = data.get('values', {})
    rows = [{**r, **{f: render_text(r.get(f), values, r.get('targets') or {}) for f in ('goals', 'management')}}
            for r in data.get('rows', []) if r.get('issue_label')]
    return render_template('careplan/_document.html', plan=plan, header=header_html(data.get('header', '')), rows=rows,
                           patient=patient, author_name=author_name, filed_at=filed_at,
                           review_due_on=_as_date(data.get('review_due_on')))


def document_data(plan: Careplan) -> dict:
    """The plan in draft shape: the working draft, or a filed plan's rows and frozen values."""
    if plan.status == CareplanStatus.draft:
        return draft_data(plan)
    return {'header': plan.header_text or '', 'review_due_on': plan.review_due_on,
            'rows': [{'issue_label': r.issue_label, 'goals': r.goals_text or '',
                      'management': r.management_text or '', 'providers': r.providers_text or '',
                      'targets': r.targets or {}} for r in plan.rows],
            'values': filed_values(plan)}


def plan_markdown(plan: Careplan, data: dict, patient: dict, author_name: str,
                  filed_at: datetime | None) -> str:
    """The plan as Markdown in sections (one per issue) for Best Practice and email. PIT's RTF
    has no tables, and sections read better on a phone; the words are the filed document's."""
    data = compact(data)
    f = current_app.jinja_env.filters
    values = data.get('values', {})
    meta = ' '.join(filter(None, [(patient.get('FIRSTNAME') or '').strip(), (patient.get('SURNAME') or '').strip()]))
    if patient.get('DOB'):
        meta += f" · DOB {f['clinical_date'](patient.get('DOB'))}"
    meta += f' · Prepared by {author_name}'
    if filed_at:
        meta += f" · {f['localdt'](filed_at)}"
    review = _as_date(data.get('review_due_on'))
    if review:
        meta += f" · Review by {review.strftime('%d/%m/%Y')}"
    out = ['# GP Chronic Condition Management Plan', '', meta]
    header = (data.get('header') or '').strip('\n')
    if header.strip():
        out += ['', '## Medical history', '']
        out += [_HEADING_RE.sub(r'**\1:**', line) for line in header.split('\n')]
    for r in data.get('rows', []):
        if not r.get('issue_label'):
            continue
        out += ['', f"## {r['issue_label']}"]
        for label, field in (('Goals', 'goals'), ('Management', 'management'), ('Providers', 'providers')):
            text = render_text(r.get(field), values, r.get('targets') or {}) if field != 'providers' else r.get(field)
            lines = [re.sub(r'^\s*[-*•]\s*', '', ln).strip() for ln in (text or '').split('\n')]
            lines = [ln for ln in lines if ln]
            if lines:
                out += ['', f'**{label}**', ''] + [f'- {ln}' for ln in lines]
    return '\n'.join(out) + '\n'


def markdown_to_text(md: str) -> str:
    """Plain text for pasting where formatting doesn't carry."""
    return re.sub(r'^#+\s+', '', md.replace('**', ''), flags=re.M)


def export_plan(plan: Careplan, user, patient: dict, channel: str) -> dict:
    """The plan for Copy, Email or BP → (sent from Comms, not here). Drafts too, by design:
    the copy filed in Best Practice is the lasting one."""
    if channel not in ('copy', 'email', 'bp'):
        raise CareplanError('Unknown destination.')
    if plan.status not in (CareplanStatus.draft, CareplanStatus.filed):
        raise CareplanError('Only the draft or the current filed plan can be sent.')
    data = document_data(plan)
    if not any(r.get('issue_label') for r in data.get('rows', [])):
        raise CareplanError('Add at least one issue first.')
    if plan.status == CareplanStatus.draft:
        author, when = getattr(user, 'display_name', None) or user.username, None
    else:
        fb = plan.filed_by
        author, when = (getattr(fb, 'display_name', None) or fb.username) if fb else '', plan.filed_at
    md = plan_markdown(plan, data, patient, author, when)
    html = plan.filed_document if plan.status != CareplanStatus.draft and plan.filed_document \
        else render_document(plan, data, patient, author, when)
    _event('exported', user.id, careplan_id=plan.id, channel=channel, status=plan.status.value,
           revision=plan.draft_revision, sha256=hashlib.sha256(md.encode('utf-8')).hexdigest())
    db.session.commit()
    day = current_app.jinja_env.filters['localdt'](when or _now(), '%d/%m/%Y')
    return {'markdown': md, 'text': markdown_to_text(md), 'html': html,
            'label': f'GP Chronic Condition Management Plan {day}'}


def export_plan_to_bp(plan: Careplan, user, patient: dict) -> dict:
    """The plan as a PIT file in the patient's Best Practice record, sent in place (ADR-174):
    the same text the Comms route would file, without going through Comms."""
    from app.utils.pit_utils import send_as_pit
    out = export_plan(plan, user, patient, 'bp')
    if not send_as_pit(patient=patient, pit_label=out['label'], body=out['text'], user=user):
        raise CareplanError('Sending to Best Practice failed. Check the PIT folder in Setup → Messaging.')
    if plan.status == CareplanStatus.filed:
        plan.bp_exported, plan.bp_exported_at = True, _now()
    _event('sent_to_bp', user.id, careplan_id=plan.id, status=plan.status.value)
    db.session.commit()
    return {'ok': True}


def draft_document(plan: Careplan, user, patient: dict) -> str:
    """The draft as it would be filed now, for a print preview. Nothing is frozen or stored."""
    if plan.status != CareplanStatus.draft:
        raise CareplanError('This plan has already been filed.')
    html = render_document(plan, draft_data(plan), patient,
                           getattr(user, 'display_name', None) or user.username, None)
    # The revision and digest show later whether the filed plan is the copy that was printed.
    _event('draft_printed', user.id, careplan_id=plan.id, revision=plan.draft_revision,
           sha256=hashlib.sha256(html.encode('utf-8')).hexdigest())
    db.session.commit()
    return html


def file_plan(plan: Careplan, user, patient: dict) -> Careplan:
    if plan.status != CareplanStatus.draft:
        raise CareplanError('This plan has already been filed.')
    data = draft_data(plan)
    if not any(r.get('issue_label') for r in data.get('rows', [])):
        raise CareplanError('Add at least one issue before filing.')
    when = _now()
    html = render_document(plan, data, patient, getattr(user, 'display_name', None) or user.username, when)
    pos = 0
    for r in data['rows']:
        if not r.get('issue_label'):
            continue
        pos += 1
        db.session.add(CareplanRow(
            careplan_id=plan.id, position=pos, issue_label=r['issue_label'], issue_source=r['issue_source'],
            targets=r.get('targets') or {},
            recipe_version_id=r.get('recipe_version_id'), goals_text=r['goals'],
            management_text=r['management'], providers_text=r['providers'], edited_from_recipe=r['edited']))
    for k, v in data.get('values', {}).items():
        db.session.add(CareplanValue(
            careplan_id=plan.id, token_key=k, label=v.get('label'), value_text=v.get('value'),
            unit=v.get('unit'), result_date=_as_date(v.get('date')), loinc_code=v.get('loinc'),
            status=v.get('status') or 'manual', fetched_at=_now(), confirmed_by_id=user.id))
    prev = last_filed(plan.patient_id)
    if prev and prev.id != plan.id:
        prev.status = CareplanStatus.superseded
    plan.status = CareplanStatus.filed
    plan.header_text = data.get('header', '')
    plan.review_due_on = _as_date(data.get('review_due_on'))
    plan.filed_by_id, plan.filed_at = user.id, when
    plan.filed_document = html
    plan.filed_sha256 = hashlib.sha256(html.encode('utf-8')).hexdigest()
    plan.draft_json = None
    _event('filed', user.id, careplan_id=plan.id, rows=pos, values=len(data.get('values', {})))
    db.session.commit()
    return plan


def void_plan(plan: Careplan, user, reason: str) -> None:
    if plan.status not in (CareplanStatus.filed, CareplanStatus.draft):
        raise CareplanError('This plan cannot be voided.')
    if not _clean(reason):
        raise CareplanError('Give a reason.')
    plan.void_reason = _clean(reason, 1000)
    was_filed = plan.status == CareplanStatus.filed
    plan.status = CareplanStatus.void
    plan.draft_json = None
    if was_filed:   # the plan it replaced becomes current again
        prev = Careplan.query.get(plan.previous_careplan_id) if plan.previous_careplan_id else None
        if prev and prev.status == CareplanStatus.superseded:
            prev.status = CareplanStatus.filed
    _event('voided', user.id, careplan_id=plan.id, was_filed=was_filed)
    db.session.commit()


def plan_history(patient_id: int) -> list[Careplan]:
    return (Careplan.query.filter(Careplan.patient_id == patient_id, Careplan.status != CareplanStatus.draft)
            .order_by(Careplan.created_at.desc()).all())
