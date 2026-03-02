# First Claw Checklist

Use this for every new client deployment.

## 1. Infrastructure

- [ ] Create DigitalOcean droplet (`Ubuntu 24.04 LTS`, minimum `2GB RAM`, recommend `4GB` for production).
- [ ] Sign up at DigitalOcean (`$200` free credit for new signups).
- [ ] Enable SSH keys and disable password auth.
- [ ] Snapshot baseline droplet after hardening.

## 2. Host Security

- [ ] Run `scripts/01-bootstrap-do.sh` (installs Node.js 22, Docker, hardening).
- [ ] Confirm UFW active with SSH allowed only from Tailnet (`TAILNET_SSH_CIDR` and/or `tailscale0`).
- [ ] Remove public `22/tcp` allow at the cloud firewall/security-group layer.
- [ ] Confirm `fail2ban` running.
- [ ] Confirm Node.js 22+ and Docker installed.

## 3. Private Access

- [ ] Run `scripts/02-install-tailscale.sh`.
- [ ] Confirm node appears in tailnet.
- [ ] Confirm SSH over Tailscale works.
- [ ] Confirm `PermitRootLogin no` and `PasswordAuthentication no`.

## 4. OpenClaw Install

- [ ] Copy `.env.example` to `.env` and fill secrets (including SPAPS credentials).
- [ ] Replace Telegram group + allowlist placeholders in `openclaw.json`.
- [ ] Run `scripts/03-install-openclaw.sh`.
- [ ] Run `scripts/04-validate.sh`.

## 4b. Optional Shared Tmux Collaboration

- [ ] Run `scripts/05-setup-collab-tmux.sh` if multi-operator shell collaboration is required.
- [ ] Confirm `tmux -S /var/run/tmux-ai/shared.sock attach -t ai` works for allowed members.

## 5. SPAPS and Portal

- [ ] Confirm SPAPS API URL, API key, agent ID, and agent secret are set in `.env`.
- [ ] Confirm `04-validate.sh` reports SPAPS API reachable.
- [ ] Confirm `04-validate.sh` reports Unclawg portal reachable.
- [ ] Trigger a test approval and verify it appears in the portal.

## 6. Telegram Notifications

- [ ] Create bot via BotFather and set token.
- [ ] Confirm `channels.telegram.groupPolicy` is `allowlist`.
- [ ] Confirm only operator IDs are in `channels.telegram.groupAllowFrom`.
- [ ] Confirm `channels.telegram.groups` has the target group chat ID as a key.
- [ ] Send a test message from an allowlisted operator account in the configured group.
- [ ] Trigger an approval event and confirm Telegram sends a portal link.

## 7. Read-Only Integrations

- [ ] Connect each system with read-only API scopes.
- [ ] Store write credentials outside OpenClaw.
- [ ] Validate no direct mutating credentials exist on claw host.
- [ ] If adding a new skill + endpoint family, create a wrapper command in `${OPENCLAW_HOME}/bin` and update skill docs to use wrapper-only commands.
- [ ] Allowlist every command segment used by the skill (for example wrapper + `jq`).

## 8. Governance and Prompts

- [ ] Populate `SOUL.md`, `AGENTS.md`, and `USER.md`.
- [ ] Run first discovery prompt:
  - `Inventory all connected systems, scopes, and data freshness.`
- [ ] Run first proposal prompt:
  - `Give top 10 opportunities with impact, risk, and required write action.`
- [ ] Run action-card prompt:
  - `Convert top 3 opportunities into approval-ready action cards.`

## 9. Write Path Validation

- [ ] Review `security/WRITE_GATEWAY_CONTRACT.md`.
- [ ] Review `security/PERMISSIONS_PLAYBOOK.md`.
- [ ] Confirm every mutating action routes through SPAPS approval.
- [ ] Confirm execution logs capture approver, payload hash, and result.
- [ ] Confirm `approvals.exec.targets[*].to` is concrete (no `${env:...}` placeholder).
