"""The practice's AI-use policy (Governance → AI-use policy, ADR-158).

The wording is the practice's own: administrators edit it in MedUI, starting from the template
beside the governance templates. Appendix A, between the two marker comments, is filled in each
time the policy is shown, printed or downloaded, with the AI providers and models enabled then.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from markupsafe import Markup, escape

SETTING_KEY = 'governance.ai_policy'
TEMPLATE = (Path(__file__).resolve().parent.parent
            / 'templates' / 'governance' / 'ai_policy' / 'policy_template.md')
MARKERS = re.compile(r'<!-- medui:enabled-ai -->.*?<!-- /medui:enabled-ai -->', re.S)
_SLOT = 'MEDUIENABLEDAISLOT'
MAX_LENGTH = 100_000


def template_text() -> str:
    return TEMPLATE.read_text(encoding='utf-8')


def get() -> dict:
    """The policy: the practice's saved text, or the template until one is saved."""
    from app.models.system_setting import SystemSetting
    saved = SystemSetting.get(SETTING_KEY)
    if isinstance(saved, dict) and (saved.get('markdown') or '').strip():
        return {'markdown': saved['markdown'], 'is_template': False,
                'updated_by': saved.get('updated_by'), 'updated_at': saved.get('updated_at')}
    return {'markdown': template_text(), 'is_template': True, 'updated_by': None,
            'updated_at': None}


def save(markdown: str, user) -> None:
    from app.models.system_setting import SystemSetting
    text = (markdown or '').replace('\r\n', '\n')
    if not text.strip():
        raise ValueError('The policy is empty.')
    if len(text) > MAX_LENGTH:
        raise ValueError(f'The policy is longer than {MAX_LENGTH:,} characters.')
    SystemSetting.set(SETTING_KEY, {
        'markdown': text,
        'updated_by': getattr(user, 'display_name', None) or getattr(user, 'username', None),
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }, description='The practice AI-use policy (Governance → AI-use policy)')


def reset() -> None:
    """Back to the template (the saved wording is removed)."""
    from app.models.system_setting import SystemSetting
    SystemSetting.set(SETTING_KEY, None)


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
    return f"Listed {info['listed_at']} from this installation ({where}{release})."


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


def _appendix(kind: str) -> str:
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


def to_html(markdown: str) -> Markup:
    """The policy as HTML. The text is the practice's, typed by an administrator: raw HTML in it
    is shown as text, and links go only to web, mail or in-page addresses."""
    import markdown as md_lib
    text = MARKERS.sub(_SLOT, markdown) if MARKERS.search(markdown) else markdown
    text = text.replace('<', '&lt;')
    html = md_lib.markdown(text, extensions=['tables', 'sane_lists'])

    def url(m):
        attr, value = m.group(1), m.group(2)
        return m.group(0) if _ALLOWED_URL.match(value) else f'{attr}="#"'
    html = re.sub(r'\b(href|src)="([^"]*)"', url, html)
    appendix = _appendix('html')
    if _SLOT in html:
        html = re.sub(rf'<p>\s*{_SLOT}\s*</p>|{_SLOT}', lambda _: appendix, html, count=1)
    else:
        html += '\n<h2>Appendix A: AI providers and models enabled</h2>\n' + appendix
    return Markup(html)


def to_markdown(markdown: str) -> str:
    """The policy as a Markdown file, with Appendix A filled in as it is now."""
    appendix = _appendix('markdown')
    if MARKERS.search(markdown):
        return MARKERS.sub(lambda _: appendix, markdown, count=1)
    return markdown.rstrip() + '\n\n## Appendix A: AI providers and models enabled\n\n' + appendix + '\n'
