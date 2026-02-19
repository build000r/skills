#!/usr/bin/env bash
set -euo pipefail

# Minimum spec: 2GB RAM (recommend 4GB for production).

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./01-bootstrap-do.sh"
  exit 1
fi

APP_USER="${APP_USER:-openclaw}"
APP_HOME="/home/${APP_USER}"

echo "[1/8] Updating OS packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade

echo "[2/8] Installing baseline packages..."
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  ufw \
  fail2ban \
  jq \
  git \
  unzip

echo "[3/8] Installing Node.js 22 LTS..."
if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | cut -d. -f1 | tr -d v)" -lt 22 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi
echo "  Node.js version: $(node --version)"

echo "[4/8] Installing Docker CE..."
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
echo "  Docker version: $(docker --version)"

echo "[5/8] Creating app user (${APP_USER}) if missing..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${APP_USER}"
  usermod -aG sudo "${APP_USER}"
fi
usermod -aG docker "${APP_USER}"

echo "[6/8] Preparing OpenClaw home..."
mkdir -p "${APP_HOME}/.openclaw"
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}/.openclaw"

echo "[7/8] Enabling host firewall..."
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow OpenSSH
ufw allow 41641/udp comment 'Tailscale (optional direct path)'
ufw --force enable

echo "[8/8] Enabling fail2ban..."
systemctl enable --now fail2ban

echo
echo "Bootstrap complete."
echo "Next: run scripts/02-install-tailscale.sh"
