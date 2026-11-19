"""install.sh: a new installation is named after its folder, and its default ports move when taken.

Runs install.sh --dry-run in a scratch folder, so it changes nothing. Every value here is invented.
"""
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(not Path('/run/systemd/system').is_dir() or os.geteuid() == 0
                                or shutil.which('ss') is None,
                                reason='install.sh checks need systemd, ss and a normal user')


def _copy(tmp_path, folder):
    d = tmp_path / folder
    (d / 'scripts').mkdir(parents=True)
    for f in ('install.sh', 'compose.yaml', 'scripts/init_env.py'):
        shutil.copy2(ROOT / f, d / f)
    return d


def _dry_run(d, *args):
    r = subprocess.run(['bash', str(d / 'install.sh'), '--dry-run', '--no-apt', '--yes',
                        '--timezone', 'brisbane', *args], cwd=d, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def test_new_install_is_named_after_its_folder(tmp_path):
    code, out = _dry_run(_copy(tmp_path, 'Invented Clinic.Demo'), '--app-port', str(_free_port()),
                         '--db-port', str(_free_port()), '--ocr-port', str(_free_port()))
    assert code == 0, out
    assert "project 'invented_clinic_demo'" in out


def test_name_option_and_existing_env_win_over_the_folder(tmp_path):
    d = _copy(tmp_path, 'invented_demo_trial')
    ports = ['--app-port', str(_free_port()), '--db-port', str(_free_port()), '--ocr-port', str(_free_port())]
    assert "project 'medui_trial'" in _dry_run(d, '--name', 'medui_trial', *ports)[1]
    (d / '.env').write_text('APP_PORT=5025\n')   # an older .env without the name keeps medui_os
    assert "project 'medui_os'" in _dry_run(d, *ports)[1]


def test_default_port_moves_but_a_chosen_one_does_not(tmp_path):
    d = _copy(tmp_path, 'invented_demo_trial')
    with socket.socket() as busy:
        busy.bind(('127.0.0.1', 0))
        busy.listen()
        port = busy.getsockname()[1]
        others = ['--db-port', str(_free_port()), '--ocr-port', str(_free_port())]
        code, out = _dry_run(d, '--app-port', str(port), *others)
        assert code != 0 and f'Port {port} (MedUI) is already in use' in out
        # The default (5005) moves on when taken; it is free or busy here, either way no failure.
        code, out = _dry_run(d, *others)
        assert code == 0, out
        assert 'Ports: MedUI 50' in out


def test_https_dry_run_runs_to_the_end(tmp_path):
    # 0.37.1: the HTTPS dry run stopped at its last line (CHECK_NAME was only set on a real run).
    ports = ['--app-port', str(_free_port()), '--db-port', str(_free_port()), '--ocr-port', str(_free_port()),
             '--https-port', str(_free_port()), '--http-port', str(_free_port())]
    code, out = _dry_run(_copy(tmp_path, 'invented_https_trial'), '--https', '--https-name', 'invented-pc',
                         '--https-ip', '192.0.2.10', *ports)
    assert code == 0, out
    assert 'unbound variable' not in out
    assert 'MedUI answers at https://invented-pc:' in out
    assert 'Dry run' in out or 'Done' in out
