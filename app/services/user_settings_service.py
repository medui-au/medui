"""Personal settings: one registry, three layers (ADR-085).

A setting's value for a user resolves as:
  1. the practice's value, when the practice has locked the setting;
  2. the user's own choice (user_preferences row, or a users column for the
     few settings that already lived there: theme, email signature);
  3. the practice default (Setup → User defaults);
  4. the registry default below.

Practice defaults and locks are one SystemSetting, 'user_defaults':
  {"<key>": {"default": <value>, "locked": true|false}, ...}

Adding a setting = adding a Preference to REGISTRY. No migration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.services import egfr_criterion, hba1c_criterion
from app.models.system_setting import SystemSetting
from app.models.user_preference import UserPreference

PRACTICE_KEY = 'user_defaults'
TEXT_MAX = 4000


class SettingLocked(Exception):
    """The practice has locked this setting; users cannot change it."""


@dataclass(frozen=True)
class Preference:
    key: str
    label: str
    kind: str                       # 'bool' | 'choice' | 'text' | 'line' | 'int'
    default: Any
    section: str = 'General'
    help: str = ''
    choices: tuple = ()             # ((value, label), ...) for 'choice'
    column: str | None = None       # stored on users.<column> instead of user_preferences
    lockable: bool = False          # practice may set a default and lock it
    on_page: bool = True            # shown on My settings / User defaults
    requires_ai: bool = False       # only for users who may start AI queries
    bp_users_only: bool = False     # only for users who log in with Best Practice


REGISTRY: dict[str, Preference] = {p.key: p for p in (
    Preference('theme', 'Theme', 'choice', 'light', section='Display',
               choices=(('light', 'Light'), ('dark', 'Dark')),
               column='theme',
               help='Also switchable with the 🌓 button in the top bar.'),
    # ADR-106: shown everywhere in MedUI instead of the BP name; BP itself is unchanged.
    Preference('preferred_name', 'Your name in MedUI', 'line', '', section='Display',
               column='preferred_name', bp_users_only=True,
               help='The name MedUI shows for you: the top bar, the day sheet, the inbox, messages '
                    'and AI drafts. Leave blank to use your name in Best Practice. Best Practice '
                    'itself is not changed.'),
    Preference('email_signature', 'Email signature', 'text', '', section='Communications',
               column='email_signature',
               help='Filled in at the end of emails you write to patients from MedUI.'),
    Preference('ai.show_instructions_expanded', "Show the AI's instructions expanded", 'bool', False,
               section='AI', lockable=True, requires_ai=True,
               help='The AI assistant always shows, in one line, which instructions the AI is '
                    'given. Turn this on to see the full text without clicking. (The scribe keeps '
                    'them to one line under Pipeline, so the transcript keeps its room.)'),
    # Off by default (decided 2026-10-19): a blocking hit pauses the request anyway (ADR-090).
    Preference('ai.review_before_send', 'Review every request before sending to cloud AI', 'bool', False,
               section='AI', lockable=True, requires_ai=True,
               help='Show the prompt as it will be sent, with the privacy check, before it goes '
                    'to a cloud AI model. A request in which the check finds the patient\'s or a '
                    'practitioner\'s identifier always stops for review, whatever this setting.'),
    # The chatbots remember the model last chosen in their dropdown (step 7 of
    # plans/TGA/05); set from the page, not on My settings.
    Preference('chatbot.patient_model', 'Patient chatbot model', 'int', None,
               section='AI', on_page=False, requires_ai=True),
    Preference('chatbot.generic_model', 'Chatbot model', 'int', None,
               section='AI', on_page=False, requires_ai=True),
    # The scribe page sets these itself; they are not on My settings.
    Preference('scribe.asr_model', 'Speech-to-text model', 'int', None,
               section='Scribe', on_page=False, requires_ai=True),
    Preference('scribe.pipeline', 'Scribe workflow', 'int', None,
               section='Scribe', on_page=False, requires_ai=True),
    Preference('scribe.chunk_interval_ms', 'Transcription interval', 'int', None,
               section='Scribe', on_page=False, requires_ai=True),
    # ADR-166: rules a user chooses to display on the Disease Profile. Purely personal, by the
    # maintainer and clinical lead's decision: off until the user ticks them, never lockable,
    # no practice default. The label is the rule itself and must match the code.
    Preference(hba1c_criterion.BADGE_PREF_KEY, hba1c_criterion.BADGE_RULE, 'bool', False,
               section='Patient record',
               help='The badge shows those results with their dates, for the patients you view. '
                    'It describes the results; whether the patient has diabetes, and recording '
                    'it, is your decision.'),
    Preference(egfr_criterion.BADGE_PREF_KEY, egfr_criterion.BADGE_RULE, 'bool', False,
               section='Patient record',
               help='The badge shows that result with its date, for the patients you view. A '
                    'result of exactly 59 is not below 59, although KDIGO counts 59 as G3a. '
                    'Whether the patient has CKD, and recording it, is your decision.'),
)}

SECTION_ORDER = ('Display', 'Communications', 'Patient record', 'AI', 'Scribe', 'General')


# ── Practice layer ────────────────────────────────────────────────────────────

def _practice_all() -> dict:
    data = SystemSetting.get(PRACTICE_KEY) or {}
    return data if isinstance(data, dict) else {}


def practice_entry(key: str) -> dict:
    """{'default': value, 'locked': bool} as the practice set it (registry default if unset)."""
    pref = REGISTRY[key]
    entry = _practice_all().get(key) or {}
    return {
        'default': entry.get('default', pref.default),
        'locked':  bool(entry.get('locked')) and pref.lockable,
    }


def save_practice_entry(key: str, default, locked: bool) -> None:
    pref = REGISTRY[key]
    if not pref.lockable:
        raise ValueError(f'{key} has no practice default')
    data = _practice_all()
    data[key] = {'default': coerce(pref, default), 'locked': bool(locked)}
    SystemSetting.set(PRACTICE_KEY, data, description='Practice defaults and locks for personal settings')


# ── User layer ────────────────────────────────────────────────────────────────

def _row(user_id: int, key: str) -> UserPreference | None:
    return UserPreference.query.filter_by(user_id=user_id, key=key).first()


def get(user, key: str):
    """The value that applies to this user now."""
    pref = REGISTRY[key]
    practice = practice_entry(key) if pref.lockable else {'default': pref.default, 'locked': False}
    if practice['locked']:
        return practice['default']
    if pref.column:
        value = getattr(user, pref.column)
        return pref.default if value is None else value
    row = _row(user.id, key)
    return row.value if row is not None else practice['default']


def is_locked(key: str) -> bool:
    return REGISTRY[key].lockable and practice_entry(key)['locked']


def set(user, key: str, value) -> None:  # noqa: A001 — mirrors SystemSetting.set
    """Store this user's choice. Raises SettingLocked or ValueError."""
    pref = REGISTRY[key]
    if is_locked(key):
        raise SettingLocked(key)
    value = coerce(pref, value)
    if pref.column:
        setattr(user, pref.column, value)
        if key == 'preferred_name':
            from app.services import practitioner_names
            practitioner_names.apply_to_user(user)
    else:
        row = _row(user.id, key)
        if row is None:
            row = UserPreference(user_id=user.id, key=key)
            db.session.add(row)
        row.value = value
    db.session.commit()


def coerce(pref: Preference, raw):
    """Validate a submitted value for this setting; return it in stored form."""
    if pref.kind == 'bool':
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ('1', 'true', 'on', 'yes')
    if pref.kind == 'choice':
        allowed = {str(v): v for v, _ in pref.choices}
        if str(raw) not in allowed:
            raise ValueError(f'{raw!r} is not one of the choices')
        return allowed[str(raw)]
    if pref.kind == 'int':
        if raw is None or raw == '':
            return None
        return int(raw)
    if pref.kind == 'line':
        line = ' '.join(str(raw or '').split())
        if len(line) > 120:
            raise ValueError('longer than 120 characters')
        return line or None
    text = '' if raw is None else str(raw).replace('\r\n', '\n').strip()
    if len(text) > TEXT_MAX:
        raise ValueError(f'longer than {TEXT_MAX} characters')
    return text


# ── Pages ─────────────────────────────────────────────────────────────────────

def _visible_to(user, pref: Preference) -> bool:
    return (pref.on_page and (not pref.requires_ai or user.can_use_ai)
            and (not pref.bp_users_only or bool(user.bpsdb_user_id)))


def page_sections(user) -> list[tuple[str, list[dict]]]:
    """My settings: [(section, [{'pref', 'value', 'locked'}, ...]), ...]."""
    by_section: dict[str, list[dict]] = {}
    for pref in REGISTRY.values():
        if not _visible_to(user, pref):
            continue
        by_section.setdefault(pref.section, []).append({
            'pref':   pref,
            'value':  get(user, pref.key),
            'locked': is_locked(pref.key),
        })
    return [(s, by_section[s]) for s in SECTION_ORDER if s in by_section]


def save_from_form(user, form) -> list[str]:
    """Apply a submitted My settings form. Returns error messages (empty = all saved)."""
    errors = []
    for pref in REGISTRY.values():
        if not _visible_to(user, pref) or is_locked(pref.key):
            continue
        # An unticked checkbox is absent from the form: that means False.
        if pref.kind == 'bool':
            raw = form.get(pref.key, 'false')
        elif pref.key in form:
            raw = form.get(pref.key)
        else:
            continue
        try:
            set(user, pref.key, raw)
        except ValueError as exc:
            errors.append(f'{pref.label}: {exc}')
    return errors


def practice_rows() -> list[dict]:
    """Setup → User defaults: one row per lockable setting, with how many users chose otherwise."""
    rows = []
    for pref in REGISTRY.values():
        if not (pref.lockable and pref.on_page):
            continue
        entry = practice_entry(pref.key)
        stored = UserPreference.query.filter_by(key=pref.key).all()
        overrides = sum(1 for r in stored if r.value != entry['default'])
        rows.append({'pref': pref, 'default': entry['default'], 'locked': entry['locked'],
                     'overrides': overrides})
    return rows
