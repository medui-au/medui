"""The OCR container is built from docker/liteparse/: upstream's server at a pinned commit, with
our package.json and lockfile choosing the LiteParse version (0.54.0)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LP = ROOT / 'docker' / 'liteparse'
COMMIT = '70cee35fb429f531d657d3328dc9939c89c0312b'


def _version():
    spec = json.loads((LP / 'package.json').read_text())['dependencies']['@llamaindex/liteparse']
    return spec.lstrip('^~')


def test_compose_builds_our_folder():
    text = (ROOT / 'compose.yaml').read_text()
    assert 'context: ./docker/liteparse' in text
    assert 'liteparse-server.git' not in text


def test_dockerfile_pins_upstream_and_uses_our_lockfile():
    text = (LP / 'Dockerfile').read_text()
    assert f'ARG LITEPARSE_SERVER_COMMIT={COMMIT}' in text
    assert 'COPY package.json pnpm-lock.yaml /workspace/' in text
    assert 'pnpm install --frozen-lockfile' in text
    assert re.search(r'corepack prepare pnpm@[\d.]+ --activate', text)


def test_package_and_lockfile_agree():
    version = _version()
    lock = (LP / 'pnpm-lock.yaml').read_text()
    root = lock.split('importers:')[1].split('\n\n  packages/')[0]
    assert f"specifier: ^{version}\n        version: {version}\n" in root
    assert f"'@llamaindex/liteparse@{version}':" in lock


def test_docs_name_the_version():
    text = (ROOT / 'docs' / 'ocr.md').read_text()
    assert f'LiteParse {_version()}' in text and COMMIT in text
