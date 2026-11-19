"""Is the Best Practice login read-only? (ADR-139)

No SQL Server here: the permission rows are invented and fed to the service, as the server
would return them for each kind of login.
"""
import pytest
from flask import Flask

from app.services import bp_login_service as bl
from app.utils import sql_utils

RO_DB = {'db_owner': 0, 'db_datawriter': 0, 'db_ddladmin': 0, 'create_table': 0,
         'alter_database': 0, 'writable_tables': 0, 'executable_procedures': 0}
RO_SERVER = {'is_sysadmin': 0, 'control_server': 0}


def _dbs(**override_for_second):
    return {'BPSPATIENTS': dict(RO_DB), 'BPSDOCUMENTSINBOX': {**RO_DB, **override_for_second}}


def test_read_only_login():
    r = bl.assess(RO_SERVER, _dbs())
    assert r.status == bl.READ_ONLY and r.read_only
    assert r.writable_databases == []
    assert 'read-only in all 2 databases' in r.summary()


def test_datawriter_role_can_write():
    r = bl.assess(RO_SERVER, _dbs(db_datawriter=1))
    assert r.status == bl.CAN_WRITE
    assert [d.name for d in r.writable_databases] == ['BPSDOCUMENTSINBOX']
    assert 'member of db_datawriter' in r.summary()


def test_grant_on_one_table_can_write():
    r = bl.assess(RO_SERVER, _dbs(writable_tables=1))
    assert r.status == bl.CAN_WRITE
    assert 'can insert, update or delete in 1 table' in r.summary()


def test_ddl_permission_can_write():
    r = bl.assess(RO_SERVER, _dbs(create_table=1))
    assert r.status == bl.CAN_WRITE and 'can create tables' in r.summary()


def test_sysadmin_can_write():
    r = bl.assess({'is_sysadmin': 1, 'control_server': 1}, _dbs())
    assert r.status == bl.CAN_WRITE
    assert r.server_problems == ['server administrator (sysadmin)']


def test_procedures_are_information_only():
    r = bl.assess(RO_SERVER, _dbs(executable_procedures=6))
    assert r.read_only
    assert [(d.name, d.executable_procedures) for d in r.procedure_databases] == [('BPSDOCUMENTSINBOX', 6)]


def test_null_permission_is_not_a_grant():
    # HAS_PERMS_BY_NAME returns NULL for an object it can't resolve.
    r = bl.assess({'is_sysadmin': None, 'control_server': None}, _dbs(create_table=None))
    assert r.read_only


def test_database_name_quoting():
    assert bl._quoted('BPS]x') == '[BPS]]x]'


# ── The service and the guard on SQL written in MedUI ──────────────────────────

@pytest.fixture
def app(monkeypatch):
    a = Flask(__name__)
    a.config['BPSDB_URI'] = 'DRIVER=x'      # never connected: _run_check is replaced
    bl._reset_for_tests()
    yield a
    bl._reset_for_tests()


def _serve(monkeypatch, result_or_exc):
    calls = []

    def fake(uri):
        calls.append(uri)
        if isinstance(result_or_exc, Exception):
            raise result_or_exc
        return result_or_exc
    monkeypatch.setattr(bl, '_run_check', fake)
    return calls


def test_check_is_cached(app, monkeypatch):
    calls = _serve(monkeypatch, bl.assess(RO_SERVER, _dbs()))
    with app.app_context():
        assert bl.check().read_only
        bl.check()
        assert len(calls) == 1
        bl.check(force=True)
        assert len(calls) == 2


def test_failed_check_is_unknown_and_not_cached(app, monkeypatch):
    calls = _serve(monkeypatch, TimeoutError('server away'))
    with app.app_context():
        assert bl.check().status == bl.UNKNOWN
        bl.check()
        assert len(calls) == 2           # an unknown result is checked again next time


def test_cached_never_checks(app, monkeypatch):
    calls = _serve(monkeypatch, bl.assess(RO_SERVER, _dbs()))
    with app.app_context():
        assert bl.cached() is None
        assert calls == []


def test_no_bp_configured_is_unknown(app):
    app.config['BPSDB_URI'] = ''
    with app.app_context():
        assert bl.check().status == bl.UNKNOWN


class _Query:
    database_target = 'bpsdb'
    sql_text = 'SELECT 1 AS one'


def test_admin_sql_refused_when_login_can_write(app, monkeypatch):
    _serve(monkeypatch, bl.assess(RO_SERVER, _dbs(db_owner=1)))
    with app.app_context():
        with pytest.raises(bl.LoginNotReadOnly) as exc:
            sql_utils.execute_sql_query(_Query())
    assert 'can change data' in str(exc.value)
    assert 'member of db_owner' in str(exc.value)


def test_admin_sql_refused_when_unconfirmed(app, monkeypatch):
    _serve(monkeypatch, TimeoutError('server away'))
    with app.app_context():
        with pytest.raises(bl.LoginNotReadOnly) as exc:
            sql_utils.execute_sql_query(_Query())
    assert "couldn't confirm" in str(exc.value)


def test_admin_sql_runs_when_read_only(app, monkeypatch):
    _serve(monkeypatch, bl.assess(RO_SERVER, _dbs()))
    ran = []

    class FakeSession:
        def __init__(self, uri): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params=None):
            ran.append(sql)
            return [{'one': 1}]
    import app.sql.query_loader as ql
    monkeypatch.setattr(ql, 'ReadOnlySession', FakeSession)
    with app.app_context():
        assert sql_utils.execute_sql_query(_Query()) == [{'one': 1}]
    assert ran == ['SELECT 1 AS one']


def test_permission_queries_are_registered_and_read_only():
    from app.sql.query_loader import load_query
    for name in ('bp_login_server_perms', 'bp_login_databases', 'bp_login_database_perms'):
        sql = load_query(name).upper()
        for word in ('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'DROP ', 'ALTER ', 'GRANT '):
            # only as quoted permission names, never as a statement
            assert f'\n{word}' not in sql and not sql.lstrip().startswith(word)


def test_result_is_logged_at_warning_even_when_read_only(app, monkeypatch, caplog):
    import logging
    _serve(monkeypatch, bl.assess(RO_SERVER, _dbs()))
    with app.app_context():
        app.logger.setLevel(logging.WARNING)       # as in medui_os: INFO is dropped
        with caplog.at_level(logging.WARNING, logger=app.logger.name):
            bl.check(force=True)
    lines = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any('bp_login: Best Practice login read-only in all 2 databases' in l for l in lines)
