"""The in-app guide: MedUI's own documentation, rendered for administrators (medui_os only).

Every Markdown page under docs/ can be shown, and a few in the repository's top folder that the
docs link to. A link between pages stays in the app; a link to anything else in the MedUI folder
(a script, a CSV file) becomes the file's name, since a browser can't open it from here.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

from flask import current_app, url_for
from markupsafe import Markup, escape

# Outside docs/: the pages docs/ links to. They are copied into the image (Dockerfile).
TOP_LEVEL = ('README.md', 'CHANGELOG.md', 'SECURITY.md', 'AGENTS.md', 'CONTRIBUTING.md',
             'scripts/windows/README.md')
TOP_PREFIX = 'repo/'          # their names in the guide's address: /setup/guide/repo/README

_ENABLED_AI = re.compile(r'<!-- medui:enabled-ai -->.*?<!-- /medui:enabled-ai -->', re.S)
_LINK = re.compile(r'<a href="([^"]*)">(.*?)</a>', re.S)
# A doc's own diagram: <img ... src="images/x.svg">, embedded so the guide needs no file route.
_IMG = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+\.svg)(")')
_SCHEME = re.compile(r'^[a-z][a-z0-9+.-]*:', re.I)


def root() -> Path:
    return Path(current_app.root_path).parent


def repo_path(name: str) -> str | None:
    """The file a guide name stands for, relative to the MedUI folder; None if it isn't one."""
    if not name or '\\' in name or name.startswith('/') or '..' in name.split('/'):
        return None
    if name.startswith(TOP_PREFIX):
        rel = name[len(TOP_PREFIX):] + '.md'
        return rel if rel in TOP_LEVEL else None
    rel = f'docs/{name}.md'
    return rel if posixpath.normpath(rel) == rel else None


def guide_name(rel: str) -> str | None:
    """The guide name for a file relative to the MedUI folder; None if the guide can't show it."""
    if rel.startswith('docs/') and rel.endswith('.md'):
        return rel[len('docs/'):-len('.md')]
    if rel in TOP_LEVEL:
        return TOP_PREFIX + rel[:-len('.md')]
    return None


def _rewrite(html: str, rel: str) -> str:
    here = posixpath.dirname(rel)

    def link(m):
        href, text = m.group(1), m.group(2)
        if not href or href.startswith(('#', '/')) or _SCHEME.match(href):
            return m.group(0)
        target, _, anchor = href.partition('#')
        path = posixpath.normpath(posixpath.join(here, target))
        name = guide_name(path) if not path.startswith('..') else None
        if name and (root() / path).is_file():
            return f'<a href="{url_for("setup.guide", name=name)}{"#" + anchor if anchor else ""}">{text}</a>'
        # Not a page the guide shows: say where the file is instead of a link that goes nowhere.
        return (f'{text} <span class="guide-file" title="A file in the MedUI folder">'
                f'(<code>{escape(path)}</code> in the MedUI folder)</span>')
    def image(m):
        src = m.group(2)
        if src.startswith('/') or _SCHEME.match(src):
            return m.group(0)
        path = posixpath.normpath(posixpath.join(here, src))
        file = root() / path
        if path.startswith('..') or not path.startswith('docs/') or not file.is_file():
            return m.group(0)
        import base64
        data = base64.b64encode(file.read_bytes()).decode('ascii')
        return f'{m.group(1)}data:image/svg+xml;base64,{data}{m.group(3)}'
    return _IMG.sub(image, _LINK.sub(link, html))


def render(name: str) -> tuple[str, Markup] | None:
    """(title, body) for a guide page, or None if there is no such page."""
    import markdown as md_lib
    rel = repo_path(name)
    if rel is None:
        return None
    path = root() / rel
    try:
        path.resolve().relative_to(root().resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    text = path.read_text(encoding='utf-8')
    heading = re.search(r'^# (.+)$', text, re.M)
    title = heading.group(1).strip() if heading else name
    html = md_lib.markdown(text, extensions=['tables', 'fenced_code', 'toc'])
    if _ENABLED_AI.search(html):                 # the AI-use policy's Appendix A, filled in now
        from app.services import ai_policy_service
        html = _ENABLED_AI.sub(lambda _: ai_policy_service._appendix('html'), html)
    return title, Markup(_rewrite(html, rel))
