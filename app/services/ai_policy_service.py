"""The practice's AI-use policy (Governance → AI-use policy, ADR-158).

The wording is the practice's own: administrators edit it in MedUI, starting from the template
beside the governance templates. Appendix A, between the two marker comments, is filled in each
time the policy is shown, printed or downloaded, with the AI providers and models enabled then.

Every save is kept as a numbered version in the practice document store (ADR-184), with Appendix A
as it was at that moment; a version can be approved once, with the next review date.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from flask import current_app
from markupsafe import Markup, escape

SETTING_KEY = 'governance.ai_policy'        # before ADR-184: carried over as version 1
DOC_KEY = 'ai_use_policy'
TEMPLATE = (Path(__file__).resolve().parent.parent
            / 'templates' / 'governance' / 'ai_policy' / 'policy_template.md')
MARKERS = re.compile(r'<!-- medui:enabled-ai -->.*?<!-- /medui:enabled-ai -->', re.S)
_SLOT = 'MEDUIENABLEDAISLOT'
MAX_LENGTH = 100_000


def template_text() -> str:
    return TEMPLATE.read_text(encoding='utf-8')


def _user_name(user) -> str | None:
    return getattr(user, 'display_name', None) or getattr(user, 'username', None)


def _document(create: bool = False):
    from app.extensions import db
    from app.models.practice_document import PracticeDocument
    doc = PracticeDocument.query.filter_by(key=DOC_KEY).first()
    if doc is None and create:
        doc = PracticeDocument(key=DOC_KEY, kind='policy', title='AI-use policy')
        db.session.add(doc)
        db.session.flush()
    return doc


def _carry_over() -> None:
    """The policy saved before versions were kept becomes version 1, once."""
    from app.extensions import db
    from app.models.practice_document import PracticeDocumentVersion
    from app.models.system_setting import SystemSetting
    doc = _document()
    if doc is not None and doc.versions:
        return
    saved = SystemSetting.get(SETTING_KEY)
    if not (isinstance(saved, dict) and (saved.get('markdown') or '').strip()):
        return
    try:
        when = datetime.fromisoformat(saved.get('updated_at') or '').astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        when = datetime.now(timezone.utc).replace(tzinfo=None)
    doc = _document(create=True)
    db.session.add(PracticeDocumentVersion(
        document_id=doc.id, number=1, markdown=saved['markdown'], saved_by_name=saved.get('updated_by'),
        saved_at=when, note='The policy as saved before MedUI kept versions'))
    db.session.commit()


def versions() -> list:
    """Every saved version, newest first."""
    _carry_over()
    doc = _document()
    return list(reversed(doc.versions)) if doc else []


def version(number: int):
    from app.models.practice_document import PracticeDocumentVersion
    doc = _document()
    if doc is None:
        return None
    return PracticeDocumentVersion.query.filter_by(document_id=doc.id, number=number).first()


def latest():
    found = versions()
    return found[0] if found else None


def get() -> dict:
    """The policy in use: the latest saved version, or the template until one is saved."""
    v = latest()
    if v is not None:
        return {'markdown': v.markdown, 'is_template': False, 'version': v,
                'updated_by': v.saved_by_name, 'updated_at': v.saved_at}
    return {'markdown': template_text(), 'is_template': True, 'version': None, 'updated_by': None,
            'updated_at': None}


def _snapshot() -> dict | None:
    try:
        return {'appendix_a': enabled_ai()}
    except Exception as exc:                 # the version is still saved without its list
        current_app.logger.warning('ai_policy: enabled AI list failed: %s', type(exc).__name__)
        return None


def save(markdown: str, user, note: str = ''):
    """Save the text as a new version, with Appendix A as it is now. Returns the new version, or
    None if the text is the same as the latest version's."""
    from app.extensions import db
    from app.models.practice_document import PracticeDocumentVersion
    text = (markdown or '').replace('\r\n', '\n')
    if not text.strip():
        raise ValueError('The policy is empty.')
    if len(text) > MAX_LENGTH:
        raise ValueError(f'The policy is longer than {MAX_LENGTH:,} characters.')
    current = latest()
    if current is not None and current.markdown == text:
        return None
    doc = _document(create=True)
    v = PracticeDocumentVersion(
        document_id=doc.id, number=(current.number + 1) if current else 1, markdown=text,
        note=(note or '').strip()[:300] or None, snapshot=_snapshot(),
        saved_by_id=getattr(user, 'id', None), saved_by_name=_user_name(user))
    db.session.add(v)
    db.session.commit()
    return v


def approve(number: int, user, review_due_on: date):
    """Record the approval of the latest version, once, with the next review date."""
    from app.extensions import db
    v, current = version(number), latest()
    if v is None:
        raise ValueError('There is no such version.')
    if current is None or v.id != current.id:
        raise ValueError('Only the latest version can be approved.')
    if v.approved_at:
        raise ValueError(f'Version {v.number} is already approved.')
    if not review_due_on or review_due_on <= date.today():
        raise ValueError('Give the next review date, in the future.')
    v.approved_by_id = getattr(user, 'id', None)
    v.approved_by_name = _user_name(user)
    v.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    v.review_due_on = review_due_on
    db.session.commit()
    return v


# ── Appendix A: what is enabled now ───────────────────────────────────────────

def enabled_ai() -> dict:
    from app.models.ai_provider import AIProviderConfig, AIModel
    from app.models.system_setting import SystemSetting
    from app.services import practice_time
    try:
        from app.version import __version__ as version     # medui_os has a release number
    except ImportError:
        version = None
    asr_id = SystemSetting.get('active_asr_model_id')
    providers = []
    for p in AIProviderConfig.query.filter_by(is_enabled=True).order_by(AIProviderConfig.name):
        models = []
        for m in (AIModel.query.filter_by(provider_id=p.id, is_enabled=True)
                  .order_by(AIModel.display_name, AIModel.model_id)):
            uses = [label for on, label in (
                (m.is_recommended, 'recommended'), (m.show_in_ai_assist, 'AI assistant'),
                (m.show_in_chatbot, 'chatbots'),
                (asr_id and str(m.id) == str(asr_id), 'voice (scribe)')) if on]
            models.append({'name': m.display_name or m.model_id, 'model_id': m.model_id,
                           'uses': uses})
        providers.append({'name': p.name, 'local': bool(p.is_local), 'models': models})
    return {
        'ai_enabled': bool(current_app.config.get('AI_ENABLED', True)),
        'practice': (SystemSetting.get('general.practice_name', '') or '').strip(),
        'version': version,
        'listed_at': datetime.now(practice_time.zone()).strftime('%d %B %Y, %H:%M'),
        'providers': providers,
    }


def _runs(p: dict) -> str:
    return ("On the practice's computers" if p['local'] else
            'Cloud: receives redacted requests only')


def _stamp(info: dict) -> str:
    where = f"{info['practice']}, " if info['practice'] else ''
    release = f"MedUI {info['version']}" if info['version'] else 'MedUI'
    when = f" when version {info['saved_version']} was saved," if info.get('saved_version') else ''
    return f"Listed {info['listed_at']}{when} from this installation ({where}{release})."


def appendix_markdown(info: dict) -> str:
    lines = [f"**{_stamp(info)}**", '']
    if not info['ai_enabled']:
        lines += ['**AI is switched off in this installation:** no AI provider or model is used.', '']
    if not info['providers']:
        return '\n'.join(lines + ['No AI provider is enabled.'])
    lines += ['| Provider | Runs | Model | Used for |', '|---|---|---|---|']
    cell = lambda v: str(v).replace('|', '\\|')
    for p in info['providers']:
        for i, m in enumerate(p['models'] or [{'name': '(no model enabled)', 'model_id': '',
                                                'uses': []}]):
            name = m['name'] + (f" (`{m['model_id']}`)"
                                if m['model_id'] and m['model_id'] != m['name'] else '')
            lines.append(f"| {cell(p['name']) if i == 0 else ''} | {_runs(p) if i == 0 else ''} | "
                         f"{cell(name)} | {cell(', '.join(m['uses']) or 'available')} |")
    return '\n'.join(lines)


def appendix_html(info: dict) -> str:
    out = [f'<p class="policy-stamp"><strong>{escape(_stamp(info))}</strong></p>']
    if not info['ai_enabled']:
        out.append('<p><strong>AI is switched off in this installation:</strong> no AI provider '
                   'or model is used.</p>')
    if not info['providers']:
        out.append('<p>No AI provider is enabled.</p>')
        return '\n'.join(out)
    out.append('<table><thead><tr><th>Provider</th><th>Runs</th><th>Model</th><th>Used for</th>'
               '</tr></thead><tbody>')
    for p in info['providers']:
        for i, m in enumerate(p['models'] or [{'name': '(no model enabled)', 'model_id': '',
                                                'uses': []}]):
            name = escape(m['name'])
            if m['model_id'] and m['model_id'] != m['name']:
                name += Markup(' <code>{}</code>').format(m['model_id'])
            out.append(f"<tr><td>{escape(p['name']) if i == 0 else ''}</td>"
                       f"<td>{escape(_runs(p)) if i == 0 else ''}</td><td>{name}</td>"
                       f"<td>{escape(', '.join(m['uses']) or 'available')}</td></tr>")
    out.append('</tbody></table>')
    return '\n'.join(out)


def _appendix(kind: str, saved: dict | None = None) -> str:
    if saved is not None:
        return appendix_html(saved) if kind == 'html' else appendix_markdown(saved)
    try:
        info = enabled_ai()
    except Exception as exc:                 # the policy still shows without its list
        current_app.logger.warning('ai_policy: enabled AI list failed: %s', type(exc).__name__)
        msg = ("The list of enabled providers and models couldn't be read: see Application "
               "Setup → Providers and Models.")
        return f'<p><em>{msg}</em></p>' if kind == 'html' else f'*{msg}*'
    return appendix_html(info) if kind == 'html' else appendix_markdown(info)


# ── the whole policy ──────────────────────────────────────────────────────────

_ALLOWED_URL = re.compile(r'^(https?://|mailto:|#|/)', re.I)


def saved_appendix(v) -> dict | None:
    """A version's Appendix A as it was when it was saved; None if it has none (e.g. carried over)."""
    info = (v.snapshot or {}).get('appendix_a') if v is not None else None
    return {**info, 'saved_version': v.number} if info else None


def to_html(markdown: str, saved: dict | None = None, missing: str | None = None) -> Markup:
    """The policy as HTML. The text is the practice's, typed by an administrator: raw HTML in it
    is shown as text, and links go only to web, mail or in-page addresses. Appendix A is the list
    as it is now, or `saved` (a version's own); `missing` replaces it when a version has none."""
    import markdown as md_lib
    text = MARKERS.sub(_SLOT, markdown) if MARKERS.search(markdown) else markdown
    text = text.replace('<', '&lt;')
    html = md_lib.markdown(text, extensions=['tables', 'sane_lists'])

    def url(m):
        attr, value = m.group(1), m.group(2)
        return m.group(0) if _ALLOWED_URL.match(value) else f'{attr}="#"'
    html = re.sub(r'\b(href|src)="([^"]*)"', url, html)
    appendix = f'<p><em>{escape(missing)}</em></p>' if missing else _appendix('html', saved)
    if _SLOT in html:
        html = re.sub(rf'<p>\s*{_SLOT}\s*</p>|{_SLOT}', lambda _: appendix, html, count=1)
    else:
        html += '\n<h2>Appendix A: AI providers and models enabled</h2>\n' + appendix
    return Markup(html)


def to_markdown(markdown: str, saved: dict | None = None, missing: str | None = None) -> str:
    """The policy as a Markdown file, with Appendix A as it is now, or a version's own."""
    appendix = f'*{missing}*' if missing else _appendix('markdown', saved)
    if MARKERS.search(markdown):
        return MARKERS.sub(lambda _: appendix, markdown, count=1)
    return markdown.rstrip() + '\n\n## Appendix A: AI providers and models enabled\n\n' + appendix + '\n'
