#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo KIT_DIR=/opt/openclaw-client-kit ./03-install-openclaw.sh"
  exit 1
fi

KIT_DIR="${KIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
APP_USER="${APP_USER:-openclaw}"
USER_HOME="$(getent passwd "${APP_USER}" | awk -F: '{print $6}' || true)"
if [[ -z "${USER_HOME}" ]]; then
  USER_HOME="/home/${APP_USER}"
fi
APP_HOME="${APP_HOME:-${USER_HOME}}"
OPENCLAW_HOME="${OPENCLAW_HOME:-${APP_HOME}/.openclaw}"
OPENCLAW_SERVICE_NAME="${OPENCLAW_SERVICE_NAME:-openclaw.service}"
OPENCLAW_SERVICE_UNIT="${OPENCLAW_SERVICE_NAME%.service}.service"
BIN_PATH=""

resolve_openclaw_bin() {
  local candidate=""
  for candidate in \
    "${USER_HOME}/.npm-global/bin/openclaw" \
    "${USER_HOME}/.local/bin/openclaw" \
    "${APP_HOME}/.npm-global/bin/openclaw" \
    "${APP_HOME}/.local/bin/openclaw" \
    "${OPENCLAW_HOME}/bin/openclaw"; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  candidate="$(su - "${APP_USER}" -c 'command -v openclaw 2>/dev/null' || true)"
  if [[ -n "${candidate}" ]]; then
    echo "${candidate}"
    return 0
  fi

  return 1
}

# --- Prerequisite checks ---

echo "[prereq] Checking Node.js..."
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed. Run 01-bootstrap-do.sh first."
  exit 1
fi
NODE_MAJOR="$(node --version | cut -d. -f1 | tr -d v)"
if [[ "${NODE_MAJOR}" -lt 22 ]]; then
  echo "Node.js ${NODE_MAJOR} found but >= 22 required. Run 01-bootstrap-do.sh to install Node.js 22."
  exit 1
fi

echo "[prereq] Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Run 01-bootstrap-do.sh first."
  exit 1
fi

# --- Kit file checks ---

if [[ ! -f "${KIT_DIR}/.env" ]]; then
  echo "Missing ${KIT_DIR}/.env. Copy .env.example and fill values first."
  exit 1
fi

if [[ ! -f "${KIT_DIR}/openclaw.json" ]]; then
  echo "Missing ${KIT_DIR}/openclaw.json."
  exit 1
fi

if grep -Eq '{{TELEGRAM_ALLOWED_USER_ID}}|{{TELEGRAM_GROUP_CHAT_ID}}' "${KIT_DIR}/openclaw.json"; then
  echo "Replace all Telegram placeholder IDs in ${KIT_DIR}/openclaw.json before install."
  exit 1
fi

if ! python3 - "${KIT_DIR}/openclaw.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    cfg = json.load(fh)

telegram = ((cfg.get("channels") or {}).get("telegram") or {})
group_policy = telegram.get("groupPolicy")
group_allow_from = telegram.get("groupAllowFrom") or []
groups = telegram.get("groups") or []

if group_policy != "allowlist":
    raise SystemExit(1)
if not isinstance(group_allow_from, list) or not group_allow_from:
    raise SystemExit(1)
if not isinstance(groups, list) or not groups:
    raise SystemExit(1)

for entry in groups:
    if not isinstance(entry, dict) or not str(entry.get("chatId", "")).strip():
        raise SystemExit(1)
PY
then
  echo "openclaw.json must define channels.telegram.groupPolicy=\"allowlist\" with non-empty groupAllowFrom and groups[]."
  exit 1
fi

if python3 - "${KIT_DIR}/openclaw.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    cfg = json.load(fh)

targets = (((cfg.get("approvals") or {}).get("exec") or {}).get("targets") or [])
for target in targets:
    to_val = target.get("to")
    if isinstance(to_val, str) and to_val.startswith("${env:"):
        sys.exit(0)
sys.exit(1)
PY
then
  echo "approvals.exec.targets[*].to cannot use \${env:...} interpolation in this runtime."
  echo "Use a concrete Telegram user/chat ID in openclaw.json before install."
  exit 1
fi

# --- Pre-place config files before install ---

echo "[1/6] Pre-placing config and env into ${OPENCLAW_HOME}..."
mkdir -p "${APP_HOME}"
chown "${APP_USER}:${APP_USER}" "${APP_HOME}"
mkdir -p "${OPENCLAW_HOME}"
install -o "${APP_USER}" -g "${APP_USER}" -m 600 "${KIT_DIR}/.env" "${OPENCLAW_HOME}/.env"
install -o "${APP_USER}" -g "${APP_USER}" -m 600 "${KIT_DIR}/openclaw.json" "${OPENCLAW_HOME}/openclaw.json"
install -o "${APP_USER}" -g "${APP_USER}" -m 600 "${KIT_DIR}/SOUL.md" "${OPENCLAW_HOME}/SOUL.md"
install -o "${APP_USER}" -g "${APP_USER}" -m 600 "${KIT_DIR}/AGENTS.md" "${OPENCLAW_HOME}/AGENTS.md"
install -o "${APP_USER}" -g "${APP_USER}" -m 600 "${KIT_DIR}/USER.md" "${OPENCLAW_HOME}/USER.md"

echo "[2/6] Installing OpenClaw CLI for ${APP_USER}..."
su - "${APP_USER}" -c 'curl -fsSL https://openclaw.ai/install.sh | bash'

BIN_PATH="$(resolve_openclaw_bin || true)"
if [[ -z "${BIN_PATH}" ]] || [[ ! -x "${BIN_PATH}" ]]; then
  echo "OpenClaw binary not found. Checked:"
  echo "  - ${APP_HOME}/.npm-global/bin/openclaw"
  echo "  - ${APP_HOME}/.local/bin/openclaw"
  echo "  - ${OPENCLAW_HOME}/bin/openclaw"
  exit 1
fi

echo "[3/6] Validating OpenClaw version..."
su - "${APP_USER}" -c "env HOME=${APP_HOME} ${BIN_PATH} --version"

echo "[4/6] Writing systemd service ${OPENCLAW_SERVICE_UNIT}..."
cat >/etc/systemd/system/${OPENCLAW_SERVICE_UNIT} <<EOF
[Unit]
Description=OpenClaw Gateway
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${OPENCLAW_HOME}
Environment=HOME=${APP_HOME}
Environment=PATH=${USER_HOME}/.npm-global/bin:${USER_HOME}/.local/bin:${APP_HOME}/.npm-global/bin:${APP_HOME}/.local/bin:${OPENCLAW_HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EnvironmentFile=${OPENCLAW_HOME}/.env
ExecStart=${BIN_PATH} gateway --tailscale serve
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${OPENCLAW_HOME}

[Install]
WantedBy=multi-user.target
EOF

echo "[5/6] Enabling and starting ${OPENCLAW_SERVICE_UNIT}..."
systemctl daemon-reload
systemctl enable --now "${OPENCLAW_SERVICE_UNIT}"

echo "[6/6] Service status:"
systemctl status "${OPENCLAW_SERVICE_UNIT}" --no-pager

echo
echo "OpenClaw install complete."
echo "Next: run scripts/04-validate.sh"
