"""medui.sh, the menu for an installed MedUI, and scripts/env_edit.py, which changes .env for it.

Every value here is invented.
"""
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import env_edit  # noqa: E402


@pytest.fixture
def env_file(tmp_path):
    p = tmp_path / '.env'
    p.write_text('# comment\nCOMPOSE_PROJECT_NAME=medui_os\nBPSDB_HOST=\nBPSDB_USER=\nBPSDB_PASSWORD=\n'
                 'SECRET_KEY=keep-me\n')
    p.chmod(0o600)
    return p


def _run(env_file, *args, **values):
    env = {**os.environ, 'MEDUI_ENV_FILE': str(env_file),
           **{f'MEDUI_SET_{k}': v for k, v in values.items()}}
    return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'env_edit.py'), *args],
                          env=env, capture_output=True, text=True)


def test_quoting_keeps_values_literal_for_compose_and_dotenv():
    assert env_edit.quote('sql.example\\BPSINSTANCE') == 'sql.example\\BPSINSTANCE'   # one backslash, bare
    assert env_edit.quote('invented_ro') == 'invented_ro'
    assert env_edit.quote('pa$$ #word') == "'pa$$ #word'"
    assert env_edit.quote('') == ''
    for bad in ("it's", 'two\nlines'):
        with pytest.raises(env_edit.EnvError):
            env_edit.quote(bad)


def test_set_replaces_appends_and_keeps_the_rest(env_file):
    r = _run(env_file, 'set', 'BPSDB_HOST', 'BPSDB_PASSWORD', 'AI_ENABLED',
             BPSDB_HOST='sql.example\\BPSINSTANCE', BPSDB_PASSWORD='inv$nted #1', AI_ENABLED='true')
    assert r.returncode == 0, r.stderr
    text = env_file.read_text()
    assert 'BPSDB_HOST=sql.example\\BPSINSTANCE\n' in text
    assert "BPSDB_PASSWORD='inv$nted #1'\n" in text
    assert text.endswith('AI_ENABLED=true\n')
    assert '# comment\n' in text and 'SECRET_KEY=keep-me\n' in text
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    backup = env_file.with_name('.env.bak')
    assert 'BPSDB_HOST=\n' in backup.read_text()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    # read back as written
    assert _run(env_file, 'get', 'BPSDB_PASSWORD').stdout.strip() == 'inv$nted #1'
    assert _run(env_file, 'get', 'BPSDB_HOST').stdout.strip() == 'sql.example\\BPSINSTANCE'


def test_has_needs_every_key_non_blank(env_file):
    assert _run(env_file, 'has', 'BPSDB_HOST', 'BPSDB_USER').returncode == 1
    _run(env_file, 'set', 'BPSDB_HOST', 'BPSDB_USER', BPSDB_HOST='sql.example', BPSDB_USER='invented_ro')
    assert _run(env_file, 'has', 'BPSDB_HOST', 'BPSDB_USER').returncode == 0
    assert _run(env_file, 'has', 'BPSDB_HOST', 'BPSDB_PASSWORD').returncode == 1


def test_refused_value_changes_nothing(env_file):
    before = env_file.read_text()
    r = _run(env_file, 'set', 'BPSDB_PASSWORD', BPSDB_PASSWORD="it's")
    assert r.returncode == 1 and 'Not changed' in r.stderr
    assert env_file.read_text() == before


def test_value_never_on_the_command_line():
    # medui.sh passes values to env_edit.py in MEDUI_SET_* variables, never as arguments.
    script = (ROOT / 'medui.sh').read_text()
    for line in script.splitlines():
        if 'env_edit.py set' in line:
            assert not re.search(r'set\s.*\$\{?(pass|host|user|db)\b', line), line


def test_medui_sh_parses_and_lists_every_menu_command():
    script = ROOT / 'medui.sh'
    assert subprocess.run(['bash', '-n', str(script)]).returncode == 0
    help_text = subprocess.run(['bash', str(script), 'help'], capture_output=True, text=True).stdout
    text = script.read_text()
    menu = re.search(r'^MENU=\((.*?)^\)', text, re.S | re.M).group(1)
    tags = re.findall(r'^\s+([a-z-]+)\s+"', menu, re.M)
    dispatch = re.search(r'^dispatch\(\) \{(.*?)^\}', text, re.S | re.M).group(1)
    for tag in tags:
        if tag == 'logs-f':
            continue                     # the menu's way to 'logs -f'
        assert re.search(rf'(^|\s){re.escape(tag)}\)', dispatch), f'menu item {tag} has no command'
        assert re.search(rf'^\s+{re.escape(tag)}\b', help_text, re.M), f'{tag} missing from help'


def test_medui_sh_never_prints_env_secrets():
    text = (ROOT / 'medui.sh').read_text()
    for secret in ('SECRET_KEY', 'MEDUI_ENCRYPTION_KEY', 'POSTGRES_PASSWORD'):
        assert secret not in text
    assert not re.search(r'(echo|printf|ok|warn)[^\n]*env_get BPSDB_PASSWORD', text)
    assert 'cat .env' not in text


def test_every_curl_has_a_time_limit():
    # Under WSL2's mirrored networking a closed port can leave curl waiting with no end, which
    # froze the menu's status screen when MedUI was stopped.
    for line in (ROOT / 'medui.sh').read_text().splitlines():
        if re.search(r'(^|[\s$(])curl\s', line):
            assert '--max-time' in line, line


def test_remove_asks_for_the_name_and_deletes_the_folder_last():
    text = (ROOT / 'medui.sh').read_text()
    body = text[text.index('cmd_remove() {'):text.index('cmd_windows() {')]
    # Never the home folder or the root, only a MedUI folder, and only this project's own folder.
    assert '"$HOME"' in body and '| / |' in body and 'compose.yaml' in body
    assert 'runs from $folder, not from here' in body
    # The typed name gates everything destructive.
    typed = body.index('Type the installation\'s name')
    assert typed < body.index('down -v --rmi local') < body.index('exec rm -rf -- "$APP_DIR"')
    assert '--profile demo down -v' in body                         # a demo's SQL Server goes too
    assert body.strip().splitlines()[-2].strip() == 'exec rm -rf -- "$APP_DIR"'   # the very last step
    assert '( cmd_backup ) </dev/null' in body           # the backup can't swallow the typed name
    # In the menu it runs outside a subshell, so the exec ends the menu with the folder.
    assert 'remove) cmd_remove ;;   # not in a subshell' in text
