"""The NIP line on the patient page (ADR-167): neutral, with the schedule's version and source.
Invented doses only."""
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.services import vaccine_eligibility_service as v

TEMPLATES = Path(__file__).resolve().parent.parent / 'app' / 'templates'


def render(vaccines):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    return env.get_template('clinical/_panels/immunization_eligibility_flags.html').render(
        vaccines=vaccines, schedule=v.SCHEDULE_TEXT)


def test_schedule_names_version_and_source():
    assert '2026' in v.SCHEDULE and '1 July 2026' in v.SCHEDULE
    assert 'health.gov.au' in v.SCHEDULE_TEXT


def test_every_row_carries_the_schedule():
    row = v._eval_zoster(70, False, set(), {}, set(), date(2026, 10, 24), [])
    assert row['schedule'] == v.SCHEDULE_TEXT


def test_line_is_neutral_and_shows_source_and_last_dose():
    html = render([{'vaccine': 'Influenza', 'last_dose_date': '01/04/2025'},
                   {'vaccine': 'Zoster', 'last_dose_date': None}])
    assert 'text-warning' not in html and 'text-muted' in html
    assert v.SCHEDULE_TEXT in html
    assert 'Influenza (last recorded 01/04/2025)' in html and 'Zoster (none recorded)' in html
    assert 'none recorded in interval' not in html


def test_nothing_when_nothing_listed():
    assert render([]).strip() == ''


def test_tooltip_repeats_the_line():
    """The line is too small to read in the title row, so the tooltip carries it in full."""
    import re
    html = render([{'vaccine': 'Influenza', 'last_dose_date': '01/04/2025'}])
    title = re.search(r'title="([^"]*)"', html).group(1)
    assert title.startswith("NIP-funded for this age or risk group")
    assert 'Influenza (last recorded 01/04/2025)' in title and v.SCHEDULE_TEXT in title
