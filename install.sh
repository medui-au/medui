#!/usr/bin/env bash
# Install MedUI with Docker on Ubuntu (native or WSL2). Safe to run again.
#
#   ./install.sh                 system packages, configuration, database, OCR, app, administrator
#   ./install.sh --dry-run       show what would be done, change nothing
#
# Options:
#   --app-port N         port for MedUI on this computer (default 5005)
#   --db-port N          port for PostgreSQL on this computer (default 55432)
#   --ocr-port N         port for LiteParse OCR on this computer (default 5707)
#   --name NAME          Docker Compose project name; keeps installs apart. Default: the folder's
#                        name (~/medui_os -> medui_os); an installation keeps the one it has
#   --timezone ZONE      the practice's timezone: a city, state or zone (melbourne, vic, Australia/Melbourne).
#                        Default: asked, with this computer's offered (from Windows on WSL2); an
#                        installation keeps the one it has
#   --no-ocr             don't build or start LiteParse OCR
#   --no-apt             skip system packages (Docker, git, curl: install them yourself)
#   --no-admin           don't create the local administrator (run 'flask install admin' later)
#   --reference-data     also import the optional drug and vaccine reference snapshots
#   --demo               a demo installation: its own SQL Server (Express) with MedUI's invented
#                        demo databases (medui_demodata) instead of Best Practice. Needs a folder of
#                        its own, e.g. ~/medui_demo; never pointed at BP. Remembered afterwards
#   --accept-sql-licence with --demo: accept Microsoft's SQL Server licence terms without asking
#   --https              HTTPS for workstations through Caddy, with a MedUI root that may only
#                        vouch for the names below (docs/https.md)
#   --https-name NAME    a name workstations type (repeatable; default: this computer's name)
#   --https-ip IP        an address workstations type (repeatable; default: this computer's address)
#   --https-cert FILE    use the practice's own certificate (PEM, full chain) instead: no MedUI root
#   --https-key FILE     its private key (PEM)
#   --https-port N       HTTPS port on this computer (default 443)
#   --http-port N        port for the setup page workstations open first (default 80)
#   --https-new-root     replace the MedUI root (when the names change; workstations need the new one)
#   --yes                don't ask: no confirmation, and live unless --demo (otherwise a new one asks)
#   --dry-run            show what would be done, change nothing
#
# What it does, in order (each step is skipped when already done):
#   1. checks: Ubuntu, not root, run from the repository, systemd, the name not used by another
#      folder, free ports (a new installation moves to the next free one)
#   2. system packages from Ubuntu's own repositories: Docker Engine, Compose, Buildx, git, curl
#   3. .env with fresh secrets (scripts/init_env.py; an existing .env is never replaced)
#   4. PostgreSQL 17 and LiteParse OCR containers
#   5. the MedUI image, database schema, defaults, AI provider templates and starter seeds
#   6. a local administrator (prompts for username and password)
#   7. MedUI started and its health check answered
#   with --demo: SQL Server in step 4, and the demo databases restored after step 5
#   8. with --https (remembered afterwards): Caddy on port 443 for the practice network
#
# Nothing is enabled beyond that: BP, AI, messaging and other options stay off until you
# configure them in .env. All ports listen on 127.0.0.1 only, except HTTPS when you turn it
# on. See AGENTS.md and README.md.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PORT="" DB_PORT="" OCR_PORT="" PROJECT="" PRACTICE_TZ="" TZ_FROM=""
OCR=1 APT=1 ADMIN=1 REFERENCE=0 YES=0 DRY=0 DEMO=0 ACCEPT_SQL=0
HTTPS=0 HTTPS_NAMES=() HTTPS_IPS=() HTTPS_CERT="" HTTPS_KEY="" HTTPS_PORT="" HTTP_PORT="" NEW_ROOT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --app-port) APP_PORT="${2:?--app-port needs a number}"; shift ;;
    --db-port) DB_PORT="${2:?--db-port needs a number}"; shift ;;
    --ocr-port) OCR_PORT="${2:?--ocr-port needs a number}"; shift ;;
    --name) PROJECT="${2:?--name needs a name}"; shift ;;
    --timezone) PRACTICE_TZ="${2:?--timezone needs a city, state or zone, e.g. melbourne}"; TZ_FROM="--timezone"; shift ;;
    --no-ocr) OCR=0 ;;
    --no-apt) APT=0 ;;
    --no-admin) ADMIN=0 ;;
    --reference-data) REFERENCE=1 ;;
    --demo) DEMO=1 ;;
    --accept-sql-licence|--accept-sql-license) ACCEPT_SQL=1 ;;
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    --https) HTTPS=1 ;;
    --https-name) HTTPS_NAMES+=("${2:?--https-name needs a name}"); HTTPS=1; shift ;;
    --https-ip) HTTPS_IPS+=("${2:?--https-ip needs an address}"); HTTPS=1; shift ;;
    --https-cert) HTTPS_CERT="${2:?--https-cert needs a file}"; HTTPS=1; shift ;;
    --https-key) HTTPS_KEY="${2:?--https-key needs a file}"; HTTPS=1; shift ;;
    --https-port) HTTPS_PORT="${2:?--https-port needs a number}"; HTTPS=1; shift ;;
    --http-port) HTTP_PORT="${2:?--http-port needs a number}"; HTTPS=1; shift ;;
    --https-new-root) NEW_ROOT=1; HTTPS=1 ;;
    -h|--help) sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then echo "  [dry run] $*"; else "$@"; fi; }
port_ok() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1024 ] && [ "$1" -le 65535 ]; }
env_get() { [ -f "$APP_DIR/.env" ] && sed -n "s/^$1=//p" "$APP_DIR/.env" | tail -1 || true; }
env_set() {   # replace KEY=... in .env, or append it
  if [ "$DRY" = 1 ]; then echo "  [dry run] set $1 in .env"; return; fi
  if grep -q "^$1=" "$APP_DIR/.env"; then sed -i "s|^$1=.*|$1=$2|" "$APP_DIR/.env"; else echo "$1=$2" >> "$APP_DIR/.env"; fi
}

cd "$APP_DIR"

# ---- 1. checks ----------------------------------------------------------------------------------------------------
say "1. Checks"
[ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root. It uses sudo only where needed."
[ -f compose.yaml ] && [ -f scripts/init_env.py ] || die "Run this from the MedUI repository folder."
. /etc/os-release
if [ "${ID:-}" != ubuntu ]; then
  warn "This script is written for Ubuntu (found ${PRETTY_NAME:-unknown}). Continuing; package names may differ."
elif [ "${VERSION_ID:-}" != 24.04 ] && [ "${VERSION_ID:-}" != 26.10 ]; then
  ok "Tested on Ubuntu 24.04 and 26.10; any recent Ubuntu should work."
fi
ok "${PRETTY_NAME:-unknown OS}, user $(id -un), folder $APP_DIR"
if grep -qi microsoft /proc/version 2>/dev/null; then
  WSL=1; ok "Running in WSL2"
else
  WSL=0
fi
if [ ! -d /run/systemd/system ]; then
  if [ "$WSL" = 1 ]; then
    die "systemd is not running, so Docker cannot run as a service. Add this to /etc/wsl.conf:
    [boot]
    systemd=true
then run 'wsl --shutdown' in Windows, reopen Ubuntu and run this script again."
  fi
  die "systemd is not running; this script needs it to run Docker as a service."
fi
command -v python3 >/dev/null || die "python3 is missing: sudo apt install python3"
if [ -n "$(git status --porcelain 2>/dev/null | grep -v '^?? ' || true)" ]; then
  warn "The repository has local changes. Installing from a clean checkout is safer."
fi
ok "Version: $(git log -1 --format='%h %s' 2>/dev/null || echo 'not a git checkout')"

# Ports given on the command line or kept in .env are used as they are; defaults on a new
# installation move to the next free port when something else holds them (see check_port).
FRESH_PORTS=" "
if [ ! -f .env ]; then
  [ -n "$APP_PORT" ] || FRESH_PORTS+="APP "
  [ -n "$DB_PORT" ] || FRESH_PORTS+="DB "
  [ -n "$OCR_PORT" ] || FRESH_PORTS+="OCR "
fi
# Settings: the options above win; otherwise what .env already has; otherwise the defaults.
APP_PORT="${APP_PORT:-$(env_get APP_PORT)}";       APP_PORT="${APP_PORT:-5005}"
DB_PORT="${DB_PORT:-$(env_get POSTGRES_PORT)}";    DB_PORT="${DB_PORT:-55432}"
OCR_PORT="${OCR_PORT:-$(env_get OCR_PORT)}";       OCR_PORT="${OCR_PORT:-5707}"
PROJECT="${PROJECT:-$(env_get COMPOSE_PROJECT_NAME)}"
# A new installation without --name is named after its folder (~/medui_demo -> medui_demo), so a
# second folder can't take over the first one's containers by default. An existing .env keeps its name.
if [ -z "$PROJECT" ] && [ ! -f .env ]; then
  PROJECT="$(basename "$APP_DIR" | tr 'A-Z' 'a-z' | sed -E 's/[^a-z0-9_-]+/_/g; s/^[^a-z0-9]+//')"
fi
PROJECT="${PROJECT:-medui_os}"
for p in "$APP_PORT" "$DB_PORT" "$OCR_PORT"; do port_ok "$p" || die "Ports must be numbers from 1024 to 65535 (got '$p')."; done

# Practice timezone: --timezone wins; otherwise an installation keeps its own; a new one takes this
# computer's (on WSL2, Windows' own setting, translated from its Windows name). Always a place
# (Australia/Melbourne), never an offset: the zone's rules move daylight saving by themselves.
windows_zone() {   # Windows timezone name -> IANA zone, for the zones a practice here is likely in
  case "$1" in
    "E. Australia Standard Time") echo Australia/Brisbane ;;
    "AUS Eastern Standard Time") echo Australia/Sydney ;;
    "Tasmania Standard Time") echo Australia/Hobart ;;
    "Cen. Australia Standard Time") echo Australia/Adelaide ;;
    "AUS Central Standard Time") echo Australia/Darwin ;;
    "W. Australia Standard Time") echo Australia/Perth ;;
    "Aus Central W. Standard Time") echo Australia/Eucla ;;
    "Lord Howe Standard Time") echo Australia/Lord_Howe ;;
    "Norfolk Standard Time") echo Pacific/Norfolk ;;
    "New Zealand Standard Time") echo Pacific/Auckland ;;
  esac
}
zone_ok() { [ -n "$1" ] && [ "$1" = "${1#/}" ] && [[ "$1" != *..* ]] && [ -f "/usr/share/zoneinfo/$1" ]; }
# The zones offered in the menu, and what people are likely to type for them.
ZONES=(Australia/Brisbane Australia/Sydney Australia/Melbourne Australia/Hobart Australia/Adelaide Australia/Darwin Australia/Perth)
ZONE_LABELS=("Brisbane     Queensland" "Sydney       NSW, ACT" "Melbourne    Victoria" "Hobart       Tasmania"
             "Adelaide     South Australia" "Darwin       Northern Territory" "Perth        Western Australia")
resolve_zone() {   # what someone typed -> the exact zone name, or nothing
  local in; in="$(echo "$1" | tr 'A-Z' 'a-z' | sed 's/^ *//; s/ *$//; s/  */ /g')"
  case "$in" in
    brisbane|qld|queensland) echo Australia/Brisbane ;;
    sydney|nsw|"new south wales"|act|canberra) echo Australia/Sydney ;;
    melbourne|vic|victoria) echo Australia/Melbourne ;;
    hobart|tas|tasmania) echo Australia/Hobart ;;
    adelaide|sa|"south australia") echo Australia/Adelaide ;;
    darwin|nt|"northern territory") echo Australia/Darwin ;;
    perth|wa|"western australia") echo Australia/Perth ;;
    */*)   # a zone name in any capitalisation: its exact spelling from the zone files
      [[ "$in" == *..* ]] && return 0
      (cd /usr/share/zoneinfo 2>/dev/null && find . -type f -ipath "./$in" 2>/dev/null | head -1 | sed 's#^\./##') ;;
  esac
}
choose_zone() {    # the menu; $1 the zone to offer by default. Prints the zone chosen.
  local def="$1" n=${#ZONES[@]} i defkey="$1" pick z
  for i in "${!ZONES[@]}"; do [ "${ZONES[$i]}" = "$def" ] && defkey=$((i + 1)); done
  while :; do
    echo "" >&2
    if [ -n "$DET_FROM" ]; then echo "  Practice timezone (detected from $DET_FROM):" >&2
    else echo "  Practice timezone (not detected: Brisbane offered):" >&2; fi
    for i in "${!ZONES[@]}"; do
      printf '    %d  %s%s\n' $((i + 1)) "${ZONE_LABELS[$i]}" \
        "$([ "${ZONES[$i]}" = "$def" ] && { [ -n "$DET_FROM" ] && echo '   <- detected' || echo '   <- offered'; })" >&2
    done
    printf '    %d  Other (type a zone name, e.g. Australia/Lord_Howe)\n' $((n + 1)) >&2
    read -rp "  Choice [$defkey]: " pick
    pick="${pick:-$defkey}"
    if [[ "$pick" =~ ^[0-9]+$ ]] && [ "$pick" -ge 1 ] && [ "$pick" -le "$n" ]; then
      z="${ZONES[$((pick - 1))]}"
    elif [ "$pick" = $((n + 1)) ]; then
      read -rp "  Zone name: " pick
      z="$(resolve_zone "$pick")"
    else
      z="$(resolve_zone "$pick")"
    fi
    if zone_ok "$z"; then echo "$z"; return; fi
    echo "  '$pick' isn't a timezone this computer knows. Choose a number, or type a city or state" >&2
    echo "  (melbourne, vic, nsw...) or a zone name such as Australia/Melbourne." >&2
  done
}
DET_FROM=""
if [ -n "$PRACTICE_TZ" ]; then                                   # --timezone, in any of the forms above
  given="$PRACTICE_TZ"; PRACTICE_TZ="$(resolve_zone "$given")"
  zone_ok "$PRACTICE_TZ" || die "--timezone '$given' isn't a timezone this computer knows. Use a city or state
(brisbane, sydney, melbourne, hobart, adelaide, darwin, perth; qld, nsw, vic...) or a zone name
such as Australia/Melbourne."
elif [ -f .env ] && [ -n "$(env_get PRACTICE_TIMEZONE)" ]; then  # an installation keeps its own
  PRACTICE_TZ="$(env_get PRACTICE_TIMEZONE)"; TZ_FROM="this installation"
else                                                             # a new one: detect, then offer
  DETECTED=""
  if [ "$WSL" = 1 ]; then
    win="$(tzutil.exe /g 2>/dev/null | tr -d '\r' || true)"
    DETECTED="$(windows_zone "$win")"; [ -n "$DETECTED" ] && DET_FROM="Windows: $win"
  fi
  if [ -z "$DETECTED" ]; then
    sys="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
    case "$sys" in ""|UTC|Etc/UTC|Etc/Universal|Universal) ;; *) DETECTED="$sys"; DET_FROM="this computer" ;; esac
  fi
  if [ "$YES" = 0 ] && [ "$DRY" = 0 ] && [ -t 0 ]; then
    PRACTICE_TZ="$(choose_zone "${DETECTED:-Australia/Brisbane}")"; TZ_FROM="chosen"
  else
    PRACTICE_TZ="${DETECTED:-Australia/Brisbane}"; TZ_FROM="${DET_FROM:-default}"
  fi
fi
zone_ok "$PRACTICE_TZ" || die "'$PRACTICE_TZ' (in .env) isn't a timezone this computer knows. Run again with
--timezone and the practice's city or state, e.g. --timezone melbourne."
ok "Practice timezone: $PRACTICE_TZ ($TZ_FROM); local time there now $(TZ="$PRACTICE_TZ" date '+%a %-d %b %H:%M')"
[ "$TZ_FROM" = default ] && warn "Not detected: check it, and run again with --timezone if it's wrong."

# HTTPS: the options above win; otherwise what an earlier --https recorded in .env.
[ "$HTTPS" = 0 ] && [ -n "$(env_get HTTPS_MODE)" ] && HTTPS=1
if [ "$HTTPS" = 1 ]; then
  [ -n "$HTTPS_CERT" ] || [ -z "$HTTPS_KEY" ] || die "--https-key needs --https-cert."
  [ -z "$HTTPS_CERT" ] || [ -n "$HTTPS_KEY" ] || die "--https-cert needs --https-key."
  [ -z "$HTTPS_CERT" ] || { [ -r "$HTTPS_CERT" ] && [ -r "$HTTPS_KEY" ]; } || die "Can't read $HTTPS_CERT or $HTTPS_KEY."
  HTTPS_MODE=ca; [ -n "$HTTPS_CERT" ] && HTTPS_MODE=cert
  [ -z "$HTTPS_CERT" ] && [ "$(env_get HTTPS_MODE)" = cert ] && [ -f https/certs/cert.pem ] && HTTPS_MODE=cert
  HTTPS_PORT="${HTTPS_PORT:-$(env_get HTTPS_PORT)}"; HTTPS_PORT="${HTTPS_PORT:-443}"
  HTTP_PORT="${HTTP_PORT:-$(env_get HTTP_PORT)}"; HTTP_PORT="${HTTP_PORT:-80}"
  for p in "$HTTPS_PORT" "$HTTP_PORT"; do
    [[ "$p" =~ ^[0-9]+$ ]] && [ "$p" -ge 1 ] && [ "$p" -le 65535 ] \
      || die "--https-port and --http-port must be numbers from 1 to 65535."
  done
  [ "$HTTPS_PORT" != "$HTTP_PORT" ] || die "--https-port and --http-port must differ."
  if [ "$HTTPS_MODE" = ca ]; then
    [ ${#HTTPS_NAMES[@]} -eq 0 ] && IFS=, read -ra HTTPS_NAMES <<< "$(env_get HTTPS_NAMES)"
    [ ${#HTTPS_IPS[@]} -eq 0 ] && IFS=, read -ra HTTPS_IPS <<< "$(env_get HTTPS_IPS)"
    if [ ${#HTTPS_NAMES[@]} -eq 0 ] && [ ${#HTTPS_IPS[@]} -eq 0 ]; then
      HTTPS_NAMES=("$(hostname | tr 'A-Z' 'a-z')")
      fqdn="$(hostname -f 2>/dev/null | tr 'A-Z' 'a-z' || true)"
      [[ "$fqdn" == *.* ]] && [ "$fqdn" != "${HTTPS_NAMES[0]}" ] && HTTPS_NAMES+=("$fqdn")
      lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)"
      [ -n "$lan_ip" ] && HTTPS_IPS=("$lan_ip")
    fi
    for n in "${HTTPS_NAMES[@]}"; do
      [[ "$n" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || die "--https-name '$n': lower-case letters, digits, '.' and '-' only."
    done
    for a in "${HTTPS_IPS[@]}"; do
      [[ "$a" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "--https-ip '$a' isn't an IPv4 address."
    done
    [ ${#HTTPS_NAMES[@]} -gt 0 ] || [ ${#HTTPS_IPS[@]} -gt 0 ] || die "--https needs at least one --https-name or --https-ip."
  fi
fi
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "--name: lower-case letters, digits, '_' and '-' only."

# A demo installation: its own SQL Server with the invented demo databases, never Best Practice.
# MedUI keeps BP patient and user numbers in its own database, so an installation is a demo from
# its first run or never: a live one can't become a demo, nor a demo be pointed at BP.
[ "$(env_get MEDUI_INSTANCE)" = demo ] && DEMO=1
# OCR stays off on a rerun if .env says so (--no-ocr before, or ./medui.sh features);
# ./medui.sh features OCR_ENABLED=on turns it back on.
[ "$(env_get OCR_ENABLED)" = false ] && OCR=0
# A new installation started by a person, without --demo or --yes, is asked once. With --yes
# (the Windows script, which asks itself; agents; scripts) it is live unless --demo says otherwise,
# and an existing installation keeps what its .env says.
if [ "$DEMO" = 0 ] && [ "$YES" = 0 ] && [ ! -f .env ] && [ -t 0 ]; then
  echo
  echo "  Live: the practice's MedUI, reading its Best Practice database."
  echo "  Demo: for demonstrations and training, with invented patients in a SQL Server of its own; never BP."
  read -rp "  Is this a live practice installation or a demo? (L/d) " answer
  [[ "$answer" =~ ^[dD] ]] && DEMO=1
fi
if [ "$DEMO" = 1 ]; then
  if [ -f .env ] && [ "$(env_get MEDUI_INSTANCE)" != demo ]; then
    die "This installation isn't a demo, and can't become one: its database may already hold Best
Practice's patient and user numbers. Install the demo in a folder of its own:
  git clone <repository> ~/medui_demo && cd ~/medui_demo && ./install.sh --demo"
  fi
  if [ -n "$(env_get BPSDB_HOST)" ] && [ "$(env_get BPSDB_HOST)" != bpsql ]; then
    die "BPSDB_HOST in .env points at a server other than this demo's own (bpsql). A demo installation reads only its demo SQL Server."
  fi
  [ "$PROJECT" != medui_os ] || die "A demo needs a name of its own, so it can't be mistaken for the practice's installation:
clone it into ~/medui_demo (named after the folder), or add --name medui_demo."
  [ "$(uname -m)" = x86_64 ] || die "The demo's SQL Server runs on x86-64 (Intel or AMD) only; this computer is $(uname -m)."
  mem_gb="$(awk '/MemTotal/ {printf "%d", $2 / 1048576}' /proc/meminfo)"
  [ "${mem_gb:-0}" -ge 6 ] || warn "This computer has ${mem_gb} GB of memory: the demo's SQL Server takes up to 2 GB on top of MedUI. 8 GB or more is comfortable."
  ok "Demo installation: SQL Server Express with MedUI's invented demo databases (medui_demodata), no Best Practice"
elif [[ "$PROJECT" == *demo* ]]; then
  warn "'$PROJECT' sounds like a demo, but this isn't one. For the demo databases: ./install.sh --demo"
fi

# Docker, if it is here yet (before step 2 it may not be, or may need sudo): docker, then sudo -n docker.
dk() {
  if docker info >/dev/null 2>&1; then docker "$@"
  elif sudo -n docker info >/dev/null 2>&1; then sudo -n docker "$@"
  else return 1; fi
}

# One project name, one folder: another folder with the same name would take over this one's
# containers (Compose names everything after the project, not the folder).
other_dir="$(dk ps -a --filter "label=com.docker.compose.project=$PROJECT" \
  --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null | sort -u \
  | while read -r d; do [ -n "$d" ] && [ "$(realpath -m "$d")" != "$(realpath -m "$APP_DIR")" ] && echo "$d"; done | head -1 || true)"
if [ -n "$other_dir" ]; then
  die "Project '$PROJECT' is already installed in $other_dir.
Run ./install.sh from that folder, or give this installation its own name, e.g. --name ${PROJECT}_2
(each installation needs its own folder, name and ports: docs/cheatsheet.md)."
fi
if [ ! -f .env ] && dk volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | grep -q .; then
  die "Docker still holds data for a project called '$PROJECT' (volumes $(dk volume ls -q --filter "label=com.docker.compose.project=$PROJECT" | xargs))
from an installation whose folder has gone or that was removed without its volumes. A new .env can't open it.
Give this installation another name (--name ...), or restore that installation's .env here, or remove
the old volumes after backing up ('docker volume rm ...'; it deletes that data for good)."
fi

# Ports other installations have claimed, running or stopped: "project port" per line.
claimed_ports() {
  local ids; ids="$(dk ps -aq 2>/dev/null)" || return 0
  [ -n "$ids" ] || return 0
  # shellcheck disable=SC2086
  dk inspect --format '{{index .Config.Labels "com.docker.compose.project"}}{{range $p, $b := .HostConfig.PortBindings}}{{range $b}} {{.HostPort}}{{end}}{{end}}' $ids 2>/dev/null \
    | awk '{for (i = 2; i <= NF; i++) print $1, $i}'
}
CLAIMED="$(claimed_ports || true)"
port_taken() {   # listening now, or published by another project's container (even a stopped one)
  { ss -ltnH "sport = :$1" 2>/dev/null | grep -q . && ! own_container_on "$1"; } && return 0
  printf '%s\n' "$CLAIMED" | awk -v p="$1" -v me="$PROJECT" '$2 == p && $1 != me {f = 1} END {exit !f}'
}
# A port is free, or already ours (a re-run): anything else listening there is a conflict.
own_container_on() {
  printf '%s\n' "$CLAIMED" | awk -v p="$1" -v me="$PROJECT" '$2 == p && $1 == me {f = 1} END {exit !f}' && return 0
  local d
  for d in "docker" "sudo -n docker"; do
    $d ps --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Ports}}' 2>/dev/null \
      | grep -q ":$1->" && return 0
  done
  return 1
}
CHOSEN=" "
check_port() {   # VAR description --option
  local var="$1" what="$2" opt="$3" port="${!1}" key="${1%_PORT}" try
  if ! port_taken "$port" && [[ "$CHOSEN" != *" $port "* ]]; then CHOSEN+="$port "; return; fi
  if [[ "$FRESH_PORTS" == *" $key "* ]]; then   # a default on a new installation: take the next free one
    for (( try = port + 1; try <= port + 50 && try <= 65535; try++ )); do
      if ! port_taken "$try" && [[ "$CHOSEN" != *" $try "* ]]; then
        warn "Port $port ($what) is taken (another installation, or something else); using $try instead ($opt to choose)."
        printf -v "$var" '%s' "$try"; CHOSEN+="$try "; return
      fi
    done
  fi
  die "Port $port ($what) is already in use on this computer$(claim_owner "$port"). Choose another with $opt, e.g. $opt $(( port + 10 ))."
}
claim_owner() {
  local who; who="$(printf '%s\n' "$CLAIMED" | awk -v p="$1" -v me="$PROJECT" '$2 == p && $1 != me {print $1; exit}')"
  [ -n "$who" ] && echo " (installation '$who')"
  return 0
}
check_port APP_PORT "MedUI" --app-port
check_port DB_PORT "PostgreSQL" --db-port
[ "$OCR" = 1 ] && check_port OCR_PORT "LiteParse OCR" --ocr-port
[ "$HTTPS" = 1 ] && check_port HTTPS_PORT "HTTPS" --https-port
[ "$HTTPS" = 1 ] && check_port HTTP_PORT "the setup page (HTTP)" --http-port
ok "Ports: MedUI $APP_PORT, PostgreSQL $DB_PORT$([ "$OCR" = 1 ] && echo ", OCR $OCR_PORT"); project '$PROJECT'"
if [ "$HTTPS" = 1 ]; then
  if [ "$HTTPS_MODE" = cert ]; then
    ok "HTTPS on port $HTTPS_PORT with the practice's own certificate"
  else
    ok "HTTPS on port $HTTPS_PORT for: ${HTTPS_NAMES[*]} ${HTTPS_IPS[*]} (MedUI root, restricted to these)"
  fi
fi

# SQL Server's licence terms are Microsoft's: the person installing accepts them, once.
if [ "$DEMO" = 1 ] && [ "$(env_get DEMO_SQL_ACCEPT_EULA)" != Y ]; then
  if [ "$ACCEPT_SQL" = 1 ]; then
    ok "SQL Server licence terms accepted (--accept-sql-licence)"
  elif [ "$DRY" = 1 ]; then
    echo "  [dry run] would ask you to accept Microsoft's SQL Server licence terms (aka.ms/useterms)"
  elif [ -t 0 ]; then
    echo
    echo "  The demo runs Microsoft SQL Server 2022 Express (free) in a container. Its licence terms are"
    echo "  Microsoft's, at https://aka.ms/useterms (and inside the image, /usr/share/doc/mssql-server)."
    echo "  MedUI turns off its usage reports to Microsoft (customer feedback) for this container."
    read -rp "  Do you accept Microsoft's SQL Server licence terms? (y/N) " answer
    [[ "$answer" =~ ^[yY]$ ]] || { echo "Nothing changed. A demo needs SQL Server; without it, install without --demo."; exit 0; }
  else
    die "A demo needs Microsoft's SQL Server licence terms accepted (https://aka.ms/useterms): add --accept-sql-licence once you have read them."
  fi
fi

if [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then
  read -rp $'\nInstall MedUI with these settings? (y/N) ' answer
  [[ "$answer" =~ ^[yY]$ ]] || { echo "Nothing changed."; exit 0; }
fi

# ---- 2. system packages -------------------------------------------------------------------------------------------
say "2. System packages"
if [ "$APT" = 1 ]; then
  pkgs=(ca-certificates curl git)
  if ! command -v docker >/dev/null; then
    pkgs+=(docker.io docker-compose-v2 docker-buildx)
  else
    docker compose version >/dev/null 2>&1 || pkgs+=(docker-compose-v2)
    docker buildx version >/dev/null 2>&1 || pkgs+=(docker-buildx)
  fi
  # IPv6 that resolves but doesn't connect makes apt crawl (each download falls back to IPv4).
  if [ ! -f /etc/apt/apt.conf.d/99force-ipv4 ] && command -v curl >/dev/null && ! curl -6 -s -m 5 -o /dev/null http://archive.ubuntu.com/ubuntu/ 2>/dev/null; then
    if [ "$DRY" = 1 ]; then echo "  [dry run] set apt to IPv4 (IPv6 doesn't connect)"
    else echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4 >/dev/null; fi
    warn "IPv6 doesn't connect from here: package downloads use IPv4."
  fi
  run sudo apt-get -o DPkg::Lock::Timeout=600 update -q
  run sudo env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y -q "${pkgs[@]}"
  run sudo systemctl enable --now docker
  ok "Installed or present: ${pkgs[*]}"
else
  ok "Skipped (--no-apt)"
fi
if [ "$DRY" = 0 ]; then
  command -v docker >/dev/null || die "Docker is not installed. Run without --no-apt, or install Docker Engine."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (package docker-compose-v2)."
fi

# Docker group: membership only applies to new logins, so use sudo for this run if needed.
DOCKER=(docker)
if [ "$DRY" = 1 ] && ! id -nG | tr ' ' '\n' | grep -qx docker; then
  echo "  [dry run] add $(id -un) to the docker group (takes effect at your next login; this run would use sudo for Docker)"
fi
if [ "$DRY" = 0 ] && ! docker info >/dev/null 2>&1; then
  if ! id -nG | tr ' ' '\n' | grep -qx docker; then
    run sudo usermod -aG docker "$(id -un)"
    warn "Added $(id -un) to the docker group: it takes effect at your next login. Using sudo for Docker this time."
  fi
  sudo docker info >/dev/null 2>&1 || die "Docker is installed but not running: sudo systemctl status docker"
  DOCKER=(sudo docker)
fi
compose() { run "${DOCKER[@]}" compose -p "$PROJECT" "$@"; }

# ---- 3. configuration ---------------------------------------------------------------------------------------------
say "3. Configuration (.env)"
if [ -f .env ]; then
  ok ".env exists; secrets kept"
else
  run python3 scripts/init_env.py
fi
if [ -f .env ] || [ "$DRY" = 1 ]; then
  env_set COMPOSE_PROJECT_NAME "$PROJECT"
  env_set APP_PORT "$APP_PORT"
  env_set POSTGRES_PORT "$DB_PORT"
  env_set OCR_PORT "$OCR_PORT"
  env_set OCR_ENABLED "$([ "$OCR" = 1 ] && echo true || echo false)"
  env_set PRACTICE_TIMEZONE "$PRACTICE_TZ"
  if [ "$DEMO" = 1 ]; then   # the demo's own SQL Server, and MedUI's read-only login to it
    new_pw() { python3 -c 'import secrets; print("Dm1-" + secrets.token_urlsafe(18))'; }
    env_set MEDUI_INSTANCE demo
    env_set DEMO_SQL_ACCEPT_EULA Y
    [ -n "$(env_get DEMO_SQL_SA_PASSWORD)" ] || env_set DEMO_SQL_SA_PASSWORD "$(new_pw)"
    env_set BPSDB_HOST bpsql
    env_set BPSDB_DATABASE BPSPATIENTS
    [ -n "$(env_get BPSDB_USER)" ] || env_set BPSDB_USER medui_demo_reader
    [ -n "$(env_get BPSDB_PASSWORD)" ] || env_set BPSDB_PASSWORD "$(new_pw)"
    env_set BPSDB_TRUST_SERVER_CERTIFICATE true
  fi
  # The host-side address of the database and OCR follow their ports (the app container uses its own).
  if [ "$DRY" = 0 ]; then
    sed -i -E "s#^(DATABASE_URL=postgresql://[^@]+@127\.0\.0\.1:)[0-9]+/#\1$DB_PORT/#" .env
    sed -i -E "s#^(OCR_SERVICE_URL=http://127\.0\.0\.1:)[0-9]+#\1$OCR_PORT#" .env
    chmod 600 .env
  fi
  ok "Ports and project name recorded in .env (mode 600)"
fi

# ---- 4. database and OCR ------------------------------------------------------------------------------------------
say "4. PostgreSQL$([ "$OCR" = 1 ] && echo " and LiteParse OCR")$([ "$DEMO" = 1 ] && echo " and the demo SQL Server")"
DEMO_UP=() DEMO_SVC=()
if [ "$DEMO" = 1 ]; then
  DEMO_UP=(--profile demo) DEMO_SVC=(bpsql)
  "${DOCKER[@]}" image inspect "$(sed -n 's/^ *image: \(mcr.microsoft.com\/mssql[^ ]*\).*/\1/p' compose.yaml)" >/dev/null 2>&1 \
    || warn "The first SQL Server download is about 1.6 GB."
fi
if [ "$OCR" = 1 ]; then
  warn "The first OCR build downloads and compiles LiteParse: allow several minutes."
  compose --profile ocr "${DEMO_UP[@]}" up -d --build --wait db liteparse "${DEMO_SVC[@]}"
else
  compose "${DEMO_UP[@]}" up -d --wait db "${DEMO_SVC[@]}"
fi
ok "Running and healthy"

# ---- 5. MedUI -----------------------------------------------------------------------------------------------------
say "5. MedUI image, database schema and starter data"
compose --profile app build app
flask_cmd() { compose --profile app run --rm app flask --app wsgi "$@"; }
flask_cmd db upgrade
flask_cmd install defaults
flask_cmd seed providers
if [ "$REFERENCE" = 1 ]; then flask_cmd install seeds --include-reference-data; else flask_cmd install seeds; fi
ok "Schema current; defaults, provider templates and starter seeds present (existing records kept)"

# ---- demo databases ------------------------------------------------------------------------------------------------
if [ "$DEMO" = 1 ]; then
  say "5b. Demo databases (medui_demodata)"
  run scripts/demo_data.sh fetch
  run scripts/demo_data.sh restore
  if [ "$(env_get DEMO_PASSWORD_SET)" = true ]; then
    ok "Demo users' password kept (a new one: ./medui.sh demo password)"
  elif [ -t 0 ] || [ -n "${MEDUI_DEMO_PASSWORD:-}" ] || [ "$DRY" = 1 ]; then
    run scripts/demo_data.sh password && env_set DEMO_PASSWORD_SET true
  else
    warn "No terminal to ask for the demo users' password. Later: ./medui.sh demo password"
  fi
  run scripts/demo_data.sh refresh
  ok "Dates brought up to today (again any time: ./medui.sh demo refresh)"
fi

# ---- 6. administrator ---------------------------------------------------------------------------------------------
say "6. Local administrator"
if [ "$ADMIN" = 0 ]; then
  ok "Skipped (--no-admin). Later: docker compose --profile app run --rm app flask --app wsgi install admin"
elif [ ! -t 0 ] && [ "$DRY" = 0 ]; then
  warn "No terminal to ask for a username and password. Later: docker compose --profile app run --rm app flask --app wsgi install admin"
else
  echo "  Choose a username (not a number) and a password of at least 12 characters."
  flask_cmd install admin --if-missing
fi

# ---- 7. start -----------------------------------------------------------------------------------------------------
say "7. Start MedUI"
compose --profile app up -d --wait app
if [ "$DRY" = 0 ]; then
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$APP_PORT/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS "http://127.0.0.1:$APP_PORT/health" >/dev/null 2>&1 \
    || die "MedUI did not answer on port $APP_PORT. See: docker compose -p $PROJECT --profile app logs app"
fi
ok "MedUI answers at http://127.0.0.1:$APP_PORT"

# ---- 8. HTTPS -----------------------------------------------------------------------------------------------------
# Caddy (compose profile https) on the practice network, in front of MedUI. Either the
# practice's own certificate, or a root made here that may only vouch for the names and
# addresses given (X.509 name constraints): even with its key, no other site can be
# impersonated to workstations that trust it. Caddy issues and renews MedUI's certificate
# from that root by itself. docs/https.md explains it for the practice's IT.
if [ "$HTTPS" = 1 ]; then
say "8. HTTPS for workstations (port $HTTPS_PORT; setup page on port $HTTP_PORT)"
command -v openssl >/dev/null || die "openssl is missing: sudo apt install openssl"
run mkdir -p https/ca https/certs https/welcome
run chmod 700 https/ca https/certs
PORT_SUFFIX=""; [ "$HTTPS_PORT" = 443 ] || PORT_SUFFIX=":$HTTPS_PORT"
SITES=()
if [ "$HTTPS_MODE" = cert ]; then
  # Checked before anything is copied, so a wrong pair never replaces a working one.
  SRC_CERT="${HTTPS_CERT:-https/certs/cert.pem}"; SRC_KEY="${HTTPS_KEY:-https/certs/key.pem}"
  if [ "$DRY" = 0 ]; then
    [ "$(openssl x509 -in "$SRC_CERT" -noout -pubkey 2>/dev/null | openssl sha256)" = \
      "$(openssl pkey -in "$SRC_KEY" -pubout 2>/dev/null | openssl sha256)" ] \
      || die "The certificate and the key don't belong together (or aren't PEM). Nothing was changed."
    openssl x509 -in "$SRC_CERT" -noout -checkend 0 >/dev/null || die "The certificate has expired. Nothing was changed."
  fi
  if [ -n "$HTTPS_CERT" ]; then
    run install -m 600 "$HTTPS_CERT" https/certs/cert.pem
    run install -m 600 "$HTTPS_KEY" https/certs/key.pem
  fi
  if [ "$DRY" = 0 ]; then
    ok "Practice certificate: $(openssl x509 -in https/certs/cert.pem -noout -subject -enddate | tr '\n' ' ')"
    SAN="$(openssl x509 -in https/certs/cert.pem -noout -ext subjectAltName 2>/dev/null | sed -n '2p')"
    echo "    names: $(echo "$SAN" | sed 's/^ *//')"
    # The names on the certificate, for the check below and the notes at the end.
    HTTPS_NAMES=(); HTTPS_IPS=()
    for e in $(echo "$SAN" | tr ',' ' '); do
      case "$e" in DNS:*) HTTPS_NAMES+=("${e#DNS:}") ;; IP*:*) HTTPS_IPS+=("${e#*:}") ;; esac
    done
  fi
  TLS_BLOCK="tls /etc/caddy/certs/cert.pem /etc/caddy/certs/key.pem"
  SITES=(":443")
  GLOBAL_PKI=""
else
  for n in "${HTTPS_NAMES[@]}"; do SITES+=("https://$n"); done
  for a in "${HTTPS_IPS[@]}"; do SITES+=("https://$a"); done
  WANT=(); for n in "${HTTPS_NAMES[@]}"; do WANT+=("DNS:$n"); done; for a in "${HTTPS_IPS[@]}"; do WANT+=("IP:$a/255.255.255.255"); done
  if [ -f https/ca/root.crt ] && [ "$NEW_ROOT" = 0 ]; then
    HAVE="$(openssl x509 -in https/ca/root.crt -noout -ext nameConstraints 2>/dev/null | grep -oE '(DNS|IP):[^ ,]+' || true)"
    for w in "${WANT[@]}"; do
      grep -qxF "$w" <<< "$HAVE" || die "The MedUI root doesn't cover '${w#*:}' (it covers: $(echo $HAVE)).
A new name needs a new root: add --https-new-root, then install the new root on every
workstation (docs/https.md). Or leave the names as they were."
    done
    ok "MedUI root kept ($(openssl x509 -in https/ca/root.crt -noout -enddate | cut -d= -f2))"
  elif [ "$DRY" = 1 ]; then
    echo "  [dry run] make a MedUI root restricted to: ${WANT[*]}"
  else
    if [ "$NEW_ROOT" = 1 ] && [ -f https/ca/root.crt ]; then
      mv https/ca/root.crt "https/ca/root.crt.replaced-$(date +%Y%m%d-%H%M%S)"
      # Caddy's intermediate and certificates came from the old root: let it make new ones.
      compose --profile https run --rm --no-deps --entrypoint sh caddy \
        -c 'rm -rf /data/caddy/pki/authorities/medui /data/caddy/certificates' || true
    fi
    NC="critical$(printf ',permitted;%s' "${WANT[@]}")"
    (umask 077; openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out https/ca/root.key)
    openssl req -x509 -new -key https/ca/root.key -sha256 -days 3650 \
      -subj "/O=MedUI/CN=MedUI HTTPS root for ${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}" \
      -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
      -addext "keyUsage=critical,keyCertSign,cRLSign" \
      -addext "nameConstraints=$NC" \
      -addext "subjectKeyIdentifier=hash" \
      -out https/ca/root.crt
    chmod 600 https/ca/root.key; chmod 644 https/ca/root.crt
    ok "MedUI root made, valid 10 years, restricted to: ${WANT[*]}"
  fi
  if [ "$DRY" = 0 ]; then
    openssl x509 -in https/ca/root.crt -outform DER -out https/medui-root.cer
    chmod 644 https/medui-root.cer
    # Prove the restriction: a certificate this root signs for MedUI's name verifies, one for
    # any other name is refused.
    t="$(mktemp -d)"
    for name in "${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}" "example.com"; do
      san="DNS:$name"; [[ "$name" =~ ^[0-9.]+$ ]] && san="IP:$name"
      openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout "$t/k" -subj "/CN=$name" \
        -addext "subjectAltName=$san" -out "$t/csr" 2>/dev/null
      openssl x509 -req -in "$t/csr" -CA https/ca/root.crt -CAkey https/ca/root.key -days 1 -copy_extensions copy \
        -out "$t/$name.crt" 2>/dev/null
    done
    openssl verify -CAfile https/ca/root.crt "$t/${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}.crt" >/dev/null 2>&1 \
      || { rm -rf "$t"; die "A certificate from the MedUI root for MedUI's own name didn't verify."; }
    openssl verify -CAfile https/ca/root.crt "$t/example.com.crt" >/dev/null 2>&1 \
      && { rm -rf "$t"; die "The MedUI root vouched for example.com: its name restriction isn't working."; }
    rm -rf "$t"
    ok "Restriction checked: vouches for ${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}, refuses example.com"
    # The setup page on port 80 (plain HTTP: the one step before a workstation trusts the root)
    # and the one-file Windows setup it offers, with the root built in. scripts/https/*.in.
    THUMB="$(openssl x509 -in https/ca/root.crt -noout -fingerprint -sha1 | cut -d= -f2 | tr -d :)"
    URL="https://${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}$PORT_SUFFIX"
    fill() {
      sed -e "s|@@CERT_B64@@|$(base64 -w0 https/medui-root.cer)|" -e "s|@@THUMB@@|$THUMB|g" \
          -e "s|@@URL@@|$URL|g" -e "s|@@HOST@@|$(hostname)|g" \
          -e "s|@@NAMES@@|$(echo ${HTTPS_NAMES[*]} ${HTTPS_IPS[*]} | sed 's/ /, /g')|g" "$1"
    }
    fill scripts/https/welcome.html.in > https/welcome/index.html
    fill scripts/https/setup-medui.cmd.in | sed 's/$/\r/' > https/welcome/setup-medui.cmd   # cmd.exe wants CRLF
    cp https/medui-root.cer https/welcome/medui-root.cer
    chmod 755 https/welcome; chmod 644 https/welcome/*
    ok "Setup page for workstations: http://${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}$([ "$HTTP_PORT" = 80 ] || echo ":$HTTP_PORT")"
  fi
  TLS_BLOCK="tls {
		issuer internal {
			ca medui
		}
	}"
  GLOBAL_PKI="	default_sni ${HTTPS_IPS[0]:-${HTTPS_NAMES[0]}}
	pki {
		ca medui {
			name \"MedUI\"
			root {
				cert /etc/caddy/ca/root.crt
				key /etc/caddy/ca/root.key
			}
		}
	}"
fi
HTTP_SETUP=""
[ "$HTTPS_MODE" = ca ] && HTTP_SETUP="	@setup path / /index.html /setup-medui.cmd /medui-root.cer
	handle @setup {
		root * /etc/caddy/welcome
		header Cache-Control no-store
		header /setup-medui.cmd Content-Disposition \"attachment; filename=setup-medui.cmd\"
		header /medui-root.cer Content-Type application/pkix-cert
		file_server
	}"
if [ "$DRY" = 1 ]; then
  echo "  [dry run] write https/Caddyfile for: ${SITES[*]}"
else
  SITE_LIST="$(printf '%s, ' "${SITES[@]}")"
  cat > https/Caddyfile <<CADDY
# Written by install.sh (docs/https.md). Run install.sh again to change it: edits here are replaced.
{
	admin off
	skip_install_trust
	auto_https disable_redirects
$GLOBAL_PKI
}

${SITE_LIST%, } {
	$TLS_BLOCK
	reverse_proxy app:8000
}

# Plain HTTP: the setup page a workstation opens first (until it trusts MedUI), and a
# redirect to HTTPS for everything else.
http:// {
$HTTP_SETUP
	handle {
		redir https://{host}$PORT_SUFFIX{uri} 308
	}
}
CADDY
  chmod 644 https/Caddyfile
fi
env_set HTTPS_MODE "$HTTPS_MODE"
env_set HTTPS_PORT "$HTTPS_PORT"
env_set HTTP_PORT "$HTTP_PORT"
env_set HTTPS_NAMES "$(IFS=,; echo "${HTTPS_NAMES[*]}")"
env_set HTTPS_IPS "$(IFS=,; echo "${HTTPS_IPS[*]}")"
env_set SESSION_COOKIE_SECURE true
env_set TRUSTED_PROXIES 1
compose --profile app up -d --wait app            # picks up the two settings above
compose --profile app --profile https up -d --force-recreate caddy
CHECK_NAME="${HTTPS_NAMES[0]:-${HTTPS_IPS[0]:-localhost}}"   # also printed in a dry run
if [ "$DRY" = 0 ]; then
  if [ "$HTTPS_MODE" = ca ]; then CURL_TRUST=(--cacert https/ca/root.crt); else CURL_TRUST=(-k); fi
  CURL_TO=(); [[ "$CHECK_NAME" =~ ^[0-9.]+$ ]] || CURL_TO=(--resolve "$CHECK_NAME:$HTTPS_PORT:127.0.0.1")
  for _ in $(seq 1 30); do
    curl -fsS "${CURL_TRUST[@]}" "${CURL_TO[@]}" "https://$CHECK_NAME:$HTTPS_PORT/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS "${CURL_TRUST[@]}" "${CURL_TO[@]}" "https://$CHECK_NAME:$HTTPS_PORT/health" >/dev/null 2>&1 \
    || die "MedUI didn't answer over HTTPS. See: docker compose -p $PROJECT --profile https logs caddy"
fi
ok "MedUI answers at https://$CHECK_NAME$PORT_SUFFIX$([ "$HTTPS_MODE" = ca ] && echo ", trusted through the MedUI root")"
fi

# ---- done ---------------------------------------------------------------------------------------------------------
say "Done"
if [ "$HTTPS" = 1 ] && [ "$HTTPS_MODE" = ca ] && [ -f https/medui-root.cer ]; then
  WIN_PATH=""
  [ "$WSL" = 1 ] && WIN_PATH="$(printf '\n    From Windows: \\\\wsl.localhost\\%s%s\\https\\medui-root.cer' \
    "${WSL_DISTRO_NAME:-<instance>}" "$(echo "$APP_DIR" | tr / '\\')")"
  HTTPS_NOTE="  - Workstations: open http://${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}$([ "$HTTP_PORT" = 80 ] || echo ":$HTTP_PORT") once on each PC: it offers a
    one-file setup that makes the PC trust the MedUI root, then goes on to
    https://${HTTPS_NAMES[0]:-${HTTPS_IPS[0]}}$PORT_SUFFIX. Give staff (or IT) the thumbprint to check:
    SHA-1 thumbprint: $(openssl x509 -in https/ca/root.crt -noout -fingerprint -sha1 | cut -d= -f2 | tr -d :)
    In a Windows domain, Group Policy instead (the root: $APP_DIR/https/medui-root.cer$WIN_PATH).
    docs/https.md has the details for IT.$([ "$WSL" = 1 ] && echo "
    Windows firewall: run scripts/windows/open_medui_https_port.ps1 as administrator." || true)"
elif [ "$HTTPS" = 1 ]; then
  HTTPS_NOTE="  - Workstations: https://${HTTPS_NAMES[0]:-${HTTPS_IPS[0]:-<the name on your certificate>}}$PORT_SUFFIX$([ "$WSL" = 1 ] && echo "
    Windows firewall: run scripts/windows/open_medui_https_port.ps1 as administrator." || true)"
else
  HTTPS_NOTE="  - Workstation access: ./install.sh --https (docs/https.md) for HTTPS on the practice network."
fi
BP_CAUTION=""
[ "$PROJECT" != medui_os ] && [ "$DEMO" = 0 ] && BP_CAUTION="
    This install is '$PROJECT'. If it is for testing, a demo or training, point it at a SQL Server
    holding only test data, never the practice's live BP: the login reads every database it can open."
[ "$WSL" = 1 ] && WSL_NOTE="  (WSL2: open it in a browser on this Windows computer.)" || WSL_NOTE=""
if [ "$DEMO" = 1 ]; then
cat <<EOF
  Demo installation '$PROJECT': MedUI reads MedUI's invented demo databases in its own SQL Server.
  Open http://127.0.0.1:$APP_PORT and log in as a demo user, such as Dr Imogen Thistlewood
  (practice owner) or Dr Callum Ravensworth, with the demo users' password, or as the local
  administrator.
$WSL_NOTE

  - Never point this installation at Best Practice: its database now holds the demo's patient and
    user numbers, which would attach to whichever real patients have the same ones.
  - Bring the dates up to today before a demo or recording: ./medui.sh demo refresh
  - ./medui.sh opens a menu: start, stop, features (AI), HTTPS for training PCs, the demo data.
$HTTPS_NOTE
  - OCR: in Setup -> External Sources, add LiteParse at http://liteparse:5707 and press Test.
  - Removing it: docs/operations.md (the demo SQL Server and its data go with it).

  Running this script again is safe: existing settings, data and secrets are kept.
EOF
exit 0
fi
cat <<EOF
  Open http://127.0.0.1:$APP_PORT and log in as the local administrator.
$WSL_NOTE

  Next steps (each is off until you set it up). ./medui.sh opens a menu for most of them.
  - Best Practice: ./medui.sh bp asks for the connection, writes .env, restarts MedUI and
    checks the login is read-only. By hand: put this practice's read-only BP account in .env (BPSDB_HOST, BPSDB_USER,
    BPSDB_PASSWORD). BP usually runs as a named instance: in .env write it with ONE backslash,
    BPSDB_HOST=192.0.2.10\BPSINSTANCE (on a bash command line it needs two, or quotes). Put a
    password containing \$, #, spaces or quotes in single quotes. Many BP servers use a
    self-signed certificate; if the connection fails with a certificate error,
    BPSDB_TRUST_SERVER_CERTIFICATE=true is the usual setting on the practice network. Then: docker compose -p $PROJECT --profile app up -d --force-recreate app$BP_CAUTION
$HTTPS_NOTE
  - OCR: in Setup -> External Sources, add LiteParse at http://liteparse:5707 and press Test.
  - AI: AI_ENABLED=true in .env, then recreate the app (command above), add a provider and
    models in Setup, and review and activate the draft workflows (docs/seed-data.md).
  - Step by step, with update and recovery commands: the Administrator setup guide,
    docs/setup-guide.md, also in the app at Admin -> Application Setup.
  - Backups: docs/operations.md.

  Running this script again is safe: existing settings, data and secrets are kept.
EOF
