# OpenClaw Client Kit (DigitalOcean + Tailscale + Telegram + SPAPS)

Production template for spinning up a new client "first claw" box with:

- DigitalOcean Droplet (Ubuntu 24.04, minimum 2GB RAM)
- Tailscale private access
- Telegram notification channel (sends portal links)
- SPAPS approval backend with OpenClawth portal for human review
- Read-only by default behavior with human-gated escalations

This kit is designed to make the agent useful on day 1:
- It can inspect, summarize, and propose.
- It cannot silently perform writes.
- Any `exec` outside an allowlist creates an approval event; Telegram notifies operators.
- Any external `POST`/`PUT`/`PATCH`/`DELETE` must go through your write gateway process.

## Directory Layout

- `openclaw.json`: hardened baseline config (v2026.2.17 schema)
- `.env.example`: environment variable template (includes SPAPS credentials)
- `AGENTS.md`: operator policy for agent behavior
- `SOUL.md`: non-negotiable guardrails and decision style
- `USER.md`: client context template
- `checklists/FIRST_CLAW_CHECKLIST.md`: handoff checklist for new clients
- `checklists/OPERATOR_RUNBOOK.md`: day-2 operations
- `scripts/01-bootstrap-do.sh`: host hardening + Node.js 22 + Docker
- `scripts/02-install-tailscale.sh`: Tailscale install and join
- `scripts/03-install-openclaw.sh`: OpenClaw install + systemd service
- `scripts/04-validate.sh`: post-install validation + SPAPS/portal connectivity
- `security/WRITE_GATEWAY_CONTRACT.md`: outbound write control pattern
- `security/PERMISSIONS_PLAYBOOK.md`: wrapper + allowlist patterns for new skill/endpoint combos

## Quick Start

1. Create a new Ubuntu 24.04 droplet (minimum 2GB RAM, recommend 4GB).
   - DigitalOcean offers `$200` free credit for new signups at `https://www.digitalocean.com/`.
2. SSH in as root and copy this folder to `/opt/openclaw-client-kit`.
3. Run host bootstrap (installs Node.js 22, Docker, hardening):
```bash
cd /opt/openclaw-client-kit/scripts
sudo ./01-bootstrap-do.sh
```
4. Install and connect Tailscale:
```bash
sudo TAILSCALE_AUTHKEY="tskey-..." TAILSCALE_HOSTNAME="client-a-openclaw" ./02-install-tailscale.sh
```
5. Prepare environment and config:
```bash
cd /opt/openclaw-client-kit
cp .env.example .env
# edit .env (gateway token, bot token, SPAPS credentials)
# edit openclaw.json: replace {{TELEGRAM_USER_ID}} placeholders
```
6. Install OpenClaw and start service:
```bash
cd /opt/openclaw-client-kit/scripts
sudo KIT_DIR="/opt/openclaw-client-kit" APP_USER="openclaw" ./03-install-openclaw.sh
sudo APP_USER="openclaw" ./04-validate.sh
```
   - Co-located claw on an existing droplet:
```bash
sudo KIT_DIR="/opt/<claw>-openclaw" APP_USER="openclaw" APP_HOME="/home/<claw>" \
  OPENCLAW_HOME="/home/<claw>/.openclaw" OPENCLAW_SERVICE_NAME="openclaw-<claw>.service" \
  ./03-install-openclaw.sh
sudo APP_USER="openclaw" APP_HOME="/home/<claw>" OPENCLAW_HOME="/home/<claw>/.openclaw" \
  OPENCLAW_SERVICE_NAME="openclaw-<claw>.service" ./04-validate.sh
```
7. In Telegram, message your bot with `/start` to connect.

## Required Edits Before Go-Live

- Update `.env`:
  - `OPENCLAW_GATEWAY_TOKEN` — tip: `openssl rand -hex 48`
  - `OPENCLAW_TG_TOKEN`
  - `SPAPS_API_URL`, `SPAPS_API_KEY`, `SPAPS_AGENT_ID`, `SPAPS_AGENT_SECRET`
  - `OPENCLAWTH_PORTAL_URL`
- Update `openclaw.json`:
  - Replace `"{{TELEGRAM_USER_ID}}"` placeholders in:
    - `channels.telegram.allowFrom`
    - `approvals.exec.targets[0].to`
  - Keep `approvals.exec.targets[*].to` as a concrete value (numeric user ID or fixed chat ID), not `${env:...}` interpolation
  - Tip: get your Telegram user ID from `@userinfobot` or via `getUpdates`.

## Security Defaults

- Gateway binds to loopback (`gateway.bind: "loopback"`).
- Access is via Tailscale Serve (`--tailscale serve`).
- Telegram DM policy is allowlist-only.
- Telegram control is limited to configured operator IDs.
- Workspace access is read-only.
- Write/edit tools are denied.
- `exec` is operator-gated with `ask: "always"`.
- `tools.exec.safeBins` must contain executable names (for example `jq`, `grep`, `echo`), not directory paths.
- `approvals.exec.targets[*].to` should be a concrete ID/string (runtime env interpolation is not guaranteed there).
- Approvals are forwarded to configured targets (Telegram by default). Add your portal integration as a downstream workflow.

## Permission Patterns for New Skill + Endpoint Combos

When a new skill needs a new endpoint family:

1. Create a wrapper command in `${OPENCLAW_HOME}/bin` (host/domain/method restrictions).
2. Add wrapper + parser bins (`jq`, etc.) to allowlist/safe bins.
3. Keep writes proposal-gated (or draft-only if explicitly approved by governance).
4. Test one allowlisted read, one blocked command, and one approval fallback.

Reference: `security/PERMISSIONS_PLAYBOOK.md`.

## Sources Used for This Template

- OpenClaw install and VPS guidance
- OpenClaw config reference and security (v2026.2.15)
- OpenClaw exec approvals and SPAPS integration docs
- OpenClaw Tailscale gateway docs
- DigitalOcean Ubuntu hardening guidance
- Tailscale CLI reference (`serve`)

Use this as a baseline and tune per client compliance needs.
