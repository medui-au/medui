"""OCR_ENABLED: the .env switch for OCR (medui_os 0.50.0).

Addresses here are invented.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize('value, on', [(None, True), ('true', True), ('false', False),
                                       ('0', False), ('yes', True)])
def test_config_default_is_on(monkeypatch, value, on):
    from app import config
    if value is None:
        monkeypatch.delenv('OCR_ENABLED', raising=False)
    else:
        monkeypatch.setenv('OCR_ENABLED', value)
    assert config._bool('OCR_ENABLED', True) is on


def test_switched_off_means_no_ocr_at_all(monkeypatch):
    """Off overrides the environment address and any saved service, before the database."""
    from app.services import ocr_service
    app = Flask(__name__)
    app.config.update(OCR_ENABLED=False, OCR_SERVICE_URL='http://liteparse.example:5707')
    with app.app_context():
        assert ocr_service._get_config() is None
        assert not ocr_service.is_configured()


def test_env_example_ships_it_on():
    assert re.search(r'^OCR_ENABLED=true$', (ROOT / '.env.example').read_text(), re.M)


def test_installer_writes_and_remembers_the_switch():
    text = (ROOT / 'install.sh').read_text()
    assert 'env_set OCR_ENABLED "$([ "$OCR" = 1 ] && echo true || echo false)"' in text
    assert '[ "$(env_get OCR_ENABLED)" = false ] && OCR=0' in text


def test_upgrade_adds_the_line_once_after_the_backup():
    text = (ROOT / 'upgrade.sh').read_text()
    step6 = text[text.index('# ---- 6. database'):text.index('# ---- 7. seeds')]
    assert 'if [ -z "$(env_get OCR_ENABLED)" ]' in step6
    assert 'env_get OCR_ENABLED' not in text[:text.index('# ---- 3.')]   # nothing before the backup


def _fake_docker(bin_dir):
    docker = bin_dir / 'docker'
    docker.write_text('#!/bin/sh\ncase "$*" in *"ps --status running --services"*) echo db;; '
                      '*"ps --services"*) echo db; echo liteparse;; esac\nexit 0\n')
    docker.chmod(0o755)


def _git(cwd, *args):
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(not shutil.which('git'), reason='needs git')
def test_upgrade_hands_over_to_the_new_versions_script(tmp_path):
    """The installed upgrade.sh runs the new version's upgrade.sh, once, with the same options.

    A dry run in a throwaway repository, with a stand-in for docker: nothing real is touched."""
    src, bare, inst, bin_dir = (tmp_path / n for n in ('src', 'origin.git', 'inst', 'bin'))
    bin_dir.mkdir()
    _fake_docker(bin_dir)
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', '.env',
                                                             'backups', 'node_modules'))
    _git(src, 'init', '-q', '-b', 'main')
    _git(src, 'add', '-A')
    _git(src, 'commit', '-qm', 'installed')
    _git(tmp_path, 'clone', '-q', '--bare', str(src), str(bare))
    _git(tmp_path, 'clone', '-q', str(bare), str(inst))
    script = (src / 'upgrade.sh').read_text()
    marker = 'echo "NEW SCRIPT: $* temp-left=$([ -e "${MEDUI_UPGRADE_HANDOFF:-/none}" ] && echo yes || echo no)"; exit 0\n'
    (src / 'upgrade.sh').write_text(script.replace('ARGS=("$@")\n', 'ARGS=("$@")\n' + marker, 1))
    _git(src, 'commit', '-qam', 'new release')
    _git(src, 'push', '-q', str(bare), 'main')
    env_text = (inst / '.env.example').read_text()
    (inst / '.env').write_text(env_text)
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
    env.pop('MEDUI_UPGRADE_HANDOFF', None)
    r = subprocess.run(['bash', './upgrade.sh', '--dry-run', '--yes'], cwd=inst, env=env,
                       capture_output=True, text=True, timeout=60)
    assert 'upgrade script' in r.stdout, r.stdout + r.stderr
    assert 'NEW SCRIPT: --dry-run --yes temp-left=no' in r.stdout, r.stdout + r.stderr


def test_features_offers_ocr_and_moves_the_container():
    text = (ROOT / 'medui.sh').read_text()
    assert re.search(r'^FEATURES=\(OCR_ENABLED ', text, re.M)
    assert 'OCR_ENABLED=false) has_container liteparse && compose --profile ocr rm -sf liteparse' in text
    assert 'compose --profile ocr up -d --build --wait liteparse' in text
    assert subprocess.run(['bash', '-n', str(ROOT / 'medui.sh')]).returncode == 0
