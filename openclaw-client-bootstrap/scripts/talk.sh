#!/usr/bin/env bash
set -euo pipefail

# talk.sh — Talk to OpenClaw agents, tail their logs, or SSH into the server.
#
# Reads claw config from references/deployed-instances.md automatically.
#
# MODES
#   --list                             List claws and their live agent IDs
#   --message "text"                   Send a message (auto-resumes last session per claw)
#   --tail                             Tail service logs (live follow, Ctrl-C to stop)
#   --logs [N]                         Print last N log lines (default: 50)
#   --ssh                              Open SSH shell to the droplet
#   --health                           Run health checks for one or more claws
#
# OPTIONS
#   --claw <name>                      Target claw (default: first/primary claw)
#   --agent <id>                       Agent ID override (auto-discovered if not set)
#   --session-id <id>                  Use a specific session (overrides saved session)
#   --new                              Start a fresh session (ignore saved session)
#   --thinking <level>                 off|minimal|low|medium|high (default: off)
#   --host <ip>                        Override SSH target (ignores deployed-instances.md)
#   --ssh-user <user>                  SSH login user (default: openclaw)
#   --ssh-fallback-users <csv>         Fallback SSH users for --health (default: root)
#   --require-root-proof               For --health, fail if SSH/UFW checks are not root-verified
#   --json                             JSON output for --health
#   --emit-logs                        Write --health output to .run/logs
#   --log-dir <path>                   Override OpenClaw health log dir for --emit-logs
#   --log-prefix <name>                Log filename prefix (default: openclaw)
#
# SESSION PERSISTENCE
#   Sessions are saved per-claw in ~/.cache/openclaw-talk/<claw>.session
#   Each --message auto-resumes the last session. Use --new to start fresh.
#
# POSITIONAL SHORTHAND
#   talk.sh example-claw "message"  Equivalent to --claw example-claw --message "message"
#
# EXAMPLES
#   talk.sh --list
#   talk.sh --claw my-claw --message "hello"                 # auto-resumes last thread
#   talk.sh --claw example-claw --message "follow up"     # continues same thread
#   talk.sh --claw example-claw --new --message "fresh start"
#   talk.sh --claw example-claw --tail
#   talk.sh --claw example-claw --logs 100
#   talk.sh --ssh
#   talk.sh --claw example-claw --ssh     # SSH with env vars pre-loaded for that claw
#   talk.sh --health --require-root-proof --json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTANCES_FILE="${SCRIPT_DIR}/../references/deployed-instances.md"
PRIMARY_USER="openclaw"
PRIMARY_BIN="/home/${PRIMARY_USER}/.npm-global/bin/openclaw"
SSH_OPTS=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

MODE=""
CLAW_NAME=""
JSON_OUTPUT="0"
EMIT_LOGS="0"
LOG_DIR_OVERRIDE=""
LOG_PREFIX="openclaw"
AGENT_ID=""
SESSION_ID=""
NEW_SESSION="false"
MESSAGE=""
THINKING="off"
LOG_LINES="50"
HOST_OVERRIDE=""
SSH_LOGIN_USER="${SSH_LOGIN_USER:-openclaw}"
SSH_FALLBACK_USERS="${SSH_FALLBACK_USERS:-root}"
REQUIRE_ROOT_PROOF="0"
SESSION_DIR="${HOME}/.cache/openclaw-talk"
HEALTH_FAIL_COUNT=0
HEALTH_WARN_COUNT=0

# ── Parse arguments ──────────────────────────────────────────────────────────

usage() { sed -n '4,30p' "$0" | sed 's/^# //; s/^#$//'; exit 0; }

  while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)       MODE="list"; shift ;;
    --message|-m) MODE="message"; MESSAGE="${2:?--message requires text}"; shift 2 ;;
    --tail)       MODE="tail"; shift ;;
    --logs)       MODE="logs"; LOG_LINES="${2:-50}"; shift 2 ;;
    --ssh)        MODE="ssh"; shift ;;
    --health)     MODE="health"; shift ;;
    --json)       JSON_OUTPUT="1"; shift ;;
    --emit-logs)  EMIT_LOGS="1"; shift ;;
    --log-dir)    LOG_DIR_OVERRIDE="${2:?--log-dir requires a path}"; shift 2 ;;
    --log-prefix) LOG_PREFIX="${2:?--log-prefix requires a value}"; shift 2 ;;
    --claw)       CLAW_NAME="${2:?--claw requires a name}"; shift 2 ;;
    --agent)      AGENT_ID="${2:?--agent requires an id}"; shift 2 ;;
    --session-id) SESSION_ID="${2:?--session-id requires a value}"; shift 2 ;;
    --new)        NEW_SESSION="true"; shift ;;
    --thinking)   THINKING="${2:-off}"; shift 2 ;;
    --host)       HOST_OVERRIDE="${2:?--host requires an ip}"; shift 2 ;;
    --ssh-user)   SSH_LOGIN_USER="${2:?--ssh-user requires a user}"; shift 2 ;;
    --ssh-fallback-users)
                  SSH_FALLBACK_USERS="${2:?--ssh-fallback-users requires csv users}"; shift 2 ;;
    --require-root-proof)
                  REQUIRE_ROOT_PROOF="1"; shift ;;
    -h|--help)    usage ;;
    # Positional shorthand: talk.sh [claw-name] [message]
    *)
      if [[ -z "${CLAW_NAME}" ]]; then
        CLAW_NAME="$1"; shift
      elif [[ -z "${MESSAGE}" ]]; then
        MODE="message"; MESSAGE="$1"; shift
      else
        echo "Unexpected argument: $1" >&2; exit 1
      fi
      ;;
  esac
done

[[ -z "${MODE}" ]] && MODE="list"

# ── Parse deployed-instances.md ───────────────────────────────────────────────
# Extracts lines: name|service|openclaw_home|tailscale_ip
# Sections start with "### <name>", fields from bullet lines.

parse_instances() {
  [[ ! -f "${INSTANCES_FILE}" ]] && return

  local ts_ip current name svc config_path
  ts_ip="$(grep -oE '100\.[0-9]+\.[0-9]+\.[0-9]+' "${INSTANCES_FILE}" | head -1 || true)"
  current="" svc="" config_path=""

  flush() {
    if [[ -n "${current}" && -n "${svc}" && -n "${config_path}" ]]; then
      echo "${current}|${svc}|${config_path%/openclaw.json}|${ts_ip}"
    fi
  }

  while IFS= read -r line; do
    if [[ "${line}" =~ ^###[[:space:]](.+)$ ]]; then
      flush
      current="${BASH_REMATCH[1]}" svc="" config_path=""
    elif [[ "${line}" =~ \*\*Services:\*\*[[:space:]]+([a-z0-9_-]+)\.service ]]; then
      svc="${BASH_REMATCH[1]}"
    elif [[ "${line}" == *'**Config path:**'* ]]; then
      config_path="$(echo "${line}" | grep -oE '/[^[:space:]`]+/openclaw\.json' || true)"
    fi
  done < "${INSTANCES_FILE}"
  flush
}

get_claw() {
  local target="${1:-}"
  while IFS='|' read -r name svc home ip; do
    if [[ -z "${target}" || "${name}" == "${target}" ]]; then
      echo "${name}|${svc}|${home}|${ip}"; return
    fi
  done < <(parse_instances)
}

# ── Helpers ───────────────────────────────────────────────────────────────────

ssh_target_for_user() {
  local ip="$1"
  local ssh_user="$2"
  [[ -n "${HOST_OVERRIDE}" ]] && echo "${ssh_user}@${HOST_OVERRIDE}" || echo "${ssh_user}@${ip}"
}

ssh_target() {
  local ip="$1"
  ssh_target_for_user "${ip}" "${SSH_LOGIN_USER}"
}

# Returns env setup string for any claw, including the primary.
# Always sets HOME, OPENCLAW_STATE_DIR, OPENCLAW_CONFIG_PATH, and sources .env
# so OPENCLAW_GATEWAY_TOKEN is available to the CLI when connecting to the
# gateway (the systemd service loads .env, but ad-hoc shells often do not).
claw_env_prefix() {
  local home="$1"
  local app_home="${home%/.openclaw}"
  local runtime_path="${home}/bin:${app_home}/.npm-global/bin:${app_home}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  echo "set -a; [ -f '${home}/.env' ] && . '${home}/.env'; set +a; export HOME='${app_home}' OPENCLAW_STATE_DIR='${home}' OPENCLAW_CONFIG_PATH='${home}/openclaw.json' PATH='${runtime_path}';"
}

remote() {
  local target="$1"; shift
  # -n prevents SSH from reading stdin, which would consume data from
  # any process substitution pipe the caller is iterating over.
  ssh -n "${SSH_OPTS[@]}" "${target}" "$@"
}

remote_timeout() {
  local seconds="$1"; shift
  local target="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${seconds}s" ssh -n "${SSH_OPTS[@]}" "${target}" "$@"
    return $?
  fi

  ssh -n "${SSH_OPTS[@]}" "${target}" "$@" &
  local ssh_pid=$!

  (
    sleep "${seconds}"
    if kill -0 "${ssh_pid}" 2>/dev/null; then
      kill -TERM "${ssh_pid}" 2>/dev/null || true
      sleep 1
      kill -KILL "${ssh_pid}" 2>/dev/null || true
    fi
  ) &
  local killer_pid=$!

  set +e
  wait "${ssh_pid}"
  local rc=$?
  set -e

  kill "${killer_pid}" 2>/dev/null || true
  wait "${killer_pid}" 2>/dev/null || true
  return "${rc}"
}

remote_tty() {
  local target="$1"; shift
  ssh "${SSH_OPTS[@]}" -t "${target}" "$@"
}

discover_agent_id() {
  local target="$1" env_prefix="$2"
  local cmd="${PRIMARY_BIN} agents list 2>/dev/null"
  [[ -n "${env_prefix}" ]] && cmd="${env_prefix} ${cmd}"
  remote_timeout 20 "${target}" "${cmd}" 2>/dev/null \
    | grep '^-' | head -1 | awk '{print $2}' || true
}

require_instances() {
  if [[ ! -f "${INSTANCES_FILE}" ]]; then
    echo "No deployed-instances.md found at:"
    echo "  ${INSTANCES_FILE}"
    echo ""
    echo "Create it from references/deployed-instances.example.md and add your claw details."
    exit 1
  fi
}

json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

resolve_openclaw_log_dir() {
  local default_paths=(
    "${HOME}/.openclaw/logs"
    "${HOME}/.local/state/openclaw/logs"
  )

  if [[ -n "${LOG_DIR_OVERRIDE}" ]]; then
    printf '%s\n' "$LOG_DIR_OVERRIDE"
    return 0
  fi

  local candidate
  for candidate in "${default_paths[@]}"; do
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

log_health_status() {
  local name="$1"
  local line="$2"
  local safe_name
  local log_dir

  safe_name="${name// /-}"
  log_dir="$(resolve_openclaw_log_dir || true)"
  [[ -n "$log_dir" ]] || return 0

  mkdir -p "$log_dir"
  printf '%s\n' "$line" >>"${log_dir}/${LOG_PREFIX}-${safe_name}.log"
}

emit_health() {
  local name="$1"
  local svc="$2"
  local host="$3"
  local status="$4"
  local ssh_status="$5"
  local service_active="$6"
  local service_enabled="$7"
  local config_present="$8"
  local env_present="$9"
  local spaps_set="${10}"
  local spaps_ok="${11}"
  local portal_set="${12}"
  local portal_ok="${13}"
  local error_count="${14}"
  local version="${15}"
  local notes="${16}"
  local ssh_password_auth="${17}"
  local ssh_root_login="${18}"
  local ufw_status="${19}"
  local ufw_service="${20}"
  local fail2ban_service="${21}"
  local security_root_proof="${22}"
  local sshd_root_proof="${23}"
  local ufw_root_proof="${24}"

  local timestamp
  local summary
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  summary="OPENCLAW_HEALTH|ts=${timestamp}|name=${name}|service=${svc}|host=${host}|status=${status}|ssh=${ssh_status}|active=${service_active}|enabled=${service_enabled}|config=${config_present}|env=${env_present}|spaps_set=${spaps_set}|spaps_ok=${spaps_ok}|portal_set=${portal_set}|portal_ok=${portal_ok}|errors=${error_count}|version=${version}|ssh_password_auth=${ssh_password_auth}|ssh_root_login=${ssh_root_login}|ufw_status=${ufw_status}|ufw_service=${ufw_service}|fail2ban_service=${fail2ban_service}|security_root_proof=${security_root_proof}|sshd_root_proof=${sshd_root_proof}|ufw_root_proof=${ufw_root_proof}|notes=${notes}"

  if [[ "${EMIT_LOGS}" == "1" ]]; then
    log_health_status "$name" "$summary" || true
  fi

  if [[ "${JSON_OUTPUT}" == "1" ]]; then
    printf '{"name":"%s","service":"%s","host":"%s","status":"%s","ssh":"%s","service_active":"%s","service_enabled":"%s","config_present":%s,"env_present":%s,"spaps_set":%s,"spaps_ok":%s,"portal_set":%s,"portal_ok":%s,"error_lines":%s,"version":"%s","ssh_password_auth":"%s","ssh_root_login":"%s","ufw_status":"%s","ufw_service":"%s","fail2ban_service":"%s","security_root_proof":"%s","sshd_root_proof":"%s","ufw_root_proof":"%s","notes":"%s"}\n' \
      "$(json_escape "$name")" \
      "$(json_escape "$svc")" \
      "$(json_escape "$host")" \
      "$(json_escape "$status")" \
      "$(json_escape "$ssh_status")" \
      "$(json_escape "$service_active")" \
      "$(json_escape "$service_enabled")" \
      "$config_present" \
      "$env_present" \
      "$spaps_set" \
      "$spaps_ok" \
      "$portal_set" \
      "$portal_ok" \
      "$error_count" \
      "$(json_escape "$version")" \
      "$(json_escape "$ssh_password_auth")" \
      "$(json_escape "$ssh_root_login")" \
      "$(json_escape "$ufw_status")" \
      "$(json_escape "$ufw_service")" \
      "$(json_escape "$fail2ban_service")" \
      "$(json_escape "$security_root_proof")" \
      "$(json_escape "$sshd_root_proof")" \
      "$(json_escape "$ufw_root_proof")" \
      "$(json_escape "$notes")"
    return 0
  fi

  echo "$summary"
}

check_one_claw_health() {
  local name="$1" svc="$2" home="$3" ip="$4"
  local target env_prefix app_home path_prepend
  local -a health_ssh_users=()
  local status="ok"
  local ssh_ok="yes"
  local service_active="unknown"
  local service_enabled="unknown"
  local config_present="0"
  local env_present="0"
  local spaps_set="0"
  local spaps_ok="0"
  local portal_set="0"
  local portal_ok="0"
  local error_count="0"
  local version="unknown"
  local ssh_password_auth="unknown"
  local ssh_root_login="unknown"
  local ufw_status="unknown"
  local ufw_service_active="unknown"
  local fail2ban_service_active="unknown"
  local security_root_proof="none"
  local sshd_root_proof="no"
  local ufw_root_proof="no"
  local notes=()
  local severity=0
  local remote_ctx=""

  health_ssh_users+=("${SSH_LOGIN_USER}")
  if [[ -n "${SSH_FALLBACK_USERS}" ]]; then
    local -a fallback_users=()
    local fallback_user candidate_user existing_user seen
    IFS=',' read -r -a fallback_users <<< "${SSH_FALLBACK_USERS}"
    for fallback_user in "${fallback_users[@]}"; do
      candidate_user="${fallback_user//[[:space:]]/}"
      [[ -n "${candidate_user}" ]] || continue
      seen=0
      for existing_user in "${health_ssh_users[@]}"; do
        if [[ "${existing_user}" == "${candidate_user}" ]]; then
          seen=1
          break
        fi
      done
      if [[ "$seen" == "0" ]]; then
        health_ssh_users+=("${candidate_user}")
      fi
    done
  fi

  target="$(ssh_target_for_user "${ip}" "${health_ssh_users[0]}")"
  env_prefix="$(claw_env_prefix "${home}")"
  app_home="${home%/.openclaw}"
  path_prepend="${app_home}/.npm-global/bin:${app_home}/.local/bin:/home/openclaw/.npm-global/bin:/home/openclaw/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

  if [[ -n "${env_prefix}" ]]; then
    remote_ctx="${env_prefix} "
  fi

  local ssh_ready=0
  local ssh_user_target
  for ssh_user_target in "${health_ssh_users[@]}"; do
    local candidate_target
    candidate_target="$(ssh_target_for_user "${ip}" "${ssh_user_target}")"
    if remote "${candidate_target}" "echo ok" >/dev/null 2>&1; then
      target="${candidate_target}"
      ssh_ready=1
      break
    fi
  done

  if [[ "$ssh_ready" == "0" ]]; then
    emit_health "${name}" "${svc}" "${target}" "fail" "no" "down" "down" 0 0 0 0 0 0 0 "unreachable" "ssh_unreachable" "unknown" "unknown" "unknown" "unknown" "unknown" "none" "no" "no"
    HEALTH_FAIL_COUNT=$((HEALTH_FAIL_COUNT + 1))
    return 0
  fi

  service_active="$(remote "${target}" "systemctl is-active ${svc}.service 2>/dev/null || echo unknown")"
  service_active="${service_active%$'\r'}"
  service_enabled="$(remote "${target}" "systemctl is-enabled ${svc}.service 2>/dev/null || echo unknown")"
  service_enabled="${service_enabled%$'\r'}"
  config_present="$(remote "${target}" "[ -f '${home}/openclaw.json' ] && echo 1 || echo 0")"
  config_present="${config_present%$'\r'}"
  env_present="$(remote "${target}" "[ -f '${home}/.env' ] && echo 1 || echo 0")"
  env_present="${env_present%$'\r'}"

  if [[ "${service_active}" != "active" ]]; then
    severity=2
    notes+=("service_not_active")
  fi
  if [[ "${config_present}" != "1" ]]; then
    severity=2
    notes+=("missing_openclaw_json")
  fi
  if [[ "${env_present}" != "1" ]]; then
    severity=2
    notes+=("missing_env")
  fi

  ufw_service_active="$(remote "${target}" "systemctl is-active ufw 2>/dev/null || echo unknown")"
  ufw_service_active="${ufw_service_active%$'\r'}"
  fail2ban_service_active="$(remote "${target}" "systemctl is-active fail2ban 2>/dev/null || echo unknown")"
  fail2ban_service_active="${fail2ban_service_active%$'\r'}"

  if [[ "${ufw_service_active}" != "active" ]]; then
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("ufw_service_not_active")
  fi
  if [[ "${fail2ban_service_active}" != "active" ]]; then
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("fail2ban_service_not_active")
  fi

  local spaps_url portal_url
  spaps_url="$(remote "${target}" "grep '^SPAPS_API_URL=' '${home}/.env' 2>/dev/null | tail -1 | cut -d= -f2- || true")"
  spaps_url="${spaps_url%$'\r'}"
  portal_url="$(remote "${target}" "grep '^UNCLAWG_PORTAL_URL=' '${home}/.env' 2>/dev/null | tail -1 | cut -d= -f2- || true")"
  portal_url="${portal_url%$'\r'}"

  if [[ -n "${spaps_url}" ]]; then
    spaps_set="1"
    if remote "${target}" "${remote_ctx}PATH='${path_prepend}'; curl -s --connect-timeout 3 --max-time 6 \"${spaps_url%/}/health\" >/dev/null 2>&1"; then
      spaps_ok="1"
    else
      spaps_ok="0"
      severity=$((severity + 0))
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("spaps_unreachable")
    fi
  else
    notes+=("spaps_missing")
    [[ "$severity" -lt 1 ]] && severity=1
  fi

  if [[ -n "${portal_url}" ]]; then
    portal_set="1"
    if remote "${target}" "${remote_ctx}PATH='${path_prepend}'; curl -s --connect-timeout 3 --max-time 6 \"${portal_url}\" >/dev/null 2>&1"; then
      portal_ok="1"
    else
      portal_ok="0"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("portal_unreachable")
    fi
  else
    notes+=("portal_missing")
    [[ "$severity" -lt 1 ]] && severity=1
  fi

  error_count="$(remote "${target}" "journalctl -u ${svc}.service -n 200 --no-pager --output=cat 2>/dev/null | grep -ciE 'error|fatal|panic|traceback|exception' || true")"
  error_count="${error_count%$'\r'}"
  if [[ -z "${error_count}" ]]; then
    error_count="0"
  fi
  if (( error_count > 25 )) && (( severity < 1 )); then
    severity=1
    notes+=("recent_error_rate_high")
  fi

  if remote "${target}" "tailscale status --json 2>/dev/null | jq -r '.BackendState // \"unknown\"' 2>/dev/null | grep -xq 'Running'"; then
    :
  else
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("tailscale_not_running")
  fi

  version="$(remote "${target}" "${remote_ctx}PATH='${path_prepend}'; if command -v openclaw >/dev/null 2>&1; then openclaw --version 2>/dev/null | head -1; else echo missing; fi")"
  version="${version%$'\r'}"

  local sshd_effective password_auth_setting root_login_setting ufw_raw
  local sshd_inferred inferred_password_setting inferred_root_setting sshd_unreadable_count
  local password_setting_source="effective" root_setting_source="effective"
  sshd_effective="$(remote "${target}" "sudo -n /usr/sbin/sshd -T 2>/dev/null || sudo -n sshd -T 2>/dev/null || true")"
  if [[ -n "${sshd_effective}" ]]; then
    sshd_root_proof="yes"
  else
    sshd_effective="$(remote "${target}" "/usr/sbin/sshd -T 2>/dev/null || sshd -T 2>/dev/null || true")"
  fi
  sshd_effective="${sshd_effective%$'\r'}"
  password_auth_setting="$(printf '%s\n' "${sshd_effective}" | awk '/^passwordauthentication / {print $2; exit}')"
  root_login_setting="$(printf '%s\n' "${sshd_effective}" | awk '/^permitrootlogin / {print $2; exit}')"

  if [[ -z "${password_auth_setting:-}" || -z "${root_login_setting:-}" ]]; then
    sshd_inferred="$(remote "${target}" "{ cat /etc/ssh/sshd_config 2>/dev/null; for f in /etc/ssh/sshd_config.d/*.conf; do [ -e \"\$f\" ] || continue; [ -r \"\$f\" ] || continue; cat \"\$f\" 2>/dev/null; done; } | awk 'BEGIN{IGNORECASE=1} /^[[:space:]]*#/ {next} /^[[:space:]]*PermitRootLogin[[:space:]]+/ {print \"permitrootlogin \" tolower(\$2)} /^[[:space:]]*PasswordAuthentication[[:space:]]+/ {print \"passwordauthentication \" tolower(\$2)}' || true")"
    sshd_inferred="${sshd_inferred%$'\r'}"
    inferred_password_setting="$(printf '%s\n' "${sshd_inferred}" | awk '/^passwordauthentication / {v=$2} END {print v}')"
    inferred_root_setting="$(printf '%s\n' "${sshd_inferred}" | awk '/^permitrootlogin / {v=$2} END {print v}')"
    sshd_unreadable_count="$(remote "${target}" "count=0; for f in /etc/ssh/sshd_config.d/*.conf; do [ -e \"\$f\" ] || continue; [ -r \"\$f\" ] || count=\$((count+1)); done; echo \"\$count\"")"
    sshd_unreadable_count="${sshd_unreadable_count%$'\r'}"

    if [[ -z "${password_auth_setting:-}" && -n "${inferred_password_setting:-}" ]]; then
      password_auth_setting="${inferred_password_setting}"
      password_setting_source="inferred"
    fi
    if [[ -z "${root_login_setting:-}" && -n "${inferred_root_setting:-}" ]]; then
      root_login_setting="${inferred_root_setting}"
      root_setting_source="inferred"
    fi

    if [[ "${password_setting_source}" == "inferred" || "${root_setting_source}" == "inferred" ]]; then
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("sshd_settings_inferred")
      if [[ "${sshd_unreadable_count:-0}" =~ ^[0-9]+$ ]] && (( sshd_unreadable_count > 0 )); then
        notes+=("sshd_config_partial_visibility")
      fi
    fi
  fi

  case "${password_auth_setting:-}" in
    no)
      ssh_password_auth="disabled"
      ;;
    yes)
      ssh_password_auth="enabled"
      severity=2
      notes+=("ssh_password_auth_enabled")
      ;;
    *)
      ssh_password_auth="unknown"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("ssh_password_auth_unknown")
      ;;
  esac

  case "${root_login_setting:-}" in
    no)
      ssh_root_login="disabled"
      ;;
    prohibit-password|without-password|forced-commands-only)
      ssh_root_login="restricted"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("ssh_root_login_restricted")
      ;;
    yes)
      ssh_root_login="enabled"
      severity=2
      notes+=("ssh_root_login_enabled")
      ;;
    *)
      ssh_root_login="unknown"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("ssh_root_login_unknown")
      ;;
  esac

  ufw_raw="$(remote "${target}" "sudo -n ufw status 2>/dev/null || true")"
  if printf '%s\n' "${ufw_raw}" | grep -qi '^Status:[[:space:]]*(active|inactive)'; then
    ufw_root_proof="yes"
  else
    ufw_raw="$(remote "${target}" "ufw status 2>/dev/null || true")"
  fi
  ufw_raw="${ufw_raw%$'\r'}"
  if printf '%s\n' "${ufw_raw}" | grep -qi '^Status:[[:space:]]*active'; then
    ufw_status="active"
  elif printf '%s\n' "${ufw_raw}" | grep -qi '^Status:[[:space:]]*inactive'; then
    ufw_status="inactive"
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("ufw_inactive")
  elif [[ -n "${ufw_raw}" ]]; then
    ufw_status="unknown"
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("ufw_status_unknown")
  else
    if [[ "${ufw_service_active}" == "active" ]]; then
      ufw_status="active_inferred"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("ufw_status_inferred_from_service")
    else
      ufw_status="unavailable"
      [[ "$severity" -lt 1 ]] && severity=1
      notes+=("ufw_status_unavailable")
    fi
  fi

  if [[ "${sshd_root_proof}" == "yes" && "${ufw_root_proof}" == "yes" ]]; then
    security_root_proof="verified"
  elif [[ "${sshd_root_proof}" == "yes" || "${ufw_root_proof}" == "yes" ]]; then
    security_root_proof="partial"
  else
    security_root_proof="none"
  fi

  if [[ "${security_root_proof}" != "verified" ]]; then
    [[ "$severity" -lt 1 ]] && severity=1
    notes+=("security_root_proof_${security_root_proof}")
    if [[ "${REQUIRE_ROOT_PROOF}" == "1" ]]; then
      severity=2
      notes+=("root_proof_required_but_unavailable")
    fi
  fi

  if [[ "${severity}" -eq 2 ]]; then
    status="fail"
  elif [[ "${severity}" -eq 1 ]]; then
    status="warn"
  else
    status="ok"
  fi

  if [[ "${status}" == "fail" ]]; then
    HEALTH_FAIL_COUNT=$((HEALTH_FAIL_COUNT + 1))
  elif [[ "${status}" == "warn" ]]; then
    HEALTH_WARN_COUNT=$((HEALTH_WARN_COUNT + 1))
  fi

  local note_text
  if (( ${#notes[@]} > 0 )); then
    note_text="$(printf '%s,' "${notes[@]}")"
    note_text="${note_text%,}"
  else
    note_text="ok"
  fi

  emit_health "${name}" "${svc}" "${target}" "${status}" "${ssh_ok}" "${service_active}" "${service_enabled}" "${config_present}" "${env_present}" "${spaps_set}" "${spaps_ok}" "${portal_set}" "${portal_ok}" "${error_count}" "${version}" "${note_text}" "${ssh_password_auth}" "${ssh_root_login}" "${ufw_status}" "${ufw_service_active}" "${fail2ban_service_active}" "${security_root_proof}" "${sshd_root_proof}" "${ufw_root_proof}"
}

do_health() {
  require_instances
  local had_target=0
  HEALTH_FAIL_COUNT=0
  HEALTH_WARN_COUNT=0

  if [[ -n "${CLAW_NAME}" ]]; then
    local info
    info="$(get_claw "${CLAW_NAME}")"
    if [[ -z "${info}" ]]; then
      echo "Claw not found: '${CLAW_NAME}'" >&2
      echo "Run: talk.sh --list" >&2
      exit 1
    fi
    IFS='|' read -r name svc home ip <<< "${info}"
    check_one_claw_health "${name}" "${svc}" "${home}" "${ip}"
    had_target=1
  else
    while IFS='|' read -r name svc home ip; do
      [[ -z "${name}" ]] && continue
      check_one_claw_health "${name}" "${svc}" "${home}" "${ip}"
      had_target=1
    done < <(parse_instances)
  fi

  if [[ "${had_target}" -eq 0 ]]; then
    echo "No claw instances found in deployed-instances.md"
  fi

  if (( HEALTH_FAIL_COUNT > 0 )); then
    return 2
  fi
}

# ── Modes ─────────────────────────────────────────────────────────────────────

do_list() {
  require_instances
  local found=0
  while IFS='|' read -r name svc home ip; do
    found=1
    local target env_prefix
    target="$(ssh_target "${ip}")"
    env_prefix="$(claw_env_prefix "${home}")"

    echo "┌── ${name}"
    echo "│   service : ${svc}.service"
    echo "│   home    : ${home}"
    echo "│   host    : ${target}"
    echo "│   agents  :"

    local cmd="${PRIMARY_BIN} agents list 2>/dev/null"
    [[ -n "${env_prefix}" ]] && cmd="${env_prefix} ${cmd}"
    remote_timeout 25 "${target}" "${cmd}" 2>/dev/null \
      | grep -E '^[-[:space:]]' \
      | sed 's/^/│             /' \
      || echo "│             (could not connect)"
    echo "│"
    echo "│   talk:  talk.sh --claw ${name} --message \"...\""
    echo "│   tail:  talk.sh --claw ${name} --tail"
    echo "│   ssh:   talk.sh --claw ${name} --ssh"
    echo ""
  done < <(parse_instances)

  if [[ "${found}" -eq 0 ]]; then
    echo "No claw instances found in deployed-instances.md"
  fi
}

do_message() {
  require_instances
  local info
  info="$(get_claw "${CLAW_NAME}")"
  if [[ -z "${info}" ]]; then
    echo "Claw not found: '${CLAW_NAME}'" >&2
    echo "Run: talk.sh --list" >&2
    exit 1
  fi

  IFS='|' read -r name svc home ip <<< "${info}"
  local target env_prefix
  target="$(ssh_target "${ip}")"
  env_prefix="$(claw_env_prefix "${home}")"

  # Auto-discover agent ID if not provided
  if [[ -z "${AGENT_ID}" ]]; then
    AGENT_ID="$(discover_agent_id "${target}" "${env_prefix}")"
  fi
  if [[ -z "${AGENT_ID}" ]]; then
    echo "Could not auto-discover agent ID for '${name}'. Use --agent <id>." >&2
    exit 1
  fi

  # Session persistence: load saved session unless --new or --session-id given
  local session_file="${SESSION_DIR}/${name}.session"
  mkdir -p "${SESSION_DIR}"
  if [[ "${NEW_SESSION}" == "true" ]]; then
    rm -f "${session_file}"
    SESSION_ID=""
  elif [[ -z "${SESSION_ID}" && -f "${session_file}" ]]; then
    SESSION_ID="$(cat "${session_file}")"
  fi

  echo "→ ${name} / ${AGENT_ID} @ ${target}"
  if [[ -n "${SESSION_ID}" ]]; then
    echo "  session : ${SESSION_ID}  (resuming — use --new to start fresh)"
  else
    echo "  session : new"
  fi
  [[ "${THINKING}" != "off" ]] && echo "  thinking: ${THINKING}"
  echo ""

  # Build remote command
  local cmd="${PRIMARY_BIN} agent --agent ${AGENT_ID} --json"
  cmd="${cmd} --message $(printf '%q' "${MESSAGE}")"
  [[ -n "${SESSION_ID}" ]] && cmd="${cmd} --session-id ${SESSION_ID}"
  [[ "${THINKING}" != "off" ]] && cmd="${cmd} --thinking ${THINKING}"
  [[ -n "${env_prefix}" ]] && cmd="${env_prefix} ${cmd}"

  # Run, pretty-print, and save the session ID for next time.
  # NOTE: python3 -c takes script as arg; stdin stays connected to the pipe.
  local session_file_arg="${session_file}"
  remote "${target}" "${cmd}" 2>&1 | python3 -c '
import sys, json, os

raw = sys.stdin.read()
session_file = sys.argv[1]
try:
    data = json.loads(raw)
    result = data.get("result", data)
    payloads = result.get("payloads", [])
    for p in payloads:
        text = p.get("text", "")
        if text:
            print(text)
    meta = result.get("meta", {})
    agent_meta = meta.get("agentMeta", {})
    if agent_meta:
        sid   = agent_meta.get("sessionId", "")
        model = agent_meta.get("model", "")
        ms    = meta.get("durationMs", "")
        # Persist session ID for next run
        if sid:
            with open(session_file, "w") as f:
                f.write(sid)
        print()
        print("  session-id :", sid)
        print("  model      :", model)
        print("  duration   :", str(ms) + "ms")
except Exception:
    print(raw)
' "${session_file_arg}"
}

do_tail() {
  require_instances
  local info
  info="$(get_claw "${CLAW_NAME}")"
  if [[ -z "${info}" ]]; then
    echo "Claw not found: '${CLAW_NAME}'. Run: talk.sh --list" >&2
    exit 1
  fi

  IFS='|' read -r name svc home ip <<< "${info}"
  local target
  target="$(ssh_target "${ip}")"

  echo "→ Tailing ${svc}.service @ ${target}  (Ctrl-C to stop)"
  echo ""
  # --all: don't truncate long lines (tool calls, payloads)
  # --output=cat: strip journald timestamp/host prefix, show raw openclaw log lines
  remote_tty "${target}" "journalctl -u ${svc} -f --no-pager --all --output=cat"
}

do_logs() {
  require_instances
  local info
  info="$(get_claw "${CLAW_NAME}")"
  if [[ -z "${info}" ]]; then
    echo "Claw not found: '${CLAW_NAME}'. Run: talk.sh --list" >&2
    exit 1
  fi

  IFS='|' read -r name svc home ip <<< "${info}"
  local target
  target="$(ssh_target "${ip}")"

  echo "→ ${svc}.service — last ${LOG_LINES} lines @ ${target}"
  echo ""
  remote "${target}" "journalctl -u ${svc} -n ${LOG_LINES} --no-pager --all --output=cat"
}

do_ssh() {
  require_instances
  local info
  info="$(get_claw "${CLAW_NAME}")"
  if [[ -z "${info}" ]]; then
    # No named claw — fall back to first instance for plain SSH
    info="$(get_claw "")"
  fi

  if [[ -z "${info}" ]]; then
    echo "No instances found. Add host to deployed-instances.md or use --host <ip>." >&2
    exit 1
  fi

  IFS='|' read -r name svc home ip <<< "${info}"
  local target env_prefix
  target="$(ssh_target "${ip}")"
  env_prefix="$(claw_env_prefix "${home}")"

  if [[ -n "${CLAW_NAME}" && -n "${env_prefix}" ]]; then
    # Drop into a shell with env vars pre-loaded so openclaw commands work immediately
    echo "→ SSH to ${target} with ${name} env loaded"
    echo "  OPENCLAW_STATE_DIR and OPENCLAW_CONFIG_PATH are set"
    echo "  Run: openclaw agents list   or   openclaw agent --agent <id> --message \"...\""
    echo ""
    remote_tty "${target}" "${env_prefix} export PATH=/home/${PRIMARY_USER}/.npm-global/bin:\$PATH; exec bash -l"
  else
    echo "→ SSH to ${target}"
    echo ""
    remote_tty "${target}"
  fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "${MODE}" in
  list)    do_list ;;
  message) do_message ;;
  tail)    do_tail ;;
  logs)    do_logs ;;
  ssh)     do_ssh ;;
  health)  do_health ;;
  *)       echo "Unknown mode: ${MODE}" >&2; exit 1 ;;
esac
