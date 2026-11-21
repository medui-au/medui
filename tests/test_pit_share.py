"""./medui.sh pit connects Best Practice's incoming share as the app's /pit (medui_os 0.53.0).

The script runs for real in a throwaway folder, at a terminal (a pty), with stand-ins for sudo,
mount, docker and curl, and test paths for /mnt, /etc/medui and /etc/fstab: nothing on this
computer is mounted or changed. Share, account and password are invented."""
import os
import pty
import re
import select
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = 'invented-Pa55 word'


def test_compose_shows_the_share_to_the_app_as_pit():
    text = (ROOT / 'compose.yaml').read_text()
    assert '- ${PIT_HOST_DIR:-./pit}:/pit' in text
    assert 'PIT_CONTAINER_DIR: /pit' in text
    assert '/pit/' in (ROOT / '.gitignore').read_text().split()


def test_medui_sh_offers_it():
    text = (ROOT / 'medui.sh').read_text()
    assert subprocess.run(['bash', '-n', str(ROOT / 'medui.sh')]).returncode == 0
    assert 'pit) cmd_pit "$@" ;;' in text
    assert '#   pit [test|status|off]' in text
    help_text = subprocess.run(['bash', str(ROOT / 'medui.sh'), 'help'], capture_output=True, text=True).stdout
    assert 'pit [test|status|off]' in help_text and 'Nothing here prints' in help_text


def _stub(bin_dir, name, body):
    p = bin_dir / name
    p.write_text('#!/bin/sh\n' + body + '\n')
    p.chmod(0o755)


@pytest.fixture
def inst(tmp_path):
    inst, bin_dir, mnt, etc = (tmp_path / n for n in ('inst', 'bin', 'mnt', 'etc'))
    for d in (bin_dir, mnt, etc):
        d.mkdir()
    for rel in ('medui.sh', 'compose.yaml', 'install.sh', 'scripts/env_edit.py', 'app/version.py'):
        (inst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, inst / rel)
    (inst / '.env').write_text('COMPOSE_PROJECT_NAME=medui_os\nPIT_EXPORT_ENABLED=false\n')
    (inst / '.env').chmod(0o600)
    fstab = etc / 'fstab'
    fstab.write_text('# invented existing line\nUUID=0000 / ext4 defaults 0 1\n')
    log = tmp_path / 'calls.log'
    # sudo runs the command as this user, except what needs root; mount records itself.
    _stub(bin_dir, 'sudo', f'echo "sudo $*" >> {log}\ncase "$1" in chown|systemctl|apt-get) exit 0;; esac\nexec "$@"')
    _stub(bin_dir, 'mount', f'echo "mount $*" >> {log}\n[ "$1" = -t ] && touch "$4/.mounted"\nexit 0')
    _stub(bin_dir, 'umount', 'rm -f "$1/.mounted"; exit 0')
    _stub(bin_dir, 'mountpoint', '[ -e "$2/.mounted" ]')
    _stub(bin_dir, 'mount.cifs', 'exit 0')
    _stub(bin_dir, 'curl', 'echo ok')
    _stub(bin_dir, 'docker', f'echo "docker $*" >> {log}\nexit 0')
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'MEDUI_TEST_MNT': str(mnt),
           'MEDUI_TEST_ETC': str(etc / 'medui'), 'MEDUI_TEST_FSTAB': str(fstab)}
    return type('Inst', (), dict(dir=inst, env=env, fstab=fstab, log=log, mnt=mnt / 'medui_os_pit',
                                  cred=etc / 'medui' / 'medui_os_pit.credentials'))


def _run(inst, args, answers):
    """Run medui.sh at a terminal, answering each prompt in turn; return everything it printed."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(['bash', './medui.sh', *args], cwd=inst.dir, env=inst.env,
                            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    out, answers, deadline = b'', list(answers), time.time() + 30
    while time.time() < deadline:
        r, _, _ = select.select([master], [], [], 0.2)
        if r:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if answers and out.endswith((b': ', b') ')):
                os.write(master, answers.pop(0).encode() + b'\n')
        elif proc.poll() is not None:
            break
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)
    os.close(master)
    return proc.returncode, out.decode(errors='replace')


def test_connect_then_disconnect(inst):
    rc, out = _run(inst, ['pit'], ['\\\\BPSERVER\\BPS Share\\Incoming', 'PRACTICE\\pitwriter', PASSWORD, 'y'])
    assert rc == 0, out
    assert PASSWORD not in out and PASSWORD not in inst.log.read_text()
    assert (inst.mnt / '.mounted').exists(), inst.log.read_text()
    assert 'mount -t cifs //BPSERVER/BPS Share/Incoming ' in inst.log.read_text()

    line = [l for l in inst.fstab.read_text().splitlines() if 'medui_os_pit' in l]
    assert len(line) == 1, inst.fstab.read_text()
    share, mnt, kind, opts, *_ = line[0].split()
    assert share == '//BPSERVER/BPS\\040Share/Incoming' and mnt == str(inst.mnt) and kind == 'cifs'
    for o in (f'credentials={inst.cred}', 'uid=10001', 'forceuid', '_netdev', 'nofail',
              'x-systemd.before=docker.service'):
        assert o in opts.split(','), opts
    assert 'UUID=0000 / ext4' in inst.fstab.read_text()                 # other lines kept

    assert inst.cred.read_text() == f'username=pitwriter\npassword={PASSWORD}\ndomain=PRACTICE\n'
    assert oct(inst.cred.stat().st_mode & 0o777) == '0o600'
    env = (inst.dir / '.env').read_text()
    assert f'PIT_HOST_DIR={inst.mnt}' in env and 'PIT_EXPORT_ENABLED=true' in env
    assert 'up -d --force-recreate --wait app' in inst.log.read_text()  # the app sees /pit

    rc, out = _run(inst, ['pit', 'off'], ['y', 'y'])
    assert rc == 0, out
    assert 'medui_os_pit' not in inst.fstab.read_text()
    assert 'UUID=0000 / ext4' in inst.fstab.read_text()
    assert not inst.cred.exists() and not (inst.mnt / '.mounted').exists()
    env = (inst.dir / '.env').read_text()
    assert re.search(r'^PIT_HOST_DIR=$', env, re.M) and 'PIT_EXPORT_ENABLED=false' in env


def test_an_account_without_a_domain(inst):
    """0.53.0 stopped here: with no domain, the password file's last line returned false, and
    pipefail made the write look failed after it had happened, leaving the file unprotected."""
    rc, out = _run(inst, ['pit'], ['//BPSERVER/BPS/Incoming', 'pitwriter', PASSWORD, 'n'])
    assert rc == 0, out
    assert inst.cred.read_text() == f'username=pitwriter\npassword={PASSWORD}\n'
    assert oct(inst.cred.stat().st_mode & 0o777) == '0o600'
    assert len([l for l in inst.fstab.read_text().splitlines() if 'medui_os_pit' in l]) == 1


def test_the_password_file_is_never_readable_by_others():
    text = (ROOT / 'medui.sh').read_text()
    assert "sudo sh -c 'umask 077 && cat > \"$1\"' sh \"$PIT_CRED\"" in text
    assert 'sudo tee "$PIT_CRED"' not in text


def test_a_wrong_share_path_changes_nothing(inst):
    rc, out = _run(inst, ['pit'], ['C:\\BPS\\Incoming'])
    assert rc != 0 and "isn't a share path" in out
    assert 'medui_os_pit' not in inst.fstab.read_text() and not inst.cred.exists()


def test_a_demo_never_connects_one(inst):
    with open(inst.dir / '.env', 'a') as fh:
        fh.write('MEDUI_INSTANCE=demo\n')
    rc, out = _run(inst, ['pit'], [])
    assert rc != 0 and 'demo installation never sends to Best Practice' in out


# ── Setup → Messaging names /pit, and says on Save what is wrong (needs the test database) ──

from types import SimpleNamespace

DB_URL = os.environ.get('MEDUI_TEST_DATABASE_URL', '')
needs_db = pytest.mark.skipif(not DB_URL.rstrip('/').endswith('_test'),
                              reason='MEDUI_TEST_DATABASE_URL (a throwaway *_test database) not set')


@pytest.fixture
def ctx(monkeypatch):
    from app import create_app
    from app import config as app_config
    from app.extensions import db
    from app.models.user import User
    for name in dir(app_config):
        cls = getattr(app_config, name)
        if isinstance(cls, type) and hasattr(cls, 'SQLALCHEMY_DATABASE_URI'):
            monkeypatch.setattr(cls, 'SQLALCHEMY_DATABASE_URI', DB_URL)
    monkeypatch.setenv('PIT_CONTAINER_DIR', '/pit')
    app = create_app('dev')
    app.config.update(TESTING=True, SERVER_NAME='test.local', WTF_CSRF_ENABLED=False)
    with app.app_context():
        if not db.engine.url.database or not db.engine.url.database.endswith('_test'):
            pytest.exit('Refusing to run: the app is not connected to a *_test database.', returncode=2)
        db.drop_all()
        db.create_all()
        lead = User(username='lead', display_name='Lead', security_level=9, password_hash='x')
        db.session.add(lead)
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as s:
            s['_user_id'] = str(lead.id)
            s['_fresh'] = True
        yield SimpleNamespace(app=app, client=client)
        db.session.remove()
        db.drop_all()


def _save_pit(ctx, folder):
    from flask import g
    g.pop('_login_user', None)
    r = ctx.client.post('/setup/messaging/save-pit', data={'pit_export_path': folder})
    assert r.status_code == 200
    return r.get_data(as_text=True)


@needs_db
def test_setup_names_pit_and_refuses_a_unc_path(ctx):
    html = _save_pit(ctx, '\\\\BPSERVER\\BPS\\Incoming')
    assert 'PIT settings saved, but:' in html and 'Windows path' in html
    assert 'connect it with ./medui.sh pit, then enter /pit here' in html


@needs_db
def test_setup_accepts_a_writable_folder(ctx, tmp_path):
    html = _save_pit(ctx, str(tmp_path))
    assert 'PIT settings saved.' in html and 'saved, but' not in html
