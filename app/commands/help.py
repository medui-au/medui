"""flask help check — problems in app/help/ and [?] buttons pointing nowhere (ADR-102)."""
import click
from flask.cli import AppGroup

help_cli = AppGroup('help', help='In-app help files.')


@help_cli.command('check')
def check():
    """List problems in the help files and in the templates' help('…') references."""
    from app.services import help_service as hs
    problems = hs.check()
    topics = hs.topics()
    click.echo(f'{len(topics)} topic(s), {sum(len(t.sections) for t in topics.values())} section(s).')
    for p in problems:
        click.echo(f'  ✗ {p}')
    if problems:
        raise SystemExit(1)
    click.echo('  ✓ no problems')
