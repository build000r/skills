# Deployment Workflow (DO + Tailscale + Telegram + SPAPS)

Use this sequence when creating a new client claw box.

---

## Architectural Decision: New Droplet vs Existing Droplet

Make this decision before collecting inputs or building a kit.

### Option A — New droplet (fully isolated)

```
New DigitalOcean droplet
  └── Docker container: new-claw
        ├── Own Tailscale node
        ├── Own Telegram bot
        ├── Own SPAPS agent ID
        └── Own agent API key (scoped to target service)
```

**Choose this when:**
- You want complete blast-radius isolation (claw can't affect other infra even if compromised)
- The claw runs at high volume or autonomously on a schedule
- You want separate billing visibility per claw
- This is a client deployment (not internal)

**Cost:** New droplet (~$12-18/mo for 2GB). Full bootstrap-do.sh + Tailscale install required.

---

### Option B — Existing droplet, new Docker container (co-located)

```
Existing DigitalOcean droplet
  ├── Docker container: existing-claw     (unchanged)
  │     ├── @existing_bot
  │     ├── Agent key A
  │     └── SPAPS agent A
  │
  └── Docker container: new-claw         (new)
        ├── @new_bot                      ← separate Telegram bot
        ├── Agent key B                   ← scoped to new target only
        └── SPAPS agent B                 ← separate approval thread
```

**Choose this when:**
- You're adding a purpose-specific claw to an existing box (e.g., a content-creation agent alongside an ops agent)
- The new claw has a narrow, low-risk write scope (e.g., draft-only content creation)
- You want to save droplet costs while keeping logical separation

**Isolation guarantees:**
- ✅ Separate Telegram bot — completely distinct identity and channel
- ✅ Separate agent API key — scoped credentials, no access bleed
- ✅ Separate SPAPS agent ID — separate approval threads
- ✅ Docker filesystem namespace — containers cannot read each other's `.env` or configs
- ✅ Separate SOUL.md / AGENTS.md — distinct identity and constraints
- ⚠️ Shared Tailscale node — each container gets its own port; route by container name not IP
- ⚠️ Shared Docker daemon — standard multi-container risk, acceptable for internal use

**Prerequisites on existing droplet:** Docker already running (it is if existing claw uses sandbox mode). No new Tailscale install needed. No new bootstrap-do.sh.

**Important: co-located claws share the same Linux user (`openclaw`).** The `APP_HOME` (e.g. `/home/openclaw-ingredient`) is a directory path created by the install script — it is NOT a new Linux user account. Both gateway processes run under the `openclaw` user, differentiated by `OPENCLAW_STATE_DIR` and `OPENCLAW_CONFIG_PATH` env vars set in their respective systemd units.

**Deploy steps (Option B only):**
1. Build kit locally as normal (new_client_kit.sh)
2. Copy kit to a **new path** on the existing droplet: `/opt/<new-claw-name>-openclaw/`
   — do NOT overwrite `/opt/openclaw-client-kit/` (existing claw's path)
3. Skip `scripts/01-bootstrap-do.sh` and `scripts/02-install-tailscale.sh` (already done)
4. Run `scripts/03-install-openclaw.sh` with a **different service + home path**:
   - `OPENCLAW_SERVICE_NAME=openclaw-<new-claw-name>.service`
   - `APP_USER=openclaw` (same Linux user as existing claw)
   - `APP_HOME=/home/<new-claw-name>` (new directory, not a new Linux user)
   - `OPENCLAW_HOME=/home/<new-claw-name>/.openclaw`
   - Example:
     `KIT_DIR=/opt/<new-claw-name>-openclaw APP_USER=openclaw APP_HOME=/home/<new-claw-name> OPENCLAW_HOME=/home/<new-claw-name>/.openclaw OPENCLAW_SERVICE_NAME=openclaw-<new-claw-name>.service ./scripts/03-install-openclaw.sh`
5. Run `scripts/04-validate.sh` with the same `APP_HOME`, `OPENCLAW_HOME`, and `OPENCLAW_SERVICE_NAME` values
6. Verify both systemd services are active:
   `systemctl status openclaw.service openclaw-<new-claw-name>.service`

**Critical: do not share volumes** — each container mounts only its own kit directory. Never mount `/opt/existing-claw/` into the new container.

### Accessing co-located claws via CLI

Since both claws run under the same Linux user, you can't use `su - <claw-name>`. Instead, override the state dir env vars:

```bash
# Talk to a co-located claw (e.g. ingredient-claw at /home/openclaw-ingredient)
OPENCLAW_STATE_DIR=/home/openclaw-ingredient/.openclaw \
OPENCLAW_CONFIG_PATH=/home/openclaw-ingredient/.openclaw/openclaw.json \
/home/openclaw/.npm-global/bin/openclaw agents list

# Send a message to an agent
OPENCLAW_STATE_DIR=/home/openclaw-ingredient/.openclaw \
OPENCLAW_CONFIG_PATH=/home/openclaw-ingredient/.openclaw/openclaw.json \
/home/openclaw/.npm-global/bin/openclaw agent \
  --agent content-creator \
  --message "summarize recent work" \
  --json

# Continue a conversation thread
OPENCLAW_STATE_DIR=... openclaw agent \
  --agent content-creator \
  --session-id <id-from-previous-response> \
  --message "follow-up question" \
  --json
```

**Note:** The `--agent` value is the agent ID shown in `openclaw agents list` (e.g. `content-creator`), **not** the persona name from `SOUL.md`. These are different things.

**Gateway port:** Each co-located claw uses a different gateway port (configured in its `openclaw.json`). If the WebSocket gateway closes with code 1006, `openclaw agent` falls back to embedded mode automatically — this is safe for debugging but the 1006 itself is worth investigating separately.

## Provider Swap Runbook (Codex/OpenAI/OpenRouter/Anthropic)

Use this ordered runbook when switching providers or rotating tokens:

1. Update model IDs first (`agents.defaults.model.primary`) in each target `openclaw.json`.
   - Codex/OpenAI direct: `openai/gpt-5.2-codex` or `openai/gpt-5.3-codex`
   - OpenRouter: `openrouter/openai/gpt-5.2-codex` or `openrouter/openai/gpt-5.3-codex`
   - Anthropic: `anthropic/<model>`
2. Deploy config files and restart services once.
3. Rotate credentials with:
   - Codex default: `bash scripts/update-oauth-token.sh`
   - OpenAI API key: `OPENAI_API_KEY=sk-proj-... bash scripts/update-oauth-token.sh --openai`
   - OpenRouter key: `OPENROUTER_API_KEY=sk-or-v1-... bash scripts/update-oauth-token.sh --openrouter`
   - Anthropic: `echo "sk-ant-..." | bash scripts/update-oauth-token.sh --anthropic`
4. Verify with:
   - `bash scripts/talk.sh --list`
   - `bash scripts/talk.sh --health`
   - `bash scripts/talk.sh --health --require-root-proof --json` (definitive SSH/UFW proof; fails if checks are only inferred)
   - `bash scripts/talk.sh --claw <name> --new --message "Reply ONLY: OK"`

Verification notes:
- `talk.sh --list` is timeboxed per claw. A slow or unhealthy claw now prints partial output instead of stalling the entire command.
- `review_live.sh` may report SSH hardening as inferred when `sshd -T` cannot be root-verified from the SSH user. Treat inferred secure state as warning-level unless `--require-root-proof` is requested.

Why this order matters:
- `openai/gpt-5.3-codex` resolves to the `openai-codex` provider, which needs token auth state (`auth-profiles.json`) in addition to env sync.
- Updating credentials before model alignment can produce misleading `No API key found for provider ...` errors.

Common failure signatures:
- `No API key found for provider "openai-codex"`: provider auth store missing or wrong schema.
- `No API key found for provider "anthropic"` while model is OpenAI (or inverse): model/provider mismatch.
- `Missing scopes: api.responses.write` (OpenAI): current token lacks required write scope. Use `--openai` with direct API key or switch to `--openrouter`.
- `Unknown config keys`: remove unsupported keys (notably `reasoningEffort` on this runtime).

---

## Storage Decision: Persistent Volume vs Root Disk

Make this decision alongside the droplet architecture choice.

### What needs to survive a restart

| Data | Survives container restart? | Survives droplet rebuild? | Notes |
|------|-----------------------------|--------------------------|-------|
| Kit config (`openclaw.json`, SOUL.md) | ✅ (on root disk) | ❌ | Rebuild from local kit — always re-deployable |
| Secrets (`.env`) | ✅ (on root disk) | ❌ | Rebuild from local kit |
| Agent memory / session state | Depends on OpenClaw internals | ❌ | Main reason to persist |
| Logs | ✅ (on root disk) | ❌ | Lost on rebuild — useful for debugging |
| Workspace scratch files | ✅ (on root disk) | ❌ | Claw-created files during operation |

**Key insight:** If the claw's real state lives in an external database (e.g., draft content in a backend API), a restart loses nothing meaningful — the claw re-queries on next run and picks up where it left off. Persistent volumes matter most for claws that accumulate local context or where logs are critical.

---

### Option 1 — Root disk only (default)

Kit lives at `/opt/<claw-name>/` on the droplet's root disk. Docker mounts it into the container.

- ✅ No extra cost or setup
- ✅ Survives container restarts and power cycles
- ❌ Lost if droplet is destroyed or rebuilt
- ❌ Can't migrate a single claw to a new droplet without data migration

**Best for:** Single-purpose claws where external DB holds all meaningful state.

---

### Option 2 — DO Block Storage volume per claw

A separate DigitalOcean volume (~$1-2/mo for 10-20GB) attached to the droplet, mounted per claw.

```
Droplet root disk
  └── /opt/<claw-name>/   ← symlink or bind mount to volume

DO Volume: <claw-name>-data  (detachable, ~$1-2/mo)
  └── /mnt/<claw-name>/
        ├── openclaw.json
        ├── .env
        ├── logs/
        └── workspace/
```

- ✅ Survives droplet destruction and rebuild
- ✅ **Detachable** — migrate claw to a new droplet by detaching + reattaching volume
- ✅ Complete per-claw isolation, independently resizable
- ✅ Best if you start on Option B (co-located) and later promote to Option A (own droplet)
- ⚠️ Small extra cost (~$1-2/mo per claw)

**Best for:** Claws you expect to run long-term or eventually migrate to their own droplet.

---

### Option 3 — One shared DO volume, subdirectories per claw

One volume, split by directory. Mount only the claw's own subdirectory into each container.

```
DO Volume: openclaw-shared-data  (~$1/mo)
  ├── /mnt/claw-storage/claw-a/
  └── /mnt/claw-storage/claw-b/

Container A mounts: /mnt/claw-storage/claw-a/  → /data
Container B mounts: /mnt/claw-storage/claw-b/  → /data
```

- ✅ Cheapest persistent option (~$1/mo covers both claws)
- ✅ Survives droplet destruction
- ⚠️ Not independently detachable per claw (volume contains both)
- ⚠️ Requires correct chmod/ownership to prevent cross-read at OS level

**Best for:** Co-located claws (Option B) you're confident will stay on the same droplet.

---

### Recommendation matrix

| Scenario | Storage choice |
|----------|----------------|
| Claw state lives in external DB (e.g., draft content) | Option 1 (root disk) — volumes unnecessary |
| Long-running claw, want rebuild safety | Option 2 (volume per claw) |
| Co-located claws, cost-sensitive, staying put | Option 3 (shared volume) |
| Co-located now, may promote to own droplet later | Option 2 (volume per claw — already detachable) |

---

## Inputs To Collect First

- Client name / slug
- DigitalOcean project and region
- Operator Telegram user IDs
- Telegram bot token (BotFather)
- SPAPS credentials (API URL, API key, agent ID, agent secret)
- Unclawg portal URL
- Tailscale auth key (ephemeral or reusable per policy)
- List of integrations and their read-only scopes

## Permission Blueprint for New Skill + Endpoint Combos

Use this whenever a claw gains a new integration (new API family + new skill).

### Step 1 — Wrap the integration

Create one wrapper command per integration under `${OPENCLAW_HOME}/bin`.

- Example: `ccurl` for `https://*.your-api.example.com`
- Wrapper should enforce: allowed hosts, allowed protocol (`https`), blocked dangerous flags (`--config`, `--proxy`, `--resolve`, `--connect-to`)

### Step 2 — Pick execution posture

- `ask: "always"` for strict human-gated mode (default analyst profile)
- `security: "allowlist"` + `ask: "on-miss"` for autonomous reads with approval fallback

### Step 3 — Allowlist every command segment

If skill examples use pipelines, each segment must be allowed.

```bash
# Example: ingredient skill read path
openclaw approvals allowlist add --agent "*" "/home/openclaw-ingredient/.openclaw/bin/ccurl"
openclaw approvals allowlist add --agent "*" "/usr/bin/jq"
```

### Step 4 — Approval targets must be concrete

In `openclaw.json`, do not use `${env:...}` for approval recipients.
Use fixed IDs/handles in `approvals.exec.targets[*].to`.

```json
{
  "approvals": {
    "exec": {
      "targets": [
        { "channel": "telegram", "to": "OPERATOR_TELEGRAM_ID" }
      ]
    }
  }
}
```

### Step 5 — Skill docs must match runtime policy

`SKILL.md` examples must:

- use wrapper commands (not raw `curl`/`node`)
- use env vars for auth headers
- list allowed read endpoints and blocked write/status/delete endpoints

### Concrete examples

1. Ingredient data combo:
   - Wrapper: `ccurl`
   - Skill examples: `ccurl ... | jq ...`
   - Allowlist: `ccurl` + `jq`
   - Approval mode: `on-miss` for non-allowlisted commands
2. Future accounting combo:
   - Wrapper: `qbget` (GET-only, fixed QuickBooks host)
   - Skill examples: `qbget "/v3/company/.../query?..."`
   - Writes: never direct from skill; generate proposal for portal approval

## Build Kit Locally

1. Instantiate from skill assets (interactive mode prompts for all values):
   - `scripts/new_client_kit.sh --dest /tmp/<client>-openclaw --interactive`
2. Or use flags directly:
   - `scripts/new_client_kit.sh --dest /tmp/<client>-openclaw --client-name "Client" --telegram-allowed-user 123456789 --telegram-group-chat -1001234567890 --bot-token "..." --spaps-url "..." --spaps-key "..." --spaps-agent-id "..." --spaps-secret "..."`
3. Verify no remaining placeholders:
   - `scripts/validate_client_kit.sh /tmp/<client>-openclaw`
4. Optional for `review_live.sh` auto-detection:
   - Copy `references/deployed-instances.example.md` to local `references/deployed-instances.md` and add real host details (this file is gitignored).

## Deploy To Droplet

1. Create Ubuntu 24.04 droplet (minimum 2GB RAM, recommend 4GB for production)
   - DigitalOcean $200 free credit: `https://www.digitalocean.com/` (sign up for free tier)
2. Copy kit to droplet path:
   - `/opt/openclaw-client-kit`
3. Run scripts in strict order:
   - `scripts/01-bootstrap-do.sh` (installs Node.js 22, Docker, hardening)
   - `scripts/02-install-tailscale.sh` (enforces Tailnet-only SSH + disables root SSH)
   - `scripts/03-install-openclaw.sh` (pre-places config, installs CLI, starts service)
   - `scripts/04-validate.sh` (includes SPAPS + portal connectivity checks)
   - Optional: `scripts/05-setup-collab-tmux.sh` (shared `tmux` socket + non-root collab user)
4. Remove any public `22/tcp` allow rule in the cloud firewall/security group.

If shared tmux is enabled, operators attach with:

```bash
tmux -S /var/run/tmux-ai/shared.sock attach -t ai
```

## Notification and Approval Test

1. Send `/start` to the bot from an allowlisted operator account
2. Confirm non-allowlisted account cannot interact
3. Trigger an exec action that requires approval
4. Confirm Telegram sends a notification with a portal link
5. Open the link in the Unclawg portal and approve/reject
6. Confirm SPAPS records the approval state change

## Post-Deploy Stabilization Checks (First 15 Minutes)

1. Validate bot token directly:
   - `curl -s "https://api.telegram.org/bot$OPENCLAW_TG_TOKEN/getMe"`
2. Confirm the right operator IDs are allowlisted:
   - `jq '.channels.telegram.groupAllowFrom, .channels.telegram.groups' <openclaw-home>/openclaw.json`
3. Verify model id is runtime-supported (watch logs for `Unknown model`):
   - `journalctl -u <service> -n 120 --no-pager`
4. Confirm service auto-recovers from config-triggered restarts:
   - Unit should use `Restart=always`
5. For co-located claws, run live review against the specific unit/home:
   - `scripts/review_live.sh --host <ip> --service <unit> --home <openclaw-home> --user <app-user>`
6. If persona seems "forgotten" after `/reset`, verify identity files exist in both:
   - `<openclaw-home>/SOUL.md`, `AGENTS.md`, `USER.md`
   - `<openclaw-home>/workspace/SOUL.md`, `AGENTS.md`, `USER.md`, `IDENTITY.md`
   - Remove stale `BOOTSTRAP.md` from workspace/sandbox if present.

## First Claw Prompt Sequence

1. `Inventory connected systems and all current access scopes.`
2. `List top 10 opportunities with expected impact and confidence.`
3. `Convert top 3 into approval-ready action cards including rollback.`

## Handoff Artifacts

- Completed `.env` (stored securely — server only, never committed)
- Final `openclaw.json`
- First proposals generated by the agent
- Operator runbook with ownership and escalation channel

## Post-Deploy: Back Up to Skill

After a successful deploy, commit the non-secret config back to the skill so the
droplet root disk is fully expendable:

```bash
CLAW=<claw-name>
DEST=~/.claude/skills/openclaw-client-bootstrap/assets/instances/$CLAW
mkdir -p $DEST

# Copy non-secret files from the generated kit
cp /tmp/$CLAW-openclaw/openclaw.json $DEST/
cp /tmp/$CLAW-openclaw/SOUL.md $DEST/
cp /tmp/$CLAW-openclaw/AGENTS.md $DEST/
cp /tmp/$CLAW-openclaw/USER.md $DEST/

# Scrub real secret values, save as .env.example
sed 's/=.\+/=REPLACE_ME/' /tmp/$CLAW-openclaw/.env > $DEST/.env.example

# Commit
cd ~/.claude
git add skills/openclaw-client-bootstrap/assets/instances/$CLAW
git commit -m "chore(openclaw): add $CLAW instance config"
```

Then add the instance to `references/deployed-instances.md`.
