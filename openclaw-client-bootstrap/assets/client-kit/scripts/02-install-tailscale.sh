#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./02-install-tailscale.sh"
  exit 1
fi

TAILSCALE_AUTHKEY="${TAILSCALE_AUTHKEY:-}"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-client-openclaw}"

echo "[1/4] Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh

echo "[2/4] Starting tailscaled..."
systemctl enable --now tailscaled

echo "[3/4] Joining tailnet..."
if [[ -n "${TAILSCALE_AUTHKEY}" ]]; then
  tailscale up \
    --authkey="${TAILSCALE_AUTHKEY}" \
    --hostname="${TAILSCALE_HOSTNAME}" \
    --ssh \
    --accept-routes=false \
    --accept-dns=false
else
  tailscale up \
    --hostname="${TAILSCALE_HOSTNAME}" \
    --ssh \
    --accept-routes=false \
    --accept-dns=false
fi

echo "[4/4] Tailnet status:"
tailscale status

echo
echo "Tailscale setup complete."
echo "Next: prepare .env + openclaw.json, then run scripts/03-install-openclaw.sh"
