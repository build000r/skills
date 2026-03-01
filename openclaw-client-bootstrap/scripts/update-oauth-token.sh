#!/usr/bin/env bash
set -euo pipefail

# update-oauth-token.sh — Push credentials to all OpenClaw claw instances.
#
# DEFAULT: reads your local Codex OAuth token from ~/.codex/auth.json and
# writes it as OPENAI_API_KEY on the VPS.  Pass --anthropic to swap to an
# Anthropic API key instead.
#
# Co-located Docker-sandboxed claws share the same host but each has its own
# systemd service and .env file.  This script keeps them in sync by:
#   1. Writing shared.env (single source of truth on the VPS)
#   2. Updating EVERY per-claw .env file with the same value
#   3. Reloading + restarting only the affected systemd services
#
# USAGE
#   update-oauth-token.sh [PROVIDER] [OPTIONS]
#
# PROVIDERS (mutually exclusive, default: --codex)
#   --codex        Read access_token from ~/.codex/auth.json → OPENAI_API_KEY
#                  Checks token expiry and warns if < 24 h remaining.
#   --anthropic    Read Anthropic API key via stdin or --value → ANTHROPIC_API_KEY
#
# OPTIONS
#   -v, --value VALUE   Override auto-sourced value (works with both providers)
#   -c, --claw NAME     Limit to one named claw (default: all claws)
#   --no-restart        Write .env files but skip service restart
#   --dry-run           Show what would change without applying anything
#   --host IP           SSH host override (bypasses deployed-instances.md)
#   --ssh-user USER     SSH login user (default: openclaw)
#   --shared-env PATH   Shared env file path on VPS (default: <first-openclaw-home>/shared.env)
#   -h, --help          Print this help
#
# EXAMPLES
#   # Push your Codex token (default) — reads ~/.codex/auth.json automatically
#   ./update-oauth-token.sh
#
#   # Push Anthropic key via stdin (never in history)
#   echo "sk-ant-..." | ./update-oauth-token.sh --anthropic
#
#   # Push Anthropic key explicitly
#   ./update-oauth-token.sh --anthropic --value "sk-ant-..."
#
#   # Dry-run Codex push
#   ./update-oauth-token.sh --dry-run
#
#   # Only update ingredient-claw, skip restart
#   ./update-oauth-token.sh --claw ingredient-claw --no-restart
#
# NOTE
#   If you SSH as non-root, restarting systemd units may require passwordless sudo.
#   Use --no-restart when sudo is unavailable, then restart services manually on host.
#
# MODELS
#   When using --codex the VPS model should be one of:
#     openai/gpt-5.2-codex   (medium reasoning — recommended)
#     openai/gpt-5.3-codex   (highest capability, matches your local config)
#   When using --anthropic:
#     anthropic/claude-haiku-4-5-20251001  (fast / cheap)
#     anthropic/claude-sonnet-4-6          (balanced)
#     anthropic/claude-opus-4-6            (highest capability)
#
#   Model is NOT changed by this script — update openclaw.json separately.
#
# SHARED .ENV ON THE VPS
#   Default: <first-openclaw-home>/shared.env
#   Override with --shared-env when needed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTANCES_FILE="${SCRIPT_DIR}/../references/deployed-instances.md"
CODEX_AUTH="${HOME}/.codex/auth.json"
PRIMARY_USER="openclaw"
SSH_OPTS=(-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

PROVIDER="codex"
KEY=""
VALUE=""
CODEX_EXP_MS=""
CLAW_NAME=""
NO_RESTART="false"
DRY_RUN="false"
HOST_OVERRIDE=""
SSH_LOGIN_USER="${SSH_LOGIN_USER:-openclaw}"
SHARED_ENV_PATH="${SHARED_ENV_PATH:-}"

# ── Helpers ────────────────────────────────────────────────────────────────────

usage() { sed -n '8,58p' "$0" | sed 's/^# //; s/^#$//'; exit 0; }
die()  { echo "error: $*" >&2; exit 1; }
log()  { printf '  %s\n' "$*"; }
info() { printf '\033[1;34m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
dry()  { printf '\033[1;35m(dry)\033[0m %s\n' "$*"; }

# ── Argument parsing ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex)        PROVIDER="codex"; shift ;;
    --anthropic)    PROVIDER="anthropic"; shift ;;
    -v|--value)     VALUE="${2:?--value requires a value}"; shift 2 ;;
    -c|--claw)      CLAW_NAME="${2:?--claw requires a name}"; shift 2 ;;
    --no-restart)   NO_RESTART="true"; shift ;;
    --dry-run)      DRY_RUN="true"; shift ;;
    --host)         HOST_OVERRIDE="${2:?--host requires an IP}"; shift 2 ;;
    --ssh-user)     SSH_LOGIN_USER="${2:?--ssh-user requires a user}"; shift 2 ;;
    --shared-env)   SHARED_ENV_PATH="${2:?--shared-env requires a path}"; shift 2 ;;
    -h|--help)      usage ;;
    *)              die "Unknown argument: $1  (use --help)" ;;
  esac
done

# ── Resolve KEY and VALUE by provider ────────────────────────────────────────

case "${PROVIDER}" in

  codex)
    KEY="OPENAI_API_KEY"

    if [[ -z "${VALUE}" ]]; then
      [[ -f "${CODEX_AUTH}" ]] || die "Codex auth file not found: ${CODEX_AUTH}
Run Codex at least once to authenticate, then retry."

      command -v jq >/dev/null 2>&1 || die "'jq' is required (brew install jq)"

      VALUE="$(jq -r '.tokens.access_token // empty' "${CODEX_AUTH}")"
      [[ -n "${VALUE}" ]] || die "No access_token in ${CODEX_AUTH} — re-authenticate with Codex."
    fi

    # Decode JWT payload (base64url → base64 → JSON) and check expiry.
    payload="$(echo "${VALUE}" | cut -d. -f2 | tr '_-' '/+' \
      | awk '{ pad=4-length($0)%4; if(pad<4) for(i=0;i<pad;i++) $0=$0"="; print }' \
      | base64 -d 2>/dev/null || true)"
    if [[ -n "${payload}" ]]; then
      exp="$(echo "${payload}" | jq -r '.exp // 0' 2>/dev/null || echo 0)"
      if [[ "${exp}" =~ ^[0-9]+$ ]] && (( exp > 0 )); then
        CODEX_EXP_MS="$(( exp * 1000 ))"
        now="$(date +%s)"
        ttl=$(( exp - now ))
        if (( ttl <= 0 )); then
          warn "Codex access_token has EXPIRED.  Run Codex locally to refresh, then retry."
          exit 1
        elif (( ttl < 86400 )); then
          warn "Token expires in $(( ttl / 3600 ))h $(( (ttl % 3600) / 60 ))m — consider refreshing soon."
        else
          log "Token valid for $(( ttl / 86400 )) day(s)"
        fi
      fi
    fi
    ;;

  anthropic)
    KEY="ANTHROPIC_API_KEY"

    if [[ -z "${VALUE}" ]]; then
      if [[ -t 0 ]]; then
        read -r -s -p "Enter ANTHROPIC_API_KEY: " VALUE
        echo
      else
        VALUE="$(cat)"
      fi
    fi
    [[ -n "${VALUE}" ]] || die "ANTHROPIC_API_KEY must not be empty"
    ;;

  *)
    die "Unknown provider '${PROVIDER}'.  Use --codex or --anthropic."
    ;;
esac

# ── Parse deployed-instances.md ───────────────────────────────────────────────

parse_instances() {
  [[ ! -f "${INSTANCES_FILE}" ]] && return
  local ts_ip current svc config_path
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

require_instances() {
  if [[ -z "${HOST_OVERRIDE}" ]] && [[ ! -f "${INSTANCES_FILE}" ]]; then
    die "No deployed-instances.md at ${INSTANCES_FILE}.
Create it from references/deployed-instances.example.md or pass --host <IP>."
  fi
}

ssh_target() {
  local ip="$1"
  [[ -n "${HOST_OVERRIDE}" ]] && echo "${SSH_LOGIN_USER}@${HOST_OVERRIDE}" || echo "${SSH_LOGIN_USER}@${ip}"
}

remote() {
  local target="$1"; shift
  ssh -n "${SSH_OPTS[@]}" "${target}" "$@"
}

# ── Core: update one .env key on the VPS ─────────────────────────────────────

update_env_key() {
  local target="$1"
  local env_path="$2"
  local key="$3"
  local value="$4"

  if [[ "${DRY_RUN}" == "true" ]]; then
    dry "Would update ${key} in ${env_path} on ${target}"
    return 0
  fi

  # Escape single quotes in value for safe shell embedding
  local escaped_value="${value//\'/\'\\\'\'}"

  remote "${target}" "
set -euo pipefail
env_path='${env_path}'
key='${key}'
new_line=\"\${key}='${escaped_value}'\"
if grep -qE \"^#?[[:space:]]*\${key}=\" \"\${env_path}\" 2>/dev/null; then
  tmp=\$(mktemp \"\${env_path}.XXXXXX\")
  chmod --reference=\"\${env_path}\" \"\${tmp}\" 2>/dev/null || chmod 600 \"\${tmp}\"
  sed \"s|^#\\?[[:space:]]*\${key}=.*|\${new_line}|\" \"\${env_path}\" > \"\${tmp}\"
  mv \"\${tmp}\" \"\${env_path}\"
else
  printf '\n%s\n' \"\${new_line}\" >> \"\${env_path}\"
fi
"
}

# ── Core: write shared.env on the VPS ─────────────────────────────────────

update_shared_env() {
  local target="$1"
  local shared_file="$2"
  local key="$3"
  local value="$4"

  if [[ "${DRY_RUN}" == "true" ]]; then
    dry "Would update ${key} in ${shared_file} on ${target}"
    return 0
  fi

  local escaped_value="${value//\'/\'\\\'\'}"
  local escaped_shared_file="${shared_file//\'/\'\\\'\'}"

  remote "${target}" "
set -euo pipefail
shared_file='${escaped_shared_file}'
shared_dir=\$(dirname \"\${shared_file}\")
key='${key}'
new_line=\"\${key}='${escaped_value}'\"

[[ -d \"\${shared_dir}\" ]] || { mkdir -p \"\${shared_dir}\"; chmod 750 \"\${shared_dir}\"; }
if [[ ! -f \"\${shared_file}\" ]]; then
  touch \"\${shared_file}\"
  chmod 600 \"\${shared_file}\"
fi

if grep -qE \"^#?[[:space:]]*\${key}=\" \"\${shared_file}\" 2>/dev/null; then
  tmp=\$(mktemp \"\${shared_file}.XXXXXX\")
  chmod --reference=\"\${shared_file}\" \"\${tmp}\" 2>/dev/null || chmod 640 \"\${tmp}\"
  sed \"s|^#\\?[[:space:]]*\${key}=.*|\${new_line}|\" \"\${shared_file}\" > \"\${tmp}\"
  mv \"\${tmp}\" \"\${shared_file}\"
else
  printf '\n%s\n' \"\${new_line}\" >> \"\${shared_file}\"
fi
echo '[shared.env] updated'
"
}

# ── Core: restart service ─────────────────────────────────────────────────────

restart_service() {
  local target="$1"
  local svc="$2"
  [[ "${DRY_RUN}" == "true" ]] && { dry "Would restart ${svc}.service"; return; }
  if remote "${target}" "systemctl daemon-reload && systemctl restart ${svc}.service" >/dev/null 2>&1; then
    return 0
  fi
  if remote "${target}" "sudo -n systemctl daemon-reload && sudo -n systemctl restart ${svc}.service" >/dev/null 2>&1; then
    return 0
  fi
  warn "Could not restart ${svc}.service via ${target} (need root or passwordless sudo)"
  return 1
}

service_status() {
  local target="$1" svc="$2"
  local status
  status="$(remote "${target}" "systemctl is-active ${svc}.service 2>/dev/null || true" | tr -d '\r' || true)"
  if [[ -n "${status}" ]]; then
    echo "${status}"
    return 0
  fi
  status="$(remote "${target}" "sudo -n systemctl is-active ${svc}.service 2>/dev/null || true" | tr -d '\r' || true)"
  if [[ -n "${status}" ]]; then
    echo "${status}"
  else
    echo "unknown"
  fi
}

inspect_model_config() {
  local target="$1"
  local openclaw_home="$2"
  local config_path="${openclaw_home}/openclaw.json"
  local escaped_config_path="${config_path//\'/\'\\\'\'}"

  remote "${target}" "
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path

path = Path('${escaped_config_path}')
if not path.exists():
    print('|0')
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding='utf-8'))
except Exception:
    print('|0')
    raise SystemExit(0)

model = data.get('agents', {}).get('defaults', {}).get('model', {})
if not isinstance(model, dict):
    print('|0')
    raise SystemExit(0)

primary = str(model.get('primary', ''))
has_reasoning_effort = '1' if 'reasoningEffort' in model else '0'
print(f'{primary}|{has_reasoning_effort}')
PY
" 2>/dev/null | tr -d '\r'
}

warn_model_alignment() {
  local provider="$1"
  local name="$2"
  local target="$3"
  local openclaw_home="$4"
  local model_info model_primary model_has_reasoning_effort

  model_info="$(inspect_model_config "${target}" "${openclaw_home}" || true)"
  IFS='|' read -r model_primary model_has_reasoning_effort <<< "${model_info}"

  if [[ -z "${model_primary}" ]]; then
    warn "${name}: could not read agents.defaults.model.primary from ${openclaw_home}/openclaw.json"
    return 0
  fi

  if [[ "${model_has_reasoning_effort}" == "1" ]]; then
    warn "${name}: found agents.defaults.model.reasoningEffort. Remove it if gateway logs show 'Unknown config keys'."
  fi

  case "${provider}" in
    codex)
      if [[ ! "${model_primary}" =~ ^openai/.+-codex$ ]]; then
        warn "${name}: model '${model_primary}' does not match Codex provider. Expected openai/*-codex."
      fi
      ;;
    anthropic)
      if [[ ! "${model_primary}" =~ ^anthropic/ ]]; then
        warn "${name}: model '${model_primary}' does not match Anthropic provider. Expected anthropic/*."
      fi
      ;;
  esac
}

sync_codex_auth_profiles() {
  local target="$1"
  local openclaw_home="$2"
  local token="$3"
  local exp_ms="$4"

  if [[ "${DRY_RUN}" == "true" ]]; then
    dry "Would sync openai-codex auth-profiles under ${openclaw_home}/agents/*/agent on ${target}"
    return 0
  fi

  local escaped_token="${token//\'/\'\\\'\'}"
  local escaped_exp_ms="${exp_ms//\'/\'\\\'\'}"

  remote "${target}" "
set -euo pipefail
export OPENCLAW_HOME='${openclaw_home}'
export OPENCLAW_TOKEN='${escaped_token}'
export OPENCLAW_EXP_MS='${escaped_exp_ms}'
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ['OPENCLAW_HOME'])
token = os.environ.get('OPENCLAW_TOKEN', '').strip()
exp_raw = os.environ.get('OPENCLAW_EXP_MS', '').strip()
exp_ms = int(exp_raw) if exp_raw.isdigit() else None

if not token:
    raise SystemExit('empty OPENCLAW_TOKEN')

agent_root = home / 'agents'
target_dirs = {agent_root / 'main' / 'agent'}
if agent_root.exists():
    for p in agent_root.glob('*/agent'):
        target_dirs.add(p)

uid = home.stat().st_uid
gid = home.stat().st_gid

profile = {
    'type': 'token',
    'provider': 'openai-codex',
    'token': token,
}
if exp_ms:
    profile['expires'] = exp_ms

store = {
    'version': 1,
    'profiles': {'openai-codex:manual': profile},
    'order': {'openai-codex': ['openai-codex:manual']},
}

for d in sorted(target_dirs):
    d.mkdir(parents=True, exist_ok=True)
    p = d / 'auth-profiles.json'
    p.write_text(json.dumps(store, indent=2) + '\\n', encoding='utf-8')
    os.chmod(p, 0o600)
    os.chown(p, uid, gid)

print(f'[auth-profiles] synced {len(target_dirs)} agent dirs')
PY
"
}

# ── Main ──────────────────────────────────────────────────────────────────────

require_instances

# Collect target claws
declare -a CLAWS=()
if [[ -n "${HOST_OVERRIDE}" ]] && [[ ! -f "${INSTANCES_FILE}" ]]; then
  # No instances file — fall back to single primary claw at override IP
  CLAWS+=("manual|openclaw|/home/openclaw/.openclaw|${HOST_OVERRIDE}")
else
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    IFS='|' read -r name svc home ip <<< "${line}"
    # Use HOST_OVERRIDE as the SSH target if provided (lets you bypass Tailscale)
    effective_ip="${HOST_OVERRIDE:-${ip}}"
    if [[ -z "${CLAW_NAME}" || "${name}" == "${CLAW_NAME}" ]]; then
      CLAWS+=("${name}|${svc}|${home}|${effective_ip}")
    fi
  done < <(parse_instances)
fi

if [[ "${#CLAWS[@]}" -eq 0 ]]; then
  [[ -n "${CLAW_NAME}" ]] \
    && die "Claw '${CLAW_NAME}' not found — run talk.sh --list" \
    || die "No claw instances found in deployed-instances.md"
fi

echo ""
info "Provider : ${PROVIDER}  →  ${KEY}"
info "Claws    : ${#CLAWS[@]}$([[ "${DRY_RUN}" == "true" ]] && echo '  (DRY RUN)' || true)"
echo ""

# All co-located claws share one VPS host
IFS='|' read -r _n _s FIRST_HOME FIRST_IP <<< "${CLAWS[0]}"
PRIMARY_TARGET="$(ssh_target "${FIRST_IP}")"
if [[ -z "${SHARED_ENV_PATH}" ]]; then
  SHARED_ENV_PATH="${FIRST_HOME}/shared.env"
fi

log "Writing ${SHARED_ENV_PATH} on ${PRIMARY_TARGET}..."
update_shared_env "${PRIMARY_TARGET}" "${SHARED_ENV_PATH}" "${KEY}" "${VALUE}"
[[ "${DRY_RUN}" == "false" ]] && ok "shared.env updated"
echo ""

for entry in "${CLAWS[@]}"; do
  IFS='|' read -r name svc home ip <<< "${entry}"
  target="$(ssh_target "${ip}")"
  env_path="${home}/.env"

  info "${name}  (${target}:${env_path})"

  if [[ "${DRY_RUN}" == "false" ]]; then
    if ! remote "${target}" "[ -f '${env_path}' ]" 2>/dev/null; then
      warn ".env not found at ${env_path} — skipping (not yet deployed?)"
      echo ""; continue
    fi
  fi
  warn_model_alignment "${PROVIDER}" "${name}" "${target}" "${home}"

  update_env_key "${target}" "${env_path}" "${KEY}" "${VALUE}"
  [[ "${DRY_RUN}" == "false" ]] && ok "${KEY} written"

  if [[ "${PROVIDER}" == "codex" ]]; then
    log "Syncing openai-codex auth profiles..."
    sync_codex_auth_profiles "${target}" "${home}" "${VALUE}" "${CODEX_EXP_MS}"
    [[ "${DRY_RUN}" == "false" ]] && ok "openai-codex auth store synced"
  fi

  if [[ "${NO_RESTART}" == "false" ]]; then
    log "Restarting ${svc}.service..."
    if restart_service "${target}" "${svc}"; then
      :
    fi
    if [[ "${DRY_RUN}" == "false" ]]; then
      sleep 2
      status="$(service_status "${target}" "${svc}")"
      [[ "${status}" == "active" ]] \
        && ok "${svc}.service active" \
        || warn "${svc}.service: ${status}  (journalctl -u ${svc} -n 20)"
    fi
  else
    log "Skipping restart.  Run: systemctl restart ${svc}.service"
  fi
  echo ""
done

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Dry run complete — nothing changed."
else
  echo "Done."
  if [[ "${PROVIDER}" == "codex" ]]; then
    echo ""
    echo "Model reminder: ensure openclaw.json uses an OpenAI model, e.g.:"
    echo "  openai/gpt-5.2-codex   (medium reasoning — balanced)"
    echo "  openai/gpt-5.3-codex   (highest capability)"
  fi
  echo ""
  echo "Verify: bash scripts/talk.sh --health"
fi
