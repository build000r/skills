#!/usr/bin/env bash

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/.."
SHARED_SCRIPTS="$SKILL_DIR/../_shared/scripts"
LOCAL_HEALTH_CHECKS=()
PROD_HEALTH_CHECKS=()

usage() {
  cat <<'EOF'
Usage: status.sh local|prod

Resolves configuration from the skillbox client overlay (via resolve_context.py).

Overlay deploy keys used:
  droplet_ssh              SSH target for prod checks
  services.*.compose_service   container name filter
  services.*.health_url    public health URL for local checks
  services.*.internal_port container-local health port
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

MODE="$1"

# --- Configuration resolution ------------------------------------------------

_resolved_from_overlay=false

try_overlay() {
  # Resolve from skillbox client overlay via resolve_context.py
  if [[ ! -f "$SHARED_SCRIPTS/resolve_context.py" ]]; then
    return 1
  fi

  local json
  json="$(python3 "$SHARED_SCRIPTS/resolve_context.py" "$PWD" --section deploy --format json)" || return 1
  [[ -n "$json" && "$json" != "null" ]] || return 1

  _resolved_from_overlay=true

  # Extract SSH target
  STATUS_REMOTE_SSH="$(printf '%s' "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('droplet_ssh',''))" 2>/dev/null)" || true

  # Build container filter from service names. For Compose services, the
  # service name is often generic ("api"); prefer the concrete runtime
  # container/alias when the overlay provides one.
  local services_filter
  services_filter="$(printf '%s' "$json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
svcs = d.get('services', {})
names = ['NAMES']
for s in svcs.values():
    for key in ('container_name', 'upstream_container', 'compose_service', 'compose_service_worker'):
        name = s.get(key, '')
        if name:
            names.append(name)
print('(' + '|'.join(names) + ')')
" 2>/dev/null)" || true
  PROD_CONTAINER_FILTER="${services_filter:-}"

  # Build LOCAL_HEALTH_CHECKS from service health URLs
  local checks
  checks="$(printf '%s' "$json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('services', {}).values():
    label = s.get('label', 'unknown')
    url = s.get('health_url', '')
    if url:
        print(f'{label}|{url}')
" 2>/dev/null)" || true
  if [[ -n "$checks" ]]; then
    while IFS= read -r line; do
      LOCAL_HEALTH_CHECKS+=("$line")
    done <<< "$checks"
  fi

  # Build PROD_HEALTH_CHECKS from service container + internal port
  local prod_checks
  prod_checks="$(printf '%s' "$json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('services', {}).values():
    label = s.get('label', 'unknown')
    container = s.get('container_name') or s.get('upstream_container') or s.get('compose_service', '')
    port = s.get('internal_port', '')
    if container and port:
        print(f'{label}|{container}|http://localhost:{port}/health')
" 2>/dev/null)" || true
  if [[ -n "$prod_checks" ]]; then
    while IFS= read -r line; do
      PROD_HEALTH_CHECKS+=("$line")
    done <<< "$prod_checks"
  fi
}

if ! try_overlay; then
  echo "ssh-info requires client.context.deploy in a matching skillbox-config overlay." >&2
  exit 1
fi

# --- Check functions ----------------------------------------------------------

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
