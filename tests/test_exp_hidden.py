"""The [EXP] document links are hidden, with their wiring kept."""
import re
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = sorted((ROOT / 'app' / 'templates').rglob('*.html'))
LINK = re.compile(r'<a\b(?:(?!</a>).)*?\[EXP\]</a>', re.S)
GUARD_OPEN = '{% if config.EXP_LINKS_ENABLED %}'


def test_the_switch_is_off_unless_set():
    import os
    from app.config import Config
    src = (ROOT / 'app' / 'config.py').read_text()
    assert "EXP_LINKS_ENABLED = _bool('EXP_LINKS_ENABLED')" in src
    if not os.environ.get('EXP_LINKS_ENABLED'):
        assert Config.EXP_LINKS_ENABLED is False


def test_every_exp_link_is_behind_the_switch():
    found = 0
    for path in TEMPLATES:
        text = path.read_text()
        for m in LINK.finditer(text):
            found += 1
            before = text[:m.start()]
            opened, closed = before.rfind(GUARD_OPEN), before.rfind('{% endif %}')
            assert opened > closed, f'[EXP] link not behind the switch in {path.relative_to(ROOT)}'
            assert text.find('{% endif %}', m.end()) > m.end()
    assert found == 10                      # the panels, the inbox and the three viewers


def test_viewer_scripts_survive_without_the_button():
    for path in TEMPLATES:
        text = path.read_text()
        assert "document.getElementById('ai-exp').href" not in text, path.name


def test_a_wrapped_link_renders_only_when_switched_on():
    snippet = ('{% if config.EXP_LINKS_ENABLED %}<a href="/x?auto=exp">[EXP]</a>{% endif %}'
               '<a href="/x?auto=sum">[SUM]</a>')
    t = Environment().from_string(snippet)
    off = t.render(config={'EXP_LINKS_ENABLED': False})
    on = t.render(config={'EXP_LINKS_ENABLED': True})
    assert '[EXP]' not in off and '[SUM]' in off and '[EXP]' in on


def test_the_panel_ignores_auto_exp_while_hidden():
    src = (ROOT / 'app' / 'blueprints' / 'clinical' / 'routes.py').read_text()
    i = src.index("auto = request.args.get('auto', '').strip().lower()")
    window = src[i:i + 300]
    assert "if auto == 'exp' and not current_app.config.get('EXP_LINKS_ENABLED'):" in window
    assert "auto = ''" in window
