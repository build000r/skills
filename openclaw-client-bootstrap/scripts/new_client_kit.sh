#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create a new OpenClaw client kit from bundled assets.

Usage:
  new_client_kit.sh --dest /path/to/output [options]

Options:
  --dest            Destination directory for the generated kit (required)
  --client-name     Value to replace {{CLIENT_NAME}} placeholder
  --telegram-id     Telegram user ID for operator allowlists
  --bot-token       Telegram bot token from BotFather
  --spaps-url       SPAPS API URL
  --spaps-key       SPAPS API key
  --spaps-agent-id  SPAPS agent ID
  --spaps-secret    SPAPS agent secret
  --portal-url      OpenClawth portal URL
  --ts-hostname     Tailscale node hostname
  --interactive     Prompt for missing values interactively (default when TTY)
  --no-interactive  Never prompt; use defaults for missing values
  --force           Allow writing into a non-empty destination directory
  -h, --help        Show this help
EOF
}

DEST=""
CLIENT_NAME=""
TELEGRAM_USER_ID=""
BOT_TOKEN=""
SPAPS_URL=""
SPAPS_KEY=""
SPAPS_AGENT_ID=""
SPAPS_SECRET=""
PORTAL_URL=""
TS_HOSTNAME=""
FORCE="false"
INTERACTIVE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      DEST="${2:-}"
      shift 2
      ;;
    --client-name)
      CLIENT_NAME="${2:-}"
      shift 2
      ;;
    --telegram-id)
      TELEGRAM_USER_ID="${2:-}"
      shift 2
      ;;
    --bot-token)
      BOT_TOKEN="${2:-}"
      shift 2
      ;;
    --spaps-url)
      SPAPS_URL="${2:-}"
      shift 2
      ;;
    --spaps-key)
      SPAPS_KEY="${2:-}"
      shift 2
      ;;
    --spaps-agent-id)
      SPAPS_AGENT_ID="${2:-}"
      shift 2
      ;;
    --spaps-secret)
      SPAPS_SECRET="${2:-}"
      shift 2
      ;;
    --portal-url)
      PORTAL_URL="${2:-}"
      shift 2
      ;;
    --ts-hostname)
      TS_HOSTNAME="${2:-}"
      shift 2
      ;;
    --interactive)
      INTERACTIVE="true"
      shift
      ;;
    --no-interactive)
      INTERACTIVE="false"
      shift
      ;;
    --force)
      FORCE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${DEST}" ]]; then
  echo "--dest is required."
  usage
  exit 1
fi

# Default to interactive when TTY is available and key values are missing.
if [[ -z "${INTERACTIVE}" ]]; then
  if [[ -t 0 ]] && [[ -z "${CLIENT_NAME}" || -z "${TELEGRAM_USER_ID}" || -z "${BOT_TOKEN}" ]]; then
    INTERACTIVE="true"
  else
    INTERACTIVE="false"
  fi
fi

# --- Interactive prompts ---

prompt_value() {
  local var_name="$1"
  local prompt_text="$2"
  local default_val="${3:-}"
  local current_val="${!var_name:-}"

  if [[ -n "${current_val}" ]]; then
    return
  fi

  if [[ "${INTERACTIVE}" != "true" ]]; then
    return
  fi

  if [[ -n "${default_val}" ]]; then
    read -rp "${prompt_text} [${default_val}]: " input
    eval "${var_name}=\"\${input:-${default_val}}\""
  else
    read -rp "${prompt_text}: " input
    eval "${var_name}=\"\${input}\""
  fi
}

if [[ "${INTERACTIVE}" == "true" ]]; then
  echo "=== OpenClaw Client Kit Generator ==="
  echo
fi

prompt_value CLIENT_NAME "Client name"
prompt_value TELEGRAM_USER_ID "Telegram operator user ID"
prompt_value BOT_TOKEN "Telegram bot token (from BotFather)"
prompt_value SPAPS_URL "SPAPS API URL" "https://spaps.openclawth.com/api"
prompt_value SPAPS_KEY "SPAPS API key"
prompt_value SPAPS_AGENT_ID "SPAPS agent ID"
prompt_value SPAPS_SECRET "SPAPS agent secret"
prompt_value PORTAL_URL "OpenClawth portal URL" "https://openclawth.com"
prompt_value TS_HOSTNAME "Tailscale node hostname" "client-openclaw"

# --- Copy assets ---

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ASSET_DIR="${SKILL_DIR}/assets/client-kit"

if [[ ! -d "${ASSET_DIR}" ]]; then
  echo "Missing asset directory: ${ASSET_DIR}"
  exit 1
fi

mkdir -p "${DEST}"

if [[ "${FORCE}" != "true" ]]; then
  if [[ -n "$(find "${DEST}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Destination is not empty: ${DEST}"
    echo "Re-run with --force to continue."
    exit 1
  fi
fi

cp -R "${ASSET_DIR}/." "${DEST}/"
chmod +x "${DEST}/scripts/"*.sh

if [[ ! -f "${DEST}/.env" && -f "${DEST}/.env.example" ]]; then
  cp "${DEST}/.env.example" "${DEST}/.env"
fi

# --- Substitute all placeholders in one pass ---

# Generate gateway token.
GATEWAY_TOKEN=""
if command -v openssl >/dev/null 2>&1; then
  GATEWAY_TOKEN="$(openssl rand -hex 48)"
fi

substitute_placeholder() {
  local placeholder="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    return
  fi
  local awk_replacement="${value//\\/\\\\}"
  awk_replacement="${awk_replacement//&/\\\\&}"
  while IFS= read -r -d '' file; do
    TMP_SUB="$(mktemp)"
    awk -v pat="${placeholder}" -v rep="${awk_replacement}" '{ gsub(pat, rep); print }' "${file}" > "${TMP_SUB}"
    mv "${TMP_SUB}" "${file}"
  done < <(find "${DEST}" -type f \( -name '*.json' -o -name '*.md' -o -name '*.sh' -o -name '.env' -o -name '.env.example' \) -print0)
}

substitute_placeholder '{{CLIENT_NAME}}' "${CLIENT_NAME}"
substitute_placeholder '{{TELEGRAM_USER_ID}}' "${TELEGRAM_USER_ID}"

# .env-specific substitutions.
if [[ -f "${DEST}/.env" ]]; then
  TMP_ENV="$(mktemp)"
  awk \
    -v gw_token="${GATEWAY_TOKEN}" \
    -v bot_token="${BOT_TOKEN}" \
    -v spaps_url="${SPAPS_URL}" \
    -v spaps_key="${SPAPS_KEY}" \
    -v spaps_agent_id="${SPAPS_AGENT_ID}" \
    -v spaps_secret="${SPAPS_SECRET}" \
    -v portal_url="${PORTAL_URL}" \
    -v client_name="${CLIENT_NAME}" \
    -v ts_hostname="${TS_HOSTNAME}" \
    '
    /^OPENCLAW_GATEWAY_TOKEN=/ && gw_token != "" { print "OPENCLAW_GATEWAY_TOKEN=" gw_token; next }
    /^OPENCLAW_TG_TOKEN=/ && bot_token != "" { print "OPENCLAW_TG_TOKEN=" bot_token; next }
    /^SPAPS_API_URL=/ && spaps_url != "" { print "SPAPS_API_URL=" spaps_url; next }
    /^SPAPS_API_KEY=/ && spaps_key != "" { print "SPAPS_API_KEY=" spaps_key; next }
    /^SPAPS_AGENT_ID=/ && spaps_agent_id != "" { print "SPAPS_AGENT_ID=" spaps_agent_id; next }
    /^SPAPS_AGENT_SECRET=/ && spaps_secret != "" { print "SPAPS_AGENT_SECRET=" spaps_secret; next }
    /^OPENCLAWTH_PORTAL_URL=/ && portal_url != "" { print "OPENCLAWTH_PORTAL_URL=" portal_url; next }
    /^CLIENT_NAME=/ && client_name != "" { print "CLIENT_NAME=" client_name; next }
    /^TAILSCALE_HOSTNAME=/ && ts_hostname != "" { print "TAILSCALE_HOSTNAME=" ts_hostname; next }
    { print }
  ' "${DEST}/.env" > "${TMP_ENV}"
  mv "${TMP_ENV}" "${DEST}/.env"
fi

# --- Summary ---

echo
echo "Client kit created at: ${DEST}"
echo
echo "=== Substitution Summary ==="

filled=()
remaining=()

check_field() {
  local label="$1"
  local value="$2"
  if [[ -n "${value}" ]]; then
    filled+=("  ${label}")
  else
    remaining+=("  ${label}")
  fi
}

check_field "Client name" "${CLIENT_NAME}"
check_field "Telegram user ID" "${TELEGRAM_USER_ID}"
check_field "Bot token" "${BOT_TOKEN}"
check_field "Gateway token" "${GATEWAY_TOKEN}"
check_field "SPAPS API URL" "${SPAPS_URL}"
check_field "SPAPS API key" "${SPAPS_KEY}"
check_field "SPAPS agent ID" "${SPAPS_AGENT_ID}"
check_field "SPAPS agent secret" "${SPAPS_SECRET}"
check_field "Portal URL" "${PORTAL_URL}"
check_field "Tailscale hostname" "${TS_HOSTNAME}"

if [[ ${#filled[@]} -gt 0 ]]; then
  echo "Filled:"
  printf '%s\n' "${filled[@]}"
fi

if [[ ${#remaining[@]} -gt 0 ]]; then
  echo "Still needs manual editing:"
  printf '%s\n' "${remaining[@]}"
fi

# Check for any remaining template markers.
remaining_markers="$(grep -rl '{{' "${DEST}" --include='*.json' --include='*.md' --include='*.sh' --include='.env' 2>/dev/null || true)"
if [[ -n "${remaining_markers}" ]]; then
  echo
  echo "Files with remaining {{...}} placeholders:"
  echo "${remaining_markers}"
fi

if python3 - "${DEST}/openclaw.json" <<'PY'
import json
import sys

cfg = json.load(open(sys.argv[1], "r", encoding="utf-8"))
targets = (((cfg.get("approvals") or {}).get("exec") or {}).get("targets") or [])
for target in targets:
    to_val = target.get("to")
    if isinstance(to_val, str) and to_val.startswith("${env:"):
        print(to_val)
        sys.exit(0)
sys.exit(1)
PY
then
  echo
  echo "WARNING: approvals.exec.targets[*].to uses \${env:...} interpolation."
  echo "Use a concrete Telegram ID in openclaw.json (runtime interpolation may fail)."
fi

echo
echo "Next: copy kit to droplet and run scripts/01-bootstrap-do.sh"
