---
name: openclaw-client-bootstrap
description: >
  Build a production-ready OpenClaw client setup for DigitalOcean + Tailscale + Telegram + SPAPS
  using a reusable hardened template with read-only defaults and human approval through the Unclawg portal.
  Use when asked to "set up OpenClaw on a droplet", "create a first claw kit", "bootstrap client box",
  "DigitalOcean + Tailscale + Telegram OpenClaw", "read-only OpenClaw config", or "approval-gated OpenClaw setup".
---

# OpenClaw Client Bootstrap

Create and apply a reusable client kit for OpenClaw with strict governance:

- private gateway exposure through Tailscale
- Tailnet-only SSH with non-root logins by default
- Telegram notification channel (sends portal links for approval events)
- SPAPS approval backend with Unclawg portal for human review
- read-only credentials in OpenClaw
- explicit write-gateway contract for all external mutations

## AI Runtime-First Skill Split

Treat tracked skills as AI runtime instructions, and keep operator/admin runbooks private.

- Runtime skills must be wrapper-only (`tools.exec.security: "allowlist"` + `safeBins`).
- Runtime skills should fail closed when required wrapper bins are missing.
- Keep local project overlays in `modes/` (gitignored).
- Keep admin-only skills (for example `unclawg-admin`) gitignored/private.
- Do not point a production claw at `../skills` wholesale; curate a runtime-safe subset.

## Architectural Decision First

Before collecting inputs or building a kit, decide:

**New droplet (Option A)** — full isolation, separate Tailscale node, separate billing. Best for client deployments or high-volume autonomous claws.

**Existing droplet, new Docker container (Option B)** — co-located, separate Telegram bot, separate agent key, separate SPAPS agent. Best for purpose-specific internal claws added to an existing box (e.g., a content-creation agent alongside an ops agent). Saves ~$12-18/mo.

See [references/deployment-workflow.md](references/deployment-workflow.md) — "Architectural Decision" section for isolation guarantees, trade-offs, and Option B deploy steps (skip bootstrap-do.sh + Tailscale, use a different systemd service name).

**Also decide storage before building the kit:** root disk (default, free), DO Block volume per claw (~$1-2/mo, detachable — best if you may migrate later), or shared volume with per-claw subdirs (~$1/mo for co-located claws). See "Storage Decision" section in the same file.

## On Trigger: Instantiate the Kit

Resolve the bundled generator script, then create a client kit directory.

```bash
GEN="$(ls ~/.codex/skills/openclaw-client-bootstrap/scripts/new_client_kit.sh ~/.claude/skills/openclaw-client-bootstrap/scripts/new_client_kit.sh ./scripts/new_client_kit.sh 2>/dev/null | head -1)"
bash "$GEN" --dest /tmp/<client>-openclaw --interactive
```

If `./scripts/...` is used, run the command from the skill directory.

## Required Inputs Before Deployment

Collect these before touching the droplet:

1. Client name and environment label
2. Telegram operator user ID allowlist
3. Telegram group chat ID (and optional topic ID)
4. Telegram bot token (from BotFather)
5. SPAPS credentials (API URL, API key, agent ID, agent secret)
6. Unclawg portal URL
7. Tailscale auth key and node hostname
8. Integration inventory with read-only scopes

Reference: [references/deployment-workflow.md](references/deployment-workflow.md)

## Customize the Kit

1. Fill `.env` values (including SPAPS credentials).
2. Replace Telegram placeholders in `openclaw.json`:
   - `{{TELEGRAM_ALLOWED_USER_ID}}`
   - `{{TELEGRAM_GROUP_CHAT_ID}}`
   - Optional: add `topicId` per group entry when topic-scoped.
   - Keep `approvals.exec.targets[*].to` concrete (numeric ID or explicit chat ID), not `${env:...}`.
3. Review `SOUL.md`, `AGENTS.md`, and `USER.md` for client-specific constraints.
4. Keep `security/WRITE_GATEWAY_CONTRACT.md` intact unless compliance requires stricter rules.
5. For any new endpoint + skill combo, follow `security/PERMISSIONS_PLAYBOOK.md` (wrapper + allowlist pattern).

## Review / Grade Implementation

Run the review script for a second-pass quality check against the [review rubric](references/review-rubric.md):

```bash
REV="$(ls ~/.codex/skills/openclaw-client-bootstrap/scripts/review_kit.sh ~/.claude/skills/openclaw-client-bootstrap/scripts/review_kit.sh 2>/dev/null | head -1)"
bash "$REV" --skill                    # review the skill template
bash "$REV" /tmp/<client>-openclaw     # review a generated kit
bash "$REV" --live                     # SSH into droplet and review live deployment
bash "$REV" --live openclaw@<tailscale-ip> # specific host
bash "$REV" --live --host <tailscale-ip> --ssh-user aiops # dedicated collab login
bash "$REV" --live --service openclaw-<claw>.service --home /home/<claw-user>/.openclaw --user openclaw
bash "$REV" --live --strict            # production gate: missing SPAPS/portal vars fail
```

Three modes:
- **`--skill`** / default: 44 file-based checks across config, env, scripts, docs, generator, validator
- **`/path/to/kit`**: same checks on a generated kit
- **`--live`**: SSHes into the droplet via `review_live.sh` and runs 30+ checks against the running deployment (service health, Node/Docker, live config schema, SPAPS/portal connectivity, Tailscale, security posture, recent logs). Auto-detects host from local `references/deployed-instances.md` when present.

## Talking to Agents via CLI (Debug & Bug-Fixing)

Use the bundled `scripts/talk.sh` for all agent interaction, log tailing, and SSH access. It reads `references/deployed-instances.md` automatically — no manual env var wrangling.

```bash
TALK="$(ls ~/.codex/skills/openclaw-client-bootstrap/scripts/talk.sh \
           ~/.claude/skills/openclaw-client-bootstrap/scripts/talk.sh \
           ./scripts/talk.sh \
           2>/dev/null | head -1)"

bash "$TALK" --list                                        # see all claws + live agent IDs
bash "$TALK" --message "what recipes exist?"               # message primary claw
bash "$TALK" --claw my-claw --message "hello"              # message a co-located claw
bash "$TALK" --claw ingredient-claw --message "follow up" --session-id <id>  # continue thread
bash "$TALK" --claw ingredient-claw --tail                 # tail logs live (Ctrl-C to stop)
bash "$TALK" --claw ingredient-claw --logs 100             # last 100 log lines
bash "$TALK" --health                                      # health summary for all claws
bash "$TALK" --health --claw ingredient-claw                # health summary for one claw
bash "$TALK" --health --emit-logs --log-dir ~/.openclaw/logs --log-prefix openclaw  # health + persisted snapshots
bash "$TALK" --ssh                                         # plain SSH into the droplet (non-root)
bash "$TALK" --ssh-user aiops --ssh                        # use dedicated collab user
bash "$TALK" --claw ingredient-claw --ssh                  # SSH with claw env pre-loaded
```

**Positional shorthand:** `talk.sh ingredient-claw "message"` is equivalent to `--claw ingredient-claw --message "message"`.

**Agent IDs vs persona names:** The `--agent` value (auto-discovered from `agents list`) is the agent config ID like `content-creator`. The persona name lives in `SOUL.md` — these are different. `--list` shows both.

**Co-located claws:** `talk.sh` handles the `OPENCLAW_STATE_DIR` / `OPENCLAW_CONFIG_PATH` env var override automatically. `--ssh --claw <name>` drops you into a shell with those vars already exported.

**Gateway 1006 fallback:** If the gateway WebSocket closes with code 1006, `openclaw agent` falls back to embedded mode. The response is still valid — but check `journalctl -u <service> -n 50` to investigate the underlying issue.

**Additional flags:** `--thinking medium` for more deliberate reasoning, `--agent <id>` to override auto-discovery, `--json` for machine-readable `--health` output.

For local integration workflows, use:
`--emit-logs`, `--log-dir`, and `--log-prefix` to persist remote claw health snapshots.

## Provider/Auth Rotation (Codex Default)

Use `scripts/update-oauth-token.sh` as the single path for credential updates across co-located claws.

```bash
# Default provider: Codex OAuth from ~/.codex/auth.json -> OPENAI_API_KEY
bash scripts/update-oauth-token.sh --dry-run
bash scripts/update-oauth-token.sh
bash scripts/update-oauth-token.sh --ssh-user aiops   # when using dedicated collab login

# Anthropic swap (stdin preferred)
echo "sk-ant-..." | bash scripts/update-oauth-token.sh --anthropic
```

What this script now enforces:
- Updates shared env (`<openclaw-home>/shared.env` by default) and each claw `.env`
- For Codex, writes canonical `auth-profiles.json` store (`version/profiles/order`) for `openai-codex` under every agent dir
- Warns on model/provider mismatch (`openai/*-codex` vs `anthropic/*`)
- Warns if `agents.defaults.model.reasoningEffort` exists (can trigger `Unknown config keys` on this runtime)

Do not hand-edit `auth-profiles.json` unless diagnosing parser behavior.

## Deterministic Recovery Order

When a claw fails after provider/model changes, recover in this exact order:

1. Fix model in each `openclaw.json` (`agents.defaults.model.primary` only).
2. Run `bash scripts/update-oauth-token.sh ...` for the target provider.
3. Restart services (script does this unless `--no-restart`).
4. Verify:
   - `bash scripts/talk.sh --list`
   - `bash scripts/talk.sh --health`
   - `bash scripts/talk.sh --health --require-root-proof --json` (definitive SSH/UFW proof; fails if checks are inferred)
   - `bash scripts/talk.sh --claw <name> --new --message "Reply ONLY: OK"`

If `talk.sh` says `Could not auto-discover agent ID`, re-run with `--agent <id>` from `--list`.

## Continuous Improvement Loop (Use skill-issue)

After every incident or rollout, run this loop to keep the bootstrap skill accurate:

1. **Audit current template and scripts**
   - `bash scripts/review_kit.sh --skill`
2. **Audit each live claw**
   - `bash scripts/review_live.sh --host <ip> --service <unit> --home <openclaw-home> --user <app-user>`
3. **Capture drift and breakages**
   - Record root cause + fix in `references/deployment-workflow.md` and update template assets/scripts
4. **Patch the reusable kit, not just the live box**
   - Update `assets/client-kit/*`, then sync stable instance snapshots in `assets/instances/<claw>/`
5. **Re-validate**
   - `bash scripts/validate_client_kit.sh assets/client-kit`
   - `bash scripts/review_kit.sh --skill`

## Validate Before Shipping

Run the bundled validation script against the generated kit:

```bash
VAL="$(ls ~/.codex/skills/openclaw-client-bootstrap/scripts/validate_client_kit.sh ~/.claude/skills/openclaw-client-bootstrap/scripts/validate_client_kit.sh ./scripts/validate_client_kit.sh 2>/dev/null | head -1)"
bash "$VAL" /tmp/<client>-openclaw
```

Reject the deployment if:

- placeholders remain in `openclaw.json`
- placeholder secrets remain in `.env`
- removed config keys detected (v2026.2.15 schema violations)
- any kit script fails shell syntax checks

## Deploy Workflow

Use the generated kit's scripts in this order on the droplet:

1. `scripts/01-bootstrap-do.sh`
2. `scripts/02-install-tailscale.sh`
3. `scripts/03-install-openclaw.sh`
4. `scripts/04-validate.sh`
5. Optional for shared operator sessions: `scripts/05-setup-collab-tmux.sh`

Then verify Telegram notification delivery and SPAPS/portal connectivity.

Cloud firewall requirement: remove public `22/tcp` and rely on Tailnet SSH only.

Reference: [references/deployment-workflow.md](references/deployment-workflow.md)

## Governance Rules (Do Not Relax By Default)

1. OpenClaw stores read-only credentials only.
2. External writes are proposed, never executed directly.
3. Write execution requires human approval through the Unclawg portal, backed by SPAPS.
4. Operator approvals must be logged with identity, timestamp, payload hash, and result.

Reference: [references/read-only-governance.md](references/read-only-governance.md)

## Deployed Instances

Two-tier tracking — non-secret config committed, secrets server-only:

- **`assets/instances/<claw-name>/`** — committed source of truth for each claw's `openclaw.json`, `SOUL.md`, `AGENTS.md`, `USER.md`, `.env.example`. If the droplet root disk is lost, redeploy from here.
- **`references/deployed-instances.md`** — private instance registry with IPs and connection details (gitignored)
- **`.env` on server** — real secrets, never committed

See [assets/instances/README.md](assets/instances/README.md) for the full pattern and redeploy steps.

After bootstrapping any new claw: copy its non-secret files into `assets/instances/<claw-name>/` and commit.

## Minimum Droplet Specs

- **RAM:** 2 GB minimum (gateway uses ~800MB; 1GB will OOM)
- **Swap:** 2 GB recommended
- **Docker:** Required for agent sandbox mode
- **Node heap:** Set `NODE_OPTIONS=--max-old-space-size=768` in systemd service

## Config Schema Notes (v2026.2.15+)

The kit template may need these fixes for current OpenClaw versions:

- `channels.pairing` is not a valid channel — use `channels.telegram.groupPolicy` + `groupAllowFrom` + `groups`
- Telegram token key is `botToken`, not `token`
- `tools.exec.ask` expects `"off"|"on-miss"|"always"`, not an array
- `tools.policyMode`, `tools.exec.fallback`, `tools.exec.rules` are not recognized — do not add them
- `tools.elevated.require` / `allowWhenRequestedBy` are not recognized; use `tools.elevated.enabled` + `tools.elevated.allowFrom.telegram`
- Run `tailscale set --operator=<app_user>` for Tailscale serve permissions

### Updates for v2026.2.17–2026.2.18

- **`tools.exec.safeBins` required** — now enforced; entries must be executable names (e.g. `["jq", "grep", "cut", "sort", "uniq", "head", "tail", "tr", "wc", "echo", "printf"]`), not directory paths like `/usr/bin`. Missing or path-style entries can cause `exec denied: allowlist miss`.
- **Ask mode for allowlist security** — when using `tools.exec.security: "allowlist"` for autonomous reads, use `tools.exec.ask: "on-miss"` so non-allowlisted commands route to approvals instead of hard-denying.
- **Approval recipient interpolation** — avoid `${env:...}` in `approvals.exec.targets[*].to`; set a concrete Telegram user/chat ID.
- **Cron webhook auth token** — `SPAPS_WEBHOOK_AUTH_TOKEN` is now supported for authenticated webhook delivery to SPAPS. Add to `.env` and wire into any cron channel config.
- **SSRF guards on cron webhooks** — v2026.2.18 blocks private RFC1918 ranges, NAT64, 6to4, and Teredo in webhook POST targets. `SPAPS_API_URL` must be a public or Tailscale-routable hostname (not a raw private IP).
- **Model forward compat** — pin to a runtime-supported model id (for example `anthropic/claude-haiku-4-5-20251001` on OpenClaw 2026.2.17). Validate from live logs before rollout.
- **Telegram inline button styles** — approval notifications can use `primary`, `success`, `danger` button styles for Approve/Reject UX.
- **Co-located claws** — use `APP_HOME`, `OPENCLAW_HOME`, and `OPENCLAW_SERVICE_NAME` when installing additional claws on the same droplet.
- **Native approval forwarding schema** — current runtime supports `approvals.exec.mode: session|targets|both`; avoid legacy `spaps` mode blocks in `openclaw.json`.
- **Runtime placeholders** — `{{MediaPath}}`, `{{Prompt}}`, `{{MaxChars}}` are valid runtime tokens for CLI media models; do not treat these as unresolved template placeholders.

### Updates for v2026.2.19–v2026.2.26

- **BREAKING: SafeBins trusted directory enforcement** — `tools.exec.safeBins` entries must resolve from trusted bin directories (default: `/bin`, `/usr/bin` only). Custom bin paths (e.g. `/home/openclaw/.openclaw/bin`) require explicit opt-in via `tools.exec.safeBinTrustedDirs`. Without this, custom safeBin entries will fail resolution at runtime.
- **BREAKING: `sort` and `grep` removed from default safe bins** — upstream hardened defaults to remove `sort` (file write via `-o`) and `grep` (recursive reads). Explicitly listing them in config still works but triggers `openclaw doctor` warnings. Keep them if needed for read-only analysis, but ensure `safeBinTrustedDirs` covers their parent directory.
- **BREAKING: Heartbeat `directPolicy`** — new key `agents.defaults.heartbeat.directPolicy` (`allow` | `block`) replaces DM toggle. Default changed to `allow` in v2026.2.24. Set `"block"` if DM heartbeat delivery is undesired for client claws.
- **BREAKING: Docker container namespace join blocked** — `network: "container:<id>"` blocked by default. Break-glass: `agents.defaults.sandbox.docker.dangerouslyAllowContainerNamespaceJoin: true`.
- **BREAKING: DM allowlist enforcement tightened** — `dmPolicy: "allowlist"` with empty `allowFrom` now silently drops all DMs (was permissive). Always populate `allowFrom` when using `allowlist` policy. `openclaw doctor --fix` restores from pairing-store.
- **Telegram `streamMode` deprecated** — replace `"streamMode": "partial"` with `"streaming": true`. Legacy values auto-mapped but deprecated since v2026.2.21.
- **Browser SSRF policy key renamed** — `browser.ssrfPolicy.allowPrivateNetwork` renamed to `browser.ssrfPolicy.dangerouslyAllowPrivateNetwork`. `openclaw doctor --fix` auto-migrates.
- **Secrets management** — new top-level `secrets` config block (`secrets.providers`, `secrets.defaults`) for env/file/exec secret sources. `openclaw secrets audit/configure/apply/reload` CLI workflow available.
- **Plugin entries resilience** — `plugins.entries.*` with unknown IDs now logs warnings instead of crash-looping gateway boot.
- **Node exec approvals hardened** — structured `commandArgv` approvals for `host=node`, `GIT_EXTERNAL_DIFF` blocked in host env keys.
- **Auth profile alias normalization** — `mode -> type`, `apiKey -> key` aliases accepted in `auth-profiles.json`.
- **`openai-codex-responses`** accepted in config model API schema.
- **`session.parentForkMaxTokens`** — default `100000` (`0` disables). Prevents oversized parent-session inheritance from bricking thread sessions.
- **`meta.lastTouchedAt` accepts numeric timestamps** — coerces `Date.now()` values to ISO strings for forward compat.
- **`gateway.http.securityHeaders.strictTransportSecurity`** — optional HSTS header for direct HTTPS deployments.

## Bundled Assets

The complete production template lives in:

- `assets/client-kit/openclaw.json`
- `assets/client-kit/.env.example`
- `assets/client-kit/SOUL.md`
- `assets/client-kit/AGENTS.md`
- `assets/client-kit/USER.md`
- `assets/client-kit/checklists/*`
- `assets/client-kit/security/WRITE_GATEWAY_CONTRACT.md`
- `assets/client-kit/security/PERMISSIONS_PLAYBOOK.md`
- `assets/client-kit/scripts/*`
