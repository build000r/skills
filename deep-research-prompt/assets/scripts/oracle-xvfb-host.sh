#!/bin/bash -p
# Supervise the single trusted ChatGPT browser host on skillbox-portfolio-devbox.
#
# One central box. No Chrome sprawl across the fleet. Hidden-headful under Xvfb
# (true headless is Cloudflare-blocked). Loopback-only CDP (config-driven port).
# Canonical 0700 profile lives only here.
#
# systemd: USER units only (no sudo / no system units).
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
LAUNCHER="${ORACLE_LAUNCHER:-$SCRIPT_DIR/launch-chatgpt-cdp.sh}"
RPC_SERVER="${ORACLE_RPC_SERVER:-$SCRIPT_DIR/oracle-rpc-server.mjs}"
POLICY_BRIDGE="${ORACLE_POLICY_BRIDGE:-/srv/skillbox/repos/opensource/skillbox/.env-manager/manage.py}"
POLICY_ROOT="${ORACLE_POLICY_ROOT:-$(cd "$(dirname "$POLICY_BRIDGE")/.." 2>/dev/null && pwd -P)}"

DISPLAY_NUM="${ORACLE_XVFB_DISPLAY:-97}"
DISPLAY_NAME=":${DISPLAY_NUM}"
PROFILE_ROOT="${ORACLE_BROWSER_PROFILE_DIR:-$HOME/.oracle/browser-profile}"
PROFILE_DIR="${ORACLE_PROFILE_DIRECTORY:-Default}"
RUNTIME_ROOT="${ORACLE_SUBAGENT_RUNTIME_DIR:-$HOME/.oracle/oracle-subagent}"
ORACLE_ROOT="${ORACLE_HOME_DIR:-$HOME/.oracle}"
XAUTHORITY_FILE="${ORACLE_XAUTHORITY:-$ORACLE_ROOT/Xauthority}"
XVFB_BIN="${ORACLE_XVFB_BIN:-$HOME/.local/bin/Xvfb}"
CHROME_BIN="${ORACLE_CHROME_BIN:-$HOME/.local/bin/chrome-wrapper.sh}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
XVFB_UNIT="oracle-xvfb.service"
CHROME_UNIT="oracle-chatgpt-cdp.service"
RPC_UNIT="oracle-rpc.service"
RPC_PORT="${ORACLE_RPC_PORT:-4117}"
WAIT_SECONDS="${ORACLE_BROWSER_WAIT_SECONDS:-45}"

die() {
  local code="$1"
  shift
  printf 'oracle-xvfb-host: %s\n' "$*" >&2
  exit "$code"
}

# Priority: ~/.oracle/config.json cdp_port > ORACLE_CDP_PORT > 9222.
# Host config is the pin (19222 on skillbox-portfolio-devbox) and beats ambient
# overlay env that still exports ORACLE_CDP_PORT=9222. Does not print config
# contents (may hold non-port secrets).
resolve_cdp_port() {
  local config_path="${ORACLE_CONFIG_PATH:-$HOME/.oracle/config.json}"
  local from_config=""
  if [ -f "$config_path" ] && [ -r "$config_path" ]; then
    from_config="$(/usr/bin/python3 -I - "$config_path" <<'PY' 2>/dev/null || true
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(0)
raw = data.get("cdp_port", data.get("cdpPort"))
if isinstance(raw, bool):
    raise SystemExit(0)
if isinstance(raw, float) and raw.is_integer():
    raw = int(raw)
if isinstance(raw, int) and 1 <= raw <= 65535:
    print(raw)
elif isinstance(raw, str) and raw.strip().isdigit():
    value = int(raw.strip())
    if 1 <= value <= 65535:
        print(value)
PY
)"
  fi
  if [ -n "$from_config" ]; then
    printf '%s\n' "$from_config"
    return
  fi
  if [ -n "${ORACLE_CDP_PORT:-}" ]; then
    printf '%s\n' "$ORACLE_CDP_PORT"
    return
  fi
  printf '9222\n'
}

PORT="$(resolve_cdp_port)"
case "$PORT" in
  ''|*[!0-9]*) die 2 "resolved CDP port is not an integer: $PORT" ;;
esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die 2 "CDP port out of range: $PORT"
case "$RPC_PORT" in
  ''|*[!0-9]*) die 2 "RPC port is not an integer" ;;
esac
[ "$RPC_PORT" -ge 1 ] && [ "$RPC_PORT" -le 65535 ] || die 2 "RPC port out of range"

usage() {
  cat <<'EOF'
usage: oracle-xvfb-host.sh <command>

Commands:
  prepare     create 0700 ~/.oracle layout + Chrome profile dirs
  install     write systemd --user units and enable them
  start       start Xvfb + Chrome (user units) and mint a CDP target receipt
  stop        stop Chrome + Xvfb user units
  status      show unit + CDP + profile posture (no secrets)
  doctor      health probe: CDP loopback + launch receipt path
  run-xvfb    foreground Xvfb (ExecStart for oracle-xvfb.service)
  run-chrome  foreground Chrome (ExecStart for oracle-chatgpt-cdp.service)
  run-rpc     foreground tailnet RPC broker (ExecStart for oracle-rpc.service)
  ensure      prepare + install + start + doctor

Port resolution (first wins):
  ~/.oracle/config.json field "cdp_port" (or "cdpPort")
  ORACLE_CDP_PORT env
  default 9222

  On skillbox-portfolio-devbox set cdp_port to 19222 — 9222 is occupied by
  tailscaled and is not reclaimable without root.

Environment:
  ORACLE_CDP_PORT              fallback after config, before default
  ORACLE_CONFIG_PATH           config file (default ~/.oracle/config.json)
  ORACLE_XVFB_DISPLAY          default 97  (DISPLAY=:$n)
  ORACLE_BROWSER_PROFILE_DIR   default $HOME/.oracle/browser-profile
  ORACLE_CHROME_BIN            default $HOME/.local/bin/chrome-wrapper.sh
  ORACLE_XVFB_BIN              default $HOME/.local/bin/Xvfb
  ORACLE_RPC_PORT              default 4117
  ORACLE_POLICY_BRIDGE         policy authority entrypoint
EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die 2 "required command not found: $1"
}

ensure_private_dir() {
  local path="$1"
  if [ ! -e "$path" ]; then
    mkdir -m 700 -p "$path" || die 2 "could not create $path"
  fi
  [ -d "$path" ] || die 2 "not a directory: $path"
  [ ! -L "$path" ] || die 2 "must not be a symlink: $path"
  local owner mode
  owner="$(stat -c '%u' "$path")"
  mode="$(stat -c '%a' "$path")"
  [ "$owner" = "$(id -u)" ] || die 2 "must be owned by current user: $path"
  case "$mode" in
    700|600) ;;
    *)
      chmod 700 "$path" || die 2 "could not chmod 700 $path"
      mode="$(stat -c '%a' "$path")"
      [ "$mode" = "700" ] || die 2 "could not secure $path (mode $mode)"
      ;;
  esac
}

cmd_prepare() {
  ensure_private_dir "$ORACLE_ROOT"
  ensure_private_dir "$PROFILE_ROOT"
  ensure_private_dir "$PROFILE_ROOT/$PROFILE_DIR"
  ensure_private_dir "$RUNTIME_ROOT"
  printf 'oracle-xvfb-host: prepared profile=%s mode=%s runtime=%s\n' \
    "$PROFILE_ROOT" "$(stat -c '%a' "$PROFILE_ROOT")" "$RUNTIME_ROOT"
}

write_unit() {
  local name="$1"
  local body="$2"
  local path="$UNIT_DIR/$name"
  mkdir -p "$UNIT_DIR"
  printf '%s\n' "$body" >"$path"
  chmod 600 "$path"
}

cmd_install() {
  need_cmd systemctl
  [ -x "$0" ] || die 2 "host script not executable: $0"
  [ -x "$LAUNCHER" ] || die 2 "launcher not executable: $LAUNCHER"
  [ -x "$XVFB_BIN" ] || die 2 "Xvfb not executable: $XVFB_BIN"
  [ -x "$CHROME_BIN" ] || die 2 "Chrome not executable: $CHROME_BIN"
  [ -f "$RPC_SERVER" ] || die 2 "RPC server missing: $RPC_SERVER"
  [ -f "$POLICY_BRIDGE" ] || die 2 "policy bridge missing"
  cmd_prepare

  write_unit "$XVFB_UNIT" "[Unit]
Description=Oracle trusted host Xvfb (hidden-headful display for ChatGPT Chrome)
Documentation=file://$SCRIPT_DIR/../../references/oracle-vps-host.md
After=default.target

[Service]
Type=simple
Environment=ORACLE_XVFB_DISPLAY=$DISPLAY_NUM
Environment=ORACLE_XAUTHORITY=$XAUTHORITY_FILE
ExecStart=$SCRIPT_DIR/oracle-xvfb-host.sh run-xvfb
Restart=always
RestartSec=2
KillMode=control-group
TimeoutStopSec=10
NoNewPrivileges=yes
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=default.target
"

  write_unit "$CHROME_UNIT" "[Unit]
Description=Oracle trusted ChatGPT Chrome (hidden-headful CDP on 127.0.0.1:${PORT})
Documentation=file://$SCRIPT_DIR/../../references/oracle-vps-host.md
After=${XVFB_UNIT}
Requires=${XVFB_UNIT}

[Service]
Type=simple
Environment=DISPLAY=${DISPLAY_NAME}
Environment=ORACLE_CDP_PORT=${PORT}
Environment=ORACLE_BROWSER_PROFILE_DIR=${PROFILE_ROOT}
Environment=ORACLE_PROFILE_DIRECTORY=${PROFILE_DIR}
Environment=ORACLE_CHROME_BIN=${CHROME_BIN}
Environment=ORACLE_SUBAGENT_RUNTIME_DIR=${RUNTIME_ROOT}
Environment=XAUTHORITY=${XAUTHORITY_FILE}
ExecStart=$SCRIPT_DIR/oracle-xvfb-host.sh run-chrome
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20
NoNewPrivileges=yes
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=default.target
"

  write_unit "$RPC_UNIT" "[Unit]
Description=Oracle tailnet RPC broker (tagged callers, policy-gated quota)
Documentation=file://$SCRIPT_DIR/../../references/oracle-vps-host.md
After=${CHROME_UNIT}
Requires=${CHROME_UNIT}

[Service]
Type=simple
Environment=ORACLE_RPC_PORT=${RPC_PORT}
Environment=ORACLE_POLICY_BRIDGE=${POLICY_BRIDGE}
Environment=SKILLBOX_STATE_ROOT=${POLICY_ROOT}/.skillbox-state
WorkingDirectory=${POLICY_ROOT}
ExecStart=$SCRIPT_DIR/oracle-xvfb-host.sh run-rpc
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20
NoNewPrivileges=yes
UMask=0077

[Install]
WantedBy=default.target
"

  systemctl --user daemon-reload
  systemctl --user enable "$XVFB_UNIT" "$CHROME_UNIT" "$RPC_UNIT"
  printf 'oracle-xvfb-host: installed user units %s %s %s\n' "$XVFB_UNIT" "$CHROME_UNIT" "$RPC_UNIT"
}

cmd_run_xvfb() {
  [ -x "$XVFB_BIN" ] || die 2 "Xvfb not executable: $XVFB_BIN"
  need_cmd xauth
  cmd_prepare
  local cookie temporary
  temporary="${XAUTHORITY_FILE}.new.$$"
  cookie="$(/usr/bin/python3 -I - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)" || die 2 "could not create Xauthority secret"
  [ "${#cookie}" -eq 32 ] || die 2 "could not create Xauthority secret"
  : >"$temporary"
  chmod 600 "$temporary"
  xauth -f "$temporary" add "$DISPLAY_NAME" . "$cookie" >/dev/null 2>&1 || {
    unset cookie
    rm -f "$temporary"
    die 2 "could not create Xauthority"
  }
  unset cookie
  mv -f "$temporary" "$XAUTHORITY_FILE"
  [ "$(stat -c '%u:%a' "$XAUTHORITY_FILE")" = "$(id -u):600" ] || die 2 "Xauthority is not private"
  exec "$XVFB_BIN" "$DISPLAY_NAME" -screen 0 1280x900x24 -auth "$XAUTHORITY_FILE" -nolisten tcp
}

cmd_run_chrome() {
  [ -x "$CHROME_BIN" ] || die 2 "Chrome not executable: $CHROME_BIN"
  case "${DISPLAY:-}" in
    :[0-9]|:[0-9][0-9]|:[0-9][0-9][0-9]) ;;
    *) die 2 "DISPLAY must be an Xvfb server (got '${DISPLAY:-empty}')" ;;
  esac
  cmd_prepare
  # Hidden-headful: real Chrome windowing under Xvfb, NOT --headless.
  # Loopback CDP only. Profile is the single fleet-canonical auth store.
  exec "$CHROME_BIN" \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE_ROOT" \
    --profile-directory="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-mode \
    --disable-dev-shm-usage \
    --window-position=-32000,-32000 \
    --window-size=1280,900 \
    about:blank
}

resolve_rpc_host() {
  if [ -n "${ORACLE_FLEET_HOST:-}" ]; then
    case "$ORACLE_FLEET_HOST" in
      *.*|*[a-zA-Z]*) printf '%s\n' "$ORACLE_FLEET_HOST"; return ;;
      *) die 2 "ORACLE_FLEET_HOST must be a MagicDNS hostname" ;;
    esac
  fi
  need_cmd tailscale
  tailscale status --json | /usr/bin/python3 -I -c '
import json, sys
self_node = json.load(sys.stdin).get("Self", {})
candidates = [
    (self_node.get("DNSName") or "").rstrip("."),
    (self_node.get("HostName") or "").rstrip("."),
]
for value in candidates:
    if not value or value.replace(".", "").isdigit():
        continue
    print(value)
    raise SystemExit(0)
raise SystemExit(1)
' || die 2 "could not resolve this host MagicDNS name"
}

cmd_run_rpc() {
  [ -f "$RPC_SERVER" ] || die 2 "RPC server missing: $RPC_SERVER"
  [ -f "$POLICY_BRIDGE" ] || die 2 "policy bridge missing"
  local rpc_host
  rpc_host="$(resolve_rpc_host)"
  export SKILLBOX_STATE_ROOT="${SKILLBOX_STATE_ROOT:-$POLICY_ROOT/.skillbox-state}"
  export ORACLE_CDP_PORT="$PORT"
  exec node "$RPC_SERVER" \
    --bind-host "$rpc_host" \
    --port "$RPC_PORT" \
    --artifact-root "$RUNTIME_ROOT/runs" \
    --mode pro \
    --policy-bridge "$POLICY_BRIDGE" \
    --required-peer-tag tag:oracle-client
}

cdp_http_ok() {
  curl -q -fsS --max-time 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1
}

port_listening() {
  ss -tln 2>/dev/null | grep -qE "127\\.0\\.0\\.1:${PORT}[[:space:]]"
}

port_is_dead_listener() {
  # Ghost / foreign listener: TCP accepts then RST, or no HTTP CDP body.
  port_listening || return 1
  cdp_http_ok && return 1
  return 0
}

rpc_http_ok() {
  tailscale status --json | /usr/bin/python3 -I -c '
import json, socket, sys
port = int(sys.argv[1])
status = json.load(sys.stdin)
self_node = status.get("Self") or {}
addresses = self_node.get("TailscaleIPs") or []
if not addresses:
    raise SystemExit(1)
host = (self_node.get("DNSName") or self_node.get("HostName") or "").rstrip(".")
if not host or any(character in host for character in "\r\n"):
    raise SystemExit(1)
with socket.create_connection((addresses[0], port), timeout=3) as connection:
    request = f"GET /healthz HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
    connection.sendall(request.encode("ascii"))
    response = b""
    while len(response) < 65536:
        chunk = connection.recv(4096)
        if not chunk:
            break
        response += chunk
if b" 200 " not in response.split(b"\r\n", 1)[0]:
    raise SystemExit(1)
body = response.split(b"\r\n\r\n", 1)[1]
value = json.loads(body)
if value.get("schema") != "oracle-fleet.health.v1" or value.get("ok") is not True:
    raise SystemExit(1)
if (value.get("service") or {}).get("ready") is not True:
    raise SystemExit(1)
policy = value.get("policy") or {}
if policy.get("ready") is not True or not policy.get("policy_id"):
    raise SystemExit(1)
' "$RPC_PORT" >/dev/null 2>&1
}

wait_for_cdp() {
  local waited=0
  until cdp_http_ok; do
    [ "$waited" -lt "$WAIT_SECONDS" ] || return 1
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

cmd_start() {
  need_cmd systemctl
  need_cmd curl
  need_cmd ss
  cmd_prepare

  if port_is_dead_listener; then
    die 5 "configured CDP port ${PORT} is listening on 127.0.0.1 but is not a live CDP endpoint. Pick a free port in ~/.oracle/config.json cdp_port (or ORACLE_CDP_PORT) and re-run install+start — do not fight foreign sockets (e.g. tailscaled on 9222)"
  fi

  systemctl --user start "$XVFB_UNIT"
  # Give Xvfb a moment before Chrome attaches.
  sleep 1
  systemctl --user start "$CHROME_UNIT"

  if ! wait_for_cdp; then
    systemctl --user --no-pager --full status "$XVFB_UNIT" "$CHROME_UNIT" >&2 || true
    die 3 "CDP did not become ready on 127.0.0.1:${PORT} within ${WAIT_SECONDS}s"
  fi

  # Mint / refresh the exact target receipt the auth doctor consumes.
  DISPLAY="$DISPLAY_NAME" \
    ORACLE_CDP_PORT="$PORT" \
    ORACLE_BROWSER_PROFILE_DIR="$PROFILE_ROOT" \
    ORACLE_PROFILE_DIRECTORY="$PROFILE_DIR" \
    ORACLE_CHROME_BIN="$CHROME_BIN" \
    ORACLE_SUBAGENT_RUNTIME_DIR="$RUNTIME_ROOT" \
  "$LAUNCHER" --json >/dev/null

  systemctl --user start "$RPC_UNIT"
  local rpc_waited=0
  until rpc_http_ok; do
    [ "$rpc_waited" -lt "$WAIT_SECONDS" ] || {
      systemctl --user --no-pager --full status "$RPC_UNIT" >&2 || true
      die 3 "RPC broker did not become live on the tailnet hostname"
    }
    sleep 1
    rpc_waited=$((rpc_waited + 1))
  done

  printf 'oracle-xvfb-host: started display=%s cdp=127.0.0.1:%s profile=%s\n' \
    "$DISPLAY_NAME" "$PORT" "$PROFILE_ROOT"
}

cmd_stop() {
  need_cmd systemctl
  systemctl --user stop "$RPC_UNIT" 2>/dev/null || true
  systemctl --user stop "$CHROME_UNIT" 2>/dev/null || true
  systemctl --user stop "$XVFB_UNIT" 2>/dev/null || true
  printf 'oracle-xvfb-host: stopped\n'
}

cmd_status() {
  need_cmd systemctl
  need_cmd ss
  printf 'host=%s\n' "$(hostname -s 2>/dev/null || hostname)"
  printf 'display=%s\n' "$DISPLAY_NAME"
  printf 'cdp=127.0.0.1:%s\n' "$PORT"
  printf 'profile=%s mode=%s\n' \
    "$PROFILE_ROOT" \
    "$(stat -c '%a' "$PROFILE_ROOT" 2>/dev/null || echo missing)"
  printf 'oracle_root=%s mode=%s\n' \
    "$ORACLE_ROOT" \
    "$(stat -c '%a' "$ORACLE_ROOT" 2>/dev/null || echo missing)"
  printf 'xvfb_unit='
  systemctl --user is-active "$XVFB_UNIT" 2>/dev/null || printf 'inactive\n'
  printf 'chrome_unit='
  systemctl --user is-active "$CHROME_UNIT" 2>/dev/null || printf 'inactive\n'
  printf 'rpc_unit='
  systemctl --user is-active "$RPC_UNIT" 2>/dev/null || printf 'inactive\n'
  if rpc_http_ok; then
    printf 'rpc_health=ok\n'
  else
    printf 'rpc_health=down\n'
  fi
  printf 'listener=\n'
  ss -tln 2>/dev/null | grep -E "127\\.0\\.0\\.1:${PORT}[[:space:]]" || printf '  (none)\n'
  if cdp_http_ok; then
    printf 'cdp_http=ok\n'
  elif port_listening; then
    printf 'cdp_http=dead_listener\n'
  else
    printf 'cdp_http=down\n'
  fi
}

cmd_doctor() {
  need_cmd curl
  need_cmd ss
  need_cmd systemctl
  local ok=1
  if ! port_listening; then
    printf 'oracle-xvfb-host doctor: FAIL listener missing on 127.0.0.1:%s\n' "$PORT"
    ok=0
  else
    printf 'oracle-xvfb-host doctor: ok listener 127.0.0.1:%s\n' "$PORT"
  fi
  if cdp_http_ok; then
    printf 'oracle-xvfb-host doctor: ok cdp /json/version\n'
  else
    printf 'oracle-xvfb-host doctor: FAIL cdp /json/version\n'
    ok=0
  fi
  local mode
  mode="$(stat -c '%a' "$ORACLE_ROOT" 2>/dev/null || echo missing)"
  if [ "$mode" = "700" ]; then
    printf 'oracle-xvfb-host doctor: ok ~/.oracle mode 700\n'
  else
    printf 'oracle-xvfb-host doctor: FAIL ~/.oracle mode=%s (want 700)\n' "$mode"
    ok=0
  fi
  mode="$(stat -c '%a' "$PROFILE_ROOT" 2>/dev/null || echo missing)"
  if [ "$mode" = "700" ]; then
    printf 'oracle-xvfb-host doctor: ok profile mode 700\n'
  else
    printf 'oracle-xvfb-host doctor: FAIL profile mode=%s (want 700)\n' "$mode"
    ok=0
  fi
  # Non-secret bind check: reject non-loopback listeners on PORT.
  if ss -tln 2>/dev/null | grep -E ":${PORT}[[:space:]]" | grep -vE "127\\.0\\.0\\.1:${PORT}[[:space:]]|\\[::1\\]:${PORT}" >/dev/null; then
    printf 'oracle-xvfb-host doctor: FAIL non-loopback bind detected on port %s\n' "$PORT"
    ok=0
  else
    printf 'oracle-xvfb-host doctor: ok loopback-only bind posture\n'
  fi
  if systemctl --user is-active --quiet "$RPC_UNIT" && rpc_http_ok; then
    printf 'oracle-xvfb-host doctor: ok tailnet RPC liveness\n'
  else
    printf 'oracle-xvfb-host doctor: FAIL tailnet RPC liveness\n'
    ok=0
  fi
  [ "$ok" -eq 1 ] || return 1
  printf 'oracle-xvfb-host doctor: READY (CDP reachable; login may still be required)\n'
}

cmd_ensure() {
  cmd_install
  cmd_start
  cmd_doctor
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    prepare) cmd_prepare ;;
    install) cmd_install ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    doctor) cmd_doctor ;;
    run-xvfb) cmd_run_xvfb ;;
    run-chrome) cmd_run_chrome ;;
    run-rpc) cmd_run_rpc ;;
    ensure) cmd_ensure ;;
    -h|--help|help|"") usage; [ -n "$cmd" ] || exit 2 ;;
    *) die 2 "unknown command: $cmd" ;;
  esac
}

main "$@"
