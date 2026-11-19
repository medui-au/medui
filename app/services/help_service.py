"""In-app help (plans/help_system_plan.md, ADR-102).

Help lives in ``app/help/<topic>.md``: YAML front matter (title, area, roles, reviewed,
related), an introduction, then sections, each a level-2 heading with a fixed ID:

    ## Charts of results {#charts}

A section is addressed as ``<topic>.<section>``, e.g. ``results-outside-range.charts``;
the ``help('…')`` template helper puts a [?] beside a part of a screen that opens that
section in the side panel. ``/help`` lists and searches the topics a user's role may see.

Files are read again when they change, so editing help needs no restart.
"""
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import yaml
from flask import current_app
from markupsafe import Markup

ROLES = ('reception', 'nurse', 'doctor', 'admin')
AREAS = ('Getting started', 'Patients', 'Day sheet and inbox', 'AI functions',
         'Library and Comms', 'Governance', 'Settings', 'Administration')
_SECTION = re.compile(r'^## +(.+?) +\{#([a-z0-9-]+)\} *$', re.M)
_ID = re.compile(r'^[a-z0-9-]+$')
_TEMPLATE_REF = re.compile(r"""help\(\s*['"]([a-z0-9-]+\.[a-z0-9-]+)['"]\s*\)""")
_SCRIPT_REF = re.compile(r"""dataset\.help\s*=\s*['"]([a-z0-9-]+\.[a-z0-9-]+)['"]""")   # a [?] made by a script
_LINK_REF = re.compile(r'\]\(help:([a-z0-9-]+)(?:\.([a-z0-9-]+))?\)')                    # [text](help:topic.section)


@dataclass
class Section:
    id: str
    title: str
    text: str                       # Markdown


@dataclass
class Topic:
    id: str
    title: str
    area: str
    roles: tuple
    reviewed: str
    related: tuple
    intro: str                      # Markdown before the first section
    requires_ai: bool = False       # hidden while AI features are off (AI_ENABLED)
    sections: list = field(default_factory=list)

    def section(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)


_cache: dict = {'stamp': None, 'topics': {}, 'problems': []}


def _help_dir() -> Path:
    return Path(current_app.root_path) / 'help'


def _parse(path: Path) -> tuple[Topic | None, list[str]]:
    problems = []
    raw = path.read_text(encoding='utf-8')
    if not raw.startswith('---\n') or '\n---\n' not in raw[4:]:
        return None, [f'{path.name}: no front matter (--- … ---) at the top']
    head, body = raw[4:].split('\n---\n', 1)
    try:
        meta = yaml.safe_load(head) or {}
    except yaml.YAMLError as exc:
        return None, [f'{path.name}: front matter is not valid YAML ({exc})']
    topic_id = path.stem
    if not _ID.match(topic_id):
        problems.append(f'{path.name}: file name must be lower-case letters, digits and "-"')
    roles = tuple(meta.get('roles') or ())
    for r in roles:
        if r not in ROLES:
            problems.append(f'{path.name}: unknown role "{r}" (use {", ".join(ROLES)})')
    if not roles:
        problems.append(f'{path.name}: no roles')
    for key in ('title', 'area', 'reviewed'):
        if not meta.get(key):
            problems.append(f'{path.name}: no {key}')
    if meta.get('area') and meta['area'] not in AREAS:
        problems.append(f'{path.name}: unknown area "{meta["area"]}"')
    parts = _SECTION.split(body)
    topic = Topic(id=topic_id, title=str(meta.get('title') or topic_id), area=str(meta.get('area') or ''),
                  roles=roles, reviewed=str(meta.get('reviewed') or ''),
                  related=tuple(meta.get('related') or ()), intro=parts[0].strip(),
                  requires_ai=bool(meta.get('requires_ai')))
    seen = set()
    for i in range(1, len(parts), 3):
        title, sid, text = parts[i], parts[i + 1], parts[i + 2].strip()
        if sid in seen:
            problems.append(f'{path.name}: section id "{sid}" used twice')
        seen.add(sid)
        topic.sections.append(Section(id=sid, title=title.strip(), text=text))
    for stray in re.findall(r'^## (?!.*\{#[a-z0-9-]+\} *$).*$', body, re.M):
        problems.append(f'{path.name}: heading without an id: "{stray}" (add {{#some-id}})')
    return topic, problems


def topics() -> dict[str, Topic]:
    """All help topics, read again when a file changes."""
    folder = _help_dir()
    files = sorted(folder.glob('*.md')) if folder.is_dir() else []
    stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if stamp != _cache['stamp']:
        found, problems = {}, []
        for f in files:
            topic, issues = _parse(f)
            problems += issues
            if topic:
                found[topic.id] = topic
        for t in found.values():
            for rel in t.related:
                if rel not in found:
                    problems.append(f'{t.id}.md: related topic "{rel}" does not exist')
        _cache.update(stamp=stamp, topics=found, problems=problems)
    return _cache['topics']


def role_of(user) -> str:
    """The help role for a user (ADR-057 levels)."""
    if getattr(user, 'is_admin', False):
        return 'admin'
    level = getattr(user, 'security_level', 0) or 0
    return 'doctor' if level >= 5 else 'nurse' if level >= 3 else 'reception'


def can_see(topic: Topic, user) -> bool:
    if topic.requires_ai and not current_app.config.get('AI_ENABLED', True):
        return False
    role = role_of(user)
    return role == 'admin' or role in topic.roles


def visible_topics(user) -> list[Topic]:
    return [t for t in topics().values() if can_see(t, user)]


def find(ref: str) -> tuple[Topic | None, Section | None]:
    """'topic.section' -> (topic, section); either may be None."""
    topic_id, _, section_id = ref.partition('.')
    topic = topics().get(topic_id)
    return topic, topic.section(section_id) if topic and section_id else None


def render(text: str) -> Markup:
    # Help is written by us and reviewed, like the templates; links to other help
    # sections are written as (help:topic.section) and become in-app links.
    text = re.sub(r'\(help:([a-z0-9-]+)(?:\.([a-z0-9-]+))?\)',
                  lambda m: f'(/help/{m.group(1)}' + (f'#{m.group(2)})' if m.group(2) else ')'), text)
    return Markup(markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists']))


def search(query: str, user, limit: int = 30) -> list[dict]:
    """Sections whose title or text holds every word of the query, best first."""
    words = [w for w in re.findall(r'\w+', query.lower()) if len(w) > 1]
    if not words:
        return []
    hits = []
    for t in visible_topics(user):
        for s in t.sections:
            plain = re.sub(r'[*_`#>\[\]()]', '', s.text)
            hay = f'{t.title} {s.title} {plain}'.lower()
            if not all(w in hay for w in words):
                continue
            score = sum(3 * (w in t.title.lower()) + 2 * (w in s.title.lower()) + hay.count(w) for w in words)
            hits.append({'topic': t, 'section': s, 'score': score, 'snippet': _snippet(plain, words)})
    return sorted(hits, key=lambda h: -h['score'])[:limit]


def _snippet(text: str, words: list[str], width: int = 160) -> Markup:
    low = text.lower()
    at = min((low.find(w) for w in words if w in low), default=0)
    start = max(0, at - width // 3)
    piece = text[start:start + width].replace('\n', ' ')
    out = html.escape(piece)
    for w in words:
        out = re.sub(f'({re.escape(html.escape(w))})', r'<mark>\1</mark>', out, flags=re.I)
    return Markup(('…' if start else '') + out + ('…' if start + width < len(text) else ''))


def check() -> list[str]:
    """Problems in the help files, and [?] buttons in templates pointing nowhere."""
    found = topics()
    problems = list(_cache['problems'])
    templates = Path(current_app.root_path) / 'templates'
    for path in sorted(templates.rglob('*.html')):
        for ref in _TEMPLATE_REF.findall(path.read_text(encoding='utf-8')):
            topic, section = find(ref)
            if not topic or not section:
                problems.append(f'{path.relative_to(templates)}: help("{ref}") points to no section')
    scripts = Path(current_app.root_path) / 'static' / 'js'
    for path in sorted(scripts.glob('*.js')):
        for ref in _SCRIPT_REF.findall(path.read_text(encoding='utf-8')):
            topic, section = find(ref)
            if not topic or not section:
                problems.append(f'static/js/{path.name}: dataset.help = "{ref}" points to no section')
    for t in found.values():
        for text in [t.intro] + [s.text for s in t.sections]:
            for topic_id, section_id in _LINK_REF.findall(text):
                target = found.get(topic_id)
                if not target or (section_id and not target.section(section_id)):
                    problems.append(f'{t.id}.md: link to help:{topic_id}{"." + section_id if section_id else ""} goes nowhere')
    if not found:
        problems.append('no help topics found in app/help/')
    return problems
