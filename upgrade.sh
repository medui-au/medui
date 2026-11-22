#!/usr/bin/env bash
# Upgrade an installed MedUI (Docker route) to a newer release, keeping its data and settings.
#
#   ./upgrade.sh                 update the current branch to its latest commit
#   ./upgrade.sh --to v1.0.0     move to a tag, branch or commit
#   ./upgrade.sh --dry-run       show what would be done, change nothing
#
# An installation from before this script existed: fetch the script, then run it from
# outside the folder (MEDUI_DIR says where MedUI is):
#   git -C ~/medui_os fetch && git -C ~/medui_os show origin/main:upgrade.sh > ~/medui-upgrade.sh
#   MEDUI_DIR=~/medui_os bash ~/medui-upgrade.sh
#
# Options:
#   --to REF             tag, branch or commit to upgrade to (default: the current branch's latest)
#   --skip-seeds         don't update the seeded prompts and workflows (run 'install resync-seeds' later)
#   --yes                don't ask for confirmation (the seed changes are still listed)
#   --dry-run            show what would be done, change nothing
#
# What it does, in order. Nothing is changed before step 3, and the running app is only
# stopped at step 6, after the new version has built:
#   1. checks: not root, run from the repository, .env present, no local code changes,
#      Docker and the database running, free disk space
#   2. shows the current and new versions and the changelog between them; asks to go ahead
#   3. backup into backups/<date>-<version>/: database dump (verified), .env, app data, and the
#      HTTPS folder (the MedUI root and its key) when HTTPS is on
#   4. the new code (git)
#   5. the new MedUI image, built while the current one keeps running; the current image
#      is kept as <project>-app:previous
#   6. stops MedUI; database upgrade; new default settings (existing ones never change)
#   7. seeded prompts and workflows: lists the changes, asks, applies (edited ones are kept)
#   8. starts MedUI and checks it answers
# If a step from 4 on fails, it prints the commands that put the previous version back.
# See docs/operations.md (Upgrades).

if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
# Started by an older upgrade.sh handing over (below): this copy is a temporary file. Bash keeps
# reading it after it is removed.
if [ -n "${MEDUI_UPGRADE_HANDOFF:-}" ] && [ "$MEDUI_UPGRADE_HANDOFF" = "${BASH_SOURCE[0]}" ]; then
  rm -f "$MEDUI_UPGRADE_HANDOFF"
fi
ARGS=("$@")

APP_DIR="$(cd "${MEDUI_DIR:-$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
TARGET="" SEEDS=1 YES=0 DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --to) TARGET="${2:?--to needs a tag, branch or commit}"; shift ;;
    --skip-seeds) SEEDS=0 ;;
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then echo "  [dry run] $*"; else "$@"; fi; }
env_get() { [ -f "$APP_DIR/.env" ] && sed -n "s/^$1=//p" "$APP_DIR/.env" | tail -1 || true; }
confirm() {   # confirm "question": yes with --yes; in a dry run, say what would be asked
  [ "$YES" = 1 ] && return 0
  if [ "$DRY" = 1 ]; then echo "  [dry run] would ask: $1"; return 0; fi
  read -rp $'\n'"$1 (y/N) " answer
  [[ "$answer" =~ ^[yY]$ ]]
}
version_at() { git show "$1:app/version.py" 2>/dev/null | sed -n "s/^__version__ = '\(.*\)'/\1/p"; }

cd "$APP_DIR"

# ---- 1. checks ----------------------------------------------------------------------------------------------------
say "1. Checks"
[ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root."
[ -f compose.yaml ] && [ -f install.sh ] && [ -d .git ] || die "Run this from the MedUI repository folder."
[ -f .env ] || die "No .env here: MedUI isn't installed in this folder. Use ./install.sh for a new installation."
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --short --untracked-files=no | sed 's/^/    /'
  die "The files above have local changes. An upgrade would mix them with the new release.
Record why they were changed (AGENTS.md: reporting a problem), then put them back with
'git restore <file>' (or 'git stash'), and run this again."
fi
PROJECT="$(env_get COMPOSE_PROJECT_NAME)"; PROJECT="${PROJECT:-medui_os}"
APP_PORT="$(env_get APP_PORT)"; APP_PORT="${APP_PORT:-5005}"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  sudo docker info >/dev/null 2>&1 || die "Docker is not running: sudo systemctl status docker"
  DOCKER=(sudo docker)
fi
compose() { "${DOCKER[@]}" compose -p "$PROJECT" "$@"; }
compose_run() { run "${DOCKER[@]}" compose -p "$PROJECT" "$@"; }
flask_cmd() { compose_run --profile app run --rm app flask --app wsgi "$@"; }

compose ps --status running --services 2>/dev/null | grep -qx db \
  || die "The database container isn't running. Start it with: docker compose -p $PROJECT up -d --wait db"
compose exec -T db sh -c 'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  || die "The database isn't accepting connections. See: docker compose -p $PROJECT logs db"
OCR=0
compose ps --services 2>/dev/null | grep -qx liteparse && OCR=1
HTTPS=0
[ -n "$(env_get HTTPS_MODE)" ] && HTTPS=1
FREE_GB=$(( $(df -Pk "$APP_DIR" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
[ "$FREE_GB" -ge 3 ] || die "Only ${FREE_GB} GB free here; the backup and new image need about 3 GB."
ok "Project '$PROJECT', MedUI on port $APP_PORT, database running$([ "$OCR" = 1 ] && echo ", OCR installed")$([ "$HTTPS" = 1 ] && echo ", HTTPS"), ${FREE_GB} GB free"

# ---- 2. what changes ----------------------------------------------------------------------------------------------
say "2. Versions"
PREV_COMMIT="$(git rev-parse HEAD)"
PREV_REF="$(git symbolic-ref -q --short HEAD || echo "$PREV_COMMIT")"
PREV_VERSION="$(version_at HEAD)"
# A token in MEDUI_GIT_TOKEN (private repository), set by upgrade_medui_wsl2.ps1 or by hand
# (docs/operations.md), is used through a temporary GIT_ASKPASS helper, never on a command
# line or on disk; otherwise git asks as usual.
if [ -n "${MEDUI_UPGRADE_HANDOFF:-}" ]; then
  :   # handed over: the installed script has just fetched (and git won't ask for the token again)
elif [ -n "${MEDUI_GIT_TOKEN:-}" ]; then
  ASKPASS="$(mktemp)"; chmod 700 "$ASKPASS"
  printf '#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) printf "%%s\\n" "$MEDUI_GIT_TOKEN" ;; esac\n' > "$ASKPASS"
  GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0 git fetch --quiet --tags origin \
    || { rm -f "$ASKPASS"; die "Couldn't fetch from the repository with the token given. Nothing was changed."; }
  rm -f "$ASKPASS"
else
  git fetch --quiet --tags origin || die "Couldn't reach the repository (git fetch). Check the network and access."
fi
if [ -z "$TARGET" ]; then
  git symbolic-ref -q HEAD >/dev/null || die "This checkout isn't on a branch. Say where to go with --to <tag or branch>."
  UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" \
    || die "Branch '$PREV_REF' has no upstream. Say where to go with --to <tag or branch>."
  TARGET_COMMIT="$(git rev-parse "$UPSTREAM")"
  TARGET_LABEL="$UPSTREAM"
else
  TARGET_COMMIT="$(git rev-parse --verify --quiet "origin/$TARGET^{commit}" || git rev-parse --verify --quiet "$TARGET^{commit}")" \
    || die "'$TARGET' isn't a tag, branch or commit in the repository."
  TARGET_LABEL="$TARGET"
fi
NEW_VERSION="$(version_at "$TARGET_COMMIT")"
ok "Now:  $PREV_VERSION  ($(git log -1 --format='%h %s' HEAD))"
ok "New:  $NEW_VERSION  ($(git log -1 --format='%h %s' "$TARGET_COMMIT"), $TARGET_LABEL)"
if [ "$TARGET_COMMIT" = "$PREV_COMMIT" ]; then
  ok "Already at that version. Nothing to do."
  exit 0
fi
if [ -z "$TARGET" ] && ! git merge-base --is-ancestor HEAD "$TARGET_COMMIT"; then
  die "'$PREV_REF' and '$UPSTREAM' have diverged; this script only moves forward. Ask the maintainers."
fi
if git merge-base --is-ancestor "$TARGET_COMMIT" HEAD; then
  die "$TARGET_LABEL is older than what is installed. Going back needs the backup taken before the upgrade
(docs/operations.md), not this script."
fi
# This script is the installed version's. If the new version's upgrade.sh differs, hand over to
# it now, before anything changes, so that steps it adds (or fixes) run in this upgrade rather
# than the next one. Once only: the new script doesn't hand over again.
if [ -z "${MEDUI_UPGRADE_HANDOFF:-}" ] && ! git diff --quiet HEAD "$TARGET_COMMIT" -- upgrade.sh; then
  NEXT="$(mktemp "${TMPDIR:-/tmp}/medui-upgrade.XXXXXX")"
  git show "$TARGET_COMMIT:upgrade.sh" > "$NEXT"
  ok "Continuing with $NEW_VERSION's upgrade script"
  MEDUI_UPGRADE_HANDOFF="$NEXT" MEDUI_DIR="$APP_DIR" exec bash "$NEXT" ${ARGS[@]+"${ARGS[@]}"}
fi
# The changelog entries newer than the installed version.
CHANGES="$(git show "$TARGET_COMMIT:CHANGELOG.md" 2>/dev/null \
  | awk -v cur="## $PREV_VERSION " 'index($0, cur) == 1 {exit} /^## / {show=1} show' || true)"
if [ -n "$CHANGES" ]; then
  echo; echo "  What's new (CHANGELOG.md):"; echo "$CHANGES" | sed 's/^/    /'
fi
confirm "Back up and upgrade MedUI from $PREV_VERSION to $NEW_VERSION?" || { echo "Nothing changed."; exit 0; }

# From here on, a failure prints how to go back.
BACKUP_DIR="backups/$(date +%Y%m%d-%H%M%S)-v$PREV_VERSION"
STAGE="backup"
rollback_help() {
  local code=$?
  [ "$code" = 0 ] && return
  [ "$DRY" = 1 ] && return
  printf '\n\033[31mThe upgrade stopped at: %s.\033[0m\n' "$STAGE" >&2
  case "$STAGE" in
    backup)
      echo "Nothing was changed. MedUI is still running the previous version." >&2 ;;
    code|image)
      cat >&2 <<EOF
The database wasn't touched and MedUI is still running the previous version.
Put the code back with:
  git checkout $PREV_REF && git reset --hard $PREV_COMMIT
EOF
      ;;
    *)
      cat >&2 <<EOF
To put the previous version back (database, code and image), from $APP_DIR:
  ${DOCKER[*]} compose -p $PROJECT --profile app stop app
  ${DOCKER[*]} compose -p $PROJECT exec -T db sh -c 'dropdb -U "\$POSTGRES_USER" --force "\$POSTGRES_DB" && createdb -U "\$POSTGRES_USER" "\$POSTGRES_DB"'
  ${DOCKER[*]} compose -p $PROJECT exec -T db sh -c 'pg_restore -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" --exit-on-error --no-owner --no-acl' < $BACKUP_DIR/medui.dump
  git checkout $PREV_REF && git reset --hard $PREV_COMMIT
  ${DOCKER[*]} image tag $PROJECT-app:previous $PROJECT-app:latest
  ${DOCKER[*]} compose -p $PROJECT --profile app up -d --wait app$([ "$HTTPS" = 1 ] && echo "
  ${DOCKER[*]} compose -p $PROJECT --profile app --profile https up -d caddy")
The first two commands replace the database with the backup taken at the start of this
upgrade: anything entered since then is lost. If MedUI only failed to start, look at its
log first: ${DOCKER[*]} compose -p $PROJECT --profile app logs app
EOF
      ;;
  esac
}
trap rollback_help EXIT

# ---- 3. backup ----------------------------------------------------------------------------------------------------
say "3. Backup to $BACKUP_DIR"
run mkdir -p "$BACKUP_DIR"
run chmod 700 backups "$BACKUP_DIR"
if [ "$DRY" = 1 ]; then
  echo "  [dry run] database dump, .env and app data into $BACKUP_DIR"
else
  (umask 077; compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP_DIR/medui.dump")
  TABLES="$(compose exec -T db pg_restore --list < "$BACKUP_DIR/medui.dump" | grep -c ' TABLE ' || true)"
  [ "${TABLES:-0}" -gt 0 ] || die "The database dump in $BACKUP_DIR couldn't be read back. Nothing was changed."
  ok "Database: medui.dump ($(du -h "$BACKUP_DIR/medui.dump" | cut -f1), $TABLES tables, read back)"
  install -m 600 .env "$BACKUP_DIR/env"
  ok "Settings: env (a copy of .env, mode 600; it holds the encryption key)"
  "${DOCKER[@]}" run --rm -v "${PROJECT}_app_data:/data:ro" -v "$APP_DIR/$BACKUP_DIR:/backup" postgres:17-bookworm \
    sh -c "tar -C /data -czf /backup/app_data.tgz . && chown $(id -u):$(id -g) /backup/app_data.tgz && chmod 600 /backup/app_data.tgz"
  ok "App data: app_data.tgz"
  if [ -d https ]; then
    (umask 077; tar -czf "$BACKUP_DIR/https.tgz" https)
    ok "HTTPS: https.tgz (Caddy's settings and the MedUI root with its key; keep it private)"
  fi
  git rev-parse HEAD > "$BACKUP_DIR/commit"
fi
warn "The backup is on this computer only. Copy it somewhere else as well for safety (docs/operations.md)."

# ---- 4. code ------------------------------------------------------------------------------------------------------
STAGE="code"
say "4. New code"
if [ -z "$TARGET" ]; then
  run git merge --ff-only --quiet "$TARGET_COMMIT"
else
  run git checkout --quiet "$TARGET"
  [ "$DRY" = 1 ] || [ "$(git rev-parse HEAD)" = "$TARGET_COMMIT" ] || run git merge --ff-only --quiet "$TARGET_COMMIT"
fi
ok "$(git log -1 --format='%h %s' "$([ "$DRY" = 1 ] && echo "$TARGET_COMMIT" || echo HEAD)")"

# ---- 5. new image -------------------------------------------------------------------------------------------------
STAGE="image"
say "5. New MedUI image (the current version keeps running)"
if "${DOCKER[@]}" image inspect "$PROJECT-app:latest" >/dev/null 2>&1; then
  run "${DOCKER[@]}" image tag "$PROJECT-app:latest" "$PROJECT-app:previous"
  ok "Current image kept as $PROJECT-app:previous"
fi
echo "  The image includes Microsoft ODBC Driver 18 for SQL Server; building it accepts Microsoft's licence terms: https://aka.ms/odbc18eula"
compose_run --profile app build app
[ "$OCR" = 1 ] && compose_run --profile ocr build liteparse
ok "Built"

# ---- 6. database --------------------------------------------------------------------------------------------------
STAGE="database"
say "6. Stop MedUI; database upgrade; new default settings"
compose_run --profile app stop app
flask_cmd db upgrade
flask_cmd install defaults
# .env settings added by a release, written once (after the backup, which holds the old .env).
# OCR_ENABLED (0.50.0): what the installation has, the LiteParse container or not.
if [ -z "$(env_get OCR_ENABLED)" ]; then
  OCR_LINE="OCR_ENABLED=$([ "$OCR" = 1 ] && echo true || echo false)"
  if [ "$DRY" = 1 ]; then echo "  [dry run] add $OCR_LINE to .env"; else echo "$OCR_LINE" >> "$APP_DIR/.env"; fi
  ok ".env: $OCR_LINE added"
fi
ok "Schema current; new settings added, existing ones kept"

# ---- 7. seeds -----------------------------------------------------------------------------------------------------
STAGE="seeds"
say "7. Seeded prompts and workflows"
if [ "$SEEDS" = 0 ]; then
  ok "Skipped (--skip-seeds). Later: docker compose -p $PROJECT --profile app run --rm app flask --app wsgi install resync-seeds --dry-run"
else
  flask_cmd install resync-seeds --dry-run
  if confirm "Apply the seed changes listed above? (Prompts the practice edited are kept.)"; then
    flask_cmd install resync-seeds
    ok "Applied"
  else
    warn "Not applied. Later: docker compose -p $PROJECT --profile app run --rm app flask --app wsgi install resync-seeds"
  fi
fi

# ---- 8. start -----------------------------------------------------------------------------------------------------
STAGE="start"
say "8. Start MedUI"
[ "$OCR" = 1 ] && compose_run --profile ocr up -d --wait liteparse
compose_run --profile app up -d --wait app
[ "$HTTPS" = 1 ] && compose_run --profile app --profile https up -d caddy
if [ "$DRY" = 0 ]; then
  HEALTH=""
  for _ in $(seq 1 30); do
    HEALTH="$(curl -fsS "http://127.0.0.1:$APP_PORT/health" 2>/dev/null)" && break
    sleep 2
  done
  [ -n "$HEALTH" ] || die "MedUI did not answer on port $APP_PORT."
  echo "$HEALTH" | grep -q "\"$NEW_VERSION\"" || warn "/health answered but didn't report $NEW_VERSION: $HEALTH"
fi
STAGE="done"
ok "MedUI $NEW_VERSION answers at http://127.0.0.1:$APP_PORT"

if [ "$DRY" = 1 ]; then say "Dry run: nothing changed"; exit 0; fi
say "Done"
cat <<EOF
  Upgraded from $PREV_VERSION to $NEW_VERSION. Backup: $APP_DIR/$BACKUP_DIR
  Check login and the changed features. The previous image stays as $PROJECT-app:previous
  until the next upgrade; old backups in backups/ are yours to remove when no longer needed.
EOF
