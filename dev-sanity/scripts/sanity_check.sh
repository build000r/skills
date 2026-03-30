#!/usr/bin/env bash

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
MODE_FILE="${DEV_SANITY_MODE_FILE:-$SCRIPT_DIR/../modes/config.sh}"
CHECK_FILTER="all"
FAILURES=0
CHECKS_RUN=0

usage() {
  cat <<'EOF'
Usage: sanity_check.sh [--mode-file /abs/path/to/config.sh] [--repos-only|--env-only|--docker-only|--health-only]

Reads private configuration from modes/config.sh by default.

Options:
  --mode-file PATH  Read configuration from PATH.
  --repos-only      Check repo paths only.
  --env-only        Check env files only.
  --docker-only     Check Docker containers only.
  --health-only     Check HTTP health endpoints only.
  -h, --help        Show this help text.

Mode file arrays (all optional):
  DEV_SANITY_REPOS=("label|/abs/path")
  DEV_SANITY_ENV_FILES=("label|/abs/path/.env")
  DEV_SANITY_CONTAINERS=("label|container-name")
  DEV_SANITY_HEALTH_URLS=("label|http://localhost:8000/health")
EOF
}

pass() { printf '  [ok]   %s\n' "$1"; }
fail() {
  printf '  [fail] %s\n' "$1"
  FAILURES=$((FAILURES + 1))
}
note() { printf '  [note] %s\n' "$1"; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode-file)
        if [[ $# -lt 2 ]]; then
          echo "--mode-file requires a path" >&2
          usage
          exit 1
        fi
        MODE_FILE="$2"
        shift 2
        ;;
      --repos-only|--env-only|--docker-only|--health-only)
        if [[ "$CHECK_FILTER" != "all" ]]; then
          echo "Only one focused mode can be selected at a time" >&2
          usage
          exit 1
        fi
        CHECK_FILTER="$1"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage
        exit 1
        ;;
    esac
  done
}

ensure_mode_file() {
  if [[ ! -f "$MODE_FILE" ]]; then
    echo "Missing dev-sanity mode file: $MODE_FILE" >&2
    echo "Copy references/mode-template.md into modes/config.sh and fill in your values." >&2
    exit 1
  fi
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

load_mode() {
  declare -ag DEV_SANITY_REPOS=()
  declare -ag DEV_SANITY_ENV_FILES=()
  declare -ag DEV_SANITY_CONTAINERS=()
  declare -ag DEV_SANITY_HEALTH_URLS=()
  # shellcheck source=/dev/null
  source "$MODE_FILE"
}

check_repos() {
  echo "=== Repos ==="
  CHECKS_RUN=$((CHECKS_RUN + 1))
  local row label path
  if [[ ${#DEV_SANITY_REPOS[@]} -eq 0 ]]; then
    note "No repos configured"
    return
  fi
  for row in "${DEV_SANITY_REPOS[@]:-}"; do
    IFS='|' read -r label path <<<"$row"
    if [[ -d "$path" ]]; then
      pass "$label -> $path"
    else
      fail "$label missing at $path"
    fi
  done
}

check_env_files() {
  echo "=== Env Files ==="
  CHECKS_RUN=$((CHECKS_RUN + 1))
  local row label path
  if [[ ${#DEV_SANITY_ENV_FILES[@]} -eq 0 ]]; then
    note "No env files configured"
    return
  fi
  for row in "${DEV_SANITY_ENV_FILES[@]:-}"; do
    IFS='|' read -r label path <<<"$row"
    if [[ -f "$path" ]]; then
      pass "$label -> $path"
    else
      fail "$label missing at $path"
    fi
  done
}

check_containers() {
  echo "=== Containers ==="
  CHECKS_RUN=$((CHECKS_RUN + 1))
  local row label container
  if [[ ${#DEV_SANITY_CONTAINERS[@]} -eq 0 ]]; then
    note "No containers configured"
    return
  fi
  if ! have_command docker; then
    fail "Docker CLI is not installed or not on PATH"
    return
  fi
  for row in "${DEV_SANITY_CONTAINERS[@]:-}"; do
    IFS='|' read -r label container <<<"$row"
    if docker ps --format '{{.Names}}' | grep -qx "$container"; then
      pass "$label -> $container"
    else
      fail "$label missing container $container"
    fi
  done
}

check_health_urls() {
  echo "=== Health Checks ==="
  CHECKS_RUN=$((CHECKS_RUN + 1))
  local row label url status
  if [[ ${#DEV_SANITY_HEALTH_URLS[@]} -eq 0 ]]; then
    note "No health endpoints configured"
    return
  fi
  if ! have_command curl; then
    fail "curl is not installed or not on PATH"
    return
  fi
  for row in "${DEV_SANITY_HEALTH_URLS[@]:-}"; do
    IFS='|' read -r label url <<<"$row"
    status="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo 000)"
    if [[ "$status" == "200" ]]; then
      pass "$label -> $url"
    else
      fail "$label -> $url (HTTP $status)"
    fi
  done
}

parse_args "$@"
ensure_mode_file
load_mode

case "$CHECK_FILTER" in
  --repos-only) check_repos ;;
  --env-only) check_env_files ;;
  --docker-only) check_containers ;;
  --health-only) check_health_urls ;;
  all)
    check_repos
    check_env_files
    check_containers
    check_health_urls
    ;;
esac

if [[ "$CHECKS_RUN" -eq 0 ]]; then
  fail "No checks ran"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  exit 1
fi
