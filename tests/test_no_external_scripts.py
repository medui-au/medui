"""No page loads code or styles from another server: the front-end libraries are vendored.

A workstation should never fetch scripts or stylesheets from a third party (a CDN can change,
or be compromised). Links that people click are fine; this checks <script src> and
<link rel="stylesheet" href> only.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'app' / 'templates'
VENDOR = ROOT / 'app' / 'static' / 'vendor'

_SCRIPT = re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)', re.I)
_STYLE = re.compile(r'<link\b(?=[^>]*\brel\s*=\s*["\']?stylesheet)[^>]*\bhref\s*=\s*["\']([^"\']+)', re.I)
_EXTERNAL = re.compile(r'^(https?:)?//', re.I)


def test_templates_load_no_external_scripts_or_styles():
    found = []
    for path in TEMPLATES.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        for rx in (_SCRIPT, _STYLE):
            for url in rx.findall(text):
                if _EXTERNAL.match(url.strip()):
                    found.append(f'{path.relative_to(ROOT)}: {url}')
    assert not found, 'External scripts or stylesheets:\n' + '\n'.join(found)


def test_vendored_files_are_present_with_licences():
    referenced = set()
    for path in TEMPLATES.rglob('*.html'):
        referenced |= set(re.findall(r"filename='vendor/([^']+)'", path.read_text(encoding='utf-8')))
    assert referenced, 'no vendored file is referenced'
    for rel in referenced:
        f = VENDOR / rel
        assert f.is_file(), f'missing vendored file {rel}'
        assert any(p.name.upper().startswith('LICENSE') for p in f.parent.iterdir()), \
            f'no licence beside {rel}'
