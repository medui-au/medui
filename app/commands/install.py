"""Non-destructive first-install commands. No legacy database is read."""
import click
from flask.cli import AppGroup
from app.extensions import db

install_cli = AppGroup('install', help='Initialise a clean MedUI installation.')


@install_cli.command('defaults')
def defaults():
    """Add neutral defaults and a basic BP bundle, preserving existing settings."""
    from app.models.system_setting import SystemSetting
    from app.models.data_bundle import DataBundle, BundleBlock
    # The AI guardrails start on in this edition (upstream ADR-087..089): scope
    # instruction (practice default 'record'), request check recorded, notices.
    for key, value in {'privacy.protect_staff': True, 'data.retention_days': 180,
                       'data.auto_cleanup': False, 'ui.default_theme': 'light',
                       'scope.enabled': True, 'scope.default_key': 'record',
                       'scope.check_mode': 'record', 'notice.enabled': True,
                       # Results-based badges and the criterion review (upstream ADR-104, 107, 109)
                       # start off in this edition: its intended purpose excludes alerts of its own.
                       # A practice that switches them on (Setup → General → Patient Record)
                       # keeps its choice; insert-only, so upgrades add them off too.
                       'clinical.egfr_criterion_badge': False,
                       'clinical.hba1c_criterion_badge': False,
                       'clinical.criterion_review': False}.items():
        if not SystemSetting.query.filter_by(key=key).first():
            db.session.add(SystemSetting(key=key, value=value))
    if not DataBundle.query.filter_by(name='clinical_context').first():
        bundle = DataBundle(name='clinical_context', description='Core Best Practice clinical data; no external summariser required.')
        db.session.add(bundle)
        db.session.flush()
        for order, block in enumerate(('demographics', 'history', 'medications', 'allergies', 'immunizations')):
            db.session.add(BundleBlock(bundle_id=bundle.id, block_order=order,
                                       block_source=block, label=block.replace('_', ' ').title()))
    db.session.commit()
    click.echo('Installation defaults ready; existing settings preserved.')


def _local_admin_exists() -> bool:
    from app.models.user import User
    return User.query.filter_by(is_local_admin=True, is_active=True).first() is not None


def _prompt_unless_admin(ctx, param, value):
    # --if-missing is checked first (is_eager), so a re-run asks for nothing.
    if value is None and not (ctx.params.get('if_missing') and _local_admin_exists()):
        return click.prompt(param.name.capitalize(), hide_input=param.name == 'password',
                            confirmation_prompt=param.name == 'password')
    return value


@install_cli.command('admin')
@click.option('--if-missing', is_flag=True, is_eager=True,
              help='Do nothing if an active local administrator already exists.')
@click.option('--username', callback=_prompt_unless_admin)
@click.option('--password', callback=_prompt_unless_admin)
def admin(if_missing, username, password):
    """Create a local administrator without copying BP accounts or credentials."""
    from app.models.user import User
    if if_missing and _local_admin_exists():
        click.echo('A local administrator already exists; nothing changed.')
        return
    username = username.strip()
    if not username or username.isdigit():
        raise click.ClickException('Use a non-numeric administrator username.')
    if len(password) < 12:
        raise click.ClickException('Use a password of at least 12 characters.')
    if User.query.filter_by(username=username).first():
        raise click.ClickException('That username already exists; nothing changed.')
    user = User(username=username, display_name=username, security_level=9,
                is_local_admin=True, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo('Local administrator created.')


@install_cli.command('seeds')
@click.option('--dry-run', is_flag=True, help='Validate and simulate all writes, then roll back.')
@click.option('--include-reference-data', is_flag=True,
              help='Also import unapproved drug mappings and legacy vaccine/risk reference tables.')
def seeds(dry_run, include_reference_data):
    """Add portable prompts, draft workflows, inactive message templates and the starting identifier labels."""
    from app.services.seed_service import install_seeds
    try:
        counts = install_seeds(dry_run=dry_run, include_reference_data=include_reference_data)
    except Exception as exc:
        raise click.ClickException(f'Seed installation rolled back: {exc}') from exc
    for name, result in counts.items():
        click.echo(f"{name}: {result['added']} added, {result['skipped']} existing preserved")
    click.echo('Dry run: all changes rolled back.' if dry_run else 'Seeds installed. Workflows remain drafts; messages inactive; drug mappings require approval.')


_RESYNC_HEADINGS = (
    ('updated', 'Updated to this release'),
    ('replaced', 'Replaced although edited here (--replace)'),
    ('added', 'Added (new in this release)'),
    ('filled', 'Given settings new in this release (only where none was chosen)'),
    ('customised', 'Edited here, left alone (to take the release version: --replace "<name>")'),
    ('dropped-archived', 'Dropped from this release, archived'),
    ('dropped', 'Dropped from this release, still here (archive with --archive-dropped)'),
    ('dropped-in-use', 'Dropped from this release, kept because something in use relies on it'),
    ('dropped-customised', 'Dropped from this release, edited here, left alone'),
    ('skipped', 'Skipped'),
)


@install_cli.command('resync-seeds')
@click.option('--dry-run', is_flag=True, help='List what would change, then roll back.')
@click.option('--archive-dropped', is_flag=True,
              help='Archive seeded items this release has dropped (never deletes).')
@click.option('--replace', multiple=True, metavar='NAME',
              help='Take the release version of a seeded item even though it was edited here. Repeatable.')
def resync_seeds(dry_run, archive_dropped, replace):
    """Bring seeded prompts and workflows up to this release after an upgrade.

    Updates only items still exactly as a release seeded them; keeps each workflow's
    model, data bundle and status; never touches items the practice created. Replaced
    text is kept as an earlier version. Back up the database first.
    """
    from app.services.seed_resync_service import resync_seeds as run
    try:
        report = run(dry_run=dry_run, archive_dropped=archive_dropped, replace=replace)
    except Exception as exc:
        raise click.ClickException(f'Seed resync rolled back: {exc}') from exc
    labels = {'system_prompts': 'system prompt', 'user_prompts': 'prompt', 'pipelines': 'workflow',
              'data_bundles': 'data bundle', 'message_templates': 'message template',
              'admin_lists': 'admin list'}
    current = sum(1 for r in report if r['outcome'] == 'current')
    click.echo(f'Already up to date: {current}')
    for outcome, heading in _RESYNC_HEADINGS:
        rows = [r for r in report if r['outcome'] == outcome]
        if not rows:
            continue
        click.echo(f'\n{heading} ({len(rows)}):')
        for r in rows:
            detail = f" — {r['note']}" if r['note'] else ''
            click.echo(f"  {labels.get(r['category'], r['category'])}: {r['name']}{detail}")
    click.echo('\nDry run: all changes rolled back.' if dry_run else
               '\nResync complete. Workflow models, data bundles and status were kept.')
