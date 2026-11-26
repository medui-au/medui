# Operations

## The MedUI menu

`./medui.sh` (in the MedUI folder) runs the tasks on this page from a menu, or one at a time:
`./medui.sh backup`, `./medui.sh upgrade`, `./medui.sh reload`... The
[cheat sheet](cheatsheet.md#the-medui-menu) lists them. The commands below are what it runs.

## Backup

PostgreSQL uses the Compose `postgres_data` volume. Container recreation does not
replace this volume. Never run `docker compose down -v` against an installation
whose data you need.

```bash
mkdir -p backups
chmod 700 backups
(umask 077; docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/medui.dump)
```

The brackets keep `umask 077` (dump readable only by you) to that one command. Left
set in the shell, it makes files from a later `git pull` unreadable to the app.

Back up `.env` securely alongside the database, especially `MEDUI_ENCRYPTION_KEY`.
With HTTPS on, also back up the `https` folder: it holds the MedUI root and its key, and a
new root means installing it on every workstation again ([HTTPS](https.md)).
Encrypted records cannot be recovered without the original key. Also back up the
`app_data` volume. The PIT folder (`./medui.sh pit`) is Best Practice's share, backed up with the BP server, not here. A Docker
volume alone is not a backup. Store another copy off the host.

## Restore rehearsal

Restore into a separate empty database before attempting a production recovery.
For a new destination container initialised with matching installation settings:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --no-owner --no-acl' < backups/medui.dump
```

This expects an empty destination; it deliberately does not drop existing tables.
Restore the encryption key and any app files before starting the restored app.
Verify login, encrypted records, and practice configuration. Keep the restored
instance disconnected from outbound messaging/PIT until its configuration is checked.

## Upgrades

`./upgrade.sh` runs the steps below in order, with a verified backup into
`backups/<date>-<version>/` (database dump, `.env`, app data) and a confirmation before
anything changes; `--dry-run` shows the plan. It builds the new image before stopping
the app, keeps the previous image as `<project>-app:previous`, and if a step fails it
prints the exact commands to restore the backup and the previous code and image.
Once it knows the new version, it carries on with that version's own `upgrade.sh` ("Continuing
with … upgrade script"), so steps a release adds run in the upgrade that brings it.
The repository is public, so the fetch needs no login. Only an installation cloned from a
private copy (a private fork, say) needs a GitHub token with read access. Git asks for it: the
username, then the token at the password prompt. Or give it for that one run without it reaching
your shell history:

```bash
read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./upgrade.sh; unset MEDUI_GIT_TOKEN
```

`upgrade.sh` passes it to git through a temporary helper; it isn't written to disk or to a
command line. `--dry-run` fetches too, so at git's prompt you type the token once for the dry
run and again for the real run. To type it once, set `MEDUI_GIT_TOKEN` and run both before
`unset`. The Windows wrapper (`upgrade_medui_wsl2.ps1`) asks for it itself.

By hand:

1. Take and verify a backup.
2. Stop the app, leaving the database running: `docker compose --profile app stop app`.
3. Build the new app image: `docker compose --profile app build app`. The code is
   built into the image, so after `git pull` a restart alone keeps running the old code.
4. Run `docker compose --profile app run --rm app flask --app wsgi db upgrade`, then
   `docker compose --profile app run --rm app flask --app wsgi install defaults` (adds
   settings new in the release; never changes existing ones).
5. Bring the seeded prompts and workflows up to the new release, after checking
   the dry-run list (see [seed data](seed-data.md#after-an-upgrade-seed-resync)):
   `docker compose --profile app run --rm app flask --app wsgi install resync-seeds --dry-run`,
   then the same without `--dry-run`.
6. Start the app (`docker compose --profile app up -d app`) and verify `/health`,
   login, and the changed features.

The Compose database image tracks supported PostgreSQL 17 patch updates.
Major PostgreSQL upgrades require a separate dump/restore or `pg_upgrade` plan;
do not just change the major image tag on an existing volume. LiteParse source is
pinned to a commit; review/test updates before changing the pin.

The `/health` endpoint checks the web process only. Monitor database health and
perform a real synthetic OCR check separately.

## Removing an installation

**This deletes the installation's data for good.** The simplest way is the menu, in the
installation's folder:

```bash
./medui.sh remove
```

It shows the installation, its folder and ports, whether it reads Best Practice, and the other
MedUI installations on the computer (which it doesn't touch). It offers a backup first, and
moves it and any earlier backups out of the folder, to `~/medui_removed/<name>-<date>/`. Then
it asks you to type the installation's name, does step 1 below, checks nothing of it is left in
Docker, and deletes the folder last. On WSL2 it prints the Windows commands that remain (the
HTTPS firewall rules; and the whole instance, when no other MedUI is in it).

By hand, take a backup first if you might need it (see [backup](#backup)). Run these as the
install user, from the installation's folder.

1. Stop MedUI and delete its containers, its database and app-data volumes, and the app and
   OCR images it built:

   ```bash
   docker compose --profile app --profile ocr --profile https --profile demo down -v --rmi local
   ```

   Each `--profile` brings in a part that may be installed: OCR, HTTPS, and a demo's SQL Server
   with its demo databases. One that isn't installed is simply skipped, so the same command
   removes any installation completely. Leave one out and that part stays behind: its container
   keeps running and keeps the network in use. The SQL Server image stays until step 3.

   With an installation made with `--name`, this takes the project name from `.env`, so run
   it from that installation's own folder. Other MedUI installations on the same computer
   are not touched.
2. Delete the folder, which includes `.env` and, with HTTPS, the `https` folder holding the
   MedUI root's key. Replace `~/medui_os` with the installation's folder:

   ```bash
   cd ~ && rm -rf ~/medui_os
   ```

3. Optional, to free space: delete the images that remain. These are the PostgreSQL and
   Caddy images it downloaded, and after an upgrade the `<project>-app:previous` image that
   `./upgrade.sh` keeps. `docker image ls` lists them; remove MedUI's by name with
   `docker image rm`. `docker image prune -a` removes **every** image no container uses, so
   use it only when no other Docker work runs on this computer.

Left in place:

- **Docker, git and curl**, which the installer added from Ubuntu's repositories. Remove
  them with `apt` only if nothing else on the computer uses them.
- **Workstations' trust in the MedUI root**, if HTTPS used one (`install.sh --https` without
  your own certificate). The root's key is gone with the folder, so nothing new can be
  signed with it, but workstations still list it. To remove it on Windows, open
  `certlm.msc` (or `certmgr.msc` if it was installed for one account only), go to *Trusted
  Root Certification Authorities → Certificates* and delete *MedUI HTTPS root for …*.
  [HTTPS](https.md) covers other systems.
- **Windows firewall rules** from `open_medui_https_port.ps1`, on WSL2. In an administrator
  PowerShell, replace `medui` with the instance name:

  ```powershell
  Get-NetFirewallRule -DisplayName "WSL2 medui MedUI*" | Remove-NetFirewallRule
  Get-NetFirewallHyperVRule | Where-Object DisplayName -like 'WSL2 medui MedUI*' | Remove-NetFirewallHyperVRule
  ```

- **A WSL2 instance made for MedUI.** If MedUI was its only use, removing the whole instance
  replaces steps 1–3: see [removing it](../scripts/windows/README.md#removing-it).
