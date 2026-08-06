#!/usr/bin/env bash
# One-time, human-gated ChatGPT enrollment on the VPS-hosted Xvfb browser.
# Browser pixels and input cross only an authenticated SSH local forward. The
# remote noVNC and VNC listeners stay on loopback; browser state never moves.

set -euo pipefail
umask 077

readonly COMMAND_NAME="oracle-enroll-forward"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly DEFAULT_HOST="skillbox-portfolio-devbox"
readonly DEFAULT_REMOTE_SCRIPT="/srv/skillbox/repos/skills/deep-research-prompt/assets/scripts/oracle-enroll-forward.sh"
readonly DEFAULT_DISPLAY=":97"
readonly DEFAULT_LOCAL_PORT=6080
readonly DEFAULT_WEB_PORT=6080
readonly DEFAULT_VNC_PORT=5900

SSH_BIN="${ORACLE_ENROLL_SSH_BIN:-ssh}"
NODE_BIN="${ORACLE_ENROLL_NODE_BIN:-node}"
SS_BIN="${ORACLE_ENROLL_SS_BIN:-ss}"
SETSID_BIN="${ORACLE_ENROLL_SETSID_BIN:-setsid}"
HOST="${ORACLE_ENROLL_HOST:-$DEFAULT_HOST}"
REMOTE_SCRIPT="${ORACLE_ENROLL_REMOTE_SCRIPT:-$DEFAULT_REMOTE_SCRIPT}"
DISPLAY_VALUE="${ORACLE_XVFB_DISPLAY:-$DEFAULT_DISPLAY}"
LOCAL_PORT="${ORACLE_ENROLL_LOCAL_PORT:-$DEFAULT_LOCAL_PORT}"
WEB_PORT="${ORACLE_ENROLL_WEB_PORT:-$DEFAULT_WEB_PORT}"
VNC_PORT="${ORACLE_ENROLL_VNC_PORT:-$DEFAULT_VNC_PORT}"
AUTH_MODE="enroll"
OPEN_BROWSER=true
PASSWORD_STDIN=false

CLIENT_STATE_ROOT="${ORACLE_ENROLL_CLIENT_STATE_DIR:-$HOME/.oracle/oracle-enrollment-forward}"
HOST_RUNTIME_ROOT="${ORACLE_SUBAGENT_RUNTIME_DIR:-$HOME/.oracle/oracle-subagent}"
HOST_STATE_ROOT="$HOST_RUNTIME_ROOT/enrollment-forward"
CLIENT_STATE_FILE="$CLIENT_STATE_ROOT/state"
CONTROL_SOCKET="$CLIENT_STATE_ROOT/ssh-control"
HOST_STATE_FILE="$HOST_STATE_ROOT/state"
HOST_VNC_PASSWORD_FILE="$HOST_STATE_ROOT/vnc-password"
HOST_XAUTHORITY="${ORACLE_XAUTHORITY:-$HOME/.oracle/Xauthority}"

fail() {
  local code="$1"
  printf '%s: blocked (%s)\n' "$COMMAND_NAME" "$code" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  oracle-enroll-forward.sh start [--host MAGICDNS] [--reauth] [--no-open]
  oracle-enroll-forward.sh status [--host MAGICDNS]
  oracle-enroll-forward.sh teardown [--host MAGICDNS]

Internal VPS commands:
  oracle-enroll-forward.sh host-start [--display :N] [--auth-mode enroll|reauth]
  oracle-enroll-forward.sh host-status
  oracle-enroll-forward.sh host-stop

start is run on the operator Mac. It starts loopback-only noVNC on the VPS,
starts the explicit enrollment login command there, creates an SSH -L tunnel
over the MagicDNS hostname, and opens the local noVNC page. teardown closes the
SSH control master and stops only this invocation's VPS helper processes.

No browser profile, cookie, token, browser port, or target identifier is copied.
USAGE
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing_dependency"
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && ((1 <= 10#$1 && 10#$1 <= 65535))
}

validate_settings() {
  [[ "$HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || fail "magicdns_hostname_required"
  [[ ! "$HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "magicdns_hostname_required"
  [[ "$REMOTE_SCRIPT" =~ ^/[A-Za-z0-9_./-]+$ ]] || fail "remote_script_invalid"
  [[ "$DISPLAY_VALUE" =~ ^:[0-9]{1,3}$ ]] || fail "display_invalid"
  valid_port "$LOCAL_PORT" || fail "local_port_invalid"
  valid_port "$WEB_PORT" || fail "web_port_invalid"
  valid_port "$VNC_PORT" || fail "vnc_port_invalid"
  [[ "$AUTH_MODE" == "enroll" || "$AUTH_MODE" == "reauth" ]] || fail "auth_mode_invalid"
}

parse_options() {
  while (($# > 0)); do
    case "$1" in
      --host)
        (($# >= 2)) || fail "usage"
        HOST="$2"
        shift 2
        ;;
      --display)
        (($# >= 2)) || fail "usage"
        DISPLAY_VALUE="$2"
        shift 2
        ;;
      --local-port)
        (($# >= 2)) || fail "usage"
        LOCAL_PORT="$2"
        shift 2
        ;;
      --web-port)
        (($# >= 2)) || fail "usage"
        WEB_PORT="$2"
        shift 2
        ;;
      --vnc-port)
        (($# >= 2)) || fail "usage"
        VNC_PORT="$2"
        shift 2
        ;;
      --auth-mode)
        (($# >= 2)) || fail "usage"
        AUTH_MODE="$2"
        shift 2
        ;;
      --password-stdin)
        PASSWORD_STDIN=true
        shift
        ;;
      --reauth)
        AUTH_MODE="reauth"
        shift
        ;;
      --no-open)
        OPEN_BROWSER=false
        shift
        ;;
      *)
        fail "usage"
        ;;
    esac
  done
  validate_settings
}

ensure_private_directory() {
  local directory="$1"
  [[ "$directory" == /* && "$directory" != "/" && "$directory" != "$HOME" ]] || fail "state_path_invalid"
  [[ ! -L "$directory" ]] || fail "state_path_invalid"
  mkdir -p -- "$directory"
  chmod 700 -- "$directory"
}

state_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | head -n 1
}

write_state() {
  local pathname="$1"
  shift
  local temporary="${pathname}.new.$$"
  : >"$temporary"
  chmod 600 -- "$temporary"
  while (($# > 0)); do
    printf '%s=%s\n' "$1" "$2" >>"$temporary"
    shift 2
  done
  mv -f -- "$temporary" "$pathname"
}

port_is_available() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind(("127.0.0.1", port))
PY
}

wait_for_loopback_port() {
  local port="$1"
  local attempt
  for attempt in {1..50}; do
    if python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.create_connection(("127.0.0.1", port), timeout=0.1):
    pass
PY
    then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

process_matches() {
  local pid="$1"
  local marker="$2"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  [[ -r "/proc/$pid/cmdline" ]] || return 1
  tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq -- "$marker"
}

stop_process() {
  local pid="$1"
  local marker="$2"
  process_matches "$pid" "$marker" || return 0
  kill -TERM "$pid" 2>/dev/null || true
  local attempt
  for attempt in {1..30}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.1
  done
  kill -KILL "$pid" 2>/dev/null || true
}

assert_loopback_listener() {
  local port="$1"
  require_command "$SS_BIN"
  local listeners
  listeners="$($SS_BIN -H -ltn "sport = :$port" 2>/dev/null || true)"
  [[ -n "$listeners" ]] || fail "listener_missing"
  [[ "$listeners" == *"127.0.0.1:$port"* ]] || fail "listener_not_loopback"
  [[ "$listeners" != *"0.0.0.0:$port"* && "$listeners" != *"[::]:$port"* ]] || fail "listener_not_loopback"
}

find_novnc_proxy() {
  if [[ -n "${ORACLE_NOVNC_PROXY_BIN:-}" && -x "$ORACLE_NOVNC_PROXY_BIN" ]]; then
    printf '%s\n' "$ORACLE_NOVNC_PROXY_BIN"
    return 0
  fi
  local candidate
  for candidate in \
    "$(command -v novnc_proxy 2>/dev/null || true)" \
    /usr/share/novnc/utils/novnc_proxy \
    /usr/share/novnc/utils/launch.sh \
    "$HOME/.local/share/novnc/utils/novnc_proxy"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

STARTED_PID=""
start_detached() {
  if command -v "$SETSID_BIN" >/dev/null 2>&1; then
    "$SETSID_BIN" "$@" </dev/null >/dev/null 2>&1 &
  else
    "$@" </dev/null >/dev/null 2>&1 &
  fi
  STARTED_PID=$!
}

host_status() {
  if [[ ! -f "$HOST_STATE_FILE" || -L "$HOST_STATE_FILE" ]]; then
    printf '{"ready":false,"reason":"not_started"}\n'
    return 1
  fi
  local x11_pid novnc_pid auth_pid x11_marker novnc_marker auth_marker state_vnc_port state_web_port
  x11_pid="$(state_value "$HOST_STATE_FILE" X11_PID)"
  novnc_pid="$(state_value "$HOST_STATE_FILE" NOVNC_PID)"
  auth_pid="$(state_value "$HOST_STATE_FILE" AUTH_PID)"
  x11_marker="$(state_value "$HOST_STATE_FILE" X11_MARKER)"
  novnc_marker="$(state_value "$HOST_STATE_FILE" NOVNC_MARKER)"
  auth_marker="$(state_value "$HOST_STATE_FILE" AUTH_MARKER)"
  state_vnc_port="$(state_value "$HOST_STATE_FILE" VNC_PORT)"
  state_web_port="$(state_value "$HOST_STATE_FILE" WEB_PORT)"
  local x11_ready=false novnc_ready=false login_running=false
  process_matches "$x11_pid" "$x11_marker" && x11_ready=true
  process_matches "$novnc_pid" "$novnc_marker" && novnc_ready=true
  process_matches "$auth_pid" "$auth_marker" && login_running=true
  if [[ "$x11_ready" == true && "$novnc_ready" == true ]]; then
    if (
      valid_port "$state_vnc_port" &&
      valid_port "$state_web_port" &&
      assert_loopback_listener "$state_vnc_port" &&
      assert_loopback_listener "$state_web_port"
    ) >/dev/null 2>&1; then
      printf '{"ready":true,"loopback_only":true,"login_running":%s}\n' "$login_running"
      return 0
    fi
    printf '{"ready":false,"reason":"listener_not_loopback","login_running":%s}\n' "$login_running"
    return 1
  fi
  printf '{"ready":false,"reason":"helper_stopped","login_running":%s}\n' "$login_running"
  return 1
}

host_stop() {
  if [[ ! -f "$HOST_STATE_FILE" || -L "$HOST_STATE_FILE" ]]; then
    printf '%s: VPS helpers already stopped\n' "$COMMAND_NAME"
    return 0
  fi
  local auth_pid novnc_pid x11_pid auth_marker novnc_marker x11_marker
  auth_pid="$(state_value "$HOST_STATE_FILE" AUTH_PID)"
  novnc_pid="$(state_value "$HOST_STATE_FILE" NOVNC_PID)"
  x11_pid="$(state_value "$HOST_STATE_FILE" X11_PID)"
  auth_marker="$(state_value "$HOST_STATE_FILE" AUTH_MARKER)"
  novnc_marker="$(state_value "$HOST_STATE_FILE" NOVNC_MARKER)"
  x11_marker="$(state_value "$HOST_STATE_FILE" X11_MARKER)"
  stop_process "$auth_pid" "$auth_marker"
  stop_process "$novnc_pid" "$novnc_marker"
  stop_process "$x11_pid" "$x11_marker"
  [[ ! -e "$HOST_VNC_PASSWORD_FILE" ]] || unlink -- "$HOST_VNC_PASSWORD_FILE"
  unlink -- "$HOST_STATE_FILE" 2>/dev/null || true
  printf '%s: VPS helpers stopped\n' "$COMMAND_NAME"
}

host_start() {
  [[ "$(uname -s)" == "Linux" ]] || fail "vps_linux_required"
  require_command python3
  require_command x11vnc
  require_command "$NODE_BIN"
  local novnc_proxy
  novnc_proxy="$(find_novnc_proxy)" || fail "novnc_missing"
  local display_number="${DISPLAY_VALUE#:}"
  [[ -S "/tmp/.X11-unix/X${display_number}" ]] || fail "xvfb_display_missing"
  ensure_private_directory "$HOST_RUNTIME_ROOT"
  ensure_private_directory "$HOST_STATE_ROOT"
  if host_status >/dev/null 2>&1; then
    host_status
    return 0
  fi
  [[ ! -e "$HOST_STATE_FILE" && ! -L "$HOST_STATE_FILE" ]] || unlink -- "$HOST_STATE_FILE"
  port_is_available "$VNC_PORT" || fail "vnc_port_in_use"
  port_is_available "$WEB_PORT" || fail "web_port_in_use"
  [[ -f "$HOST_XAUTHORITY" && ! -L "$HOST_XAUTHORITY" ]] || fail "xauthority_unavailable"
  [[ "$(stat -c '%u:%a' "$HOST_XAUTHORITY" 2>/dev/null || true)" == "$(id -u):600" ]] || fail "xauthority_invalid"

  local vnc_secret=""
  [[ "$PASSWORD_STDIN" == true ]] || fail "vnc_secret_required"
  IFS= read -r vnc_secret || fail "vnc_secret_unavailable"
  [[ "$vnc_secret" =~ ^[A-Za-z0-9_-]{24,128}$ ]] || fail "vnc_secret_invalid"
  x11vnc -storepasswd "$vnc_secret" "$HOST_VNC_PASSWORD_FILE" >/dev/null 2>&1 || {
    unset vnc_secret
    fail "vnc_secret_create_failed"
  }
  unset vnc_secret
  chmod 600 -- "$HOST_VNC_PASSWORD_FILE"
  [[ "$(stat -c '%u:%a' "$HOST_VNC_PASSWORD_FILE" 2>/dev/null || true)" == "$(id -u):600" ]] || fail "vnc_secret_insecure"

  local x11_pid="" novnc_pid="" auth_pid=""
  cleanup_failed_start() {
    [[ -z "$auth_pid" ]] || stop_process "$auth_pid" "$SCRIPT_DIR/oracle-subagent-auth.mjs"
    [[ -z "$novnc_pid" ]] || stop_process "$novnc_pid" "$novnc_proxy"
    [[ -z "$x11_pid" ]] || stop_process "$x11_pid" "x11vnc"
    [[ ! -e "$HOST_VNC_PASSWORD_FILE" ]] || unlink -- "$HOST_VNC_PASSWORD_FILE"
  }
  trap cleanup_failed_start ERR INT TERM

  local -a x11_args=(
    -display "$DISPLAY_VALUE"
    -listen 127.0.0.1
    -rfbport "$VNC_PORT"
    -forever
    -shared
    -rfbauth "$HOST_VNC_PASSWORD_FILE"
    -auth "$HOST_XAUTHORITY"
    -noxdamage
    -quiet
  )
  start_detached x11vnc "${x11_args[@]}"
  x11_pid="$STARTED_PID"
  wait_for_loopback_port "$VNC_PORT" || fail "vnc_start_failed"
  assert_loopback_listener "$VNC_PORT"

  start_detached "$novnc_proxy" \
    --listen "127.0.0.1:$WEB_PORT" \
    --vnc "127.0.0.1:$VNC_PORT"
  novnc_pid="$STARTED_PID"
  wait_for_loopback_port "$WEB_PORT" || fail "novnc_start_failed"
  assert_loopback_listener "$WEB_PORT"

  local -a login_args=("$SCRIPT_DIR/oracle-subagent-auth.mjs" login --json)
  if [[ "$AUTH_MODE" == "enroll" ]]; then
    login_args+=(--enroll-current-account)
  fi
  start_detached "$NODE_BIN" "${login_args[@]}"
  auth_pid="$STARTED_PID"
  sleep 0.2
  process_matches "$auth_pid" "$SCRIPT_DIR/oracle-subagent-auth.mjs" || fail "login_command_failed"

  write_state "$HOST_STATE_FILE" \
    X11_PID "$x11_pid" \
    X11_MARKER x11vnc \
    NOVNC_PID "$novnc_pid" \
    NOVNC_MARKER "$novnc_proxy" \
    AUTH_PID "$auth_pid" \
    AUTH_MARKER "$SCRIPT_DIR/oracle-subagent-auth.mjs" \
    DISPLAY "$DISPLAY_VALUE" \
    WEB_PORT "$WEB_PORT" \
    VNC_PORT "$VNC_PORT"
  trap - ERR INT TERM
  printf '{"ready":true,"loopback_only":true,"login_running":true}\n'
}

client_start() {
  require_command "$SSH_BIN"
  require_command python3
  ensure_private_directory "$CLIENT_STATE_ROOT"
  [[ ! -e "$CLIENT_STATE_FILE" && ! -S "$CONTROL_SOCKET" ]] || fail "already_started"
  port_is_available "$LOCAL_PORT" || fail "local_port_in_use"

  local vnc_secret
  vnc_secret="$(python3 -I - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)" || fail "vnc_secret_create_failed"
  [[ "$vnc_secret" =~ ^[A-Za-z0-9_-]{24,128}$ ]] || fail "vnc_secret_create_failed"
  if ! printf '%s\n' "$vnc_secret" | "$SSH_BIN" -T "$HOST" -- "$REMOTE_SCRIPT" host-start \
    --display "$DISPLAY_VALUE" \
    --web-port "$WEB_PORT" \
    --vnc-port "$VNC_PORT" \
    --auth-mode "$AUTH_MODE" \
    --password-stdin >/dev/null; then
    unset vnc_secret
    fail "vps_helper_start_failed"
  fi

  if ! "$SSH_BIN" \
    -M \
    -S "$CONTROL_SOCKET" \
    -o ControlMaster=yes \
    -o ControlPersist=no \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -fNT \
    -L "127.0.0.1:$LOCAL_PORT:127.0.0.1:$WEB_PORT" \
    "$HOST"; then
    "$SSH_BIN" -T "$HOST" -- "$REMOTE_SCRIPT" host-stop >/dev/null 2>&1 || true
    fail "ssh_forward_failed"
  fi
  "$SSH_BIN" -S "$CONTROL_SOCKET" -O check "$HOST" >/dev/null 2>&1 || fail "ssh_forward_failed"
  write_state "$CLIENT_STATE_FILE" \
    HOST "$HOST" \
    LOCAL_PORT "$LOCAL_PORT" \
    WEB_PORT "$WEB_PORT" \
    REMOTE_SCRIPT "$REMOTE_SCRIPT" \
    VNC_PASSWORD "$vnc_secret"
  unset vnc_secret

  local browser_url="http://127.0.0.1:$LOCAL_PORT/vnc.html?autoconnect=1&resize=scale"
  printf '%s: ready via %s\n' "$COMMAND_NAME" "$HOST"
  printf 'Open: %s\n' "$browser_url"
  printf 'VNC password: stored in private state file %s\n' "$CLIENT_STATE_FILE"
  printf 'Teardown: %s teardown\n' "$0"
  if [[ "$OPEN_BROWSER" == true && "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    open "$browser_url" >/dev/null 2>&1 || true
  fi
}

client_status() {
  if [[ ! -f "$CLIENT_STATE_FILE" || -L "$CLIENT_STATE_FILE" ]]; then
    printf '{"ready":false,"reason":"not_started"}\n'
    return 1
  fi
  local state_host state_remote
  state_host="$(state_value "$CLIENT_STATE_FILE" HOST)"
  state_remote="$(state_value "$CLIENT_STATE_FILE" REMOTE_SCRIPT)"
  [[ "$state_host" == "$HOST" ]] || fail "state_host_mismatch"
  "$SSH_BIN" -S "$CONTROL_SOCKET" -O check "$state_host" >/dev/null 2>&1 || fail "ssh_forward_missing"
  "$SSH_BIN" -T "$state_host" -- "$state_remote" host-status
}

client_teardown() {
  require_command "$SSH_BIN"
  local state_host="$HOST" state_remote="$REMOTE_SCRIPT"
  if [[ -f "$CLIENT_STATE_FILE" && ! -L "$CLIENT_STATE_FILE" ]]; then
    state_host="$(state_value "$CLIENT_STATE_FILE" HOST)"
    state_remote="$(state_value "$CLIENT_STATE_FILE" REMOTE_SCRIPT)"
    [[ "$state_host" == "$HOST" ]] || fail "state_host_mismatch"
  fi
  "$SSH_BIN" -S "$CONTROL_SOCKET" -O exit "$state_host" >/dev/null 2>&1 || true
  "$SSH_BIN" -T "$state_host" -- "$state_remote" host-stop >/dev/null
  [[ ! -e "$CLIENT_STATE_FILE" ]] || unlink -- "$CLIENT_STATE_FILE"
  [[ ! -e "$CONTROL_SOCKET" ]] || unlink -- "$CONTROL_SOCKET"
  printf '%s: tunnel and VPS helpers stopped\n' "$COMMAND_NAME"
}

main() {
  local command="${1:-help}"
  if (($# > 0)); then
    shift
  fi
  case "$command" in
    start)
      parse_options "$@"
      client_start
      ;;
    status)
      parse_options "$@"
      client_status
      ;;
    teardown|stop)
      parse_options "$@"
      client_teardown
      ;;
    host-start)
      OPEN_BROWSER=false
      parse_options "$@"
      host_start
      ;;
    host-status)
      (($# == 0)) || fail "usage"
      validate_settings
      host_status
      ;;
    host-stop)
      (($# == 0)) || fail "usage"
      validate_settings
      host_stop
      ;;
    help|--help|-h)
      usage
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
