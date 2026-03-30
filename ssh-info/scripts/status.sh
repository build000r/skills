#!/usr/bin/env bash

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
MODES_DIR="$SCRIPT_DIR/../modes"
MODE_FILE="${SSH_INFO_MODE_FILE:-$MODES_DIR/config.sh}"
LOCAL_HEALTH_CHECKS=()
PROD_HEALTH_CHECKS=()

usage() {
  cat <<'EOF'
Usage: status.sh local|prod

Reads private configuration from modes/config.sh.

Expected mode variables:
  STATUS_REMOTE_SSH      optional SSH target for prod checks
  LOCAL_HEALTH_CHECKS    bash array of "Label|URL"
  PROD_CONTAINER_FILTER  optional egrep pattern for container summary
  PROD_HEALTH_CHECKS     bash array of "Label|Container|URL"
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

MODE="$1"

if [[ ! -f "$MODE_FILE" ]]; then
  echo "Missing ssh-info mode file: $MODE_FILE" >&2
  echo "Copy references/mode-template.md into modes/config.sh and fill in your values." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$MODE_FILE"

run_prod() {
  if [[ -n "${STATUS_REMOTE_SSH:-}" ]]; then
    ssh "$STATUS_REMOTE_SSH" "$@"
  else
    bash -lc "$*"
  fi
}

check_health() {
  local label="$1"
  local url="$2"
  local status
  status="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo 000)"
  if [[ "$status" == "200" ]]; then
    printf '  [ok]   %-24s %s\n' "$label" "$url"
  else
    printf '  [fail] %-24s %s (HTTP %s)\n' "$label" "$url" "$status"
  fi
}

check_container_health() {
  local label="$1"
  local container="$2"
  local url="$3"
  local status
  status="$(run_prod "docker exec $container sh -lc 'curl -s -o /dev/null -w \"%{http_code}\" --connect-timeout 3 --max-time 5 \"$url\"'" 2>/dev/null || echo 000)"
  status="$(printf '%s' "$status" | tail -n1 | tr -d '[:space:]')"
  if [[ "$status" == "200" ]]; then
    printf '  [ok]   %-24s %s (%s)\n' "$label" "$url" "$container"
  else
    printf '  [fail] %-24s %s (%s, HTTP %s)\n' "$label" "$url" "$container" "$status"
  fi
}

print_local_health() {
  echo "=== Local / Known Health Checks ==="
  if [[ ${#LOCAL_HEALTH_CHECKS[@]} -eq 0 ]]; then
    echo "  No LOCAL_HEALTH_CHECKS configured"
    return
  fi
  local row label url
  for row in "${LOCAL_HEALTH_CHECKS[@]}"; do
    IFS='|' read -r label url <<<"$row"
    check_health "$label" "$url"
  done
}

print_prod_status() {
  echo "=== Container Status ==="
  local filter="${PROD_CONTAINER_FILTER:-}"
  if [[ -n "$filter" ]]; then
    run_prod "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E '$filter' || true"
  else
    echo "  No PROD_CONTAINER_FILTER configured"
  fi
  echo
  echo "=== Prod Health Checks ==="
  if [[ ${#PROD_HEALTH_CHECKS[@]} -eq 0 ]]; then
    echo "  No PROD_HEALTH_CHECKS configured"
    return
  fi
  local row label container url
  for row in "${PROD_HEALTH_CHECKS[@]}"; do
    IFS='|' read -r label container url <<<"$row"
    check_container_health "$label" "$container" "$url"
  done
}

case "$MODE" in
  local)
    print_local_health
    ;;
  prod)
    print_prod_status
    ;;
  *)
    usage
    exit 1
    ;;
esac
