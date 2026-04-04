#!/usr/bin/env bash

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
LEGACY_MODE_FILE="${DEV_SANITY_MODE_FILE:-$SCRIPT_DIR/../modes/config.sh}"
CHECK_FILTER="all"
FAILURES=0
CHECKS_RUN=0
TARGET_CWD="${PWD}"

usage() {
  cat <<'EOF'
Usage: sanity_check.sh [--config /abs/path/to/context.yaml] [--repos-only|--env-only|--docker-only|--health-only]

Resolves configuration from skillbox client overlay (dev_sanity section).
Falls back to legacy modes/config.sh if no overlay matches.

Options:
  --config PATH       Use a specific context.yaml file (sets SKILLBOX_CLIENT_CONTEXT).
  --cwd PATH          Override the working directory for overlay matching.
  --mode-file PATH    (legacy) Read configuration from a shell config file.
  --repos-only        Check repo paths only.
  --env-only          Check env files only.
  --docker-only       Check Docker containers only.
  --health-only       Check HTTP health endpoints only.
  -h, --help          Show this help text.
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
      --config)
        [[ $# -ge 2 ]] || { echo "--config requires a path" >&2; usage; exit 1; }
        export SKILLBOX_CLIENT_CONTEXT="$2"
        shift 2
        ;;
      --cwd)
        [[ $# -ge 2 ]] || { echo "--cwd requires a path" >&2; usage; exit 1; }
        TARGET_CWD="$2"
        shift 2
        ;;
      --mode-file)
        [[ $# -ge 2 ]] || { echo "--mode-file requires a path" >&2; usage; exit 1; }
        LEGACY_MODE_FILE="$2"
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

have_command() {
  command -v "$1" >/dev/null 2>&1
}

load_config() {
  # Initialize arrays
  declare -ag DEV_SANITY_REPOS=()
  declare -ag DEV_SANITY_ENV_FILES=()
  declare -ag DEV_SANITY_CONTAINERS=()
  declare -ag DEV_SANITY_HEALTH_URLS=()

  # Try overlay resolver first
  local resolver="$SCRIPT_DIR/resolve_sanity.py"
  if [[ -f "$resolver" ]] && have_command python3; then
    local shell_output
    if shell_output="$(python3 "$resolver" "$TARGET_CWD" --format shell 2>/dev/null)"; then
      eval "$shell_output"
      return 0
    fi
  fi

  # Fall back to legacy modes/config.sh
  if [[ -f "$LEGACY_MODE_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$LEGACY_MODE_FILE"
    return 0
  fi

  echo "No dev-sanity config found." >&2
  echo "Options:" >&2
  echo "  1. Add a dev_sanity section to your skillbox client overlay" >&2
  echo "  2. Create a legacy modes/config.sh file" >&2
  echo "  3. Pass --config /path/to/context.yaml" >&2
  exit 1
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
load_config

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
