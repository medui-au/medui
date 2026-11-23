# How MedUI is built

**For:** IT staff, developers and anyone checking how MedUI works. **You'll know:** its parts, how
to install it by hand, how to develop on it, and where the detailed guides are.

To install MedUI the usual way, use the [installation guide](install/README.md) instead.

## The parts

| Part | What it is |
|---|---|
| MedUI | A Flask web application, run by Gunicorn in a container |
| MedUI's own database | PostgreSQL 17, in a container: users, settings, prompts, workflows, run history. Changed only by Alembic migrations, which never run during web startup. |
| Best Practice | BP's SQL Server, read-only, through Microsoft ODBC Driver 18 (in the container, under [Microsoft's licence terms](https://aka.ms/odbc18eula); see [NOTICE](../NOTICE)). Every BP query is a `.sql` file in `app/sql/`, run through a read-only session. |
| OCR (optional, recommended) | LiteParse, a local container, for scanned documents ([OCR](ocr.md)) |
| HTTPS (optional) | Caddy, in front of MedUI, for workstations ([HTTPS](https.md)) |
| Redaction | The `bps-redaction` library ([source](https://github.com/medui-au/redaction-core)), a pinned wheel in `vendor/wheels/`, connected in `app/services/redaction_core.py` |

The code is in three layers: routes (`app/blueprints/`) call services (`app/services/`), which call
repositories and BP queries (`app/repositories/`, `app/sql/`). AI workflows run as a sequence of
steps: assemble and redact the data, build the prompt, check the redaction policy against the
model and call it, then restore the placeholders in the answer. [AGENTS.md](../AGENTS.md) has more
on each.

Each installation has its own empty PostgreSQL database. Don't point MedUI at another
installation's database.

## Optional features

All are off until set to `true` in `.env`:

| Setting | Turns on |
|---|---|
| `AI_ENABLED` | AI panels, scribe, chatbots, prompt manager, workflow runs |
| `MESSAGING_ENABLED` | Outbound email and SMS to patients |
| `PIT_EXPORT_ENABLED` | PIT file export |
| `PATIENT_API_ENABLED` | Patient and practice REST APIs (needs `PATIENT_API_KEY`) |

Configure the provider or delivery path before turning one on. The starter pack has prompts and
draft workflows, but no AI accounts, models or active workflows ([seed data](seed-data.md)).

Drug and vaccine reference tables are an optional seed package. Drug mappings need local
approval; vaccine and risk tables need review before import. Where the vaccine tables are missing,
MedUI says that eligibility has not been assessed: that is not the same as ineligible.

## Installing by hand

`./install.sh` does all of this, checks each step and skips what is done. By hand, for other
systems or Docker Desktop, you need Docker Engine with Compose v2 and Buildx, and `python3`:

```bash
python3 scripts/init_env.py
docker compose --profile ocr up -d --build --wait db liteparse
docker compose --profile app build app
docker compose --profile app run --rm app flask --app wsgi db upgrade
docker compose --profile app run --rm app flask --app wsgi install defaults
docker compose --profile app run --rm app flask --app wsgi seed providers
docker compose --profile app run --rm app flask --app wsgi install seeds
docker compose --profile app run --rm app flask --app wsgi install admin
docker compose --profile app up -d --wait app
```

Then open http://127.0.0.1:5005 and follow the [Administrator setup guide](setup-guide.md). `install admin` asks
for the administrator's username and password; there is no default account. `install defaults`
and `install seeds` add what is missing and never replace what is there.

Set the practice's `BPSDB_*` details in `.env` and recreate the app container, using the read-only
login BP supplies. A test installation should use a server with test data only, never the
practice's live BP: the login reads every database it can open there. All published ports listen
on localhost only.

Other ways: [other ways to install](install/other-ways.md). MedUI without Docker isn't
supported.

## Developing

Use the same PostgreSQL and LiteParse containers, with Flask in `.venv`:

```bash
docker compose --profile ocr up -d --wait db liteparse
.venv/bin/flask --app wsgi db upgrade
.venv/bin/flask --app wsgi install defaults
.venv/bin/flask --app wsgi install admin
.venv/bin/python run.py
```

Stop the app container first if it is using port 5005. The generated `DATABASE_URL` uses
PostgreSQL on host port 55432; inside the app container, Compose sets it to `db:5432`. Settings in
the process environment take precedence over `.env`. A host `.venv` needs Microsoft's ODBC 18
driver installed separately.

## Checks

```bash
.venv/bin/python -m pytest
.venv/bin/flask --app wsgi db check
```

Database tests also need `MEDUI_TEST_DATABASE_URL`, pointing to an empty, disposable PostgreSQL
database whose name ends in `_test`. They apply migrations and create invented accounts. Never use
the application database.

## The detailed guides

| Guide | Covers |
|---|---|
| [Installing MedUI](install/README.md) | The four installation recipes, and other ways to install |
| [Administrator setup guide](setup-guide.md) | First-time setup after any recipe, a demo installation, updating |
| [Operations](operations.md) | Backups, restore, upgrades, removing MedUI |
| [Cheat sheet](cheatsheet.md) | Every installer switch and everyday command |
| [HTTPS](https.md) | Workstation access and certificates |
| [OCR](ocr.md) | Scanned documents |
| [Seed data](seed-data.md) | What the starter pack holds |
| [Redaction lists](redaction-lists.md) | The practice's own lists |
| [Troubleshooting](troubleshooting.md) | Common problems and how to diagnose them |
| [Maintainers](maintainers/) | Releasing, and carrying changes over from the upstream application |

[Back to MedUI](../README.md)
