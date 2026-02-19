#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-openclaw}"
USER_HOME="$(getent passwd "${APP_USER}" | awk -F: '{print $6}' || true)"
if [[ -z "${USER_HOME}" ]]; then
  USER_HOME="/home/${APP_USER}"
fi
APP_HOME="${APP_HOME:-${USER_HOME}}"
OPENCLAW_HOME="${OPENCLAW_HOME:-${APP_HOME}/.openclaw}"
OPENCLAW_SERVICE_NAME="${OPENCLAW_SERVICE_NAME:-openclaw.service}"
OPENCLAW_SERVICE_UNIT="${OPENCLAW_SERVICE_NAME%.service}.service"
OPENCLAW_PATH="${USER_HOME}/.npm-global/bin:${USER_HOME}/.local/bin:${APP_HOME}/.npm-global/bin:${APP_HOME}/.local/bin:${OPENCLAW_HOME}/bin:${PATH}"

run_openclaw() {
  sudo -u "${APP_USER}" env HOME="${APP_HOME}" PATH="${OPENCLAW_PATH}" openclaw "$@"
}

echo "[1/9] openclaw service status..."
sudo systemctl status "${OPENCLAW_SERVICE_UNIT}" --no-pager

echo "[2/9] openclaw recent logs..."
sudo journalctl -u "${OPENCLAW_SERVICE_UNIT}" -n 80 --no-pager

echo "[3/9] tailscale status..."
tailscale status

echo "[4/9] openclaw version..."
run_openclaw --version

echo "[5/9] openclaw config test..."
run_openclaw config get gateway.mode
if ! run_openclaw config get channels.telegram.enabled; then
  run_openclaw config get telegram.enabled
fi

echo "[6/9] approval target sanity..."
if python3 - "${OPENCLAW_HOME}/openclaw.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    cfg = json.load(fh)

targets = (((cfg.get("approvals") or {}).get("exec") or {}).get("targets") or [])
bad = [
    t.get("to")
    for t in targets
    if isinstance(t.get("to"), str) and t.get("to").startswith("${env:")
]
if bad:
    for item in bad:
        print(item)
    sys.exit(1)
sys.exit(0)
PY
then
  echo "  Approval targets are concrete values."
else
  echo "  ERROR: approvals.exec.targets[*].to contains \${env:...} placeholder(s)."
  echo "  Set a concrete Telegram user/chat ID in openclaw.json."
  exit 1
fi

echo "[7/9] security audit (deep)..."
run_openclaw security audit --deep

echo "[8/9] SPAPS connectivity..."
if [[ -f "${OPENCLAW_HOME}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${OPENCLAW_HOME}/.env"
fi
SPAPS_URL="${SPAPS_API_URL:-}"
if [[ -n "${SPAPS_URL}" ]]; then
  if curl -sf --max-time 10 "${SPAPS_URL}/health" >/dev/null 2>&1; then
    echo "  SPAPS API reachable at ${SPAPS_URL}"
  else
    echo "  WARNING: SPAPS API not reachable at ${SPAPS_URL}/health"
  fi
else
  echo "  SKIPPED: SPAPS_API_URL not set in .env"
fi

echo "[9/9] OpenClawth portal connectivity..."
PORTAL_URL="${OPENCLAWTH_PORTAL_URL:-}"
if [[ -n "${PORTAL_URL}" ]]; then
  if curl -sf --max-time 10 "${PORTAL_URL}" >/dev/null 2>&1; then
    echo "  OpenClawth portal reachable at ${PORTAL_URL}"
  else
    echo "  WARNING: OpenClawth portal not reachable at ${PORTAL_URL}"
  fi
else
  echo "  SKIPPED: OPENCLAWTH_PORTAL_URL not set in .env"
fi

echo
echo "Validation complete."
