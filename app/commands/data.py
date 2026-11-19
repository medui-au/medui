"""flask data — data management utilities."""
import click
from flask.cli import AppGroup

data_cli = AppGroup('data', help='Data management utilities.')


@data_cli.command('query')
@click.argument('name')
@click.option('--patient-id', type=int, help='Patient InternalID for parameterised queries')
def query_cmd(name: str, patient_id: int | None) -> None:
    """Run a named BPSDB query and print results. See QUERY_REGISTRY for names."""
    from flask import current_app
    from app.sql.query_loader import load_query, ReadOnlySession

    bpsdb_uri = current_app.config.get('BPSDB_URI')
    if not bpsdb_uri:
        raise click.ClickException('BPSDB_URI not configured')

    sql = load_query(name)
    param_count = sql.count('?')
    if param_count and not patient_id:
        raise click.ClickException(
            f'Query {name!r} requires {param_count} parameter(s). Use --patient-id.'
        )
    # Fill all ? placeholders with patient_id (works for any patient-scoped query)
    params = [patient_id] * param_count if patient_id and param_count else None

    with ReadOnlySession(bpsdb_uri) as session:
        rows = session.execute(sql, params)

    if not rows:
        click.echo('(no rows)')
        return

    headers = list(rows[0].keys())
    click.echo('\t'.join(headers))
    for row in rows:
        click.echo('\t'.join(str(v) for v in row.values()))
    click.echo(f'\n{len(rows)} row(s)')


@data_cli.command('set-password')
@click.argument('username')
@click.argument('password')
def set_password_cmd(username: str, password: str) -> None:
    """Set a user's password (dev use only)."""
    from app.extensions import db
    from app.models.user import User
    user = User.query.filter_by(username=username).first()
    if not user:
        raise click.ClickException(f'User {username!r} not found')
    user.set_password(password)
    db.session.commit()
    click.echo(f'Password updated for {username} ({user.display_name})')
