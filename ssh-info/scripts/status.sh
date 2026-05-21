#!/usr/bin/env bash

set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/.."
SHARED_SCRIPTS="$SKILL_DIR/../_shared/scripts"
LOCAL_HEALTH_CHECKS=()
PROD_HEALTH_CHECKS=()
SSH_CONNECT_TIMEOUT_SECONDS="${SSH_CONNECT_TIMEOUT_SECONDS:-8}"
ssh_identity_file=""
ssh_identity_args=()

cleanup() {
  if [[ -n "$ssh_identity_file" ]]; then
    rm -f "$ssh_identity_file"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: status.sh local|prod [service_id]

Resolves configuration from the skillbox client overlay (via resolve_context.py).

Overlay deploy keys used:
  droplet_ssh              SSH target for prod checks
  services.*.compose_service   container name filter
  services.*.health_url    public health URL for local checks
  services.*.internal_port container-local health port
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

MODE="$1"
STATUS_SERVICE="${2:-${STATUS_SERVICE:-}}"
export STATUS_SERVICE

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
  if [[ -n "${DO_DROPLET_IP:-}" ]]; then
    if [[ -z "${DO_SSH_USER:-}" ]]; then
      echo "DO_SSH_USER is required when DO_DROPLET_IP overrides droplet_ssh" >&2
      exit 1
    fi
    STATUS_REMOTE_SSH="${DO_SSH_USER}@${DO_DROPLET_IP}"
  fi

  # Build container filter from service names. For Compose services, the
  # service name is often generic ("api"); prefer the concrete runtime
  # container/alias when the overlay provides one.
  local services_filter
  services_filter="$(printf '%s' "$json" | python3 -c "
import sys, json
import os
d = json.load(sys.stdin)
svcs = d.get('services', {})
names = ['NAMES']
generic = {'api', 'app', 'web', 'worker', 'db', 'redis'}
target = os.environ.get('STATUS_SERVICE', '')
for service_id, s in svcs.items():
    if target and service_id != target:
        continue
    for key in (
        'container_name',
        'upstream_container',
        'worker_container',
        'db_container',
        'redis_container',
    ):
        name = s.get(key) or ''
        if name:
            names.append(name)
    service_name = s.get('compose_service') or ''
    if service_name and service_name not in generic:
        names.append(service_name)
print('(' + '|'.join(names) + ')')
" 2>/dev/null)" || true
  PROD_CONTAINER_FILTER="${services_filter:-}"

  # Build LOCAL_HEALTH_CHECKS from service health URLs
  local checks
  checks="$(printf '%s' "$json" | python3 -c "
import sys, json
import os
d = json.load(sys.stdin)
target = os.environ.get('STATUS_SERVICE', '')
for service_id, s in d.get('services', {}).items():
    if target and service_id != target:
        continue
    label = s.get('label') or service_id
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
import os
d = json.load(sys.stdin)
target = os.environ.get('STATUS_SERVICE', '')
for service_id, s in d.get('services', {}).items():
    if target and service_id != target:
        continue
    label = s.get('label') or service_id
    container = s.get('container_name') or s.get('upstream_container') or ''
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

prepare_ssh_identity() {
  ssh_identity_args=()
  if [[ -z "${DO_SSH_PRIVATE_KEY_B64:-}" ]]; then
    return 0
  fi

  ssh_identity_file="$(mktemp)"
  chmod 600 "$ssh_identity_file"
  if python3 - "$ssh_identity_file" <<'PY'
import base64
import os
import sys

try:
    decoded = base64.b64decode(os.environ["DO_SSH_PRIVATE_KEY_B64"], validate=True)
except Exception:
    sys.exit(1)

with open(sys.argv[1], "wb") as handle:
    handle.write(decoded)
PY
  then
    ssh_identity_args=(-i "$ssh_identity_file")
  else
    echo "invalid DO_SSH_PRIVATE_KEY_B64" >&2
    rm -f "$ssh_identity_file"
    ssh_identity_file=""
    exit 1
  fi
}

# --- Check functions ----------------------------------------------------------

run_prod() {
  if [[ -n "${STATUS_REMOTE_SSH:-}" ]]; then
    ssh -o BatchMode=yes -o ConnectTimeout="$SSH_CONNECT_TIMEOUT_SECONDS" "${ssh_identity_args[@]}" "$STATUS_REMOTE_SSH" "$@"
  else
    bash -lc "$*"
  fi
}

shell_quote() {
  python3 - "$1" <<'PY'
import shlex
import sys

print(shlex.quote(sys.argv[1]))
PY
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
  local probe quoted_probe quoted_container quoted_url
  probe="$(cat <<'SH'
url="$1"
if command -v curl >/dev/null 2>&1; then
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "$url"
elif command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  py_bin="$(command -v python3 2>/dev/null || command -v python)"
  "$py_bin" - "$url" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        print(response.status, end="")
except Exception:
    print("000", end="")
PY
else
  printf '000'
fi
SH
)"
  quoted_probe="$(shell_quote "$probe")"
  quoted_container="$(shell_quote "$container")"
  quoted_url="$(shell_quote "$url")"
  status="$(run_prod "docker exec $quoted_container sh -lc $quoted_probe sh $quoted_url" 2>/dev/null || echo 000)"
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
    run_prod "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E '^$filter[[:space:]]' || true"
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
    prepare_ssh_identity
    print_prod_status
    ;;
  *)
    usage
    exit 1
    ;;
esac
