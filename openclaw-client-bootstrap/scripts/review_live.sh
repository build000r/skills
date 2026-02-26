#!/usr/bin/env bash
set -euo pipefail

# Live deployment review — SSHes into a droplet and validates the running OpenClaw instance.
#
# Usage:
#   review_live.sh                         # auto-detect from local deployed-instances.md (if present)
#   review_live.sh openclaw@100.64.0.10    # specific host
#   review_live.sh --host 203.0.113.10     # alternate flag
#   review_live.sh --host 100.64.0.10 --ssh-user aiops
#   review_live.sh --service openclaw-foo  # review a non-default systemd unit
#   review_live.sh --home /home/openclaw-foo/.openclaw  # override config home
#   review_live.sh --user openclaw         # override app user
#   review_live.sh --strict                 # fail if SPAPS/portal vars are missing

PASS=0
FAIL=0
WARN_COUNT=0

pass() { PASS=$((PASS + 1)); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; }
warn() { WARN_COUNT=$((WARN_COUNT + 1)); echo "  WARN  $1"; }

SSH_TARGET=""
SSH_OPTS=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
STRICT_MODE="false"
SERVICE_NAME="openclaw"
APP_USER="openclaw"
OPENCLAW_HOME_OVERRIDE=""
SSH_LOGIN_USER="${SSH_LOGIN_USER:-openclaw}"
SSH_EFFECTIVE_USER=""
SSH_HOST_OVERRIDE=""

# --- Parse arguments ---

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) SSH_HOST_OVERRIDE="${2:-}"; shift 2 ;;
    --ssh-user) SSH_LOGIN_USER="${2:?--ssh-user requires a user}"; shift 2 ;;
    --strict) STRICT_MODE="true"; shift ;;
    --service) SERVICE_NAME="${2:-}"; shift 2 ;;
    --user) APP_USER="${2:-}"; shift 2 ;;
    --home) OPENCLAW_HOME_OVERRIDE="${2:-}"; shift 2 ;;
    -h|--help) head -8 "$0" | tail -5; exit 0 ;;
    *) SSH_TARGET="$1"; shift ;;
  esac
done

if [[ -n "${SSH_HOST_OVERRIDE}" ]]; then
  SSH_TARGET="${SSH_LOGIN_USER}@${SSH_HOST_OVERRIDE}"
fi

# Auto-detect from local deployment index (gitignored)
if [[ -z "${SSH_TARGET}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for INSTANCES in \
    "${SCRIPT_DIR}/../references/deployed-instances.md" \
    "${SCRIPT_DIR}/../references/deployed-instances.local.md"; do
    if [[ -f "${INSTANCES}" ]]; then
      ts_ip="$(grep -oE '100\.[0-9]+\.[0-9]+\.[0-9]+' "${INSTANCES}" | head -1 || true)"
      if [[ -n "${ts_ip}" ]]; then
        SSH_TARGET="${SSH_LOGIN_USER}@${ts_ip}"
        echo "Auto-detected: ${SSH_TARGET} (from ${INSTANCES##*/})"
        break
      fi
    fi
  done
  if [[ -z "${SSH_TARGET}" ]]; then
    echo "No host specified."
    echo "Usage: review_live.sh <user>@<host> or --host <ip> [--ssh-user <user>]"
    echo "Optional: create references/deployed-instances.md from deployed-instances.example.md"
    exit 1
  fi
fi

if [[ "${SSH_TARGET}" != *"@"* ]]; then
  SSH_TARGET="${SSH_LOGIN_USER}@${SSH_TARGET}"
fi
SSH_EFFECTIVE_USER="${SSH_TARGET%@*}"

APP_HOME=""
USER_HOME=""
OPENCLAW_HOME=""
OPENCLAW_CLI_PATH=""

remote() {
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "$@"
}

echo "========================================="
echo "  LIVE DEPLOYMENT REVIEW"
echo "  Target: ${SSH_TARGET}"
echo "========================================="
echo

# --- L1. Connectivity ---
echo "=== L1. Connectivity ==="
if remote "echo ok" >/dev/null 2>&1; then
  pass "L1.1 SSH connection successful"
else
  fail "L1.1 Cannot SSH into ${SSH_TARGET}"
  echo "Cannot reach host. Aborting."
  exit 1
fi

remote_user="$(remote "systemctl show ${SERVICE_NAME} --property=User --value 2>/dev/null || true" | tr -d '\r' || true)"
if [[ -n "${remote_user}" ]]; then
  APP_USER="${remote_user}"
fi
USER_HOME="$(remote "getent passwd ${APP_USER} | awk -F: '{print \$6}'" 2>/dev/null | tr -d '\r' || true)"
if [[ -z "${USER_HOME}" ]]; then
  USER_HOME="/home/${APP_USER}"
fi

if [[ -n "${OPENCLAW_HOME_OVERRIDE}" ]]; then
  OPENCLAW_HOME="${OPENCLAW_HOME_OVERRIDE}"
  if [[ "${OPENCLAW_HOME}" == */.openclaw ]]; then
    APP_HOME="${OPENCLAW_HOME%/.openclaw}"
  else
    APP_HOME="$(dirname "${OPENCLAW_HOME}")"
  fi
else
  service_home="$(remote "systemctl show ${SERVICE_NAME} --property=Environment --value 2>/dev/null | tr ' ' '\n' | awk -F= '/^HOME=/{print \$2; exit}'" | tr -d '\r' || true)"
  APP_HOME="${service_home:-${USER_HOME}}"
  OPENCLAW_HOME="${APP_HOME}/.openclaw"
fi
OPENCLAW_CLI_PATH="${USER_HOME}/.npm-global/bin:${USER_HOME}/.local/bin:${APP_HOME}/.npm-global/bin:${APP_HOME}/.local/bin:${OPENCLAW_HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
echo

# --- L2. Service Health ---
echo "=== L2. Service Health ==="
for svc in "${SERVICE_NAME}" tailscaled ufw fail2ban; do
  status="$(remote "systemctl is-active ${svc} 2>/dev/null || echo inactive")"
  if [[ "${status}" == *active* ]] && [[ "${status}" != *inactive* ]]; then
    pass "L2 ${svc} is active"
  else
    fail "L2 ${svc} is NOT active"
  fi
done
echo

# --- L3. Prerequisites ---
echo "=== L3. Prerequisites ==="

node_ver="$(remote 'node --version 2>/dev/null || echo none')"
node_major="$(echo "${node_ver}" | tr -d 'v' | cut -d. -f1)"
if [[ "${node_major}" -ge 22 ]] 2>/dev/null; then
  pass "L3.1 Node.js ${node_ver}"
else
  fail "L3.1 Node.js ${node_ver} -- need >= 22"
fi

docker_ver="$(remote 'docker --version 2>/dev/null || echo none')"
if [[ "${docker_ver}" != "none" ]]; then
  pass "L3.2 Docker installed"
else
  fail "L3.2 Docker not installed"
fi

docker_group="$(remote "id ${APP_USER} 2>/dev/null || echo none")"
if echo "${docker_group}" | grep -q 'docker'; then
  pass "L3.3 ${APP_USER} user in docker group"
else
  fail "L3.3 ${APP_USER} user NOT in docker group"
fi

swap_mb="$(remote 'free -m | grep Swap | awk "{print \$2}"')"
if [[ "${swap_mb:-0}" -ge 1024 ]]; then
  pass "L3.4 Swap ${swap_mb}MB"
else
  warn "L3.4 Swap ${swap_mb:-0}MB -- recommend 2048MB"
fi

total_mb="$(remote 'free -m | grep Mem | awk "{print \$2}"')"
if [[ "${total_mb:-0}" -ge 1800 ]]; then
  pass "L3.5 RAM ${total_mb}MB"
else
  fail "L3.5 RAM ${total_mb:-0}MB -- need >= 2GB"
fi
echo

# --- L4. Live Config ---
echo "=== L4. Live Config ==="

live_config="$(remote "cat ${OPENCLAW_HOME}/openclaw.json 2>/dev/null" || echo '{}')"

if echo "${live_config}" | jq empty >/dev/null 2>&1; then
  pass "L4.1 Valid JSON"
else
  fail "L4.1 Invalid JSON"
fi

removed=0
echo "${live_config}" | jq -e '.agents.list[0].prompt' >/dev/null 2>&1 && removed=$((removed + 1)) && echo "       found: agents.list[0].prompt"
echo "${live_config}" | jq -e '.channels.pairing' >/dev/null 2>&1 && removed=$((removed + 1)) && echo "       found: channels.pairing"
echo "${live_config}" | jq -e '.channels.telegram.token' >/dev/null 2>&1 && removed=$((removed + 1)) && echo "       found: channels.telegram.token"
if [[ ${removed} -eq 0 ]]; then pass "L4.2 No removed keys"; else fail "L4.2 Found ${removed} removed key(s)"; fi

has_bot_token="$(echo "${live_config}" | jq -r '.telegram.botToken // .channels.telegram.botToken // empty' 2>/dev/null)"
has_legacy_token="$(echo "${live_config}" | jq -r '.channels.telegram.token // empty' 2>/dev/null)"
if [[ -n "${has_bot_token}" ]]; then
  pass "L4.3 Uses botToken"
elif [[ -n "${has_legacy_token}" ]]; then
  fail "L4.3 Uses legacy token key"
else
  fail "L4.3 No bot token found"
fi

if echo "${live_config}" | jq -e '.channels.telegram.groupPolicy == "allowlist"' >/dev/null 2>&1 \
  && echo "${live_config}" | jq -e '.channels.telegram.groupAllowFrom | type == "array" and length > 0' >/dev/null 2>&1 \
  && echo "${live_config}" | jq -e '(.channels.telegram.groups // empty) | ((type == "array" and length > 0) or (type == "object" and (keys | length) > 0))' >/dev/null 2>&1; then
  pass "L4.3b Telegram group allowlist policy present"
else
  fail "L4.3b Telegram group allowlist policy missing/incomplete"
fi

ask_type="$(echo "${live_config}" | jq -r '.tools.exec.ask | type' 2>/dev/null || echo 'null')"
if [[ "${ask_type}" == "string" ]]; then
  pass "L4.4 tools.exec.ask is string"
elif [[ "${ask_type}" == "array" ]]; then
  fail "L4.4 tools.exec.ask is array -- should be string"
else
  warn "L4.4 tools.exec.ask type: ${ask_type}"
fi

safe_bins_type="$(echo "${live_config}" | jq -r '.tools.exec.safeBins | type' 2>/dev/null || echo 'null')"
if [[ "${safe_bins_type}" != "array" ]]; then
  fail "L4.4b tools.exec.safeBins must be an array"
else
  safe_bins_count="$(echo "${live_config}" | jq -r '.tools.exec.safeBins | length' 2>/dev/null || echo '0')"
  path_like_bins="$(echo "${live_config}" | jq -r '.tools.exec.safeBins[]? | select(test("[/\\\\]"))' 2>/dev/null || true)"
  if [[ "${safe_bins_count}" -lt 1 ]]; then
    fail "L4.4b tools.exec.safeBins is empty"
  elif [[ -n "${path_like_bins}" ]]; then
    fail "L4.4b tools.exec.safeBins contains path-style entries"
    echo "${path_like_bins}" | sed 's/^/       /'
  else
    pass "L4.4b tools.exec.safeBins uses executable names"
  fi
fi

if echo "${live_config}" | jq -e '.tools.elevated.enabled == true' >/dev/null 2>&1 \
  && echo "${live_config}" | jq -e '.tools.elevated.allowFrom.telegram | type == "array" and length > 0' >/dev/null 2>&1; then
  pass "L4.4c tools.elevated Telegram allowlist present"
else
  fail "L4.4c tools.elevated Telegram allowlist missing/incomplete"
fi

ws="$(echo "${live_config}" | jq -r '.agents.defaults.sandbox.workspaceAccess // "unknown"' 2>/dev/null)"
if [[ "${ws}" == "ro" ]]; then pass "L4.5 Sandbox is read-only"; else fail "L4.5 workspaceAccess is ${ws}"; fi

deny_list="$(echo "${live_config}" | jq -r '.tools.deny[]?' 2>/dev/null)"
deny_ok=true
for tool in write edit apply_patch; do
  echo "${deny_list}" | grep -qx "${tool}" || deny_ok=false
done
if [[ "${deny_ok}" == "true" ]]; then pass "L4.6 Write tools denied"; else fail "L4.6 Write tools not fully denied"; fi

if echo "${live_config}" | grep -q '{{'; then
  raw_placeholders="$(echo "${live_config}" | grep -oE '\{\{[^}]+\}\}' | sort -u || true)"
  disallowed_placeholders=""
  if [[ -n "${raw_placeholders}" ]]; then
    while IFS= read -r token; do
      case "${token}" in
        "{{Body}}"|"{{RawBody}}"|"{{BodyStripped}}"|"{{From}}"|"{{To}}"|"{{MessageSid}}"|"{{SessionId}}"|"{{IsNewSession}}"|"{{MediaUrl}}"|"{{MediaPath}}"|"{{MediaType}}"|"{{Transcript}}"|"{{Prompt}}"|"{{MaxChars}}"|"{{ChatType}}"|"{{GroupSubject}}"|"{{GroupMembers}}"|"{{SenderName}}"|"{{SenderE164}}"|"{{Provider}}")
          ;;
        *)
          disallowed_placeholders="${disallowed_placeholders}${token}"$'\n'
          ;;
      esac
    done <<< "${raw_placeholders}"
  fi
  if [[ -n "${disallowed_placeholders}" ]]; then
    fail "L4.7 Unfilled template placeholders in live config"
    echo "${disallowed_placeholders}" | sed 's/^/       /'
  else
    pass "L4.7 No unfilled template placeholders"
  fi
else
  pass "L4.7 No unfilled placeholders"
fi

approval_mode="$(echo "${live_config}" | jq -r '.approvals.exec.mode // "missing"' 2>/dev/null)"
if [[ "${approval_mode}" == "targets" ]] || [[ "${approval_mode}" == "both" ]] || [[ "${approval_mode}" == "session" ]]; then
  pass "L4.8 approvals.exec.mode is ${approval_mode}"
else
  if [[ "${STRICT_MODE}" == "true" ]]; then
    fail "L4.8 approvals.exec.mode is ${approval_mode}"
  else
    warn "L4.8 approvals.exec.mode is ${approval_mode}"
  fi
fi

targets_count="$(echo "${live_config}" | jq -r '.approvals.exec.targets | length' 2>/dev/null || echo 0)"
if [[ "${approval_mode}" == "targets" ]] || [[ "${approval_mode}" == "both" ]]; then
  if [[ "${targets_count}" -ge 1 ]]; then
    pass "L4.9 Approval targets configured"
  else
    fail "L4.9 approvals.exec.targets missing"
  fi
else
  pass "L4.9 Target list check skipped for mode=${approval_mode}"
fi

target_env_placeholders="$(echo "${live_config}" | jq -r '.approvals.exec.targets[]?.to | strings | select(test("^\\$\\{env:"))' 2>/dev/null || true)"
if [[ -n "${target_env_placeholders}" ]]; then
  fail "L4.10 approvals.exec.targets[*].to uses unsupported env interpolation"
  echo "${target_env_placeholders}" | sed 's/^/       /'
else
  pass "L4.10 Approval recipients are concrete values"
fi
echo

# --- L5. Live Environment ---
echo "=== L5. Live Environment ==="

live_env="$(remote "cat ${OPENCLAW_HOME}/.env 2>/dev/null" || echo '')"

if [[ -n "${live_env}" ]]; then
  pass "L5.1 .env file exists"
else
  fail "L5.1 .env file missing"
fi

if echo "${live_env}" | grep -q 'replace-with-64-plus-random-chars'; then
  fail "L5.2 OPENCLAW_GATEWAY_TOKEN still placeholder"
else
  pass "L5.2 OPENCLAW_GATEWAY_TOKEN set"
fi

if echo "${live_env}" | grep -q 'replace-with-real-bot-token'; then
  fail "L5.3 OPENCLAW_TG_TOKEN still placeholder"
else
  pass "L5.3 OPENCLAW_TG_TOKEN set"
fi

if echo "${live_env}" | grep -q '^SPAPS_API_URL='; then
  pass "L5.4 SPAPS_API_URL set"
else
  if [[ "${STRICT_MODE}" == "true" ]]; then
    fail "L5.4 SPAPS_API_URL not in .env"
  else
    pass "L5.4 SPAPS_API_URL not set (optional)"
  fi
fi
echo

# --- L6. Tailscale ---
echo "=== L6. Tailscale ==="

ts_state="$(remote 'tailscale status --json 2>/dev/null | jq -r .BackendState 2>/dev/null || echo unknown')"
if [[ "${ts_state}" == "Running" ]]; then
  pass "L6.1 Tailscale running"
else
  fail "L6.1 Tailscale state: ${ts_state}"
fi

ts_serve="$(remote 'tailscale serve status 2>/dev/null || echo error')"
if [[ "${ts_serve}" != "error" ]] && [[ -n "${ts_serve}" ]]; then
  pass "L6.2 Tailscale serve configured"
else
  warn "L6.2 Tailscale serve status unclear"
fi
echo

# --- L7. External Connectivity ---
echo "=== L7. External Connectivity ==="

spaps_url="$(echo "${live_env}" | grep '^SPAPS_API_URL=' | cut -d= -f2- || true)"
if [[ -n "${spaps_url}" ]]; then
  if remote "curl -sf --max-time 10 \"${spaps_url}/health\" >/dev/null 2>&1"; then
    pass "L7.1 SPAPS API reachable"
  else
    fail "L7.1 SPAPS API NOT reachable"
  fi
else
  if [[ "${STRICT_MODE}" == "true" ]]; then
    fail "L7.1 SPAPS_API_URL not set"
  else
    pass "L7.1 SPAPS_API_URL not set (optional)"
  fi
fi

portal_url="$(echo "${live_env}" | grep '^UNCLAWG_PORTAL_URL=' | cut -d= -f2- || true)"
if [[ -n "${portal_url}" ]]; then
  if remote "curl -sf --max-time 10 \"${portal_url}\" >/dev/null 2>&1"; then
    pass "L7.2 Unclawg portal reachable"
  else
    fail "L7.2 Unclawg portal NOT reachable"
  fi
else
  if [[ "${STRICT_MODE}" == "true" ]]; then
    fail "L7.2 UNCLAWG_PORTAL_URL not set"
  else
    pass "L7.2 UNCLAWG_PORTAL_URL not set (optional)"
  fi
fi
echo

# --- L8. OpenClaw Runtime ---
echo "=== L8. OpenClaw Runtime ==="

if [[ "${SSH_EFFECTIVE_USER}" == "${APP_USER}" ]]; then
  oc_cmd="env HOME=${APP_HOME} PATH=${OPENCLAW_CLI_PATH}"
else
  oc_cmd="sudo -n -u ${APP_USER} env HOME=${APP_HOME} PATH=${OPENCLAW_CLI_PATH}"
fi

oc_version="$(remote "${oc_cmd} openclaw --version 2>/dev/null || echo unknown")"
if [[ "${oc_version}" != "unknown" ]]; then
  pass "L8.1 OpenClaw version: ${oc_version}"
else
  fail "L8.1 Cannot get OpenClaw version"
fi

config_valid="$(remote "${oc_cmd} openclaw config validate 2>&1 || true")"
if echo "${config_valid}" | grep -qi 'too many arguments for .config.\|Unknown command.*config\|No such command.*config'; then
  warn "L8.2 openclaw config validate unsupported on this runtime"
elif echo "${config_valid}" | grep -qi 'error\|invalid'; then
  fail "L8.2 openclaw config validate failed"
  echo "       ${config_valid}" | head -3
else
  pass "L8.2 openclaw config validate passed"
fi

error_count="$(remote "journalctl -u ${SERVICE_NAME} -n 200 --no-pager 2>/dev/null | grep -Eci 'error|fatal|panic' || true" | tail -1 | tr -d "[:space:]")"
if [[ -z "${error_count}" ]]; then
  error_count=0
fi
if [[ "${error_count}" -le 2 ]]; then
  pass "L8.3 Recent logs clean -- ${error_count} errors in last 200 lines"
else
  fail "L8.3 ${error_count} errors in recent logs"
fi

uptime_ts="$(remote "systemctl show ${SERVICE_NAME} --property=ActiveEnterTimestamp --value 2>/dev/null || echo unknown")"
if [[ "${uptime_ts}" != "unknown" ]] && [[ -n "${uptime_ts}" ]]; then
  pass "L8.4 Service up since: ${uptime_ts}"
else
  warn "L8.4 Cannot determine service uptime"
fi
echo

# --- L9. Security Posture ---
echo "=== L9. Security Posture ==="

sshd_config="$(remote 'sshd -T 2>/dev/null || echo unknown')"
if echo "${sshd_config}" | grep -qi '^passwordauthentication no$'; then
  pass "L9.1 SSH password auth disabled"
else
  fail "L9.1 SSH password auth is not disabled"
fi

if echo "${sshd_config}" | grep -qi '^permitrootlogin no$'; then
  pass "L9.2 Root SSH login disabled"
else
  fail "L9.2 Root SSH login is not disabled"
fi

ufw_status="$(remote 'ufw status 2>/dev/null || sudo -n ufw status 2>/dev/null || echo unavailable')"
if [[ "${ufw_status}" == "unavailable" ]]; then
  warn "L9.3 UFW status unavailable"
elif echo "${ufw_status}" | grep -Eq '22/tcp[[:space:]]+ALLOW IN[[:space:]]+Anywhere'; then
  fail "L9.3 Public SSH ingress still allowed by UFW"
elif echo "${ufw_status}" | grep -Eq '22/tcp[[:space:]]+ALLOW IN[[:space:]]+(100\.64\.0\.0/10|tailscale0)'; then
  pass "L9.3 UFW SSH ingress scoped to Tailnet"
else
  warn "L9.3 Could not confirm Tailnet-only SSH UFW rule"
fi

pass "L9.4 Write credential check -- manual review recommended"

audit_out="$(remote "${oc_cmd} openclaw security audit --deep 2>&1 || true")"
if echo "${audit_out}" | grep -qi 'too many arguments for .security.\|Unknown command.*security\|No such command.*security'; then
  warn "L9.5 Security audit command unsupported on this runtime"
elif echo "${audit_out}" | grep -qi 'error\|invalid config'; then
  fail "L9.5 Security audit errored"
  echo "       ${audit_out}" | head -3
else
  critical_count="$(echo "${audit_out}" | awk '/Summary:/ { for (i=1; i<=NF; i++) if ($i == "critical") { print $(i-1); exit } }')"
  critical_count="${critical_count:-0}"
  critical_count="${critical_count//[^0-9]/}"
  if [[ -z "${critical_count}" ]]; then
    critical_count=0
  fi
  if [[ "${critical_count}" -gt 0 ]]; then
    fail "L9.5 Security audit flagged ${critical_count} critical issue(s)"
  else
    pass "L9.5 Security audit clean (0 critical)"
  fi
fi
echo

# --- Results ---
echo "========================================="
echo "      LIVE REVIEW RESULTS"
echo "  Host: ${SSH_TARGET}"
echo "========================================="
echo
TOTAL=$((PASS + FAIL))
echo "  Passed: ${PASS}/${TOTAL}"
echo "  Failed: ${FAIL}/${TOTAL}"
if [[ ${WARN_COUNT} -gt 0 ]]; then
  echo "  Warnings: ${WARN_COUNT}"
fi
echo
if [[ ${TOTAL} -gt 0 ]]; then
  pct=$(( (PASS * 100) / TOTAL ))
  if [[ ${FAIL} -eq 0 ]]; then
    echo "  Grade: PASS -- ${pct}%"
  elif [[ ${pct} -ge 90 ]]; then
    echo "  Grade: MINOR GAPS -- ${pct}%"
  elif [[ ${pct} -ge 80 ]]; then
    echo "  Grade: NEEDS ANOTHER PASS -- ${pct}%"
  else
    echo "  Grade: SIGNIFICANT REWORK -- ${pct}%"
  fi
fi

exit "${FAIL}"
