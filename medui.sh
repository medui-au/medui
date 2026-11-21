#!/usr/bin/env bash
# Run an installed MedUI (Docker, on Ubuntu or in WSL2): a menu, or one command at a time.
#
#   ./medui.sh                   the menu (needs a terminal; whiptail if present)
#   ./medui.sh <command> ...     one command, for IT, scripts and coding agents
#
# Commands:
#   status               containers, health, version and settings (no secrets)
#   start                start MedUI (database, OCR and HTTPS too, when installed)
#   stop [--all]         stop MedUI and HTTPS; --all also stops the database and OCR
#   restart              restart the app container
#   reload               recreate the app so it reads .env again (after any .env change)
#   bp                   set the Best Practice connection in .env, then reload and check it
#   bp-check             check the Best Practice login: reachable, and read-only?
#   bp-clear             remove the Best Practice connection (an install without BP)
#   features [KEY=on|off ...]   optional features (OCR, AI, messaging, PIT export), then reload
#   https [options]      HTTPS for workstations: runs ./install.sh --https [options]
#   backup               back up the database, .env, app data and HTTPS folder now
#   backups              list the backups
#   upgrade [options]    ./upgrade.sh --dry-run, then (after a yes) ./upgrade.sh [options]
#   logs [-f]            the app's last 200 log lines; -f follows them
#   admin                add a local administrator
#   password             set a new password for a local administrator
#   seeds                show seeded prompt and workflow updates, then apply them after a yes
#   ocr start|stop       LiteParse OCR
#   pit [test|status|off]   connect Best Practice's PIT folder (its incoming share) as /pit
#   installs             MedUI installations on this computer
#   use                  make this installation the running one (stops the others' app and HTTPS)
#   windows              WSL2: the commands that run on Windows (keep-alive task, firewall)
#   support              a summary for a problem report: versions and states, no data or secrets
#   demo [status|refresh [--dry-run]|password]   a demo installation's data (install.sh --demo)
#   remove               remove this installation: its containers, data and folder (asks first)
#
# Every command prints the command it runs, so what it does can be repeated by hand
# (docs/cheatsheet.md). Nothing here prints .env's secrets. See docs/operations.md.

if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -uo pipefail

APP_DIR="$(cd "${MEDUI_DIR:-$(dirname "${BASH_SOURCE[0]}")}" && pwd)"
cd "$APP_DIR" || exit 1

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
show() { printf '  \033[2m$ %s\033[0m\n' "$*"; "$@"; }          # print a command, then run it
confirm() {   # confirm "question" [default y|n]
  local def="${2:-n}" answer
  read -rp $'\n'"$1 $([ "$def" = y ] && echo '(Y/n)' || echo '(y/N)') " answer
  answer="${answer:-$def}"
  [[ "$answer" =~ ^[yY]$ ]]
}
env_get() { python3 scripts/env_edit.py get "$1" 2>/dev/null; }
env_has() { python3 scripts/env_edit.py has "$@" 2>/dev/null; }
version() { sed -n "s/^__version__ = '\(.*\)'/\1/p" app/version.py 2>/dev/null; }
is_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }

setup() {   # checks and settings every command needs
  [ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root."
  [ -f compose.yaml ] && [ -f install.sh ] && [ -f scripts/env_edit.py ] || die "Run this from the MedUI folder."
  [ -f .env ] || die "No .env here: MedUI isn't installed in this folder. Use ./install.sh first."
  command -v python3 >/dev/null || die "python3 is missing: sudo apt install python3"
  PROJECT="$(env_get COMPOSE_PROJECT_NAME)"; PROJECT="${PROJECT:-medui_os}"
  APP_PORT="$(env_get APP_PORT)"; APP_PORT="${APP_PORT:-5005}"
  HTTPS_MODE="$(env_get HTTPS_MODE)"
  DEMO=""; [ "$(env_get MEDUI_INSTANCE)" = demo ] && DEMO=1
  DOCKER=(docker)
  if ! docker info >/dev/null 2>&1; then
    sudo -n docker info >/dev/null 2>&1 || sudo docker info >/dev/null 2>&1 \
      || die "Docker is not running, or this account can't use it: sudo systemctl status docker"
    DOCKER=(sudo docker)
  fi
}
compose()   { show "${DOCKER[@]}" compose -p "$PROJECT" "$@"; }     # shown
compose_q() { "${DOCKER[@]}" compose -p "$PROJECT" "$@"; }          # quiet, for looking
has_container() { compose_q ps -a --services 2>/dev/null | grep -qx "$1"; }
running() { compose_q ps --status running --services 2>/dev/null | grep -qx "$1"; }
profiles() {   # the profiles this installation uses
  local p=(--profile app)
  has_container liteparse && p+=(--profile ocr)
  [ -n "$HTTPS_MODE" ] && p+=(--profile https)
  has_container bpsql && p+=(--profile demo)
  printf '%s\n' "${p[@]}"
}
health() {   # MedUI's /health, with a time limit: under WSL2's mirrored networking a closed
  # port can leave a connection waiting instead of refusing it.
  curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:$APP_PORT/health" 2>/dev/null
}
wait_health() {
  local _
  for _ in $(seq 1 30); do
    health >/dev/null && { ok "MedUI answers at http://127.0.0.1:$APP_PORT"; return 0; }
    sleep 2
  done
  warn "MedUI didn't answer on port $APP_PORT. See: ./medui.sh logs"
  return 1
}
app_python() {   # app_python <function name> <code> [tty]: python in the app container
  # (the running one, else a one-off). The code is shown by name, not printed in full.
  # FLASK_RUN_FROM_CLI: no startup BP check in this one-off process (ADR-139 skips it for commands).
  local where="$1" code="$2" t=(-T -e FLASK_RUN_FROM_CLI=1); [ "${3:-}" = tty ] && t=(-e FLASK_RUN_FROM_CLI=1)
  if running app; then
    printf '  \033[2m$ %s compose -p %s exec %s app python -c "…"   (the code: %s in medui.sh)\033[0m\n' "${DOCKER[*]}" "$PROJECT" "${t[*]}" "$where"
    compose_q exec "${t[@]}" app python -c "$code"
  else
    printf '  \033[2m$ %s compose -p %s --profile app run --rm %s app python -c "…"   (the code: %s in medui.sh)\033[0m\n' "${DOCKER[*]}" "$PROJECT" "${t[*]}" "$where"
    compose_q --profile app run --rm "${t[@]}" app python -c "$code"
  fi
}

# ---- commands ---------------------------------------------------------------------------------------------------

cmd_status() {
  say "MedUI $(version) — installation '$PROJECT' in $APP_DIR"
  ok "Code: $(git log -1 --format='%h %s' 2>/dev/null || echo 'not a git checkout') ($(git symbolic-ref -q --short HEAD 2>/dev/null || echo 'no branch'))"
  local s
  for s in db bpsql liteparse app caddy; do
    if running "$s"; then ok "$s: running"
    elif has_container "$s"; then warn "$s: stopped"
    fi
  done
  if ! running app; then warn "Health: not checked, the app is stopped (./medui.sh start)"
  elif health >/dev/null; then ok "Health: answers on http://127.0.0.1:$APP_PORT"
  else warn "Health: no answer on port $APP_PORT"; fi
  if [ -n "$DEMO" ]; then
    ok "Demo installation: reads MedUI's invented demo databases in its own SQL Server (bpsql), never BP. ./medui.sh demo"
  elif env_has BPSDB_URI || env_has BPSDB_HOST BPSDB_USER BPSDB_PASSWORD; then
    ok "Best Practice: set (server $(env_get BPSDB_HOST)). Check it with: ./medui.sh bp-check"
  else
    warn "Best Practice: not set (only the local administrator can log in). Set it with: ./medui.sh bp"
  fi
  if [ -n "$HTTPS_MODE" ]; then ok "HTTPS for workstations: on (port $(env_get HTTPS_PORT | sed 's/^$/443/'))"
  else ok "HTTPS for workstations: off (MedUI is reachable from this computer only)"; fi
  local f on=()
  [ "$(env_get OCR_ENABLED)" != false ] && on+=(OCR)       # on unless .env says off
  for f in AI_ENABLED MESSAGING_ENABLED PIT_EXPORT_ENABLED PATIENT_API_ENABLED; do
    [[ "$(env_get $f)" =~ ^(1|true|yes)$ ]] && on+=("${f%_ENABLED}")
  done
  ok "Optional features on: ${on[*]:-none}"
  if [ -z "$DEMO" ] && [[ " ${on[*]} " == *" PIT_EXPORT "* ]]; then
    pit_paths
    if pit_mounted; then ok "PIT folder: $(pit_fstab_share) mounted, shown to MedUI as /pit"
    else warn "PIT folder: no share mounted at $PIT_MNT (./medui.sh pit)"; fi
  fi
  ok "Practice timezone: $(env_get PRACTICE_TIMEZONE)"
  local last; last="$(ls -1d backups/*/ 2>/dev/null | tail -1)"
  if [ -n "$last" ]; then ok "Last backup: ${last%/}"; else warn "No backup yet: ./medui.sh backup"; fi
  is_wsl && ok "WSL2 instance '${WSL_DISTRO_NAME:-?}': the keep-alive task runs on Windows (./medui.sh windows)"
  return 0
}

cmd_start() {
  say "Start MedUI"
  local svcs=(db) p; mapfile -t p < <(profiles)
  has_container bpsql && svcs+=(bpsql)
  has_container liteparse && svcs+=(liteparse)
  svcs+=(app); [ -n "$HTTPS_MODE" ] && svcs+=(caddy)
  compose "${p[@]}" up -d --wait "${svcs[@]}" || die "Couldn't start. See: ./medui.sh logs"
  wait_health
}

cmd_stop() {
  say "Stop MedUI"
  local svcs=(app) p; mapfile -t p < <(profiles)
  [ -n "$HTTPS_MODE" ] && svcs+=(caddy)
  if [ "${1:-}" = --all ]; then has_container liteparse && svcs+=(liteparse); has_container bpsql && svcs+=(bpsql); svcs+=(db); fi
  compose "${p[@]}" stop "${svcs[@]}"
  ok "Stopped: ${svcs[*]}. It stays stopped after a restart of the computer until: ./medui.sh start"
  is_wsl && ok "The WSL2 instance itself keeps running (the keep-alive task); that's fine."
  return 0
}

cmd_restart() { say "Restart the app"; compose --profile app restart app; wait_health; }

cmd_reload() {
  say "Recreate the app so it reads .env again"
  compose --profile app up -d --force-recreate --wait app || die "Couldn't start. See: ./medui.sh logs"
  wait_health
}

not_on_demo() {   # a demo installation reads only its own demo SQL Server
  [ -z "$DEMO" ] && return 0
  die "This is a demo installation: it reads only its own demo SQL Server, never Best Practice.
Its database holds the demo's patient and user numbers, which would attach to whichever real
patients have the same ones. For Best Practice, install MedUI in a folder of its own (without --demo)."
}

cmd_bp() {
  not_on_demo
  say "Best Practice connection"
  cat <<'EOF'
  MedUI reads Best Practice's SQL Server with a READ-ONLY login: the one BP supplies for
  database access. For every function it needs read access to BPSPatients,
  BPSDocumentsInbox and the BPSDocuments databases (letters and scanned documents).
  Afterwards, Application Setup -> Database checks every database this login can open
  and confirms it can't change any of them.
  A test, demo or training installation belongs on a server with test data only, never
  the practice's live server: MedUI's demo databases (invented patients, for SQL Server
  2022: github.com/medui-au/medui_demodata), or BP's sample databases.
EOF
  [ -t 0 ] || die "This asks questions: run it in a terminal."
  local host db user pass trust cur_trust
  read -rp $'\n'"  Server (name or address; a named instance as SERVER\\INSTANCE, one backslash) [$(env_get BPSDB_HOST)]: " host
  host="${host:-$(env_get BPSDB_HOST)}"
  [ -n "$host" ] || die "No server given. Nothing was changed."
  read -rp "  Database [$(env_get BPSDB_DATABASE | sed 's/^$/BPSPatients/')]: " db
  db="${db:-$(env_get BPSDB_DATABASE)}"; db="${db:-BPSPatients}"
  read -rp "  Login [$(env_get BPSDB_USER)]: " user
  user="${user:-$(env_get BPSDB_USER)}"
  [ -n "$user" ] || die "No login given. Nothing was changed."
  read -rsp "  Password$(env_has BPSDB_PASSWORD && echo ' (Enter keeps the current one)'): " pass; echo
  if [ -z "$pass" ]; then
    env_has BPSDB_PASSWORD || die "No password given. Nothing was changed."
    pass="$(env_get BPSDB_PASSWORD)"
  fi
  cur_trust="$(env_get BPSDB_TRUST_SERVER_CERTIFICATE)"
  echo "  Many BP servers use a self-signed certificate. Trusting it is usual for a server on the"
  echo "  practice network; otherwise its CA certificate must be installed on this computer."
  if confirm "  Trust the server's certificate?" "$([[ "$cur_trust" =~ ^(1|true|yes)$ ]] && echo y || echo n)"; then trust=true; else trust=false; fi
  MEDUI_SET_BPSDB_HOST="$host" MEDUI_SET_BPSDB_DATABASE="$db" MEDUI_SET_BPSDB_USER="$user" \
  MEDUI_SET_BPSDB_PASSWORD="$pass" MEDUI_SET_BPSDB_TRUST_SERVER_CERTIFICATE="$trust" \
    python3 scripts/env_edit.py set BPSDB_HOST BPSDB_DATABASE BPSDB_USER BPSDB_PASSWORD BPSDB_TRUST_SERVER_CERTIFICATE \
    || die "Nothing was changed."
  ok "Saved in .env (mode 600; the previous file is .env.bak)"
  if confirm "Recreate MedUI now so it uses this, then check the login?" y; then
    cmd_reload && cmd_bp_check
  else
    ok "Later: ./medui.sh reload, then ./medui.sh bp-check"
  fi
}

cmd_bp_check() {
  say "Check the Best Practice login"
  app_python cmd_bp_check "
from wsgi import app
from app.services import bp_login_service as b
with app.app_context():
    r = b.check(force=True)
    print('  ' + ('OK: ' if r.status == b.READ_ONLY else 'NOT READ-ONLY: ' if r.status == b.CAN_WRITE else 'NOT CHECKED: ') + r.summary())
    raise SystemExit(0 if r.status == b.READ_ONLY else 1 if r.status == b.CAN_WRITE else 3)
" 2>/dev/null
  local rc=$?
  case $rc in
    0) ;;
    1) warn "This login can change Best Practice data. Ask BP for the read-only login for database access;"
       warn "until then MedUI won't run Query Manager SQL. Details: Application Setup → Database." ;;
    *) warn "MedUI couldn't reach Best Practice with these settings. Check the server name (SERVER\\INSTANCE),"
       warn "the login and password, and the certificate setting (./medui.sh bp), then the server's firewall."
       warn "Testing outside MedUI: docs/cheatsheet.md (Best Practice connection, sqlcmd)." ;;
  esac
  return $rc
}

cmd_bp_clear() {
  not_on_demo
  say "Remove the Best Practice connection"
  echo "  Without it only the local administrator can log in, and the patient screens are empty."
  confirm "Remove the BPSDB_ settings from .env?" || { ok "Nothing was changed."; return 0; }
  MEDUI_SET_BPSDB_HOST= MEDUI_SET_BPSDB_USER= MEDUI_SET_BPSDB_PASSWORD= \
    python3 scripts/env_edit.py set BPSDB_HOST BPSDB_USER BPSDB_PASSWORD || die "Nothing was changed."
  ok "Removed (the previous file is .env.bak)"
  cmd_reload
}

FEATURES=(OCR_ENABLED AI_ENABLED MESSAGING_ENABLED PIT_EXPORT_ENABLED)
FEATURE_TEXT=("OCR: text from scanned documents (LiteParse, on this computer)"
              "AI: assistant, scribe, chatbots, workflows (choose models in Setup)"
              "Messaging: email and SMS to patients (set up in Setup)"
              "PIT file export")
cmd_features() {
  say "Optional features"
  local i k v changes=()
  if [ $# -gt 0 ]; then
    for a in "$@"; do
      k="${a%%=*}"; v="${a#*=}"
      [[ " ${FEATURES[*]} " == *" $k "* ]] || die "$k isn't one of: ${FEATURES[*]}"
      case "$v" in on|true|yes|1) v=true ;; off|false|no|0) v=false ;; *) die "$a: use on or off" ;; esac
      changes+=("$k=$v")
    done
  else
    [ -t 0 ] || die "Say which: ./medui.sh features AI_ENABLED=on"
    for i in "${!FEATURES[@]}"; do
      k="${FEATURES[$i]}"
      local cur=n; [[ "$(env_get $k)" =~ ^(1|true|yes)$ ]] && cur=y
      [ "$k" = OCR_ENABLED ] && [ -z "$(env_get $k)" ] && cur=y      # on unless .env says off
      if confirm "  ${FEATURE_TEXT[$i]}: on?" "$cur"; then v=true; else v=false; fi
      [ "$v" = true ] && [ "$cur" = y ] && continue
      [ "$v" = false ] && [ "$cur" = n ] && continue
      changes+=("$k=$v")
    done
  fi
  [ ${#changes[@]} -gt 0 ] || { ok "No change."; return 0; }
  local envs=() keys=()
  for c in "${changes[@]}"; do envs+=("MEDUI_SET_${c}"); keys+=("${c%%=*}"); done
  env "${envs[@]}" python3 scripts/env_edit.py set "${keys[@]}" || die "Nothing was changed."
  ok "Saved: ${changes[*]}"
  # OCR's container follows the switch: removed when off (its image is kept), so start, stop
  # and upgrades leave it alone; built if needed and started when on.
  for c in "${changes[@]}"; do
    case "$c" in
      OCR_ENABLED=false) has_container liteparse && compose --profile ocr rm -sf liteparse ;;
      OCR_ENABLED=true)
        has_container liteparse || warn "The first OCR build downloads and compiles LiteParse: allow several minutes."
        compose --profile ocr up -d --build --wait liteparse || warn "OCR didn't start: ./medui.sh logs, and docs/ocr.md" ;;
    esac
  done
  cmd_reload
}

cmd_https() {
  say "HTTPS for workstations"
  echo "  Caddy on port 443 in front of MedUI, so workstations reach it by name over HTTPS"
  echo "  (also needed for the scribe's microphone). docs/https.md explains it for the practice's IT."
  echo "  MedUI's own port $APP_PORT stays on this computer only: it is plain HTTP."
  show ./install.sh --https "$@" || return 1
  if is_wsl; then
    warn "WSL2: Windows must let workstations in too. On Windows, in PowerShell run as administrator:"
    echo "      powershell.exe -ExecutionPolicy Bypass -File .\\open_medui_https_port.ps1 -Instance ${WSL_DISTRO_NAME:-medui}"
    echo "    (the script is in this folder's scripts/windows; see scripts/windows/README.md)"
  else
    ok "If this computer has a firewall (ufw), allow 443 and 80 from the practice network only."
  fi
}

cmd_backup() {
  local dir; dir="backups/$(date +%Y-%m-%d-%H%M)-$(version)-manual"
  say "Backup to $dir"
  running db || die "The database isn't running: ./medui.sh start"
  local free; free=$(( $(df -Pk "$APP_DIR" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
  [ "$free" -ge 1 ] || die "Less than 1 GB free here."
  mkdir -p "$dir" && chmod 700 backups "$dir"
  (umask 077; compose_q exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$dir/medui.dump") \
    || die "The database dump failed."
  local tables; tables="$(compose_q exec -T db pg_restore --list < "$dir/medui.dump" | grep -c ' TABLE ' || true)"
  [ "${tables:-0}" -gt 0 ] || die "The dump in $dir couldn't be read back."
  ok "Database: medui.dump ($(du -h "$dir/medui.dump" | cut -f1), $tables tables, read back)"
  install -m 600 .env "$dir/env"
  ok "Settings: env (a copy of .env, mode 600; it holds the encryption key)"
  "${DOCKER[@]}" run --rm -v "${PROJECT}_app_data:/data:ro" -v "$APP_DIR/$dir:/backup" postgres:17-bookworm \
    sh -c "tar -C /data -czf /backup/app_data.tgz . && chown $(id -u):$(id -g) /backup/app_data.tgz && chmod 600 /backup/app_data.tgz" \
    && ok "App data: app_data.tgz"
  if [ -d https ]; then (umask 077; tar -czf "$dir/https.tgz" https) && ok "HTTPS: https.tgz (keep it private)"; fi
  git rev-parse HEAD > "$dir/commit" 2>/dev/null
  warn "The backup is on this computer only. Copy it somewhere else as well (docs/operations.md)."
}

cmd_backups() {
  say "Backups in $APP_DIR/backups"
  local d n=0
  for d in backups/*/; do
    [ -d "$d" ] || continue
    n=$((n + 1)); printf '  %s  %s\n' "$(du -sh "$d" | cut -f1)" "${d%/}"
  done
  [ $n -gt 0 ] || warn "None yet: ./medui.sh backup"
  echo "  Restoring one is in docs/operations.md (Restore rehearsal)."
}

cmd_upgrade() {
  say "Upgrade"
  show ./upgrade.sh --dry-run "$@" || return 1
  confirm "Go ahead with the upgrade above? (it backs up first)" || { ok "Nothing was changed."; return 0; }
  show ./upgrade.sh --yes "$@"
}

cmd_logs() {
  if [ "${1:-}" = -f ]; then compose --profile app logs -f --tail 50 app
  else compose --profile app logs --tail 200 app; fi
  echo "  Logs can hold details of patients' records: describe a problem by its shape, don't paste logs (AGENTS.md)."
}

cmd_admin() {
  say "Add a local administrator"
  echo "  A username (not a number) and a password of at least 12 characters."
  compose --profile app run --rm app flask --app wsgi install admin   # asks for a username and password
}

cmd_password() {
  say "New password for a local administrator"
  [ -t 0 ] || die "This asks questions: run it in a terminal."
  app_python cmd_password "
import getpass
from wsgi import app
from app.extensions import db
from app.models.user import User
with app.app_context():
    admins = User.query.filter_by(is_local_admin=True, is_active=True).order_by(User.username).all()
    if not admins:
        raise SystemExit('No local administrator. Add one with: ./medui.sh admin')
    print('  Local administrators: ' + ', '.join(u.username for u in admins))
    name = input('  Username: ').strip()
    user = next((u for u in admins if u.username == name), None)
    if not user:
        raise SystemExit('Not a local administrator. Nothing was changed.')
    pw = getpass.getpass('  New password (at least 12 characters): ')
    if len(pw) < 12:
        raise SystemExit('Too short. Nothing was changed.')
    if getpass.getpass('  Again: ') != pw:
        raise SystemExit('The passwords differ. Nothing was changed.')
    user.set_password(pw)
    db.session.commit()
    print('  Password changed.')
" tty
}

cmd_seeds() {
  say "Seeded prompts and workflows"
  compose --profile app run --rm -T app flask --app wsgi install resync-seeds --dry-run || return 1
  confirm "Apply the updates listed above? (ones the practice edited are kept)" || { ok "Nothing was changed."; return 0; }
  compose --profile app run --rm -T app flask --app wsgi install resync-seeds
}

cmd_ocr() {
  case "${1:-}" in
    start) compose --profile ocr up -d --wait liteparse ;;
    stop)  compose --profile ocr stop liteparse ;;
    *) die "Use: ./medui.sh ocr start  or  ./medui.sh ocr stop" ;;
  esac
}

# ---- the PIT folder: Best Practice's incoming share, mounted here and shown to the app as /pit ----
# The app runs in a container that sees none of this computer's folders, so the share is mounted
# here (CIFS, in /etc/fstab so it comes back after a restart) and passed in by compose.yaml
# (PIT_HOST_DIR -> /pit). The folder under the mount is root's: if the share isn't mounted, the app
# can't write there, so sending to BP fails visibly instead of filling a local folder.
PIT_UID=10001   # the app container's user (Dockerfile)
pit_paths() {
  PIT_MNT="${MEDUI_TEST_MNT:-/mnt}/${PROJECT}_pit"
  PIT_CRED="${MEDUI_TEST_ETC:-/etc/medui}/${PROJECT}_pit.credentials"
  PIT_FSTAB="${MEDUI_TEST_FSTAB:-/etc/fstab}"
}
pit_mounted() { mountpoint -q "$PIT_MNT" 2>/dev/null; }
pit_fstab_share() { awk -v m="$PIT_MNT" '$2 == m && $3 == "cifs" { gsub(/\\040/, " ", $1); print $1; exit }' "$PIT_FSTAB" 2>/dev/null; }

cmd_pit() {
  [ -z "$DEMO" ] || die "A demo installation never sends to Best Practice: its PIT files carry the demo's
patient numbers, which would attach to whichever real patients have the same ones."
  pit_paths
  case "${1:-}" in
    "") ;;
    test)   pit_test; return ;;
    status) pit_status; return ;;
    off)    pit_off; return ;;
    *) die "Use: ./medui.sh pit (connect the share), pit test, pit status or pit off" ;;
  esac
  say "Connect Best Practice's PIT folder"
  cat <<EOF
  Best Practice imports reports from a shared folder on the practice network (BP's own
  settings name it, often something like \\\\SERVER\\BPS\\Incoming). This connects that share to
  this computer at $PIT_MNT and shows it to MedUI as /pit. You need:
   - the share's path;
   - a Windows (or domain) account that can write to it. Its password is kept in
     $PIT_CRED, readable by root only.
  It uses sudo, and installs cifs-utils if it is missing.
EOF
  [ -t 0 ] || die "This asks questions: run it in a terminal."
  local share cur user dom="" pass
  cur="$(pit_fstab_share)"
  read -rp $'\n'"  Share (\\\\SERVER\\share\\folder or //SERVER/share/folder)${cur:+ [$cur]}: " share
  share="${share:-$cur}"; share="${share//\\//}"; share="${share%/}"
  [[ "$share" =~ ^//[^/]+/[^/]+ ]] || die "That isn't a share path like //SERVER/share. Nothing was changed."
  read -rp "  Windows account (user, or DOMAIN\\user): " user
  [ -n "$user" ] || die "No account given. Nothing was changed."
  if [[ "$user" == *\\* ]]; then dom="${user%%\\*}"; user="${user#*\\}"; fi
  read -rsp "  Its password: " pass; echo
  [ -n "$pass" ] || die "No password given. Nothing was changed."

  command -v mount.cifs >/dev/null || show sudo apt-get install -y cifs-utils || die "Couldn't install cifs-utils. Nothing else was changed."
  show sudo mkdir -p "$PIT_MNT" "$(dirname "$PIT_CRED")" || die "Couldn't make $PIT_MNT."
  pit_mounted && { show sudo umount "$PIT_MNT" || die "$PIT_MNT is in use and won't unmount. Nothing else was changed."; }
  show sudo chown root:root "$PIT_MNT" && show sudo chmod 755 "$PIT_MNT"
  # Written with umask 077, so the file is root's alone from its first byte; the password goes
  # through a pipe, never a command line.
  printf '  \033[2m$ sudo sh -c "umask 077; cat > %s"   (the account and password, shown nowhere else)\033[0m\n' "$PIT_CRED"
  {
    printf 'username=%s\npassword=%s\n' "$user" "$pass"
    if [ -n "$dom" ]; then printf 'domain=%s\n' "$dom"; fi
  } | sudo sh -c 'umask 077 && cat > "$1"' sh "$PIT_CRED" || die "Couldn't write $PIT_CRED."
  pass=""
  show sudo chmod 600 "$PIT_CRED" && show sudo chown root:root "$PIT_CRED"
  local opts="credentials=$PIT_CRED,uid=$PIT_UID,forceuid,gid=$(id -g),forcegid,dir_mode=0775,file_mode=0664,iocharset=utf8"
  if ! show sudo mount -t cifs "$share" "$PIT_MNT" -o "$opts"; then
    warn "The share didn't mount. Check its path, the account and its password, and that this"
    warn "computer can reach the server (port 445). Messages from the mount above say more."
    die "Nothing else was changed. Try again: ./medui.sh pit"
  fi
  ok "Mounted $share at $PIT_MNT"

  # In /etc/fstab, so it is mounted again after a restart, before Docker starts the app.
  show sudo sed -i "\\# $PIT_MNT cifs #d" "$PIT_FSTAB"
  printf '%s %s cifs %s,_netdev,nofail,x-systemd.before=docker.service,x-systemd.mount-timeout=30 0 0\n' \
    "${share// /\\040}" "$PIT_MNT" "$opts" | show sudo tee -a "$PIT_FSTAB" >/dev/null || die "Couldn't add the share to $PIT_FSTAB."
  command -v systemctl >/dev/null && sudo systemctl daemon-reload 2>/dev/null
  ok "Added to $PIT_FSTAB: mounted again after a restart"

  MEDUI_SET_PIT_HOST_DIR="$PIT_MNT" python3 scripts/env_edit.py set PIT_HOST_DIR >/dev/null || die "Couldn't save PIT_HOST_DIR in .env."
  local changes=(PIT_HOST_DIR)
  if [[ ! "$(env_get PIT_EXPORT_ENABLED)" =~ ^(1|true|yes)$ ]] && confirm "PIT export is off. Turn it on?" y; then
    MEDUI_SET_PIT_EXPORT_ENABLED=true python3 scripts/env_edit.py set PIT_EXPORT_ENABLED >/dev/null && changes+=(PIT_EXPORT_ENABLED=true)
  fi
  ok "Saved in .env: ${changes[*]}"
  cmd_reload || return 1
  app_python cmd_pit "
from wsgi import app
from app.models.system_setting import SystemSetting
with app.app_context():
    if SystemSetting.get('pit_export_path', '') != '/pit':
        SystemSetting.set('pit_export_path', '/pit')
        print('  Setup → Messaging → PIT Export Folder set to /pit')
"
  pit_test
}

pit_test() {
  say "Can MedUI write to the PIT folder?"
  app_python pit_test "
import os
from wsgi import app
from app.models.system_setting import SystemSetting
from app.utils.pit_utils import folder_problem
with app.app_context():
    folder = SystemSetting.get('pit_export_path', '') or '/pit'
problem = folder_problem(folder)
if problem:
    print('  NO: ' + problem); raise SystemExit(1)
probe = os.path.join(folder, '.medui_write_test_%d' % os.getpid())
with open(probe, 'w') as fh:
    fh.write('MedUI write test, deleted straight away\n')
os.remove(probe)
print('  YES: a test file was written to ' + folder + ' and deleted again')
"
}

pit_status() {
  say "PIT folder"
  local share; share="$(pit_fstab_share)"
  if [ -n "$share" ]; then ok "Share: $share, in $PIT_FSTAB"; else warn "No share connected (./medui.sh pit)"; fi
  if pit_mounted; then ok "Mounted at $PIT_MNT"; else warn "Not mounted at $PIT_MNT"; fi
  local host; host="$(env_get PIT_HOST_DIR)"
  if [ "$host" = "$PIT_MNT" ]; then ok "Shown to MedUI as /pit (PIT_HOST_DIR)"; else warn "PIT_HOST_DIR is ${host:-not set}: MedUI's /pit isn't the share"; fi
  [[ "$(env_get PIT_EXPORT_ENABLED)" =~ ^(1|true|yes)$ ]] && ok "PIT export: on" || warn "PIT export: off (./medui.sh features PIT_EXPORT_ENABLED=on)"
  running app && pit_test
  return 0
}

pit_off() {
  say "Disconnect the PIT folder"
  confirm "Unmount the share, remove it from $PIT_FSTAB and delete its saved password?" || { ok "Nothing was changed."; return 0; }
  pit_mounted && show sudo umount "$PIT_MNT"
  show sudo sed -i "\\# $PIT_MNT cifs #d" "$PIT_FSTAB"
  show sudo rm -f "$PIT_CRED"
  local envs=(MEDUI_SET_PIT_HOST_DIR=) keys=(PIT_HOST_DIR)
  if confirm "Turn PIT export off too?" y; then envs+=(MEDUI_SET_PIT_EXPORT_ENABLED=false); keys+=(PIT_EXPORT_ENABLED); fi
  env "${envs[@]}" python3 scripts/env_edit.py set "${keys[@]}" >/dev/null
  ok "Disconnected. Sending to BP now fails with a clear reason until a folder is connected again."
  cmd_reload
}

medui_installs() {   # name<TAB>folder<TAB>status, for each MedUI installation Docker knows
  "${DOCKER[@]}" compose ls --all --format json 2>/dev/null | python3 -c '
import json, os, sys
for p in json.load(sys.stdin) or []:
    folder = os.path.dirname((p.get("ConfigFiles") or "").split(",")[0])
    if os.path.exists(os.path.join(folder, "app", "version.py")) and os.path.exists(os.path.join(folder, "install.sh")):
        print(p["Name"], folder, p.get("Status", ""), sep="\t")
'
}

cmd_installs() {
  say "MedUI installations on this computer"
  local name folder status
  while IFS=$'\t' read -r name folder status; do
    printf '  %s %-16s %-28s %s\n' "$([ "$name" = "$PROJECT" ] && echo '*' || echo ' ')" "$name" "$status" "$folder"
  done < <(medui_installs)
  echo "  * this one. Each installation has its own database: keep a sample-data install apart from"
  echo "  the practice's, and switch with './medui.sh use' in the one you want running."
}

cmd_use() {
  say "Make '$PROJECT' the running installation"
  local name folder status
  while IFS=$'\t' read -r name folder status; do
    [ "$name" = "$PROJECT" ] && continue
    case "$status" in *running*)
      local also=()   # a demo's SQL Server too: it holds up to 2 GB of memory
      "${DOCKER[@]}" ps -q --filter "label=com.docker.compose.project=$name" \
        --filter label=com.docker.compose.service=bpsql | grep -q . && also=(--profile demo bpsql)
      show "${DOCKER[@]}" compose -p "$name" --project-directory "$folder" -f "$folder/compose.yaml" \
        --profile app --profile https stop app caddy "${also[@]}" ;;
    esac
  done < <(medui_installs)
  cmd_start
}

cmd_demo() {
  [ -n "$DEMO" ] || die "This isn't a demo installation. A demo goes in a folder of its own: ./install.sh --demo (docs/setup-guide.md)."
  case "${1:-status}" in
    status)   say "Demo data"; scripts/demo_data.sh status ;;
    refresh)  shift; say "Bring the demo dates up to today"; show scripts/demo_data.sh refresh "$@" ;;
    password) say "The demo users' password"
              show scripts/demo_data.sh password || return 1
              MEDUI_SET_DEMO_PASSWORD_SET=true python3 scripts/env_edit.py set DEMO_PASSWORD_SET >/dev/null ;;
    *) die "demo status | refresh [--dry-run] | password" ;;
  esac
}

cmd_remove() {
  # Everything about this installation, and nothing else: its containers, volumes, images and
  # network (by its project name, from its own .env), then its folder. The folder goes last, by
  # exec, so nothing is left that needs to read this script once its file has gone.
  say "Remove the installation '$PROJECT'"
  [ -t 0 ] || die "Removing asks you to type the installation's name: run it in a terminal."
  local others=() name folder status
  while IFS=$'\t' read -r name folder status; do
    if [ "$name" = "$PROJECT" ] && [ "$(realpath -m "$folder")" != "$(realpath -m "$APP_DIR")" ]; then
      die "Docker says '$PROJECT' runs from $folder, not from here. Nothing was changed."
    fi
    [ "$name" != "$PROJECT" ] && others+=("$name ($folder)")
  done < <(medui_installs)
  case "$APP_DIR" in "" | / | "$HOME" | "$HOME/") die "Refusing to remove $APP_DIR. Nothing was changed." ;; esac
  [ -f "$APP_DIR/compose.yaml" ] && [ -f "$APP_DIR/medui.sh" ] || die "$APP_DIR doesn't look like a MedUI folder. Nothing was changed."

  local kind=live bp
  [ -n "$DEMO" ] && kind="demo (invented data)"
  bp="$(env_get BPSDB_HOST)"
  echo "  Installation: $PROJECT, MedUI $(version), $kind"
  echo "  Folder:       $APP_DIR"
  echo "  Port:         $APP_PORT$([ -n "$HTTPS_MODE" ] && echo ", HTTPS on $(env_get HTTPS_PORT | sed 's/^$/443/')")"
  [ -z "$DEMO" ] && echo "  Best Practice: ${bp:-not set}"
  echo "  Other MedUI installations here: ${others[*]:-none} (not touched)"
  echo
  echo "  This deletes for good: MedUI's database (users, settings, prompts, history), its stored"
  echo "  files, .env with its encryption key, the folder and everything in it, backups/ included."
  [ -z "$DEMO" ] && [ -n "$bp" ] && warn "This installation reads Best Practice: it may be the practice's own MedUI."

  # A backup first, kept outside the folder that is about to go.
  local keep="$HOME/medui_removed/$PROJECT-$(date +%Y-%m-%d-%H%M%S)" saved=""
  local nb; nb="$(find backups -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
  if confirm "Back up the database and settings first, into $keep?" "$([ -n "$DEMO" ] && echo n || echo y)"; then
    running db || compose up -d --wait db || die "The database wouldn't start, so no backup. Nothing was removed."
    ( cmd_backup ) </dev/null || die "The backup failed. Nothing was removed."   # its docker exec mustn't read the keyboard
    saved=1
  fi
  if [ -n "$saved" ] || { [ "$nb" -gt 0 ] && confirm "Keep the $nb backup(s) in backups/, in $keep?" y; }; then
    mkdir -p "$keep" && chmod 700 "$HOME/medui_removed" "$keep"
    mv backups "$keep/" || die "Couldn't move the backups to $keep. Nothing was removed."
    ok "Backups kept in $keep/backups (they hold .env copies with the encryption key: keep them private)"
  fi

  read -rp $'\n'"  Type the installation's name ($PROJECT) to remove it, or press Enter to keep it: " name
  [ "$name" = "$PROJECT" ] || { ok "Nothing was removed."; return 0; }

  local had_https="$HTTPS_MODE" root=""
  [ "$HTTPS_MODE" = ca ] && root=1
  compose --profile app --profile ocr --profile https --profile demo down -v --rmi local \
    || die "Docker couldn't remove everything (above). The folder is kept: run ./medui.sh remove again."
  local left
  left="$("${DOCKER[@]}" ps -aq --filter "label=com.docker.compose.project=$PROJECT"; "${DOCKER[@]}" volume ls -q --filter "label=com.docker.compose.project=$PROJECT")"
  [ -z "$left" ] || die "Some of '$PROJECT' is still in Docker: docker ps -a / docker volume ls. The folder is kept."
  ok "Containers, database, stored files, images and network of '$PROJECT' removed"
  pit_paths
  if [ -z "$DEMO" ] && { [ -n "$(pit_fstab_share)" ] || [ -e "$PIT_CRED" ] || pit_mounted; }; then
    say "Its PIT share"
    pit_mounted && show sudo umount "$PIT_MNT"
    show sudo sed -i "\\# $PIT_MNT cifs #d" "$PIT_FSTAB"
    show sudo rm -f "$PIT_CRED"
    show sudo rmdir "$PIT_MNT" 2>/dev/null
    ok "Disconnected: unmounted, out of $PIT_FSTAB, its saved password deleted"
  fi

  say "Last: the folder $APP_DIR"
  [ -n "$root" ] && echo "  Workstations that trusted this installation's MedUI root still list it (docs/operations.md)."
  if is_wsl; then
    local inst="${WSL_DISTRO_NAME:-<instance>}"
    if [ -n "$had_https" ]; then
      echo "  On Windows, close the HTTPS ports it had (PowerShell as administrator; only if no other"
      echo "  installation in this instance has HTTPS now):"
      echo "    Get-NetFirewallRule -DisplayName 'WSL2 $inst MedUI HTTPS', 'WSL2 $inst MedUI setup page (HTTP)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    fi
    if [ ${#others[@]} -eq 0 ]; then
      echo "  No other MedUI is in this instance. To remove the whole instance too, in PowerShell on Windows:"
      echo "    Stop-ScheduledTask -TaskName 'WSL2 $inst keep-alive'; Unregister-ScheduledTask -TaskName 'WSL2 $inst keep-alive' -Confirm:\$false"
      echo "    wsl --unregister $inst"
      echo "    Get-NetFirewallRule -DisplayName 'WSL2 $inst *' | Remove-NetFirewallRule    # as administrator: its SSH and HTTPS rules"
    fi
  fi
  echo "  Your shell may still be in the removed folder afterwards: cd ~"
  echo "  If rm reports 'Permission denied' for a file, remove what is left with: sudo rm -rf $APP_DIR"
  cd "$HOME" || cd /
  exec rm -rf -- "$APP_DIR"
}

cmd_windows() {
  local inst="${WSL_DISTRO_NAME:-medui}"
  say "Windows side (WSL2 instance '$inst')"
  is_wsl || warn "This computer isn't WSL2: nothing here applies."
  cat <<EOF
  These run in PowerShell on Windows. The instance can't start Windows programs itself.

  Keep-alive task (keeps the instance, and so MedUI, running):
    Stop-ScheduledTask  -TaskName "WSL2 $inst keep-alive"     # end it first, to stop the instance
    wsl --terminate $inst                                     # then stop the instance
    Start-ScheduledTask -TaskName "WSL2 $inst keep-alive"     # start it again
    Get-ScheduledTask   -TaskName "WSL2 $inst keep-alive"     # is it running?

  Let workstations reach HTTPS (PowerShell run as administrator, after ./medui.sh https):
    powershell.exe -ExecutionPolicy Bypass -File .\\open_medui_https_port.ps1 -Instance $inst

  Upgrade from Windows (snapshot first):  .\\upgrade_medui_wsl2.ps1 -Instance $inst
  The scripts are in scripts/windows (README.md there).
EOF
}

cmd_support() {
  say "Summary for a problem report (no patient data, no secrets)"
  echo "  MedUI:   $(version), $(git log -1 --format='%h' 2>/dev/null) on $(git symbolic-ref -q --short HEAD 2>/dev/null || echo 'no branch')$([ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ] && echo ', LOCAL CHANGES')"
  echo "  OS:      $(. /etc/os-release; echo "$PRETTY_NAME")$(is_wsl && echo ', WSL2')"
  echo "  Docker:  $("${DOCKER[@]}" version --format '{{.Server.Version}}' 2>/dev/null), compose $("${DOCKER[@]}" compose version --short 2>/dev/null)"
  local s
  for s in db bpsql liteparse app caddy; do
    has_container "$s" && echo "  $s: $(compose_q ps -a --format '{{.State}} {{.Status}}' "$s" 2>/dev/null | head -1)"
  done
  echo "  Health:  $(health || echo 'no answer')"
  echo "  Demo installation: ${DEMO:+yes}${DEMO:-no}"
  echo "  BP set:  $(env_has BPSDB_URI || env_has BPSDB_HOST BPSDB_USER BPSDB_PASSWORD && echo yes || echo no);  HTTPS: ${HTTPS_MODE:-off}"
  echo "  Features: AI=$(env_get AI_ENABLED) MESSAGING=$(env_get MESSAGING_ENABLED) PIT=$(env_get PIT_EXPORT_ENABLED)"
  pit_paths; echo "  PIT share: $( [ -n "$(pit_fstab_share)" ] && echo 'in fstab' || echo 'none'), $(pit_mounted && echo mounted || echo 'not mounted'), PIT_HOST_DIR $( [ "$(env_get PIT_HOST_DIR)" = "$PIT_MNT" ] && echo 'matches' || echo 'differs')"
  echo "  Add: the step, what was expected, what happened (AGENTS.md: reporting a problem)."
}

# ---- menu -------------------------------------------------------------------------------------------------------

MENU=(
  status   "Status: containers, health, settings"
  start    "Start MedUI"
  stop     "Stop MedUI"
  reload   "Restart after a .env change (recreate the app)"
  bp       "Best Practice connection: set it, then check"
  bp-check "Best Practice: check the login is read-only"
  bp-clear "Best Practice: remove the connection"
  features "Optional features: AI, messaging, PIT export"
  https    "Open MedUI to workstations (HTTPS)"
  backup   "Back up now"
  backups  "List backups"
  upgrade  "Upgrade (shows what changes first)"
  logs     "App log: last 200 lines"
  logs-f   "App log: follow (Ctrl+C to stop)"
  admin    "Add a local administrator"
  password "New password for a local administrator"
  seeds    "Seeded prompt and workflow updates"
  ocr      "OCR: start or stop"
  pit      "PIT folder: connect Best Practice's incoming share"
  installs "Installations on this computer"
  use      "Make this installation the running one"
  windows  "WSL2: commands that run on Windows"
  support  "Summary for a problem report"
  remove   "Remove this installation (deletes its data; asks first)"
)

choose() {   # choose "title" tag text ...  -> prints the tag picked
  local title="$1"; shift
  if command -v whiptail >/dev/null; then
    whiptail --title "$title" --menu "" 24 76 16 "$@" 3>&1 1>&2 2>&3
  else
    local i n=0 tags=() pick
    echo "" >&2; echo "  $title" >&2
    while [ $# -gt 0 ]; do n=$((n + 1)); tags+=("$1"); printf '  %2d  %s\n' "$n" "$2" >&2; shift 2; done
    read -rp "  Number (Enter to leave): " pick
    [[ "$pick" =~ ^[0-9]+$ ]] && [ "$pick" -ge 1 ] && [ "$pick" -le $n ] || return 1
    echo "${tags[$((pick - 1))]}"
  fi
}

menu() {
  [ -t 0 ] && [ -t 1 ] || die "The menu needs a terminal. Commands: ./medui.sh help"
  local pick sub
  local items=("${MENU[@]}")
  [ -n "$DEMO" ] && items+=(demo "Demo data: dates, users' password")
  while pick="$(choose "MedUI $(version) — $PROJECT$([ -n "$DEMO" ] && echo ' (demo)')" "${items[@]}")"; do
    clear
    case "$pick" in
      logs-f) ( cmd_logs -f ) ;;
      ocr) sub="$(choose "OCR" start "Start OCR" stop "Stop OCR")" && ( cmd_ocr "$sub" ) ;;
      pit) sub="$(choose "PIT folder" connect "Connect the share (or change it)" status "What is connected" \
              test "Check MedUI can write to it" off "Disconnect it")" && { [ "$sub" = connect ] && sub=""; ( cmd_pit $sub ); } ;;
      remove) cmd_remove ;;   # not in a subshell: it ends this menu with the folder (exec)
      demo) sub="$(choose "Demo data" status "What is there" refresh "Bring the dates up to today" \
              password "Set the demo users' password")" && ( cmd_demo "$sub" ) ;;
      stop) if confirm "Stop the database (and OCR) as well?" n; then ( cmd_stop --all ); else ( cmd_stop ); fi ;;
      *) ( dispatch "$pick" ) ;;
    esac
    read -rp $'\n'"Press Enter to return to the menu " _
  done
  clear
}

dispatch() {
  local c="$1"; shift
  case "$c" in
    status) cmd_status ;; start) cmd_start ;; stop) cmd_stop "$@" ;; restart) cmd_restart ;;
    reload) cmd_reload ;; bp) cmd_bp ;; bp-check) cmd_bp_check ;; bp-clear) cmd_bp_clear ;;
    features) cmd_features "$@" ;; https) cmd_https "$@" ;; backup) cmd_backup ;; backups) cmd_backups ;;
    upgrade) cmd_upgrade "$@" ;; logs) cmd_logs "$@" ;; admin) cmd_admin ;; password) cmd_password ;;
    seeds) cmd_seeds ;; ocr) cmd_ocr "$@" ;; pit) cmd_pit "$@" ;; installs) cmd_installs ;; use) cmd_use ;;
    windows) cmd_windows ;; support) cmd_support ;; demo) cmd_demo "$@" ;; remove) cmd_remove ;;
    *) echo "Unknown command: $c (see ./medui.sh help)" >&2; return 2 ;;
  esac
}

case "${1:-}" in
  -h|--help|help) sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") setup; menu ;;
  *) setup; dispatch "$@" ;;
esac
