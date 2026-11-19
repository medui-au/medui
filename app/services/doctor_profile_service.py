"""Doctor profile lookups against BPSDB.

Deliberately kept separate from billing_analysis_service — these facts
(all-time billing span, provider numbers, registration) describe the doctor,
not any particular billing period, and are expected to be surfaced on other
screens beyond Billing Analysis (e.g. a future doctor detail view).
"""

import datetime
import threading
import time
from dataclasses import dataclass
from typing import Callable

from flask import current_app

from app.sql.query_loader import ReadOnlySession
from app.repositories.doctor_profile_repository import DoctorProfileRepository


class DoctorProfileService:
    @staticmethod
    def _session() -> ReadOnlySession:
        return ReadOnlySession(current_app.config['BPSDB_URI'])

    @staticmethod
    def get_profile(bpsdb_user_id: int) -> dict:
        with DoctorProfileService._session() as sess:
            repo = DoctorProfileRepository(sess)
            span              = repo.get_billing_span(bpsdb_user_id)
            provider_numbers  = repo.get_provider_numbers(bpsdb_user_id)
            registration      = repo.get_registration_info(bpsdb_user_id)

        first_day = span.get('first_billing_day') if span else None
        last_day  = span.get('last_billing_day') if span else None
        if isinstance(first_day, (datetime.date, datetime.datetime)):
            first_day = first_day.isoformat()
        if isinstance(last_day, (datetime.date, datetime.datetime)):
            last_day = last_day.isoformat()

        # PROVIDER_LOCATION covers multi-site provider numbers; fall back to the
        # single scalar USERS.ProviderNo if a doctor has no PROVIDER_LOCATION rows.
        if not provider_numbers and registration and registration.get('ProviderNo'):
            provider_numbers = [registration['ProviderNo']]
        provider_numbers = [p.strip() for p in provider_numbers if p and p.strip()]

        # BPSDB stores RegistrationNo in a fixed-length CHAR column — strip padding.
        ahpra_no = registration.get('RegistrationNo') if registration else None
        ahpra_no = ahpra_no.strip() if ahpra_no else None

        return {
            'first_billing_day':     first_day,
            'last_billing_day':      last_day,
            'provider_numbers':      provider_numbers,
            'ahpra_registration_no': ahpra_no,
        }


# ── The details card on the user's name in the top bar (ADR-125) ─────────────
# One entry per line, in order. A new detail is one entry here (and, if BP holds
# it somewhere new, a query and a repository method); the template lists
# whatever is here and leaves out lines with no value.

@dataclass(frozen=True)
class CardField:
    key: str
    label: str
    value: Callable[[dict], object]     # str, or a list of str for several lines


def _fmt_date(value) -> str | None:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%-d %b %Y')
    return None


def _provider_lines(bp: dict) -> list[str]:
    sites = [s for s in bp.get('provider_sites') or [] if (s.get('provider_no') or '').strip()]
    if sites:
        return [f"{s['provider_no']} ({s['site']})" if s.get('site') else s['provider_no']
                for s in sites]
    single = (bp.get('identity') or {}).get('provider_no')
    return [single] if single else []


def _count(value) -> str | None:
    return f'{value:,}' if isinstance(value, int) and value > 0 else None


CARD_FIELDS: list[CardField] = [
    CardField('qualifications', 'Qualifications', lambda bp: bp.get('qualifications') or []),
    CardField('registration', 'AHPRA registration', lambda bp: (bp.get('identity') or {}).get('registration_no')),
    CardField('hpii', 'HPI-I', lambda bp: (bp.get('identity') or {}).get('hpii')),
    CardField('provider', 'Provider number', _provider_lines),
    CardField('prescriber', 'Prescriber number', lambda bp: (bp.get('identity') or {}).get('prescriber_no')),
    CardField('first_visit', 'First patient visit', lambda bp: _fmt_date((bp.get('visits') or {}).get('first_visit'))),
    CardField('visits', 'Patient visits', lambda bp: _count((bp.get('visits') or {}).get('visits'))),
    CardField('patients', 'Patients seen', lambda bp: _count((bp.get('visits') or {}).get('patients'))),
]

CARD_TTL = 3600                     # seconds; the card shows when it was read
_card_cache: dict[int, tuple[float, dict]] = {}
_card_lock = threading.Lock()


def _read_bp(bpsdb_user_id: int) -> dict:
    with DoctorProfileService._session() as sess:
        repo = DoctorProfileRepository(sess)
        return {
            'identity':       repo.get_card_identity(bpsdb_user_id),
            'qualifications': repo.get_qualifications(bpsdb_user_id),
            'provider_sites': repo.get_provider_sites(bpsdb_user_id),
            'visits':         repo.get_visit_totals(bpsdb_user_id),
        }


def card_lines(bp: dict) -> list[dict]:
    """[{key, label, values}] for the fields that have a value."""
    out = []
    for field in CARD_FIELDS:
        value = field.value(bp)
        values = [v for v in (value if isinstance(value, list) else [value])
                  if isinstance(v, str) and v.strip()]
        if values:
            out.append({'key': field.key, 'label': field.label, 'values': values})
    return out


def is_doctor(user) -> bool:
    """A BP-linked user with a provider or prescriber number: a doctor, whatever their
    BP group (a practice owner who consults is in group 3). For the admin lookup."""
    return bool(getattr(user, 'bpsdb_user_id', None)
                and (getattr(user, 'bpsdb_provider_no', None) or getattr(user, 'bpsdb_prescriber_no', None)))


def get_card(user) -> dict:
    """The card for this user: {lines, as_at, unavailable}. Always the user's real BP
    user id, never a preferred-name shadow user (ADR-106, ADR-112). Cached per user."""
    uid = getattr(user, 'bpsdb_user_id', None)
    if not uid:
        return {'lines': [], 'as_at': None, 'unavailable': False}
    now = time.monotonic()
    with _card_lock:
        hit = _card_cache.get(uid)
        if hit and now - hit[0] < CARD_TTL:
            return hit[1]
    try:
        bp = _read_bp(int(uid))
    except Exception as exc:                     # BPSDB boundary: the page must still work
        current_app.logger.warning('details card: BP read failed for user %s: %s',
                                   getattr(user, 'id', '?'), type(exc).__name__)
        return {'lines': [], 'as_at': None, 'unavailable': True}
    card = {'lines': card_lines(bp), 'as_at': datetime.datetime.now(), 'unavailable': False}
    with _card_lock:
        _card_cache[uid] = (now, card)
    return card
