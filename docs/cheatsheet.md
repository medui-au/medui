# Cheat sheet

One page of the commands and switches for installing, upgrading and running MedUI on the
Docker route. Each line links to the page that explains it. Run the Linux commands in the
MedUI folder (`~/medui_os` by default) as the install user, not root.

## Install

```bash
./install.sh --dry-run     # show the plan, change nothing
./install.sh               # install, or re-run safely: keeps data and settings
./install.sh --help        # every option
```

| Switch | What it does |
|---|---|
| `--dry-run` | Show what would be done; change nothing |
| `--yes` | Don't ask for confirmation |
| `--name NAME` | Compose project name; keeps a second installation apart. Default: the folder's name (`~/medui_demo` → `medui_demo`); an installation keeps its own |
| `--timezone ZONE` | The practice's timezone: `brisbane`, `vic` or `Australia/Melbourne`. Changes it on an existing installation too |
| `--app-port N` | MedUI's port on this computer (default 5005) |
| `--db-port N` | PostgreSQL's port (default 55432) |
| `--ocr-port N` | LiteParse OCR's port (default 5707) |
| `--no-ocr` | Don't build or start OCR |
| `--no-apt` | Skip system packages (Docker, git, curl): install them yourself |
| `--no-admin` | Don't create the local administrator now (`install admin` later) |
| `--reference-data` | Also import the optional drug and vaccine reference snapshots |
| `--demo` | A demo installation: its own SQL Server with MedUI's invented demo databases, never BP ([Administrator setup guide](setup-guide.md#a-demo-installation)). Without it, a new installation asks live or demo (not with `--yes`) |
| `--accept-sql-licence` | With `--demo`: accept Microsoft's SQL Server licence terms without being asked |
| `--https` | HTTPS for workstations through Caddy ([HTTPS](https.md)); remembered afterwards |
| `--https-name NAME` | A name workstations type (repeatable; default: this computer's name) |
| `--https-ip IP` | An address workstations type (repeatable; default: this computer's address) |
| `--https-cert FILE` / `--https-key FILE` | Use the practice's own certificate and key (PEM) instead of a MedUI root |
| `--https-port N` | HTTPS port (default 443) |
| `--http-port N` | Port for the setup page workstations open first (default 80) |
| `--https-new-root` | Replace the MedUI root (when the names change; every workstation needs the new one) |

Two installations on one computer, for example one with sample data and one without, need
their own folder, name and ports. A second folder is named after itself, and its ports move to
the next free ones, so this is enough:

```bash
git clone <repository> ~/medui_test && cd ~/medui_test
./install.sh               # project medui_test; ports 5006, 55433, 5708 if the first install has the defaults
```

`install.sh` stops if the name is already installed from another folder, or if Docker still
holds data under that name from a removed installation. `--name` and the port options still
choose for themselves; a port you choose, or one an installation already has, never moves.

## Upgrade

```bash
./upgrade.sh --dry-run     # versions, changelog and plan; change nothing
./upgrade.sh               # back up, then upgrade to the current branch's latest
./upgrade.sh --to v1.0.0   # move to a tag, branch or commit
```

| Switch | What it does |
|---|---|
| `--to REF` | Tag, branch or commit to upgrade to |
| `--skip-seeds` | Don't update the seeded prompts and workflows (`install resync-seeds` later) |
| `--yes` | Don't ask (the seed changes are still listed) |
| `--dry-run` | Show what would be done; change nothing (it still fetches) |

While the repository is private, give the GitHub token for one run, so you type it once and
it never reaches your shell history ([Upgrades](operations.md#upgrades)):

```bash
read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./upgrade.sh --dry-run && ./upgrade.sh; unset MEDUI_GIT_TOKEN
```

Each upgrade backs up into `backups/<date>-<version>/` and keeps the previous image as
`<project>-app:previous`. If a step fails, it prints the commands that put the old version back.

## The MedUI menu

`./medui.sh` opens a menu for the everyday tasks below. Each also works as one command
(`./medui.sh status`, `./medui.sh reload`...; `./medui.sh help` lists them). Every action prints
the command it runs, so it can be repeated by hand, and nothing in it prints `.env`'s secrets.

| Command | What it does |
|---|---|
| `status` | Containers, health, version, BP set or not, HTTPS, features, last backup |
| `start` / `stop` (`--all`) | Start or stop MedUI (and HTTPS); `--all` also stops the database and OCR |
| `reload` | Recreate the app so it reads `.env` again |
| `bp` / `bp-check` / `bp-clear` | Set the Best Practice connection (then reload and check it), check the login is read-only, or remove it |
| `features` | Turn AI, messaging or PIT export on or off, then reload (`features AI_ENABLED=on`) |
| `https` | HTTPS for workstations (`./install.sh --https`, with its options); on WSL2 it shows the Windows firewall step |
| `backup` / `backups` | Back up now into `backups/<date>-<version>-manual/`, or list the backups |
| `upgrade` | `./upgrade.sh --dry-run`, then the upgrade after a yes |
| `logs` (`-f`) | The app's last 200 log lines, or follow them |
| `admin` / `password` | Add a local administrator, or set a new password for one |
| `seeds` | Seeded prompt and workflow updates: listed, then applied after a yes |
| `ocr start` / `ocr stop` | LiteParse OCR |
| `installs` / `use` | MedUI installations on this computer; make this one the running one |
| `windows` | WSL2: the PowerShell commands for the keep-alive task and the firewall |
| `support` | Versions and states for a problem report, with no data or secrets |
| `demo` (`refresh`, `password`) | A demo installation: its data, dates brought up to today, the demo users' password |
| `remove` | Remove this installation: its containers, data and folder, after a backup offer and typing its name |

The menu doesn't open MedUI's own port (5005) to the network: it is plain HTTP. Workstations
use HTTPS. It also doesn't switch one installation between the practice's BP and sample data:
MedUI's database keeps users and history tied to one BP, so the demo gets its own
installation (`./install.sh --demo` in its own folder), and `use` switches which one runs.

## Every day

The menu commands above cover most of it. The same by hand, for when the menu isn't there or
you need another service's log ([Troubleshooting](troubleshooting.md#first-look)):

| Task | Menu | By hand |
|---|---|---|
| What is running, and its health | `./medui.sh status` | `docker compose --profile app --profile ocr ps` |
| The app's recent output | `./medui.sh logs` | `docker compose --profile app logs app --tail 60` |
| Follow the app's output live | `./medui.sh logs -f` | `docker compose --profile app logs -f app` |
| PostgreSQL / OCR output | | `docker compose logs db --tail 40` / `docker compose --profile ocr logs liteparse --tail 40` |
| Is the web process up? | | `curl -s http://127.0.0.1:5005/health` |
| Restart the app | `./medui.sh restart` | `docker compose --profile app restart app` |
| Pick up a `.env` change | `./medui.sh reload` | `docker compose --profile app up -d --force-recreate app` |
| Stop / start the app | `./medui.sh stop` / `./medui.sh start` | `docker compose --profile app stop app` / `docker compose --profile app up -d app` |

After `git pull`, a restart alone keeps running the old code: use `./upgrade.sh`, or rebuild by
hand ([upgrades](operations.md#upgrades)). With
`--name`, add `-p <name>` only when running outside that installation's folder.

## Back up and restore

`./medui.sh backup` backs up the database (read back to check it), `.env`, the app data and, with
HTTPS on, the `https` folder into `backups/`; `./medui.sh backups` lists them. Keep another copy off the
computer: `.env` holds `MEDUI_ENCRYPTION_KEY`. Doing it by hand, and restoring into an
**empty** database only: [operations](operations.md#backup).

## MedUI's own commands

Run each as `docker compose --profile app run --rm app flask --app wsgi <command>`.

| Command | What it does |
|---|---|
| `install admin` | Create another local administrator (asks for a new username and password) |
| `install defaults` | Add settings new in a release; never changes existing ones |
| `install seeds --dry-run` / `install seeds` | Preview or install the starter prompts and workflows ([seed data](seed-data.md)) |
| `install seeds --include-reference-data` | The same, plus the drug and vaccine reference snapshots |
| `install resync-seeds --dry-run` / `install resync-seeds` | Bring seeded prompts and workflows up to this release; edited ones are kept |
| `install resync-seeds --replace NAME` | Take the release version of an item edited here (repeatable) |
| `install resync-seeds --archive-dropped` | Archive seeded items the release dropped (never deletes) |
| `seed providers` | Add the AI provider templates (no accounts are switched on) |
| `seed sync-bpsdb-users --dry-run` | Show which security levels and patient-ID links would be copied from Best Practice's users (without `--dry-run`, applies them; only raises levels) |
| `db upgrade` | Apply database schema changes |
| `db check` | Check the schema matches the code |

## Best Practice connection

`./medui.sh bp` asks for these, writes them to `.env`, reloads and checks the login. By hand, add
them to `.env`, then `./medui.sh reload` ([Administrator setup guide](setup-guide.md#2-best-practice-connection)):

```text
BPSDB_HOST=192.0.2.10\BPSINSTANCE
BPSDB_DATABASE=BPSPatients
BPSDB_USER=<the read-only login from Best Practice Software>
BPSDB_PASSWORD=<its password>
BPSDB_TRUST_SERVER_CERTIFICATE=true
```

- A named instance takes **one** backslash in `.env`.
- **Application Setup → Database** shows whether the login is read-only in every database it
  can open.
- The login reads every database it can open on that server. A test or demo installation
  belongs on a SQL Server with only test data, never the practice's live server. For MedUI's
  invented demo databases, install a demo instead: `./install.sh --demo` sets up its own.
- To test the login outside MedUI: `sqlcmd -S '192.0.2.10\BPSINSTANCE' -U <bp_user> -C -Q "SELECT 1"`.

## Windows (WSL2)

In PowerShell, in the folder holding the scripts ([Windows scripts](../scripts/windows/README.md)):

| Task | Command |
|---|---|
| New instance with MedUI (ordinary PowerShell, not as administrator) | `powershell.exe -NoExit -ExecutionPolicy Bypass -File .\create_medui_wsl2.ps1` |
| Upgrade (`-Instance <name>`, `-To <tag>` optional) | `powershell.exe -NoExit -ExecutionPolicy Bypass -File .\upgrade_medui_wsl2.ps1` |
| Open the HTTPS port to the network (as administrator) | `.\open_medui_https_port.ps1 -Instance medui` (`-Port 443`, `-HttpPort 80`, `0` leaves 80 closed) |
| Trust the MedUI root on a workstation | `.\install_medui_root.ps1 -Path <medui-root.cer>` (`-CurrentUser` for this account only) |
| A shell in the instance | `wsl -d medui` |
| Re-run the installer | `wsl -d medui --cd /home/medui/medui_os -- ./install.sh` |
| List instances | `wsl -l -v` |
| Stop an instance | `Stop-ScheduledTask -TaskName "WSL2 medui keep-alive"`, then `wsl --terminate medui` (the task first, or it starts the instance again) |

A downloaded script may first need `Unblock-File .\<script>.ps1`.

## Removing

**These delete data for good.** In the installation's folder, `./medui.sh remove` does it with
checks: it shows what it will remove, offers a backup (kept outside the folder, in
`~/medui_removed/`), and asks you to type the installation's name. By hand, from the
installation's own folder ([Removing an installation](operations.md#removing-an-installation)):

```bash
docker compose --profile app --profile ocr --profile https --profile demo down -v --rmi local
cd ~ && rm -rf ~/medui_os
```

To remove a whole WSL2 instance, run `wsl --unregister medui` in PowerShell
([Removing it](../scripts/windows/README.md#removing-it)).
