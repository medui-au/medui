"""The practice's timezone: MedUI's local time (ADR-101).

"Today" on the day sheet and elsewhere comes from the process's local time
(``datetime.now()``), so the zone is applied to the whole process: ``TZ`` and
``time.tzset()``, plus ``PRACTICE_TIMEZONE`` in the app config for the code that
converts stored UTC times (the ``localdt`` filter, usage reports).

Which zone, in order: the one set in Application Setup → General (a system
setting), else ``PRACTICE_TIMEZONE`` from the installation's environment, else
Australia/Brisbane. Always a place, never an offset, so daylight saving changes
by itself.

When: at start-up (the installation's zone; no database needed), straight after
a change in Setup, and on a request at most once a minute after that, so another
front-end sharing the database (the shadow server) follows a change too.
"""
import os
import threading
import time
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from flask import Flask, current_app

SETTING_KEY = 'general.practice_timezone'
DEFAULT_ZONE = 'Australia/Brisbane'
CHECK_EVERY = 60  # seconds between looks at the setting

# Offered in Setup, with the states each covers.
CHOICES = [
    ('Australia/Brisbane', 'Brisbane (Queensland)'),
    ('Australia/Sydney', 'Sydney (NSW, ACT)'),
    ('Australia/Melbourne', 'Melbourne (Victoria)'),
    ('Australia/Hobart', 'Hobart (Tasmania)'),
    ('Australia/Adelaide', 'Adelaide (South Australia)'),
    ('Australia/Darwin', 'Darwin (Northern Territory)'),
    ('Australia/Perth', 'Perth (Western Australia)'),
]

_lock = threading.Lock()
_applied: str | None = None
_next_check = 0.0


def installation_zone() -> str:
    """PRACTICE_TIMEZONE from the environment, if it names a zone; else the default."""
    zone = (os.environ.get('PRACTICE_TIMEZONE') or '').strip()
    return zone if is_zone(zone) else DEFAULT_ZONE


@lru_cache(maxsize=1)
def _known_zones() -> frozenset:
    return frozenset(available_timezones())


def is_zone(name: str) -> bool:
    """A zone name this system knows (a place such as Australia/Melbourne)."""
    return bool(name) and name in _known_zones()


def normalise(name: str) -> str:
    """A typed zone name in its exact spelling (australia/melbourne -> Australia/Melbourne), or ''."""
    wanted = (name or '').strip().lower()
    return next((z for z in _known_zones() if z.lower() == wanted), '') if wanted else ''


def configured_zone() -> str:
    """The zone set in Setup, else the installation's."""
    from app.models.system_setting import SystemSetting
    zone = (SystemSetting.get(SETTING_KEY, '') or '').strip()
    return zone if is_zone(zone) else installation_zone()


def zone() -> ZoneInfo:
    """The practice's zone as applied to this process, for converting stored UTC times."""
    try:
        return ZoneInfo(current_app.config.get('PRACTICE_TIMEZONE') or DEFAULT_ZONE)
    except (RuntimeError, ValueError, KeyError):  # no app context, or a bad name
        return ZoneInfo(_applied or installation_zone())


def apply(app: Flask, name: str) -> None:
    """Make ``name`` this process's local time."""
    global _applied
    with _lock:
        if name == _applied:
            return
        os.environ['TZ'] = name
        time.tzset()
        app.config['PRACTICE_TIMEZONE'] = name
        _applied = name
    app.logger.info('Practice timezone: %s', name)


def refresh(app: Flask, force: bool = False) -> None:
    """Apply the configured zone if it changed; looks at the database at most once a minute."""
    global _next_check
    now = time.monotonic()
    if not force and now < _next_check:
        return
    _next_check = now + CHECK_EVERY
    try:
        apply(app, configured_zone())
    except Exception as exc:  # the database may not be ready (first start, migrations)
        app.logger.warning('Practice timezone not read from the database: %s', exc)


def init_app(app: Flask) -> None:
    apply(app, installation_zone())

    @app.before_request
    def _practice_time_refresh():
        refresh(app)
