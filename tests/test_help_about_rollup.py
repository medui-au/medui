"""Help ▾ → Help / About, and the Results Rollup's Deselect all + Copy to Clipboard (ADR-187)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPNAV = (ROOT / 'app' / 'templates' / 'components' / 'topnav.html').read_text()
ROLLUP = (ROOT / 'app' / 'templates' / 'components' / 'results_rollup_modal.html').read_text()


def test_help_is_a_dropdown_with_help_and_about():
    start = TOPNAV.index('id="nav-help"')
    menu = TOPNAV[start:TOPNAV.index('</ul>', start)]
    assert "toggleDropdown('nav-help')" in menu and 'Help ▾' in menu
    assert "url_for('help.index') }}\">Help</a>" in menu
    assert "url_for('main.about') }}\">About</a>" in menu
    assert 'class="topnav-link" href="{{ url_for(\'help.index\') }}"' not in TOPNAV


def test_the_help_menu_opens_to_the_left_at_the_screen_edge():
    css = (ROOT / 'app' / 'static' / 'css' / 'style.css').read_text()
    assert '.dropdown-menu--right { left: auto; right: 0;' in css
    assert 'dropdown-menu dropdown-menu--right' in TOPNAV


def test_about_route_exists():
    from app.blueprints.main import routes
    assert callable(routes.about)


def test_rollup_button_reads_copy_to_clipboard():
    assert 'Generate &amp; Copy' not in ROLLUP and "'Generate & Copy'" not in ROLLUP
    assert ROLLUP.count('Copy to Clipboard') == 2          # the button and after the spinner


def test_rollup_has_deselect_all():
    assert 'onclick="deselectAllResultsRollup(); return false;">Deselect all</a>' in ROLLUP
    fn = ROLLUP[ROLLUP.index('window.deselectAllResultsRollup'):ROLLUP.index('window.generateResultsRollup')]
    assert 'cb.checked = false' in fn and 'updateResultsRollupCount()' in fn
