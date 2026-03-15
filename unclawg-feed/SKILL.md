---
name: unclawg-feed
description: >
  Feed social listening candidates into the OpenClaw approval portal. Takes found
  posts (from unclawg-discover, manual paste, or any source), pulls the agent's
  current soul/instructions from the policy API, generates proposed replies using
  that voice, and POSTs them as approval requests. Use when:
  "/unclawg-feed", "/feed-approvals", "feed the portal", "create approval cards",
  "submit posts for approval", "load posts into openclaw", "feed-me"
metadata:
  openclaw:
    emoji: "📬"
    requires:
      bins:
        - uc_feed
---

# /unclawg-feed

Take social posts → pull the agent's soul → generate proposed replies → create approval cards in the portal.

## Runtime Security Profile (AI Default)

- This skill is AI-runtime-first and must run through wrapper command `uc_feed`.
- Do not execute raw `curl` from this skill during runtime.
- If `uc_feed` is unavailable, fail closed and request wrapper installation.
- Keep write actions in proposal/approval flow; never bypass portal routing.

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

**Machine key must have scope `approval_request.create.social_reply`.**
If machine auth fails with `MACHINE_KEY_EXPIRED` or `MACHINE_KEY_REVOKED`, rotate or re-provision the key via `/unclawg-internet` before continuing.

### Existing OpenClaw Provisioning Path

If you already run an OpenClaw runtime and just need this skill to work with it:

1. In the Unclawg portal sidebar, run **Add Agent**.
2. Complete Step 1 (create machine key), then choose **Connect existing claw** in Step 2.
3. Use your runtime claw ID (for example `example-claw`) and issue the connect packet.
4. Save the generated env block as `.claude/agents/<agent-id>.env`.
5. Re-run `/unclawg-feed`; it will auto-discover that identity file.

## Soul / Skill Separation

This skill is **mechanical**. It fetches, generates, and POSTs. All personality — voice, tone, reply archetypes, persona voice calibration, engagement principles, boundaries — comes from the **soul** (`soul_md` policy document fetched in Phase 1).

- The soul says HOW to talk. This skill says HOW to call the API.
- If the soul changes, replies change. If this skill changes, only plumbing changes.
- When generating replies in Phase 3, use the soul's Voice, Reply Archetypes, Personas, and Boundaries sections. Do not invent personality guidance that isn't in the soul.

## NEVER Do These Things

- **NEVER execute raw `curl` directly in AI runtime.** Use `uc_feed` wrapper only.
- **NEVER use `/api/v1/` or `/api/v2/` routes.** All endpoints are `/v0/`.
- **NEVER guess header names.** Exact casing: `X-API-Key`, `X-Tenant-Id`, `X-Machine-Key-Id`, `X-Machine-Secret`.
- **NEVER store auth headers in a bash variable.** Always write each `-H` flag inline.
- **NEVER assume a POST succeeded.** Check HTTP status code on every request.
- **NEVER proceed past bootstrap if the smoke test fails.**
- **NEVER hardcode voice or personality guidance in this skill.** Pull it from the soul.

## Wrapper Commands (Runtime Path)

```bash
uc_feed smoke
uc_feed soul --agent-id "${OPENCLAW_AGENT_ID}"
uc_feed submit --input <candidate-file.json>
```

If your local wrapper exposes different subcommands, keep the same policy:
wrapper-only, `/v0`-only, schema-validated requests.

## HTTP Contract Reference (Wrapper Implementation)

Every API call uses this header pattern:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/..."
```

If your gateway requires client-supplied app binding, also add:
`-H "X-API-Key: ${OPENCLAW_API_KEY}"`.

Always append `-w "\nHTTP_STATUS:%{http_code}"` to capture the status code. Parse it after every call.

## Execution Flow

### Phase 0 — Bootstrap & Smoke Test

```bash
# ── Agent identity bootstrap ──
AGENTS_DIR=".claude/agents"
AGENT_ENV=""

if [ -d "$AGENTS_DIR" ]; then
  AGENT_FILES=($AGENTS_DIR/*.env)
  if [ ${#AGENT_FILES[@]} -eq 1 ] && [ -f "${AGENT_FILES[0]}" ]; then
    AGENT_ENV="${AGENT_FILES[0]}"
  elif [ ${#AGENT_FILES[@]} -gt 1 ]; then
    if [ -n "$OPENCLAW_AGENT_ID" ] && [ -f "$AGENTS_DIR/${OPENCLAW_AGENT_ID}.env" ]; then
      AGENT_ENV="$AGENTS_DIR/${OPENCLAW_AGENT_ID}.env"
    else
      echo "Multiple agents found:"
      for f in $AGENTS_DIR/*.env; do echo "  - $(basename "$f" .env)"; done
      echo "Set OPENCLAW_AGENT_ID to pick one."
      exit 1
    fi
  fi
fi

if [ -z "$AGENT_ENV" ] && [ -f "services/approval_feedback_api/.env" ]; then
  AGENT_ENV="services/approval_feedback_api/.env"
fi

if [ -z "$AGENT_ENV" ]; then
  echo "No agent identity found. Run /unclawg-internet (CLI device flow) or create .claude/agents/<agent-id>.env"
  exit 1
fi

set -a && source "$AGENT_ENV" && set +a

# Validate required vars exist (`OPENCLAW_API_KEY` is optional)
missing=""
for var in OPENCLAW_API_URL OPENCLAW_TENANT_ID \
           OPENCLAW_MACHINE_KEY_ID OPENCLAW_MACHINE_SECRET OPENCLAW_AGENT_ID; do
  eval val=\$$var
  [ -z "$val" ] && missing="$missing $var"
done
[ -n "$missing" ] && echo "MISSING:$missing" && exit 1

# Smoke test: hit list approvals and confirm 200 (auth/connectivity only)
# Note: list returns only approvals where this machine is a participant.
# An empty list (200 with 0 items) is still a successful smoke test.
# For self-hosted gateways requiring client app binding, add:
#   -H "X-API-Key: ${OPENCLAW_API_KEY}" \
SMOKE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/approval-requests?limit=1")

STATUS=$(echo "$SMOKE" | grep "HTTP_STATUS:" | cut -d: -f2)
if [ "$STATUS" != "200" ]; then
  echo "SMOKE TEST FAILED (HTTP $STATUS):"
  echo "$SMOKE"
  exit 1
fi
echo "SMOKE TEST PASSED"
```

**If smoke test fails:**
- `401 MACHINE_KEY_NOT_FOUND` → key ID is unknown in this tenant/app context. Confirm key ID and tenant, then re-provision if needed.
- `401 UNAUTHORIZED` → machine secret is wrong. Re-copy the secret or rotate the key.
- `403 MACHINE_KEY_EXPIRED` → key expired. Run `/unclawg-internet` (or rotate in portal) and update `.claude/agents/<agent-id>.env`.
- `403 MACHINE_KEY_REVOKED` → key was revoked. Provision a fresh key.
- `403 APP_BINDING_MISMATCH` → missing/wrong `X-API-Key` on self-hosted gateways.
- `403 MACHINE_AGENT_MISMATCH` → key is bound to a different `OPENCLAW_AGENT_ID`.
- `TENANT_CONTEXT_REQUIRED` → missing/empty `OPENCLAW_TENANT_ID`.
- Connection refused / DNS errors → verify `OPENCLAW_API_URL` and service health.

### Phase 1 — Pull the Soul

Fetch the agent's published soul from the policy API:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/integrations/claw-runtime/policies/soul_md?agent_id=${OPENCLAW_AGENT_ID}"
```

Parse `data.published.content` — this is the agent's complete personality document. It contains:

- **Identity** — who the agent is
- **Voice** — core tone, platform calibration, reply archetypes with examples
- **Personas** — target audience definitions with per-persona voice adjustments
- **Boundaries** — off-limits topics, competitor avoidance, honesty constraints
- **Engagement Principles** — rules for reply quality

Use ALL of these sections when generating replies in Phase 3. The soul is the single source of truth for personality.

If no published soul exists (`data.published` is null), tell the user:
> "No published soul for this agent. Generate replies without a soul (generic voice), or run `/unclawg-internet` to create one first?"

### Phase 2 — Gather Posts

Accept posts from any of these sources:

**A. From `/unclawg-discover` output** — read the brief file at `~/.claude/skills/unclawg-discover/briefs/YYYYMMDD_*.md` and extract the candidates table.

**B. From user paste** — user pastes a URL or post text directly. Fetch the content if it's a URL.

**C. From a file** — user provides a path to a JSON/markdown file with posts.

For each post, extract:
- `source_platform` — one of: `x`, `reddit`, `linkedin`, `hacker_news`, `youtube`, `instagram`, `tiktok`, `other`
- `source_post_url` — the URL (**required, must be non-empty**)
- `source_post_text` — the post content (required)
- `source_author_handle` — e.g. `@handle` or `u/username` (optional)
- `source_author_name` — display name (optional)
- `source_post_id` — platform-specific ID (optional)
- `persona_hint` — which persona they match (optional)
- `intent_signal` — what pain they're expressing (optional)

**URL validation (critical):** The API returns `422 string_too_short` if `source_post_url`
is empty. LinkedIn posts from the Apify scraper frequently have empty URLs. Before submission:
1. Skip candidates with empty `source_post_url` (log them as skipped)
2. Or construct a placeholder URL from author profile if available

Present a summary table and ask:
> "Found N posts. Generate replies for all, or select specific ones?"

### Phase 3 — Generate Proposed Replies

For each selected post, generate a proposed reply using the soul:

1. **Match persona** — which soul persona does this post's author best fit? Use that persona's voice adjustment and preferred archetypes.
2. **Pick archetype** — select a reply archetype from the soul's list. Vary across replies (never same archetype twice in a row).
3. **Apply platform calibration** — use the soul's platform-specific style rules for this post's platform.
4. **Check boundaries** — verify the reply doesn't violate any of the soul's off-limits rules or honesty constraints.
5. **Generate** — write the reply in the soul's voice, with the persona adjustment applied.

Also generate:
- `summary` — 1-sentence description of why this post is worth engaging
- `reply_strategy` — maps to the archetype used (e.g., `mechanism_drop`, `reframe`, `validate_only`, `quick_solve`)
- `action` — `social:reply`, `social:engage`, `social:quote-tweet`, `dm:reply`, `email:respond`

Present each proposed reply for quick review:

```
Post 1: @handle on Twitter
> "My bot went rogue and..."
Proposed reply: "..."
Action: social:reply
```

Ask: "Submit all, edit any, or skip some?"

### Phase 4 — Create Approval Requests

For each approved post+reply pair:

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  "${OPENCLAW_API_URL}/v0/approval-requests/social-reply" \
  -d "{
    \"agent_id\": \"${OPENCLAW_AGENT_ID}\",
    \"action\": \"social_reply_approval\",
    \"resource_type\": \"social_post\",
    \"resource_id\": \"<source_post_url>\",
    \"expires_at\": \"<24h from now in ISO8601>\",
    \"proposed_reply\": \"<the generated reply>\",
    \"summary\": \"<1-sentence summary>\",
    \"candidate\": {
      \"source_platform\": \"<platform>\",
      \"source_post_url\": \"<url>\",
      \"source_post_text\": \"<post text>\",
      \"source_post_id\": <string or null>,
      \"source_author_handle\": <string or null>,
      \"source_author_name\": <string or null>,
      \"discovered_at\": \"<ISO8601 now>\",
      \"persona_hint\": <string or null>,
      \"intent_signal\": <string or null>
    }
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')

if [ "$STATUS" != "201" ]; then
  echo "FAILED ($STATUS): $BODY"
fi
```

**Response validation:**
- `201` → success, card created (machine key is auto-added as observer participant for future reads)
- `401 MACHINE_KEY_NOT_FOUND` → key ID is unknown in this tenant/app context
- `401 UNAUTHORIZED` → machine secret is wrong
- `403 MACHINE_KEY_EXPIRED` → key expired; rotate/re-provision before retry
- `403 MACHINE_KEY_REVOKED` → key revoked; provision a fresh key
- `403 APP_BINDING_MISMATCH` → missing/wrong `X-API-Key` on self-hosted gateways
- `403 MACHINE_AGENT_MISMATCH` → machine key bound to wrong agent
- `403 MACHINE_SCOPE_DENIED` → key missing `approval_request.create.social_reply` scope
- `409` → idempotency conflict (already submitted)
- `422 string_too_short` → `source_post_url` is empty or too short. Common with LinkedIn posts from the Apify scraper which returns empty URL fields. Pre-filter candidates to skip those with empty URLs before submission.
- `429` → rate limited, back off

### Phase 5 — Verify

After all POSTs:

1. Capture each successful `approval_id` from the `201` responses in Phase 4.
2. For each `approval_id`, confirm detail is readable (HTTP 200):

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/approval-requests/${APPROVAL_ID}"
```

Optional: list pending social approvals for spot-check visibility:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/approval-requests?status=pending&context_type=social_reply&limit=5"
```

Print summary:

```
## Feed Summary

- Posts submitted: N
- Cards created: N (HTTP 201)
- Failed: N
- Portal: https://unclawg.com/approvals
```

## High-Volume Batch Workflow

When feeding 30+ candidates (e.g., from `/divide-and-conquer` discovery runs):

1. **Pre-validate all candidates** before submission:
   - Remove entries with empty `source_post_url` (422 rejection)
   - Remove entries with empty/too-short `source_post_text`
   - Deduplicate by URL (Twitter) or by `text[0:100] + author_name` (LinkedIn)

2. **Submit via Python script** (more reliable than bash loop for 30+ entries):
   - Read combined replies JSON
   - Build payload per candidate with `uuid4()` idempotency keys
   - POST sequentially with `time.sleep(0.5)` every 10 requests to avoid 429
   - Capture success/failure counts and approval IDs
   - Log failures for retry

3. **Verify batch** after all submissions:
   - GET `/v0/approval-requests?status=pending&limit=100` to confirm count
   - Report platform breakdown (Twitter vs LinkedIn vs Reddit)

## Cross-References

- `/unclawg-discover` — upstream: discovers posts to feed
- `/unclawg-respond` — downstream: handles human feedback on these cards
- `references/api-contract.md` — shared with unclawg-respond, full endpoint specs
