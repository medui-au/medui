"""MedUI on the bps_redaction core (upstream ADR-114).

The redaction rules, the token vault and the pre-send checker are the core's
(`bps_redaction`, a pinned wheel). MedUI keeps the pipeline: which passes run,
in which order, under which policy, and every screen. This module is the one
place that connects the two:

  source  Best Practice through the core's own read-only adapter and SQL, plus
          practitioners' preferred names (ADR-106) as extra rows with their own
          user ids ("528p"), beside the BP rows, never instead of them
  lists   the mapping tables (always_redact, name_variants, identifier_labels,
          first_names)
  cache   SystemSetting, under the keys MedUI's own copy used

The old module paths (redaction_service, hcp_redaction_service, …) stay as thin
shims over `bound()` so callers are unchanged.
"""

from __future__ import annotations

import functools
import logging
import threading

from flask import current_app, has_app_context

_lock = threading.Lock()
_redactor = None
_preferred_seen: tuple | None = None


class _Source:
    """The core's BP adapter, with the preferred names added as host rows."""

    def __init__(self, bp) -> None:
        self._bp = bp

    def query(self, name: str, params=None) -> list[dict]:
        rows = self._bp.query(name, params)
        if name in ('practice_doctors', 'practice_staff'):
            from app.services import practitioner_names
            rows = list(rows) + [{**r, 'user_id': f"{r.get('user_id')}p"}
                                 for r in practitioner_names.extra_rows(rows)]
        elif name == 'practice_users':            # the checker's: names only, no ids
            from app.services import practitioner_names
            ids = [{'user_id': uid, 'first_name': '', 'surname': ''}
                   for uid in practitioner_names.preferred_by_bp_user()]
            rows = list(rows) + [{'first_name': r['first_name'], 'surname': r['surname']}
                                 for r in practitioner_names.extra_rows(ids)]
        return rows


class _Lists:
    def rows(self, table: str) -> list[dict]:
        from app.services import mapping_service
        try:
            rows, _total = mapping_service.get_rows(table, page=1, per_page=5000)
        except ValueError:                         # table not created yet
            return []
        return rows


class _Cache:
    def get(self, key: str):
        from app.models.system_setting import SystemSetting
        return SystemSetting.get(key)

    def set(self, key: str, value: str, description: str = '') -> None:
        from app.models.system_setting import SystemSetting
        SystemSetting.set(key, value, description or None)


def redactor():
    """The process's Redactor. Its caches are dropped when the practitioners'
    preferred names change, so a name saved in MedUI applies to the next run."""
    global _redactor, _preferred_seen
    from app.services import practitioner_names
    preferred = tuple(sorted(practitioner_names.preferred_by_bp_user().items()))
    with _lock:
        if _redactor is None:
            # The core logs to 'bps_redaction' (never text or tokens): into MedUI's log.
            core_log = logging.getLogger('bps_redaction')
            if not core_log.handlers:
                for handler in current_app.logger.handlers:
                    core_log.addHandler(handler)
                core_log.setLevel(current_app.logger.getEffectiveLevel())
            from bps_redaction import Redactor
            from bps_redaction.adapters.bp import BPSource
            # practice_first_names (ADR-134): the first-name sweep also takes the practice's
            # own users' first names, as BP holds them.
            _redactor = Redactor(_Source(BPSource(current_app.config.get('BPSDB_URI') or '')),
                                 lists=_Lists(), cache=_Cache(), practice_first_names=True)
        elif preferred != _preferred_seen:
            _redactor.forget()
        _preferred_seen = preferred
        return _redactor


def forget() -> None:
    """Apply a list change to the next call rather than when the caches expire."""
    if _redactor is not None:
        _redactor.forget()


def in_context(fn):
    """A core function that reads the environment, callable as an ordinary one."""
    @functools.wraps(fn)
    def call(*args, **kwargs):
        if not has_app_context():
            raise RuntimeError('redaction needs the MedUI app context')
        with redactor().context():
            return fn(*args, **kwargs)
    return call


class bound:
    """A core rule class whose methods run in MedUI's Redactor context.

    `RedactionService = bound(core.RedactionService)` keeps every existing call
    (`RedactionService.redact(...)`) working unchanged.
    """

    def __init__(self, cls) -> None:
        self._cls = cls

    def __getattr__(self, name: str):
        value = getattr(self._cls, name)
        return in_context(value) if callable(value) else value

    def __repr__(self) -> str:
        return f'<{self._cls.__name__} (bps_redaction core)>'
