#!/usr/bin/env bash
# The demo databases of a demo installation (install.sh --demo): MedUI's invented
# medui_demodata, restored into this installation's own SQL Server container (service bpsql).
#
#   scripts/demo_data.sh fetch      get medui_demodata into ./demodata (once)
#   scripts/demo_data.sh restore    restore the three databases (once) and the read-only login
#   scripts/demo_data.sh password   set the demo users' password (asks; or MEDUI_DEMO_PASSWORD)
#   scripts/demo_data.sh refresh    bring the dates up to today (--dry-run to look first)
#   scripts/demo_data.sh status     what is there
#
# Run from the MedUI folder, by install.sh and ./medui.sh. It works only on a demo installation
# (MEDUI_INSTANCE=demo in .env) and only on its own bpsql container: never on Best Practice.
# Passwords travel in the environment or a mode-600 file that is deleted afterwards, never on
# a command line. MEDUI_GIT_TOKEN, when set, is used for a private medui_demodata.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
DEMO_REPO="${MEDUI_DEMO_REPO:-https://github.com/medui-au/medui_demodata.git}"
DEMO_DIR="$APP_DIR/demodata"
DBS=(BPSPATIENTS BPSDocuments1 BPSDOCUMENTSINBOX)

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
env_get() { [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1 || true; }

[ -f .env ] || die "No .env here: run ./install.sh --demo first."
[ "$(env_get MEDUI_INSTANCE)" = demo ] || die "This isn't a demo installation (MEDUI_INSTANCE=demo in .env). The demo data goes only into a demo installation of its own."
[ "$(env_get BPSDB_HOST)" = bpsql ] || die "BPSDB_HOST isn't bpsql, this installation's own demo SQL Server. Nothing done."
PROJECT="$(env_get COMPOSE_PROJECT_NAME)"; PROJECT="${PROJECT:-medui_os}"
SA_PASSWORD="$(env_get DEMO_SQL_SA_PASSWORD)"
[ -n "$SA_PASSWORD" ] || die "DEMO_SQL_SA_PASSWORD is missing from .env: run ./install.sh --demo again."
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  sudo docker info >/dev/null 2>&1 || die "Docker is not running, or this account can't use it."
  DOCKER=(sudo docker)
fi
container() { "${DOCKER[@]}" compose -p "$PROJECT" --profile demo ps -q bpsql 2>/dev/null | head -1; }
sqlcmd() {   # sqlcmd as sa inside the bpsql container; SQL on stdin
  local c; c="$(container)"; [ -n "$c" ] || die "The demo SQL Server isn't running: docker compose -p $PROJECT --profile demo up -d --wait bpsql"
  SQLCMDPASSWORD="$SA_PASSWORD" "${DOCKER[@]}" exec -i -e SQLCMDPASSWORD "$@" "$c" \
    /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -h -1 -W
}
present() {   # how many of the three databases exist
  printf 'SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name IN (%s);\n' \
    "$(printf "'%s'," "${DBS[@]}" | sed 's/,$//')" | sqlcmd | tr -d '[:space:]'
}
tool() {   # tool <script.py> [args]: a medui_demodata tool in this installation's app image, as sa,
  # on this installation's network only. The secrets file is mode 600 and deleted afterwards.
  local secrets rc=0; secrets="$(mktemp)"; chmod 600 "$secrets"
  printf 'MSSQL_SA_PASSWORD=%s\nDEMO_USER_PASSWORD=%s\n' "$SA_PASSWORD" "${DEMO_USER_PASSWORD:-}" > "$secrets"
  "${DOCKER[@]}" run --rm --user 0 --network "${PROJECT}_default" -e BPSQL_HOST=bpsql \
    --entrypoint python -v "$DEMO_DIR/tools:/work:ro" -v "$secrets:/secrets/dst.env:ro" -w /work \
    "${PROJECT}-app" -I -B "$@" || rc=$?
  rm -f "$secrets"
  return $rc
}

cmd_fetch() {
  if [ -d "$DEMO_DIR/backups" ]; then ok "Demo data present: $(git -C "$DEMO_DIR" log -1 --format='%h %ad' --date=short 2>/dev/null || echo "$DEMO_DIR")"; return; fi
  [ -e "$DEMO_DIR" ] && die "$DEMO_DIR exists but holds no backups/. Remove it, then run this again."
  echo "  Downloading the demo data from $DEMO_REPO"
  if [ -n "${MEDUI_GIT_TOKEN:-}" ]; then
    local ask; ask="$(mktemp)"; chmod 700 "$ask"
    printf '#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) printf "%%s\\n" "$MEDUI_GIT_TOKEN" ;; esac\n' > "$ask"
    GIT_ASKPASS="$ask" GIT_TERMINAL_PROMPT=0 git clone --quiet "$DEMO_REPO" "$DEMO_DIR" || { rm -f "$ask"; die "Couldn't download the demo data with the token given."; }
    rm -f "$ask"
  else
    git clone --quiet "$DEMO_REPO" "$DEMO_DIR" || die "Couldn't download the demo data. While medui_demodata is private, give a GitHub token that can read it:
  read -rsp 'GitHub token: ' MEDUI_GIT_TOKEN && export MEDUI_GIT_TOKEN && ./install.sh --demo; unset MEDUI_GIT_TOKEN"
  fi
  ok "Demo data: $(git -C "$DEMO_DIR" log -1 --format='%h %ad' --date=short)"
}

cmd_restore() {
  [ -d "$DEMO_DIR/backups" ] || cmd_fetch
  local n; n="$(present)"
  if [ "$n" = 3 ]; then
    ok "Demo databases already restored (kept as they are)"
  elif [ "$n" != 0 ]; then
    die "Only $n of the three demo databases exist in the demo SQL Server. Remove its volume (docker compose -p $PROJECT --profile demo down bpsql; docker volume rm ${PROJECT}_bpsql_data), then run this again."
  else
    (cd "$DEMO_DIR/backups" && sha256sum --quiet -c SHA256SUMS) || die "The demo backups don't match their checksums."
    local c d; c="$(container)"
    "${DOCKER[@]}" exec -u mssql "$c" mkdir -p /var/opt/mssql/backup
    for d in "${DBS[@]}"; do
      "${DOCKER[@]}" cp "$DEMO_DIR/backups/$d.bak" "$c:/var/opt/mssql/backup/$d.bak" >/dev/null
      "${DOCKER[@]}" exec -u 0 "$c" chown mssql /var/opt/mssql/backup/$d.bak
    done
    sqlcmd < "$DEMO_DIR/restore/restore.sql" >/dev/null
    "${DOCKER[@]}" exec -u 0 "$c" rm -rf /var/opt/mssql/backup
    ok "Demo databases restored: ${DBS[*]}"
  fi
  # The read-only login MedUI uses, with the password in .env (kept in step with it on every run).
  READER_USER="$(env_get BPSDB_USER)" READER_PASSWORD="$(env_get BPSDB_PASSWORD)"
  [ -n "$READER_USER" ] && [ -n "$READER_PASSWORD" ] || die "BPSDB_USER or BPSDB_PASSWORD is missing from .env."
  export READER_USER READER_PASSWORD
  sqlcmd -e READER_USER -e READER_PASSWORD < "$DEMO_DIR/restore/create_reader.sql" >/dev/null
  printf "ALTER LOGIN [\$(READER_USER)] WITH PASSWORD = '\$(READER_PASSWORD)';\n" | sqlcmd -e READER_USER -e READER_PASSWORD >/dev/null
  ok "Read-only login '$READER_USER' in the three databases"
}

cmd_password() {
  if [ -z "${MEDUI_DEMO_PASSWORD:-}" ]; then
    [ -t 0 ] || die "No terminal to ask in. Set MEDUI_DEMO_PASSWORD for this one command, or run: ./medui.sh demo password"
    echo "  The demo users (Dr Imogen Thistlewood, Dr Callum Ravensworth, the nurse, reception…) all share one password."
    local a b
    while :; do
      read -rsp "  Password for the demo users (at least 8 characters): " a; echo
      [ ${#a} -ge 8 ] || { warn "Too short."; continue; }
      read -rsp "  Again: " b; echo
      [ "$a" = "$b" ] && break
      warn "They don't match."
    done
    MEDUI_DEMO_PASSWORD="$a"
  fi
  DEMO_USER_PASSWORD="$MEDUI_DEMO_PASSWORD" tool set_user_password.py >/dev/null
  ok "Demo users' password set: they log in with it on MedUI's login page"
}

cmd_refresh() {
  tool refresh_dates.py "$@"
}

cmd_status() {
  if [ -d "$DEMO_DIR/backups" ]; then ok "Demo data: $(git -C "$DEMO_DIR" log -1 --format='%h %ad' --date=short 2>/dev/null || echo present)"
  else warn "Demo data: not downloaded"; fi
  if [ -z "$(container)" ]; then warn "Demo SQL Server: not running"; return 0; fi
  local n; n="$(present)"
  if [ "$n" = 3 ]; then ok "Demo SQL Server: running, ${DBS[*]} restored"
  else warn "Demo SQL Server: running, $n of 3 databases restored"; fi
}

case "${1:-}" in
  fetch|restore|password|status) "cmd_$1" ;;
  refresh) shift; cmd_refresh "$@" ;;
  *) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
