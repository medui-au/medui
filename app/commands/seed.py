"""Optional BP user sync and neutral AI provider templates."""
from pathlib import Path
import json
import click
from flask.cli import AppGroup

seed_cli = AppGroup('seed', help='Optional BP user sync and provider templates.')

# # BPSDB USER SYNC
# ---------------------------------------------------------------------------

# GROUPCODE → Gen5 security_level: the same table login uses.
from app.services.auth_service import LOGIN_GROUP_LEVELS as _GROUPCODE_LEVEL  # noqa: E402


@seed_cli.command('sync-bpsdb-users')
@click.option('--dry-run', is_flag=True, default=False,
              help='Show what would change without writing to DB')
@click.option('--force-lower', is_flag=True, default=False,
              help='Allow lowering security_level (default: only raise)')
def sync_bpsdb_users_cmd(dry_run: bool, force_lower: bool) -> None:
    """
    Sync security levels and internal patient ID mappings from BPSDB.

    For each Gen5 user whose bpsdb_user_id matches a BPSDB USERID:
      - Sets security_level based on GROUPCODE (only raises by default; use --force-lower to also lower)
      - Populates bpsdb_internal_id from the PATIENTS.OTHERNOTES BP_USER mapping
        (does not overwrite if already set manually)
    """
    import pyodbc
    from flask import current_app
    from app.extensions import db
    from app.models.user import User

    bpsdb_uri = current_app.config.get('BPSDB_URI')
    if not bpsdb_uri:
        raise click.ClickException('BPSDB_URI is not configured.')

    conn = pyodbc.connect(bpsdb_uri, autocommit=True)
    try:
        cur = conn.cursor()

        # ── Fetch BPSDB users ──────────────────────────────────────────────
        cur.execute(
            'SELECT USERID, GroupCode, Firstname, Surname '
            'FROM USERS WHERE recordstatus = 1 AND userstatus IN (1, 2)'
        )
        cols = [d[0] for d in cur.description]
        bpsdb_users = {
            str(row[cols.index('USERID')]): dict(zip(cols, row))
            for row in cur.fetchall()
        }

        # ── Fetch staff patient-ID map (via OTHERNOTES BP_USER field) ─────
        staff_map_sql = Path(__file__).parent.parent / 'sql' / 'privacy_staff_map.sql'
        cur.execute(staff_map_sql.read_text())
        cols2 = [d[0] for d in cur.description]
        staff_by_userid = {}   # bpsdb_user_id (str) → patient_id (int)
        for row in cur.fetchall():
            r = dict(zip(cols2, row))
            bp_user = str(r['bp_user']).strip() if r.get('bp_user') else None
            patient_id = r.get('patient_id')
            if bp_user and patient_id:
                staff_by_userid[bp_user] = int(patient_id)
    finally:
        conn.close()

    # ── Update Gen5 users ──────────────────────────────────────────────────
    gen5_users = User.query.filter(User.bpsdb_user_id.isnot(None)).all()
    updated = skipped = 0

    for u in gen5_users:
        uid = str(u.bpsdb_user_id).strip()
        bps = bpsdb_users.get(uid)
        changed = False

        if bps:
            groupcode = int(bps['GroupCode'] or 0)
            mapped_level = _GROUPCODE_LEVEL.get(groupcode, 1)
            would_lower = mapped_level < u.security_level
            if u.security_level != mapped_level and (not would_lower or force_lower):
                if not dry_run:
                    u.security_level = mapped_level
                click.echo(
                    f'  {u.username:20s}  level {u.security_level} → {mapped_level}'
                    f'  (groupcode {groupcode})'
                    + (' [DRY RUN]' if dry_run else '')
                )
                changed = True
            elif would_lower and not force_lower:
                click.echo(
                    f'  {u.username:20s}  level {u.security_level} → {mapped_level} skipped'
                    f'  (groupcode {groupcode}; use --force-lower to apply)'
                )
        else:
            click.echo(f'  {u.username:20s}  not found in BPSDB — skipped')
            skipped += 1
            continue

        patient_id = staff_by_userid.get(uid)
        if patient_id and not u.bpsdb_internal_id:
            if not dry_run:
                u.bpsdb_internal_id = patient_id
            click.echo(
                f'  {u.username:20s}  internal_id → {patient_id}'
                + (' [DRY RUN]' if dry_run else '')
            )
            changed = True

        if changed:
            updated += 1
        else:
            skipped += 1

    if not dry_run:
        db.session.commit()

    action = 'would update' if dry_run else 'updated'
    click.echo(f'\nSync complete: {action} {updated} users, {skipped} unchanged/skipped.')


# ---------------------------------------------------------------------------
# PROVIDER PRESETS
# ---------------------------------------------------------------------------

_PROVIDER_PRESETS = [
    dict(provider_key='ollama',        display_name='Ollama (local)',         provider_type='openai_compatible',
         base_url_default='http://localhost:11434/v1', is_local_default=True,
         supports_model_fetching=True,  static_models_json=None,
         notes='Local LLM runner. Fetch models from the /models endpoint.',  sort_order=1),
    dict(provider_key='lm_studio',     display_name='LM Studio (local)',      provider_type='openai_compatible',
         base_url_default='http://localhost:1234/v1',  is_local_default=True,
         supports_model_fetching=True,  static_models_json=None,
         notes='Local LLM via LM Studio. Exposes OpenAI-compatible API.',    sort_order=2),
    dict(provider_key='openai',        display_name='OpenAI',                 provider_type='openai_compatible',
         base_url_default='https://api.openai.com/v1', is_local_default=False,
         supports_model_fetching=True,  static_models_json=None,
         notes='OpenAI cloud API. Requires OPENAI_API_KEY.',                  sort_order=10),
    dict(provider_key='anthropic',     display_name='Anthropic',              provider_type='anthropic',
         base_url_default='https://api.anthropic.com', is_local_default=False,
         supports_model_fetching=False,
         static_models_json=None,
         notes='Anthropic native API. Requires ANTHROPIC_API_KEY.',           sort_order=11),
    dict(provider_key='openrouter',    display_name='OpenRouter',             provider_type='openai_compatible',
         base_url_default='https://openrouter.ai/api/v1', is_local_default=False,
         supports_model_fetching=True,  static_models_json=None,
         notes='OpenAI-compatible router with access to many cloud models.',  sort_order=12),
    dict(provider_key='groq',          display_name='Groq',                   provider_type='openai_compatible',
         base_url_default='https://api.groq.com/openai/v1', is_local_default=False,
         supports_model_fetching=True,  static_models_json=None,
         notes='Ultra-fast inference via Groq hardware.',                      sort_order=13),
    dict(provider_key='deepseek',      display_name='DeepSeek',               provider_type='openai_compatible',
         base_url_default='https://api.deepseek.com/v1', is_local_default=False,
         supports_model_fetching=False,
         static_models_json=None,
         notes='DeepSeek cloud API.',                                          sort_order=14),
    dict(provider_key='whisper_local', display_name='Whisper (local ASR)',    provider_type='asr_whisper',
         base_url_default='http://localhost:9000', is_local_default=True,
         supports_model_fetching=False,
         static_models_json=None,
         notes='Local Whisper HTTP server (e.g. faster-whisper-server).',     sort_order=20),
    dict(provider_key='deepgram',      display_name='Deepgram (ASR)',         provider_type='asr_deepgram',
         base_url_default='https://api.deepgram.com', is_local_default=False,
         supports_model_fetching=False,
         static_models_json=None,
         notes='Deepgram cloud ASR. Medical model recommended for clinical dictation.', sort_order=21),
]


@seed_cli.command('providers')
@click.option('--reset', is_flag=True, default=False,
              help='Delete existing presets before inserting (re-seed from scratch)')
def seed_providers_cmd(reset: bool) -> None:
    """Seed AI provider presets (Ollama, OpenAI, Anthropic, OpenRouter, Groq, etc.)."""
    from app.extensions import db
    from app.models.ai_provider import AIProviderPreset

    if reset:
        db.session.query(AIProviderPreset).delete()
        db.session.commit()
        click.echo('Existing presets cleared.')

    added = skipped = 0
    for p in _PROVIDER_PRESETS:
        if AIProviderPreset.query.filter_by(provider_key=p['provider_key']).first():
            skipped += 1
            continue
        db.session.add(AIProviderPreset(**p))
        added += 1

    db.session.commit()
    click.echo(f'Provider presets: {added} added, {skipped} already present.')
