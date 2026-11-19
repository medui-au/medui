"""Is the Best Practice login read-only? (ADR-139)

MedUI only sends read queries to Best Practice. It is the SQL Server login, though, that
decides what could be written: BP's own script creates a read-only account for database
access, but nothing makes an installation use it. This asks SQL Server what the login may do
(it never tries a write) and keeps the answer:

- the whole server: server administrator (sysadmin) or CONTROL SERVER;
- each user database the login can open: a write role (db_owner, db_datawriter,
  db_ddladmin), CREATE TABLE or ALTER on the database, and the number of tables with an
  INSERT, UPDATE or DELETE grant (permissions granted table by table count too).

Stored procedures the login may run are counted for information only: what one does can't
be told from its permission.

The result is cached for CACHE_S. Setup → Database runs a fresh check; startup runs one in
the background and logs it; page renders only read the cache (never a database call), and
`require_read_only()` refuses admin-written SQL (Query Manager, BPSDB data sources) unless
the latest check found the login read-only.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

READ_ONLY = 'read_only'
CAN_WRITE = 'can_write'
UNKNOWN = 'unknown'

CACHE_S = 600

_lock = threading.Lock()
_cached: 'LoginCheck | None' = None
_cached_at = 0.0


@dataclass
class DatabasePerms:
    name: str
    problems: list[str] = field(default_factory=list)
    executable_procedures: int = 0


@dataclass
class LoginCheck:
    status: str                                   # read_only | can_write | unknown
    server_problems: list[str] = field(default_factory=list)
    databases: list[DatabasePerms] = field(default_factory=list)
    error: str = ''
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def read_only(self) -> bool:
        return self.status == READ_ONLY

    @property
    def writable_databases(self) -> list[DatabasePerms]:
        return [d for d in self.databases if d.problems]

    @property
    def procedure_databases(self) -> list[DatabasePerms]:
        return [d for d in self.databases if d.executable_procedures]

    def summary(self) -> str:
        """One line for the log: no login name, no server name."""
        if self.status == UNKNOWN:
            return f'could not be checked ({self.error})'
        if self.read_only:
            return f'read-only in all {len(self.databases)} databases it can open'
        parts = list(self.server_problems)
        parts += [f'{d.name}: {", ".join(d.problems)}' for d in self.writable_databases]
        return 'CAN WRITE: ' + '; '.join(parts)


class LoginNotReadOnly(RuntimeError):
    """Admin-written SQL refused: the BP login isn't confirmed read-only."""


def _flag(value) -> bool:
    return bool(value) and int(value) == 1


def assess(server_row: dict, database_rows: dict[str, dict]) -> LoginCheck:
    """The verdict from the permission rows (no database here, so tests can call it)."""
    server = []
    if _flag(server_row.get('is_sysadmin')):
        server.append('server administrator (sysadmin)')
    elif _flag(server_row.get('control_server')):
        server.append('CONTROL SERVER permission')
    dbs = []
    for name, row in database_rows.items():
        problems = [f'member of {role}' for role in ('db_owner', 'db_datawriter', 'db_ddladmin')
                    if _flag(row.get(role))]
        if _flag(row.get('create_table')):
            problems.append('can create tables')
        if _flag(row.get('alter_database')):
            problems.append('can alter the database')
        tables = int(row.get('writable_tables') or 0)
        if tables:
            problems.append(f'can insert, update or delete in {tables} '
                            f'table{"s" if tables != 1 else ""}')
        dbs.append(DatabasePerms(name, problems, int(row.get('executable_procedures') or 0)))
    status = CAN_WRITE if server or any(d.problems for d in dbs) else READ_ONLY
    return LoginCheck(status, server, dbs)


def _quoted(name: str) -> str:
    return '[' + name.replace(']', ']]') + ']'


def _run_check(uri: str) -> LoginCheck:
    from app.sql.query_loader import ReadOnlySession, load_query
    with ReadOnlySession(uri) as session:
        server = (session.execute(load_query('bp_login_server_perms')) or [{}])[0]
        names = [r['name'] for r in session.execute(load_query('bp_login_databases'))]
        stmt = load_query('bp_login_database_perms')
        rows = {}
        for name in names:
            # sp_executesql in that database runs the statement in its context.
            rows[name] = (session.execute(f'EXEC {_quoted(name)}.sys.sp_executesql ?', [stmt])
                          or [{}])[0]
    return assess(server, rows)


def check(force: bool = False) -> LoginCheck:
    """The login's permissions, from the cache unless it is older than CACHE_S or force."""
    global _cached, _cached_at
    from flask import current_app
    with _lock:
        if (not force and _cached and _cached.status != UNKNOWN
                and time.monotonic() - _cached_at < CACHE_S):
            return _cached
    uri = current_app.config.get('BPSDB_URI')
    if not uri:
        result = LoginCheck(UNKNOWN, error='Best Practice is not configured')
    else:
        try:
            result = _run_check(uri)
        except Exception as exc:          # pyodbc errors, timeouts: report, don't raise
            result = LoginCheck(UNKNOWN, error=type(exc).__name__)
            current_app.logger.warning('bp_login: permission check failed: %s', exc)
    with _lock:
        previous = _cached
        _cached, _cached_at = result, time.monotonic()
    if previous is None or previous.status != result.status:
        # WARNING whatever the result: the confirmation must reach a log that passes only
        # warnings (medui_os's does), so "read-only" can be told from "didn't run".
        current_app.logger.warning('bp_login: Best Practice login %s', result.summary())
    return result


def cached() -> LoginCheck | None:
    """The last result, without checking: for page renders."""
    return _cached


def require_read_only() -> None:
    """Raise LoginNotReadOnly unless the login is confirmed read-only."""
    result = check()
    if result.read_only:
        return
    if result.status == UNKNOWN:
        raise LoginNotReadOnly(
            "MedUI couldn't confirm that its Best Practice login is read-only "
            f'({result.error}), so it won\'t run SQL written here. See Setup → Database.')
    raise LoginNotReadOnly(
        'MedUI\'s Best Practice login can change data (' + result.summary()[len('CAN WRITE: '):]
        + "), so it won't run SQL written here. Use the read-only account BP supplies for "
          'database access. See Setup → Database.')


def check_in_background(app) -> None:
    """Run one check after startup, off the request path, and log it."""
    def _go():
        with app.app_context():
            check(force=True)
    threading.Thread(target=_go, name='bp-login-check', daemon=True).start()


def _reset_for_tests() -> None:
    global _cached, _cached_at
    with _lock:
        _cached, _cached_at = None, 0.0
