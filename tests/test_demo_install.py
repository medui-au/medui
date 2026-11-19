"""Demo installations (install.sh --demo): their own SQL Server with the invented medui_demodata,
kept apart from Best Practice. The refusals run install.sh --dry-run in scratch folders, so they
change nothing. Every value here is invented.
"""
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / 'compose.yaml').read_text()
needs_host = pytest.mark.skipif(not Path('/run/systemd/system').is_dir() or os.geteuid() == 0
                                or shutil.which('ss') is None,
                                reason='install.sh checks need systemd, ss and a normal user')


def _bpsql_block():
    m = re.search(r'\n  bpsql:\n(.*?)\n  [a-z]+:\n', COMPOSE, re.S)
    assert m, 'compose.yaml has no bpsql service'
    return m.group(1)


def test_demo_sql_server_is_private_and_needs_the_licence_accepted():
    block = _bpsql_block()
    assert 'profiles: [demo]' in block            # never started on a live installation
    assert 'ports:' not in block                  # reachable from this installation's containers only
    assert 'ACCEPT_EULA: ${DEMO_SQL_ACCEPT_EULA:-N}' in block
    assert 'MSSQL_PID: Express' in block
    assert re.search(r'image: mcr\.microsoft\.com/mssql/server:2022-CU\d+[-\w.]*', block)  # pinned, not latest
    assert 'customerfeedback = false' in (ROOT / 'scripts' / 'demo_mssql.conf').read_text()


def test_demo_data_folder_is_not_committed():
    assert 'demodata/' in (ROOT / '.gitignore').read_text().split()


def test_demo_scripts_keep_passwords_off_command_lines():
    text = (ROOT / 'scripts' / 'demo_data.sh').read_text()
    assert 'SQLCMDPASSWORD="$SA_PASSWORD" "${DOCKER[@]}" exec -i -e SQLCMDPASSWORD' in text
    assert '-P ' not in text and '--password' not in text
    assert 'chmod 600 "$secrets"' in text and 'rm -f "$secrets"' in text
    # It works only on a demo installation, against its own bpsql.
    assert 'MEDUI_INSTANCE)" = demo ]' in text and 'BPSDB_HOST)" = bpsql ]' in text


def test_menu_refuses_bp_settings_on_a_demo():
    text = (ROOT / 'medui.sh').read_text()
    for cmd in ('cmd_bp() {\n  not_on_demo', 'cmd_bp_clear() {\n  not_on_demo'):
        assert cmd in text


def _copy(tmp_path, folder, env=None):
    d = tmp_path / folder
    (d / 'scripts').mkdir(parents=True)
    for f in ('install.sh', 'compose.yaml', 'scripts/init_env.py'):
        shutil.copy2(ROOT / f, d / f)
    if env is not None:
        (d / '.env').write_text(env)
        (d / '.env').chmod(0o600)
    return d


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _install(d, *args):
    ports = ['--app-port', str(_free_port()), '--db-port', str(_free_port()), '--ocr-port', str(_free_port())]
    r = subprocess.run(['bash', str(d / 'install.sh'), '--no-apt', '--no-ocr', '--yes', '--timezone', 'brisbane',
                        *ports, *args], cwd=d, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout + r.stderr


@needs_host
def test_demo_needs_a_name_other_than_the_practice_one(tmp_path):
    code, out = _install(_copy(tmp_path, 'medui_os'), '--demo', '--dry-run')
    assert code != 0 and 'A demo needs a name of its own' in out


@needs_host
def test_a_live_installation_never_becomes_a_demo(tmp_path):
    d = _copy(tmp_path, 'practice_one', env='COMPOSE_PROJECT_NAME=practice_one\nBPSDB_HOST=192.0.2.10\\BPSINSTANCE\n')
    code, out = _install(d, '--demo', '--dry-run')
    assert code != 0 and "isn't a demo, and can't become one" in out


@needs_host
def test_demo_without_a_terminal_needs_the_licence_flag(tmp_path):
    code, out = _install(_copy(tmp_path, 'invented_demo_trial'), '--demo')   # stops in step 1, before any change
    assert code != 0 and '--accept-sql-licence' in out
    assert not (tmp_path / 'invented_demo_trial' / '.env').exists()


@needs_host
def test_demo_dry_run_plans_the_demo_steps(tmp_path):
    if os.uname().machine != 'x86_64':
        pytest.skip('the demo SQL Server is x86-64 only')
    code, out = _install(_copy(tmp_path, 'invented_demo_trial'), '--demo', '--dry-run')
    assert code == 0, out
    for step in ("project 'invented_demo_trial'", 'set MEDUI_INSTANCE in .env', 'set BPSDB_HOST in .env',
                 '--profile demo up -d --wait db bpsql', 'scripts/demo_data.sh restore', 'scripts/demo_data.sh refresh'):
        assert step in out, step


@needs_host
@pytest.mark.skipif(shutil.which('script') is None, reason='needs script(1) for a terminal')
def test_a_new_install_asks_live_or_demo_but_not_with_yes(tmp_path):
    def run(folder, answer, *extra):
        d = _copy(tmp_path, folder)
        cmd = ' '.join(['./install.sh', '--dry-run', '--no-apt', '--no-ocr', '--timezone', 'brisbane',
                        '--app-port', str(_free_port()), '--db-port', str(_free_port()), *extra])
        r = subprocess.run(['script', '-qec', cmd, '/dev/null'], cwd=d, input=answer + '\n',
                           capture_output=True, text=True, timeout=120)
        return r.stdout
    if os.uname().machine == 'x86_64':
        out = run('invented_asked_d', 'd')
        assert 'live practice installation or a demo' in out and 'set MEDUI_INSTANCE in .env' in out
    out = run('invented_asked_l', '')
    assert 'live practice installation or a demo' in out and 'MEDUI_INSTANCE' not in out
    out = run('invented_yes', '', '--yes')
    assert 'live practice installation or a demo' not in out and 'MEDUI_INSTANCE' not in out
