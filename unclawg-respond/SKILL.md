---
name: unclawg-respond
description: >
  Poll pending revision requests, analyze user feedback patterns, generate
  revised outputs, and fulfill them via the OpenClaw API. Use when:
  "/unclawg-respond", "/respond-feedback", "respond to feedback", "handle
  revisions", "fulfill pending revisions", "process revision requests"
metadata:
  openclaw:
    emoji: "🔁"
    requires:
      bins:
        - uc_respond
---

# /unclawg-respond

## Runtime Security Profile (AI Default)

- Run this skill via wrapper command `uc_respond` only.
- Do not execute raw `curl` commands from this skill in runtime.
- If `uc_respond` is missing, fail closed and ask for wrapper install/allowlist.

### Wrapper Source

- Checked-in wrapper implementation: `scripts/uc_respond`
- Example local install:

```bash
chmod +x scripts/uc_respond
ln -sf "$(pwd)/scripts/uc_respond" "${HOME}/.local/bin/uc_respond"
```

## Prerequisites

Agent identity env vars. Auto-discovered from `.claude/agents/<agent-id>.env` (preferred). Legacy fallback to `services/approval_feedback_api/.env` only works if that file already includes `OPENCLAW_*` identity vars.

| Variable | Purpose |
|----------|---------|
| `OPENCLAW_API_URL` | Base URL (e.g. `https://api.unclawg.com`) |
| `OPENCLAW_API_KEY` | Optional app key for gateways that do not inject server-side app binding |
| `OPENCLAW_TENANT_ID` | Tenant context |
| `OPENCLAW_MACHINE_KEY_ID` | Machine key ID |
| `OPENCLAW_MACHINE_SECRET` | Machine key secret |
| `OPENCLAW_AGENT_ID` | Agent ID the machine key is bound to |

If machine auth fails with `MACHINE_KEY_EXPIRED` or `MACHINE_KEY_REVOKED`, rotate or re-provision the key via `/unclawg-internet` before continuing.

### Existing OpenClaw Provisioning Path

If the runtime already exists and you only need agent credentials wired:

1. In the Unclawg portal sidebar, run **Add Agent**.
2. Create the machine key in Step 1.
3. In Step 2, select **Connect existing claw** and enter the runtime claw ID.
4. Save the env block as `.claude/agents/<agent-id>.env`.
5. Re-run `/unclawg-respond`; bootstrap auto-detects that file.

## Soul / Skill Separation

This skill is **mechanical**. It polls revision requests, reads feedback, generates revised outputs, and creates instruction proposals. All personality comes from the **soul** (`soul_md`).

- When generating revised outputs in Phase 4, pull the agent's published soul and use its Voice, Personas, Reply Archetypes, and Boundaries sections.
- When detecting patterns in Phase 3 and proposing soul updates in Phase 7, the proposal should target the soul's personality sections (voice calibration, persona adjustments, boundary refinements) — not add personality to the skill itself.
- Instruction proposals are about evolving the soul, not the skill.

## NEVER Do These Things

- **NEVER execute raw `curl` directly in AI runtime.** Use `uc_respond` wrapper only.
- **NEVER use `/api/v1/` or `/api/v2/` routes.** All endpoints are `/v0/`.
- **NEVER guess header names.** Use exact casing: `X-API-Key`, `X-Tenant-Id`, `X-Machine-Key-Id`, `X-Machine-Secret`.
- **NEVER store auth headers in a bash variable** like `AUTH="-H ..."` — it breaks quoting. Always write each `-H` flag inline.
- **NEVER assume a POST succeeded.** Check the HTTP status code on every request.
- **NEVER proceed past bootstrap if the smoke test fails.** Stop and tell the user what broke.
- **NEVER retry the same failing curl with different header casing or variations.** If auth fails, check the env vars and the api-contract reference.
- **NEVER hardcode voice or personality guidance in this skill.** Pull it from the soul.

## Wrapper Commands (Runtime Path)

```bash
uc_respond smoke
uc_respond list --status pending
uc_respond canary --approval-id <id> [--revision-id <id>] [--dry-run] [--force]
uc_respond fulfill --approval-id <id> --revision-id <id> --input <revised.json>
uc_respond reconcile --agent-id <agent_id> [--dry-run]
```

## Execution Flow

### Phase 0 — Bootstrap & Smoke Test

Run:

```bash
uc_respond smoke
```

**If smoke test fails:**
- `401 MACHINE_KEY_NOT_FOUND` → key ID is unknown in this tenant/app context. Confirm key ID and tenant, then re-provision if needed.
- `401 UNAUTHORIZED` → machine secret is wrong. Re-copy the secret or rotate the key.
- `403 MACHINE_KEY_EXPIRED` → key expired. Run `/unclawg-internet` (or rotate in portal) and update `.claude/agents/<agent-id>.env`.
- `403 MACHINE_KEY_REVOKED` → key was revoked. Provision a fresh key.
- `403 APP_BINDING_MISMATCH` → missing/wrong `X-API-Key` on self-hosted gateways.
- `403 MACHINE_AGENT_MISMATCH` → key bound to wrong agent. Check `OPENCLAW_AGENT_ID`.
- `TENANT_CONTEXT_REQUIRED` → `X-Tenant-Id` header missing or empty. Check `OPENCLAW_TENANT_ID`.
- Connection refused / DNS errors → verify `OPENCLAW_API_URL` and service health.

### Phase 1 — Non-interactive Batch Reconcile

Run:

```bash
uc_respond reconcile --agent-id "${OPENCLAW_AGENT_ID}"
```

Behavior:
- Prints effective target (`api_url`, `tenant_id`, `agent_id`) as the first line.
- Pulls pending approvals from `/v0/approval-requests?status=pending&agent_id={agent_id}`.
- Derives work from message chronology:
  - queues items where latest `feedback` is newer than latest machine `edit_diff/comment`
  - queues items with feedback and no machine response
  - queues items when published soul version drift is detected, even without new feedback
- Uses agent revision rows only as fulfill anchors (`pending`/`dispatched` preferred, `expired` fallback).
- Loads latest published `soul_md` once per run.
- For each queued approval, re-checks approval status and skips only `approved`/`denied` approvals.
- Aggregates feedback thread messages.
- Chooses one machine fulfillment per item:
  - `edit_diff` with revised suggestion, or
  - `comment` with `Recommend deny ...` rationale.
- `edit_diff.edited_content` must be publish-ready plain text:
  - no audit markers (for example `[Reconciled under soul ...]`, `Feedback addressed: ...`)
  - materially different from the original suggestion (no no-op fulfills)
- Uses deterministic idempotency key per `(approval_id, revision_id, feedback fingerprint, soul version)`.
- Appends new machine entries (no in-place mutation of old suggestions).
- Re-pulls pending queue and prints summary:
  - `fulfilled`
  - `deny_recommended`
  - `skipped`
  - `failed`
  - `remaining_pending`

Optional preview mode:

```bash
uc_respond reconcile --agent-id "${OPENCLAW_AGENT_ID}" --dry-run
```

### Phase 2 — Single-card Canary / Override

If you need deterministic validation for one card before a full reconcile:

```bash
uc_respond canary --approval-id <id> --dry-run
uc_respond canary --approval-id <id>
```

Use `--force` when the card currently looks `up_to_date` because of a bad prior machine reply, but you still want to rebuild exactly that approval:

```bash
uc_respond canary --approval-id <id> --dry-run --force
uc_respond canary --approval-id <id> --force
```

If you need a fully hand-authored payload for one card:

```bash
uc_respond fulfill --approval-id <id> --revision-id <id> --input <revised.json>
```

## Key Rules

1. **Skip scope** — skip only approved/denied cards; expired items are still attempted.
2. **Machine auth only** — all API calls use machine key headers, never human auth
3. **Idempotent fulfillment** — deterministic keys make reruns safe.
4. **Version-aware** — use `expected_version` from approval detail and handle conflicts gracefully.
5. **Append-only auditability** — add new machine messages; do not mutate old suggestions.
6. **Validate every response** — never assume write success without checking HTTP status.

## Cross-References

- `/divide-and-conquer` — parallel sub-agents when custom rewrite logic is needed at scale
- `references/api-contract.md` — full endpoint specs, response shapes, error codes
