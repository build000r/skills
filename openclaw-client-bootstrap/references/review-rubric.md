# Review Rubric — OpenClaw Client Bootstrap

Three review modes. Each category is scored pass/fail. Final grade = pass count / total checks.

---

## File-Based Review (`--skill` or `/path/to/kit`)

### 1. Config Schema (openclaw.json)

| # | Check | Pass Condition |
|---|-------|---------------|
| 1.1 | Valid JSON | `jq empty` succeeds |
| 1.2 | No removed keys | No `agents.list[].prompt`, `channels.pairing`, `tools.elevated`, `channels.telegram.token` |
| 1.3 | Correct token key | Uses `telegram.botToken` (not `channels.telegram.token`) |
| 1.4 | exec.ask type | `tools.exec.ask` is a string (`"always"`, `"on-miss"`, `"off"`), not an array |
| 1.4b | exec.safeBins semantics | `tools.exec.safeBins` is a non-empty array of executable names (no `/` path separators) |
| 1.5 | DM policy present | `channels.telegram.dmPolicy` exists |
| 1.6 | approvals mode present | `approvals.exec.mode` exists |
| 1.7 | Approval target present | `approvals.exec.targets[0].channel` exists |
| 1.7b | Approval target recipient concrete | `approvals.exec.targets[*].to` does not use `${env:...}` interpolation |
| 1.8 | Sandbox read-only | `agents.defaults.sandbox.workspaceAccess` is `"ro"` |
| 1.9 | Write tools denied | `tools.deny` includes `write`, `edit`, `apply_patch` |
| 1.10 | Placeholder format | Uses `{{TELEGRAM_USER_ID}}` (not `<YOUR_TELEGRAM_USER_ID>`) |

### 2. Environment (.env.example)

| # | Check | Pass Condition |
|---|-------|---------------|
| 2.1 | Gateway token | `OPENCLAW_GATEWAY_TOKEN` present |
| 2.2 | Bot token | `OPENCLAW_TG_TOKEN` present |
| 2.3 | SPAPS vars | All 4 present: `SPAPS_API_URL`, `SPAPS_API_KEY`, `SPAPS_AGENT_ID`, `SPAPS_AGENT_SECRET` |
| 2.4 | Portal URL | `OPENCLAWTH_PORTAL_URL` present |
| 2.5 | No legacy vars | No `TELEGRAM_APPROVAL_CHAT_ID` |

### 3. Scripts

| # | Check | Pass Condition |
|---|-------|---------------|
| 3.1 | Shell syntax | All `scripts/*.sh` pass `bash -n` |
| 3.2 | Bootstrap prereqs | `01-bootstrap-do.sh` installs Node.js 22+ and Docker |
| 3.3 | Install prereq checks | `03-install-openclaw.sh` checks for node and docker before proceeding |
| 3.4 | Pre-place config | `03-install-openclaw.sh` copies config files before running `openclaw setup` |
| 3.5 | Placeholder check | `03-install-openclaw.sh` checks for `{{TELEGRAM_USER_ID}}` (not legacy format) |
| 3.6 | SPAPS connectivity | `04-validate.sh` checks SPAPS API reachability |
| 3.7 | Portal connectivity | `04-validate.sh` checks OpenClawth portal reachability |
| 3.8 | Config path updated | `04-validate.sh` checks `channels.telegram.enabled` with legacy fallback |
| 3.9 | Approval target sanity | `04-validate.sh` fails if `approvals.exec.targets[*].to` uses `${env:...}` |

### 4. Documentation Consistency

| # | Check | Pass Condition |
|---|-------|---------------|
| 4.1 | Architecture alignment | All docs describe Telegram as notification channel, not approval surface |
| 4.2 | SPAPS mentioned | SKILL.md, README.md, AGENTS.md, deployment-workflow.md all reference SPAPS |
| 4.3 | Portal mentioned | Approval docs reference OpenClawth portal |
| 4.4 | Placeholder format | All docs use `{{TELEGRAM_USER_ID}}` (not `<YOUR_TELEGRAM_USER_ID>`) |
| 4.5 | Min spec | Docs say 2GB min (not 1GB) |
| 4.6 | No TELEGRAM_APPROVAL_CHAT_ID | No doc references this removed variable |
| 4.7 | No channels.pairing | No doc references this removed config path |
| 4.8 | No tools.elevated | No doc references this removed config path |

### 5. Generator (new_client_kit.sh)

| # | Check | Pass Condition |
|---|-------|---------------|
| 5.1 | Interactive mode | Supports `--interactive` flag |
| 5.2 | SPAPS flags | Accepts `--spaps-url`, `--spaps-key`, `--spaps-agent-id`, `--spaps-secret` |
| 5.3 | Placeholder substitution | Replaces `{{TELEGRAM_USER_ID}}` and `{{CLIENT_NAME}}` across all files |
| 5.4 | Summary output | Shows filled vs. remaining values |
| 5.5 | Remaining marker check | Reports files with unfilled `{{...}}` markers |

### 6. Validator (validate_client_kit.sh)

| # | Check | Pass Condition |
|---|-------|---------------|
| 6.1 | Schema checks | Detects removed keys (`prompt`, `pairing`, `elevated`, `channels.telegram.token`) |
| 6.2 | exec.ask type check | Catches array vs. string |
| 6.2b | exec.safeBins semantic check | Catches empty/path-style `tools.exec.safeBins` values |
| 6.2c | Approval recipient interpolation check | Catches `${env:...}` in `approvals.exec.targets[*].to` |
| 6.3 | SPAPS placeholder checks | Catches unfilled SPAPS env vars |
| 6.4 | Template marker check | Catches remaining `{{...}}` markers |
| 6.5 | Legacy placeholder check | Catches `<YOUR_TELEGRAM_USER_ID>` if present |

### File-Based Scoring

- **All checks pass**: Ship it
- **>= 90%**: Minor gaps, fix before deploy
- **>= 80%**: Needs another pass
- **< 80%**: Significant rework needed

---

## Live Deployment Review (`--live`)

SSHes into the droplet (auto-detects from local `deployed-instances.md` when present, or takes explicit host).
Use `--strict` for production gating where missing SPAPS/portal vars are hard failures.

### L1. Connectivity

| # | Check | Pass Condition |
|---|-------|---------------|
| L1.1 | SSH connection | Can SSH into host within 10s |

### L2. Service Health

| # | Check | Pass Condition |
|---|-------|---------------|
| L2.1 | openclaw.service | `systemctl is-active openclaw` = active |
| L2.2 | tailscaled | `systemctl is-active tailscaled` = active |
| L2.3 | ufw | `systemctl is-active ufw` = active |
| L2.4 | fail2ban | `systemctl is-active fail2ban` = active |

### L3. Prerequisites

| # | Check | Pass Condition |
|---|-------|---------------|
| L3.1 | Node.js | `node --version` >= 22 |
| L3.2 | Docker | `docker --version` returns something |
| L3.3 | Docker group | `openclaw` user is in docker group |
| L3.4 | Swap | >= 1024 MB configured |
| L3.5 | RAM | >= 2 GB total |

### L4. Live Config

| # | Check | Pass Condition |
|---|-------|---------------|
| L4.1 | Valid JSON | Live `openclaw.json` parses |
| L4.2 | No removed keys | No `prompt`, `channels.pairing`, `tools.elevated`, `channels.telegram.token` |
| L4.3 | Token key | Uses `botToken` (not `token`) |
| L4.4 | exec.ask type | String, not array |
| L4.4b | exec.safeBins semantics | Non-empty array of executable names (no path-style entries) |
| L4.5 | Sandbox read-only | `workspaceAccess` = `"ro"` |
| L4.6 | Write tools denied | `tools.deny` includes `write`, `edit`, `apply_patch` |
| L4.7 | No placeholders | No `{{...}}` in live config |
| L4.8 | Approvals mode valid | `approvals.exec.mode` is `targets|both|session` |
| L4.9 | Approval targets configured | Targets exist when mode requires them |
| L4.10 | Approval recipient concrete | No `${env:...}` in `approvals.exec.targets[*].to` |

### L5. Live Environment

| # | Check | Pass Condition |
|---|-------|---------------|
| L5.1 | .env exists | File present at `~/.openclaw/.env` |
| L5.2 | Gateway token | Not placeholder value |
| L5.3 | Bot token | Not placeholder value |
| L5.4 | SPAPS URL | `SPAPS_API_URL` set |

### L6. Tailscale

| # | Check | Pass Condition |
|---|-------|---------------|
| L6.1 | Running | `tailscale status --json` BackendState = Running |
| L6.2 | Serve configured | `tailscale serve status` returns config |

### L7. External Connectivity (from droplet)

| # | Check | Pass Condition |
|---|-------|---------------|
| L7.1 | SPAPS API | `curl` to SPAPS health endpoint succeeds |
| L7.2 | OpenClawth portal | `curl` to portal URL succeeds |

### L8. OpenClaw Runtime

| # | Check | Pass Condition |
|---|-------|---------------|
| L8.1 | Version | `openclaw --version` returns something |
| L8.2 | Config validate | `openclaw config validate` passes |
| L8.3 | Recent logs | <= 2 error/fatal/panic lines in last 200 journal lines |
| L8.4 | Uptime | Service has a start timestamp |

### L9. Security Posture

| # | Check | Pass Condition |
|---|-------|---------------|
| L9.1 | SSH password auth | Disabled in sshd config |
| L9.2 | No write creds | No obvious write credentials in .env |
| L9.3 | Security audit | `openclaw security audit --deep` clean |

### Live Scoring

- **All pass**: Ship it
- **>= 90%**: Minor gaps, fix before traffic
- **>= 80%**: Needs another pass
- **< 80%**: Significant rework needed
