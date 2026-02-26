#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./05-setup-collab-tmux.sh"
  exit 1
fi

COLLAB_USER="${COLLAB_USER:-aiops}"
COLLAB_GROUP="${COLLAB_GROUP:-ai-collab}"
COLLAB_MEMBERS="${COLLAB_MEMBERS:-}"
TMUX_SOCKET_DIR="${TMUX_SOCKET_DIR:-/var/run/tmux-ai}"
TMUX_SOCKET="${TMUX_SOCKET_DIR}/shared.sock"
TMUX_SESSION="${TMUX_SESSION:-ai}"
ENABLE_SYSTEMD="${ENABLE_SYSTEMD:-true}"
SSHD_HARDEN_FILE="${SSHD_HARDEN_FILE:-/etc/ssh/sshd_config.d/99-openclaw-tailnet.conf}"

echo "[1/6] Ensuring collaboration group/user..."
if ! getent group "${COLLAB_GROUP}" >/dev/null 2>&1; then
  groupadd "${COLLAB_GROUP}"
fi
if ! id -u "${COLLAB_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${COLLAB_USER}"
fi
usermod -aG "${COLLAB_GROUP}",sudo,docker,adm "${COLLAB_USER}"

if [[ -n "${COLLAB_MEMBERS}" ]]; then
  IFS=',' read -ra MEMBERS <<< "${COLLAB_MEMBERS}"
  for member in "${MEMBERS[@]}"; do
    member="$(echo "${member}" | xargs)"
    [[ -z "${member}" ]] && continue
    if id -u "${member}" >/dev/null 2>&1; then
      usermod -aG "${COLLAB_GROUP}" "${member}"
    else
      echo "  WARN: member user not found, skipping: ${member}"
    fi
  done
fi

echo "[2/6] Ensuring tmux is installed..."
if ! command -v tmux >/dev/null 2>&1; then
  apt-get update
  apt-get install -y tmux
fi

echo "[3/6] Creating shared tmux socket directory..."
install -d -m 2770 -o "${COLLAB_USER}" -g "${COLLAB_GROUP}" "${TMUX_SOCKET_DIR}"

echo "[4/6] Starting shared tmux session..."
runuser -u "${COLLAB_USER}" -- tmux -S "${TMUX_SOCKET}" new-session -Ad -s "${TMUX_SESSION}"
chgrp "${COLLAB_GROUP}" "${TMUX_SOCKET}"
chmod 660 "${TMUX_SOCKET}"

if [[ "${ENABLE_SYSTEMD}" == "true" ]]; then
  echo "[5/6] Installing tmux-ai.service for reboot persistence..."
  cat >/etc/systemd/system/tmux-ai.service <<EOF
[Unit]
Description=Shared tmux collaboration session
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/install -d -m 2770 -o ${COLLAB_USER} -g ${COLLAB_GROUP} ${TMUX_SOCKET_DIR}
ExecStart=/usr/sbin/runuser -u ${COLLAB_USER} -- /usr/bin/tmux -S ${TMUX_SOCKET} new-session -Ad -s ${TMUX_SESSION}
ExecStartPost=/bin/chgrp ${COLLAB_GROUP} ${TMUX_SOCKET}
ExecStartPost=/bin/chmod 660 ${TMUX_SOCKET}
ExecStop=/usr/sbin/runuser -u ${COLLAB_USER} -- /usr/bin/tmux -S ${TMUX_SOCKET} kill-session -t ${TMUX_SESSION}
ExecStopPost=/bin/rm -f ${TMUX_SOCKET}

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now tmux-ai.service
else
  echo "[5/6] Skipping systemd persistence (ENABLE_SYSTEMD=${ENABLE_SYSTEMD})..."
fi

echo "[6/6] Ensuring collab SSH login is allowed..."
if [[ -f "${SSHD_HARDEN_FILE}" ]] && grep -q '^AllowUsers[[:space:]]' "${SSHD_HARDEN_FILE}"; then
  if ! grep -Eq "(^|[[:space:]])${COLLAB_USER}([[:space:]]|$)" "${SSHD_HARDEN_FILE}"; then
    sed -i.bak -E "s/^AllowUsers[[:space:]]+(.+)$/AllowUsers \\1 ${COLLAB_USER}/" "${SSHD_HARDEN_FILE}"
    sshd -t
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  fi
fi

echo
echo "Shared tmux collaboration setup complete."
echo "Attach command:"
echo "  tmux -S ${TMUX_SOCKET} attach -t ${TMUX_SESSION}"
