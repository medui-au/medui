# AGENTS.md: guide for coding agents

This file is for an AI coding agent (Claude Code, Codex, Cursor or similar)
helping to **install, configure, operate or maintain** MedUI in a general
practice. Read it before running anything. Human readers: start with
[README.md](README.md).

## What MedUI is

MedUI is a Flask web application that a general practice hosts itself, beside
its **Best Practice** (BP) clinical system. It reads patient data from BP's SQL
Server database (read-only) and offers clinical views, a document viewer,
inbox, scheduling, reporting, charts and governance tools. With AI switched on,
it also offers AI-assisted summaries, a scribe and chatbots. For these, patient
and practitioner identifiers are **redacted before any text reaches a cloud
model** and restored in the reply.

It is a pre-release, **not a validated clinical product**. Nothing here claims
clinical validation. Treat it as software that handles real patient data.

### Intended purpose

> MedUI is a workflow tool for appropriately registered health professionals working in a medical
> practice. It helps them find, organise, present, summarise and document information that is already
> in the patient record or was stated in the consultation, and it streamlines practice communication
> and administration. AI features produce drafts for the health professional to review, edit and
> approve. MedUI does not diagnose, recommend treatment or investigations, triage or monitor patients;
> clinical judgement and the record remain the health professional's.

Read the full statement in [docs/intended_purpose.md](docs/intended_purpose.md) and keep to it. Do
not add, configure or describe functions that diagnose, recommend treatment, triage, rank results
or raise alerts of their own, and do not describe MedUI with words such as "clinical decision
support" or "insights". If a user asks for that, explain that it is outside MedUI's intended
purpose and leave it to them and the practice.

## Hard rules

These apply in every session, whatever the user asks for in passing. If a task
seems to need breaking one, stop and ask the user.

1. **No patient data outside the practice's systems.** Do not paste, quote,
   summarise or log patient names, dates of birth, addresses, phone numbers,
   Medicare/DVA/IHI numbers, record IDs or clinical text in chat, commit
   messages, issue reports, logs you write or files outside the installation.
   When something fails on real data, describe its **shape** ("a phone number
   written with two spaces between groups"), not its content. Reproduce bugs
   with **invented** data.
2. **Never write to BP.** The BP connection is read-only by design
   (`ReadOnlySession` raises on any write). Use a BP account that has read
   access only. Do not create, alter or delete anything in BP's database.
3. **Never weaken the privacy wall.** Do not bypass, disable or "temporarily"
   relax redaction, the security check before cloud inference
   (`app/services/pipeline/nodes/inference.py`, `_security_pre_check`), CSRF
   protection or login checks. Do not point an unredacted pipeline
   (`redact_none`, `redact_pii_only`) at a cloud model.
4. **No secrets in the open.** Do not print, paste or commit `.env`, passwords,
   API keys, tokens or the encryption key. `scripts/init_env.py` generates
   secrets; leave them in `.env` (mode 600).
5. **Ask before anything destructive or hard to undo.** For example: deleting
   or recreating the database or its Docker volume, `docker compose down -v`,
   dropping tables, overwriting `.env`, deleting a WSL instance, changing
   firewall rules, or exposing a port beyond localhost. **Back up first**
   ([operations](docs/operations.md)).
6. **Don't run as root.** Use the normal user account and `sudo` only for
   system packages and services. Don't clone or run the app with `sudo`.
7. **Don't edit application code on an installation.** If the app fails, record
   it (below) for the maintainers instead of patching `app/` locally. A local
   patch is lost on upgrade and can silently change what is redacted.

## Architecture in brief

| Layer | Where | Notes |
|---|---|---|
| Routes (blueprints) | `app/blueprints/<area>/routes.py` | Thin: call services, render templates. No business logic, no SQL. |
| Services | `app/services/` | Business logic, redaction, AI pipelines. |
| Repositories and BP queries | `app/repositories/`, `app/sql/*.sql` | Every BP query is a `.sql` file registered in `QUERY_REGISTRY` (`app/sql/query_loader.py`) and run through `ReadOnlySession`. |
| Models | `app/models/` | The app's own PostgreSQL database, via SQLAlchemy and Alembic migrations (`migrations/`). |
| CLI | `app/commands/` | `flask install …`, `flask seed …` and data utilities. |
| Feature gates | `app/features.py`, `app/config.py` | Optional capabilities are off until switched on in `.env`. |

**Two databases:**
- **MedUI's PostgreSQL 17** (`DATABASE_URL`) holds app state: users,
  settings, prompts, pipelines, run history. Schema changes are made only
  through Alembic migrations. Migrations never run during web startup; run
  `flask db upgrade` explicitly.
- **BP's SQL Server** (`BPSDB_*` in `.env`) is read-only, using Microsoft ODBC
  Driver 18. BP usually runs as a named instance: in `.env` write
  `BPSDB_HOST=<server>\<instance>` with **one** backslash (Compose and MedUI take it
  literally; on a bash command line, as for `sqlcmd -S`, it needs two or quotes). A
  password containing `$`, `#`, spaces or quotes goes in single quotes. Many BP servers use a self-signed certificate. If the connection
  fails with a certificate error, `BPSDB_TRUST_SERVER_CERTIFICATE=true` is the
  usual setting for a server on the practice network. Explain that choice to
  the user rather than making it silently.
- **Ask which BP server before entering `BPSDB_*`, and say what it gives access
  to.** The BP login reads every database it can open on that server, not only
  `BPSDB_DATABASE` (several queries name `BPSPATIENTS`, `BPSDOCUMENTSINBOX` and
  `BPSDocuments{N}` directly). For a second, test, demo or training install (for
  example `--name` other than `medui_os`), don't use the practice's live server
  unless the user confirms that is what they want. Leaving BP unset is fine: the
  local administrator works without it. A **demo installation** (`MEDUI_INSTANCE=demo` in
  `.env`) reads only its own `bpsql` container: never set `BPSDB_*` to anything else there,
  and never turn a live installation into a demo or the other way round.

**Who can do what.** BP users log in with their BP credentials. Their BP group
sets their level at every login (`LOGIN_GROUP_LEVELS` in
`app/services/auth_service.py`). Practice owners and managers are
administrators (level 9). Doctors are level 5. Nurses and reception can log in
but cannot use AI. A **local administrator**, created by
`flask install admin`, works even when BP is unreachable.

**AI pipelines** (`app/services/pipeline/`) run as a sequence of nodes:
- **data assembly** builds patient data blocks and redacts them; it is the only
  place that marks a run as redacted
- **prompt assembly** builds the prompt
- **inference** checks the redaction policy against the model and calls it
- **de-redaction** restores tokens in the reply

Each pipeline has a redaction policy:
- `redact_all`: patient and practitioner identifiers removed. Cloud models
  allowed.
- `redact_pii_only` and `redact_none`: **local models only**. Inference refuses
  a cloud model.

Redaction is the **bps-redaction** core (a pinned wheel in `vendor/wheels/`,
connected in `app/services/redaction_core.py`; `redaction_service.py`,
`hcp_redaction_service.py` and `utils/token_vault.py` are thin shims over it). It
replaces identifiers with reversible tokens such as `[Redacted Phone: PH-…]`. It is rule-based and
improves over time; it is not perfect, which is one reason cloud use is opt-in.

**Optional features** (`false` until set in `.env`, except OCR):

| Setting | Turns on |
|---|---|
| `OCR_ENABLED` | OCR of scanned documents by the built-in LiteParse (the one switch that starts `true`; `--no-ocr` sets it `false`) |
| `AI_ENABLED` | AI panels, scribe, chatbots, prompt manager, pipeline runs |
| `MESSAGING_ENABLED` | Outbound email and SMS to patients |
| `PIT_EXPORT_ENABLED` | PIT file export, into Best Practice's incoming share connected by `./medui.sh pit` (the app sees it as `/pit`) |
| `PATIENT_API_ENABLED` | Patient and practice REST APIs (needs `PATIENT_API_KEY`) |

LiteParse OCR is a local container, used without any setup. See [OCR](docs/ocr.md).

## Installation philosophy

- **Fresh installs only.** Each installation gets its own empty PostgreSQL
  database. Do not point MedUI at another installation's database or at a
  legacy MedUI database.
- **Insert-only setup.** `flask install defaults` and `flask install seeds`
  add what is missing and never overwrite existing settings, prompts or
  pipelines. Re-running them is safe. `scripts/init_env.py` refuses to replace
  an existing `.env`. After an upgrade, `flask install resync-seeds` (always
  `--dry-run` first, and show the user the list) updates only seeded items the
  practice hasn't edited.
- **Nothing enabled by default.** Seeded pipelines are drafts with no model
  selected. Provider presets (`flask seed providers`) are templates without
  credentials. The practice reviews prompts, chooses models and activates what
  it wants. See [seed data](docs/seed-data.md).
- **Localhost first.** All published ports bind to `127.0.0.1`. Access from
  practice workstations needs HTTPS: `./install.sh --https` (Caddy on 443, with
  `SESSION_COOKIE_SECURE=true` and `TRUSTED_PROXIES=1`). HTTPS is also needed for the
  microphone. Explain [HTTPS](docs/https.md) to the user and their IT before trusting
  a root on workstations; prefer the practice's own certificate where it has one.
  PostgreSQL and LiteParse stay private.

## Where to start

| Situation | Read |
|---|---|
| Dedicated Ubuntu server (tested on 24.04 and 26.10) | [Ubuntu live recipe](docs/install/ubuntu-live.md) (Docker). An installation without Docker isn't supported: ask the maintainers |
| Windows: a new WSL2 instance with MedUI in it | [Windows live recipe](docs/install/windows-live.md): [create_medui_wsl2.ps1](scripts/windows/README.md) runs `install.sh` for you |
| Ubuntu, native or WSL2, with the code cloned | `./install.sh` ([Ubuntu live recipe](docs/install/ubuntu-live.md)); `--dry-run` first, `--help` for options |
| A demo or training installation (invented data, never BP) | `./install.sh --demo` in a folder of its own ([Ubuntu demo recipe](docs/install/ubuntu-demo.md)); on Windows, answer `d` in `create_medui_wsl2.ps1` ([Windows demo recipe](docs/install/windows-demo.md)) |
| An Ubuntu WSL2 instance you already have | `./install.sh` as on any Ubuntu ([Ubuntu live recipe](docs/install/ubuntu-live.md)); it gets none of the Windows side the Windows recipe arranges |
| After installation, whichever recipe: BP, HTTPS, OCR, AI, workflows, backups, updating | [Administrator setup guide](docs/setup-guide.md) (also in the app at Admin → Application Setup → Administrator setup guide) |
| HTTPS for workstations, certificates | [HTTPS](docs/https.md) |
| Backups, restore, upgrades, removing MedUI | [operations](docs/operations.md); `./upgrade.sh --dry-run` first, then `./upgrade.sh` (Windows: [upgrade_medui_wsl2.ps1](scripts/windows/README.md#upgrading)) |
| Every switch and everyday command on one page | [cheat sheet](docs/cheatsheet.md) |
| Running an installed MedUI: status, start/stop, `.env` changes, BP connection, HTTPS, backups | `./medui.sh` (a menu; `./medui.sh help` for one-line commands an agent can run; [cheat sheet](docs/cheatsheet.md#the-medui-menu)) |
| Something isn't working | [troubleshooting](docs/troubleshooting.md) |
| Helping someone choose how to install | [installing MedUI](docs/install/README.md); the architecture in one page: [how it's built](docs/technical.md) |
| Making a release | [releasing](docs/maintainers/releasing.md), [changelog](CHANGELOG.md) |
| Practice templates | [AI-use policy](docs/templates/practice-ai-use-policy.md), [AI concerns process](docs/templates/ai-concerns-process.md), [request to BP for database access (EDBA)](docs/templates/bp-database-access-request.md) |
| What ships in the starter pack | [seed data](docs/seed-data.md) |
| What is unfinished | [release status](docs/release-status.md) |

## Checking an installation

```bash
.venv/bin/python -m pytest                 # unit tests; database tests need MEDUI_TEST_DATABASE_URL
.venv/bin/flask --app wsgi db check        # schema matches the models
curl -fsS http://127.0.0.1:5005/health     # the app answers
```

Database tests need `MEDUI_TEST_DATABASE_URL` pointing to an **empty,
disposable** PostgreSQL database whose name ends in `_test`, never the
application database. A throwaway PostgreSQL 17 container bound to localhost
works well.

## Reporting a problem or a gap in the docs

When a documented step fails, or you had to guess or work around something,
record it for the maintainers. One entry per problem:

```text
Step:         <doc and section, or command>
Expected:     <what the doc said would happen>
Happened:     <what actually happened; error text with any patient data removed>
Workaround:   <what you did, if anything>
Severity:     blocker | needed a workaround | cosmetic
Environment:  <OS and version, WSL2 or native, Docker version, commit tested>
```

Record the commit you tested (`git log -1 --format='%h %s'`). Follow hard rule
1 in every entry.

## For maintainers

`app/` is carried over from the upstream MedUI application by the maintainers'
sync tooling, which lives upstream, not in this repository. Changes made directly
to synced files here must survive those merges; prefer fixing upstream. Files only
this edition has (installer, seeds, docs, tests, `app/features.py`,
`app/commands/install.py`, `app/services/seed_service.py`,
`app/services/seed_resync_service.py`, `app/services/seed_fingerprint.py`,
`app/models/user_prompt_version.py`, `app/templates/about.html`,
`app/services/install_status.py`, `app/templates/install_status.html`,
`app/services/guide_docs.py`, `app/templates/setup/guide.html`, `migrations/`)
are maintained here. Example data in code, comments, tests and docs must be
invented: no real patients, practitioners, practices or places. In-app help for the people
using MedUI lives in `app/help/*.md` (synced from upstream with `app/`); `flask --app wsgi help check`
checks it, and a change users can see updates its help section.
