# Troubleshooting

Commands run in the MedUI checkout (`~/medui_os` by default) on the Ubuntu or WSL2
host, as the install user, not root. The Compose project name comes from `.env`
(`COMPOSE_PROJECT_NAME`); add `-p <name>` only if you installed with `--name`.

Never paste `.env`, tokens, passwords or patient details into a ticket, chat or AI
tool. Logs can contain patient details too: share the error line, not the whole log.

## First look

`./medui.sh status` shows the containers, health, version and settings (no secrets),
`./medui.sh logs` the app's last 200 lines, and `./medui.sh support` a summary for a problem
report. The same by hand, with the other services' logs:

```bash
docker compose --profile app --profile ocr ps                 # what is running, and its health
docker compose --profile app logs app --tail 60               # the app's recent output
docker compose logs db --tail 40                              # PostgreSQL
docker compose --profile ocr logs liteparse --tail 40         # OCR
curl -s http://127.0.0.1:5005/health                          # {"status": "ok", ...} (web process only)
ss -ltnp | grep -E ':5005|:55432|:5707'                       # which ports are bound (defaults)
```

In a traceback, the **last** line is the one that matters (for example
`password authentication failed`, `relation "…" does not exist`, `Login timeout expired`).

If what you see doesn't match these pages, check the version (the foot of every page, or
`/health`) and upgrade first: `./upgrade.sh` ([upgrades](operations.md#upgrades)).

## Symptoms and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Every page gives **500**; the log ends `password authentication failed for user "medui"` | `.env` was replaced or edited after installation: PostgreSQL keeps the password it was **first** created with | Put back the `.env` the installer made, or set the database password to the one in `.env` (below) |
| 500; the log says `relation "…" does not exist` | A different `COMPOSE_PROJECT_NAME` in `.env` started a new, empty database volume | Restore the original `COMPOSE_PROJECT_NAME`, then recreate the app |
| A page that shows a stored secret or setting errors after a `.env` change | `MEDUI_ENCRYPTION_KEY` changed: data encrypted under the old key can't be read | Restore the original key (keep it backed up); for a fresh install, re-enter the setting |
| Everyone is logged out after a `.env` change | `SECRET_KEY` changed | Nothing to fix: sign in again |
| The day sheet opens on yesterday (or tomorrow) | MedUI's timezone isn't the practice's (a server is often set to UTC) | Application Setup → General → Practice Timezone; or `./install.sh --timezone brisbane` (your zone) |
| An edit to `.env` has no effect | Containers read `.env` only when they are created | `./medui.sh reload` (by hand: `docker compose --profile app up -d --force-recreate app`) |
| Patients, inbox or login can't reach Best Practice | `BPSDB_*` settings, TLS, or the named instance | See [Best Practice connection](#best-practice-connection) |
| Documents show no text | OCR switched off (`OCR_ENABLED=false`, or installed with `--no-ocr`), or its container isn't running | The home page's installation status says which; `./medui.sh features OCR_ENABLED=on`, or `./medui.sh ocr start`; see [OCR](ocr.md) |
| Port already in use at installation | Another service, or a second MedUI install | A new installation moves its default ports to free ones; a port you chose, or one in `.env`, doesn't: rerun `./install.sh` with `--app-port`, `--db-port`, `--ocr-port` |
| `Project '…' is already installed in <folder>` | A second folder with the same project name would take over the first one's containers | Run `./install.sh` in that folder, or give this one its own `--name` |
| `Docker still holds data for a project called '…'` | A removed installation left its volumes, and a new `.env` can't open them | Another `--name`; or put that installation's `.env` back; or, after backing up, `docker volume rm` them (deletes that data) |

### Set the database password to the one in `.env`

Inside its own container PostgreSQL accepts a local connection without a password,
so this works while the app can't log in. The password travels on standard input,
not on a command line.

```bash
set -a && . ./.env && set +a && printf "ALTER USER \"%s\" PASSWORD '%s';\n" "$POSTGRES_USER" "$POSTGRES_PASSWORD" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose --profile app up -d --force-recreate app
```

It prints `ALTER ROLE`. Keep `.env` as the installer made it and add only the
`BPSDB_*` block: copying a whole `.env` from another installation brings its
database password, encryption key and project name with it.

## Downloading MedUI (`git clone`)

| Symptom | Fix |
|---|---|
| `destination path 'medui_os' already exists` | A folder of that name is there already, and may hold an installation, its settings or local work: look at what it holds, and don't delete it to make the error go away. For another installation, clone into a folder of its own (`git clone … ~/medui_test`). |
| `Repository not found` / `Authentication failed` | While the repository is private, git needs your GitHub username and a **token** with read access to its Contents (not your GitHub password). Being able to log in to the computer is not enough. |
| `Could not resolve host: github.com` | The computer can't reach GitHub: check its internet connection and DNS. MedUI isn't involved yet. |
| `Permission denied` creating the folder | You aren't in your own home folder: `cd ~` and clone again. Don't use `sudo`. |
| `install.sh` says systemd isn't running (WSL2) | Add `systemd=true` under `[boot]` in `/etc/wsl.conf`, run `wsl --shutdown` in Windows, open the instance again and rerun `./install.sh`. |

## Windows installer (`create_medui_wsl2.ps1`)

| Symptom | Fix |
|---|---|
| The token prompt shows one `*` | Ctrl+V and Ctrl+Shift+V don't paste into the hidden prompt: **right-click**. A token shows as a long row of `*`. |
| "GitHub rejected the token" / "cannot read this repository" | The token has expired, or lacks read access to the repository's Contents: make a new one. |
| Step 6 "The download failed" | Read the git message above it: usually the token or the network. |
| "already exists and will not be touched" | Choose another instance name, or remove the half-built one (below). |

To start again after a failed run, check the instance name, then remove it. This
deletes the instance and everything in it:

```powershell
wsl -l -v
wsl --unregister <name>
```

## Best Practice connection

- BP usually runs as a **named instance**. In `.env` write it with **one** backslash:
  `BPSDB_HOST=192.0.2.10\BPSINSTANCE`. On a bash command line it needs two, or quotes.
- BP's SQL Server uses a self-signed certificate on most practice networks:
  `BPSDB_TRUST_SERVER_CERTIFICATE=true`.
- `./medui.sh bp` sets the connection, recreates the app and checks the login; `./medui.sh bp-check`
  checks it again. After editing `BPSDB_*` by hand: `./medui.sh reload`.
- To test the account outside MedUI (needs `sqlcmd`; the Windows installer can add it):

  ```bash
  sqlcmd -S '192.0.2.10\BPSINSTANCE' -U <bp_user> -C -Q "SELECT 1"
  ```

  `-C` trusts the self-signed certificate. It prompts for the password.

## Administrator access

`./medui.sh admin` creates another local administrator: it prompts for a **new** username and a
password of at least 12 characters, and doesn't change an existing account.
`./medui.sh password` sets a new password for an existing local administrator. By hand:

```bash
docker compose --profile app run --rm app flask --app wsgi install admin
```

## Starting completely fresh

Only on an installation whose data you don't need. `down -v` deletes the database
and app-data volumes. Keeping `.env` reuses its secrets, which is fine for an empty
database; to start with new secrets too, move `.env` aside before `./install.sh`:

```bash
docker compose --profile app --profile ocr --profile https --profile demo down -v
./install.sh       # keeps .env: the new database is created with its password
```
