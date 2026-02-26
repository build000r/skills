# Review Rubric — OpenClaw Client Bootstrap

Three review modes. Each category is scored pass/fail. Final grade = pass count / total checks.

---

## File-Based Review (`--skill` or `/path/to/kit`)

### 1. Config Schema (openclaw.json)

| # | Check | Pass Condition |
|---|-------|---------------|
| 1.1 | Valid JSON | `jq empty` succeeds |
| 1.2 | No removed keys | No `agents.list[].prompt`, `channels.pairing`, `channels.telegram.token` |
| 1.3 | Correct token key | Uses `telegram.botToken` (not `channels.telegram.token`) |
| 1.4 | exec.ask type | `tools.exec.ask` is a string (`"always"`, `"on-miss"`, `"off"`), not an array |
| 1.4b | exec.safeBins semantics | `tools.exec.safeBins` is a non-empty array of executable names (no `/` path separators) |
| 1.5 | Group allowlist policy present | `channels.telegram.groupPolicy=="allowlist"` with non-empty `groupAllowFrom` and `groups` |
| 1.6 | approvals mode present | `approvals.exec.mode` exists |
| 1.7 | Approval target present | `approvals.exec.targets[0].channel` exists |
| 1.7b | Approval target recipient concrete | `approvals.exec.targets[*].to` does not use `${env:...}` interpolation |
| 1.8 | Sandbox read-only | `agents.defaults.sandbox.workspaceAccess` is `"ro"` |
| 1.9 | Write tools denied | `tools.deny` includes `write`, `edit`, `apply_patch` |
| 1.10 | Placeholder format | Uses `{{TELEGRAM_ALLOWED_USER_ID}}` + `{{TELEGRAM_GROUP_CHAT_ID}}` (not legacy format) |

### 2. Environment (.env.example)

| # | Check | Pass Condition |
|---|-------|---------------|
| 2.1 | Gateway token | `OPENCLAW_GATEWAY_TOKEN` present |
| 2.2 | Bot token | `OPENCLAW_TG_TOKEN` present |
| 2.2b | Group chat env | `TELEGRAM_GROUP_CHAT_IDS` present |
| 2.2c | Operator allowlist env | `TELEGRAM_ALLOWED_USER_IDS` present |
| 2.3 | SPAPS vars | All 4 present: `SPAPS_API_URL`, `SPAPS_API_KEY`, `SPAPS_AGENT_ID`, `SPAPS_AGENT_SECRET` |
| 2.4 | Portal URL | `UNCLAWG_PORTAL_URL` present |
| 2.5 | No legacy vars | No `TELEGRAM_APPROVAL_CHAT_ID` |

### 3. Scripts

| # | Check | Pass Condition |
|---|-------|---------------|
| 3.1 | Shell syntax | All `scripts/*.sh` pass `bash -n` |
| 3.2 | Bootstrap prereqs | `01-bootstrap-do.sh` installs Node.js 22+, Docker, and tmux |
| 3.3 | Install prereq checks | `03-install-openclaw.sh` checks for node and docker before proceeding |
| 3.4 | Pre-place config | `03-install-openclaw.sh` copies config files before running `openclaw setup` |
| 3.5 | Placeholder check | `03-install-openclaw.sh` checks for group/allowlist placeholders (not legacy format) |
| 3.6 | SPAPS connectivity | `04-validate.sh` checks SPAPS API reachability |
| 3.7 | Portal connectivity | `04-validate.sh` checks Unclawg portal reachability |
| 3.8 | Config path updated | `04-validate.sh` checks `channels.telegram.enabled` with legacy fallback |
| 3.9 | Approval target sanity | `04-validate.sh` fails if `approvals.exec.targets[*].to` uses `${env:...}` |
| 3.10 | Tailnet SSH hardening | `02-install-tailscale.sh` enforces `PermitRootLogin no`, `AllowUsers`, and Tailnet SSH UFW rules |
| 3.11 | Shared tmux optional script | `05-setup-collab-tmux.sh` exists for controlled multi-operator sessions |

### 4. Documentation Consistency

| # | Check | Pass Condition |
|---|-------|---------------|
| 4.1 | Architecture alignment | All docs describe Telegram as notification channel, not approval surface |
| 4.2 | SPAPS mentioned | SKILL.md, README.md, AGENTS.md, deployment-workflow.md all reference SPAPS |
| 4.3 | Portal mentioned | Approval docs reference Unclawg portal |
| 4.4 | Placeholder format | All docs use new Telegram group/allowlist placeholders (not legacy format) |
| 4.5 | Min spec | Docs say 2GB min (not 1GB) |
| 4.6 | No TELEGRAM_APPROVAL_CHAT_ID | No doc references this removed variable |
| 4.7 | No channels.pairing | No doc references this removed config path |
| 4.8 | No legacy tools.elevated keys | No docs reference `tools.elevated.require` or `allowWhenRequestedBy` |

### 5. Generator (new_client_kit.sh)

| # | Check | Pass Condition |
|---|-------|---------------|
| 5.1 | Interactive mode | Supports `--interactive` flag |
| 5.2 | SPAPS flags | Accepts `--spaps-url`, `--spaps-key`, `--spaps-agent-id`, `--spaps-secret` |
| 5.3 | Placeholder substitution | Replaces `{{TELEGRAM_ALLOWED_USER_ID}}`, `{{TELEGRAM_GROUP_CHAT_ID}}`, and `{{CLIENT_NAME}}` across all files |
| 5.4 | Summary output | Shows filled vs. remaining values |
| 5.5 | Remaining marker check | Reports files with unfilled `{{...}}` markers |

### 6. Validator (validate_client_kit.sh)

| # | Check | Pass Condition |
|---|-------|---------------|
| 6.1 | Schema checks | Detects removed keys (`prompt`, `pairing`, `channels.telegram.token`) and enforces group allowlist fields |
| 6.2 | exec.ask type check | Catches array vs. string |
| 6.2b | exec.safeBins semantic check | Catches empty/path-style `tools.exec.safeBins` values |
| 6.2c | Approval recipient interpolation check | Catches `${env:...}` in `approvals.exec.targets[*].to` |
| 6.2d | SSH hardening checks | Catches missing `PermitRootLogin no`, `AllowUsers`, or Tailnet SSH rule in `02-install-tailscale.sh` |
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
| L4.2 | No removed keys | No `prompt`, `channels.pairing`, `channels.telegram.token` |
| L4.3 | Token key | Uses `botToken` (not `token`) |
| L4.3b | Telegram group allowlist policy | `groupPolicy=="allowlist"` with non-empty `groupAllowFrom` and `groups` |
| L4.4 | exec.ask type | String, not array |
| L4.4b | exec.safeBins semantics | Non-empty array of executable names (no path-style entries) |
| L4.4c | tools.elevated allowlist | `tools.elevated.enabled=true` and non-empty `allowFrom.telegram` |
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
| L7.2 | Unclawg portal | `curl` to portal URL succeeds |

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
| L9.2 | Root SSH login | Disabled in sshd config |
| L9.3 | SSH boundary | UFW does not allow `22/tcp` from `Anywhere`; Tailnet scope present |
| L9.4 | No write creds | No obvious write credentials in .env |
| L9.5 | Security audit | `openclaw security audit --deep` clean |

### Live Scoring

- **All pass**: Ship it
- **>= 90%**: Minor gaps, fix before traffic
- **>= 80%**: Needs another pass
- **< 80%**: Significant rework needed
