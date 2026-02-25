---
name: unclawg-feed
description: >
  Feed social listening candidates into the OpenClaw approval portal. Takes found
  posts (from unclawg-discover, manual paste, or any source), pulls the agent's
  current soul/instructions from the policy API, generates proposed replies using
  that voice, and POSTs them as approval requests. Use when:
  "/unclawg-feed", "/feed-approvals", "feed the portal", "create approval cards",
  "submit posts for approval", "load posts into openclaw", "feed-me"
---

# /unclawg-feed

Take social posts → pull the agent's soul → generate proposed replies → create approval cards in the portal.

## Prerequisites

Same 6 env vars as unclawg-respond. Auto-discovered from `.claude/agents/<agent-id>.env` (preferred) or `services/approval_feedback_api/.env` (legacy fallback):

| Variable | Purpose |
|----------|---------|
| `OPENCLAW_API_URL` | Base URL (e.g. `http://localhost:8010`) |
| `OPENCLAW_API_KEY` | API key for the app binding |
| `OPENCLAW_TENANT_ID` | Tenant context |
| `OPENCLAW_MACHINE_KEY_ID` | Machine key ID |
| `OPENCLAW_MACHINE_SECRET` | Machine key secret |
| `OPENCLAW_AGENT_ID` | Agent ID the machine key is bound to |

**Machine key must have scope `approval_request.create.social_reply`.**

## NEVER Do These Things

- **NEVER use `/api/v1/` routes.** All approval endpoints are `/api/v2/`. Policy endpoints are `/v1/integrations/claw-runtime/`.
- **NEVER guess header names.** Exact casing: `X-API-Key`, `X-Tenant-Id`, `X-Machine-Key-Id`, `X-Machine-Secret`.
- **NEVER store auth headers in a bash variable.** Always write each `-H` flag inline.
- **NEVER assume a POST succeeded.** Check HTTP status code on every request.
- **NEVER proceed past bootstrap if the smoke test fails.**

## Curl Template

Every API call uses this exact header pattern:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/api/v2/..."
```

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
  echo "No agent identity found. Run /unclawg-onboard or create .claude/agents/<agent-id>.env"
  exit 1
fi

set -a && source "$AGENT_ENV" && set +a

# Validate all 6 vars exist
missing=""
for var in OPENCLAW_API_URL OPENCLAW_API_KEY OPENCLAW_TENANT_ID \
           OPENCLAW_MACHINE_KEY_ID OPENCLAW_MACHINE_SECRET OPENCLAW_AGENT_ID; do
  eval val=\$$var
  [ -z "$val" ] && missing="$missing $var"
done
[ -n "$missing" ] && echo "MISSING:$missing" && exit 1

# Smoke test: hit list approvals and confirm 200 (auth/connectivity only)
# Note: list returns only approvals where this machine is a participant.
# An empty list (200 with 0 items) is still a successful smoke test.
SMOKE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/api/v2/approval-requests?limit=1")

STATUS=$(echo "$SMOKE" | grep "HTTP_STATUS:" | cut -d: -f2)
if [ "$STATUS" != "200" ]; then
  echo "SMOKE TEST FAILED (HTTP $STATUS):"
  echo "$SMOKE"
  exit 1
fi
echo "SMOKE TEST PASSED"
```

### Phase 1 — Pull the Soul

Fetch the agent's published soul from the policy API:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  "${OPENCLAW_API_URL}/v1/integrations/claw-runtime/policies/soul_md?agent_id=${OPENCLAW_AGENT_ID}"
```

Parse `data.published.content` — this is the agent's voice/tone guide.

If no published soul exists (`data.published` is null), tell the user:
> "No published soul for this agent. Generate replies without a soul, or create one first via the governance API?"

### Phase 2 — Gather Posts

Accept posts from any of these sources:

**A. From `/unclawg-discover` output** — read the brief file at `~/.claude/skills/unclawg-discover/briefs/YYYYMMDD_*.md` and extract the candidates table.

**B. From user paste** — user pastes a URL or post text directly. Fetch the content if it's a URL.

**C. From a file** — user provides a path to a JSON/markdown file with posts.

For each post, extract:
- `source_platform` — one of: `x`, `reddit`, `linkedin`, `hacker_news`, `youtube`, `instagram`, `tiktok`, `other`
- `source_post_url` — the URL (required)
- `source_post_text` — the post content (required)
- `source_author_handle` — e.g. `@handle` or `u/username` (optional)
- `source_author_name` — display name (optional)
- `source_post_id` — platform-specific ID (optional)
- `persona_hint` — which persona they match (optional)
- `intent_signal` — what pain they're expressing (optional)

Present a summary table and ask:
> "Found N posts. Generate replies for all, or select specific ones?"

### Phase 3 — Generate Proposed Replies

For each selected post, generate a proposed reply using:
- The soul from Phase 1 (tone, length, platform calibration)
- The post content and context
- The Unclawg angle (what problem does OpenClaw solve for this person?)

Also generate:
- `summary` — 1-sentence description of why this post is worth engaging
- `reply_strategy` — `educational`, `empathetic`, `shitpost`, `consultative`, etc.
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
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  "${OPENCLAW_API_URL}/api/v2/approval-requests/social-reply" \
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
- `403 MACHINE_AGENT_MISMATCH` → machine key bound to wrong agent
- `403 MACHINE_SCOPE_DENIED` → key missing `approval_request.create.social_reply` scope
- `409` → idempotency conflict (already submitted)
- `429` → rate limited, back off

### Phase 5 — Verify

After all POSTs:

1. Capture each successful `approval_id` from the `201` responses in Phase 4.
2. For each `approval_id`, confirm detail is readable (HTTP 200):

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/api/v2/approval-requests/${APPROVAL_ID}"
```

Optional: list pending social approvals for spot-check visibility:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-API-Key: ${OPENCLAW_API_KEY}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/api/v2/approval-requests?status=pending&context_type=social_reply&limit=5"
```

Print summary:

```
## Feed Summary

- Posts submitted: N
- Cards created: N (HTTP 201)
- Failed: N
- Portal: http://localhost:5173/approvals
```

## Cross-References

- `/unclawg-discover` — upstream: discovers posts to feed
- `/unclawg-respond` — downstream: handles human feedback on these cards
- `references/api-contract.md` — shared with unclawg-respond, full endpoint specs
