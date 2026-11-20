"""The four install recipes each stand alone (medui_os 0.52.2): the use case and the script are at
the top, no page sends the reader to another for its steps, and the commands repeated between pages
stay the same."""
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / 'docs' / 'install'
RECIPES = ['windows-live', 'windows-demo', 'ubuntu-live', 'ubuntu-demo']


def _text(name):
    return (DOCS / f'{name}.md').read_text()


def _blocks(text, lang):
    """Fenced code blocks of one language, with the list indentation taken off."""
    out = []
    for body in re.findall(rf'^ *```{lang}\n(.*?)^ *```', text, flags=re.S | re.M):
        out.append('\n'.join(line.strip() for line in body.strip().splitlines()))
    return out


@pytest.mark.parametrize('name', RECIPES)
def test_use_case_and_script_come_first(name):
    top = '\n'.join(_text(name).splitlines()[:12])
    for label in ('**Use this when**', '**Not this one**', '**The script**'):
        assert label in top, (name, label)


@pytest.mark.parametrize('name', RECIPES)
def test_no_recipe_leans_on_another_for_its_steps(name):
    text = _text(name)
    assert 'differences' not in text.lower(), name
    assert 'Follow that page' not in text, name
    assert re.search(r'^## 1\. ', text, flags=re.M), name


@pytest.mark.parametrize('name', RECIPES)
def test_the_short_version_repeats_the_full_steps(name):
    """The commands under "In short" are the same as those further down the page."""
    text = _text(name)
    lang = 'powershell' if name.startswith('windows') else 'bash'
    blocks = _blocks(text, lang)
    first, rest = text.split('**In short:**', 1)[1].split('\n## ', 1)
    for block in _blocks(first, lang):
        assert block in _blocks(rest, lang), (name, block)
    assert blocks


def test_both_windows_pages_run_the_script_the_same_way():
    def run(name):
        return [b for b in _blocks(_text(name), 'powershell') if 'create_medui_wsl2.ps1' in b]
    live, demo = run('windows-live'), run('windows-demo')
    assert live and set(live) == set(demo)


def test_both_windows_pages_link_the_same_download():
    links = {n: set(re.findall(r'\]\((https://github\.com/[^)]*create_medui_wsl2\.ps1)\)', _text(n)))
             for n in ('windows-live', 'windows-demo')}
    assert len(links['windows-live']) == 1 and links['windows-live'] == links['windows-demo']


def test_both_ubuntu_pages_clone_the_same_repository():
    def clone(name):
        return {re.sub(r' ~/medui_\w+$', '', b) for b in _blocks(_text(name), 'bash') if 'git clone' in b}
    assert clone('ubuntu-live') == clone('ubuntu-demo') and len(clone('ubuntu-live')) == 1
