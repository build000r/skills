---
name: unclawg-respond
description: >
  Poll pending revision requests, analyze user feedback patterns, generate
  revised outputs, and fulfill them via the OpenClaw API. Use when:
  "/unclawg-respond", "/respond-feedback", "respond to feedback", "handle
  revisions", "fulfill pending revisions", "process revision requests"
---

# /unclawg-respond

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

## Soul / Skill Separation

This skill is **mechanical**. It polls revision requests, reads feedback, generates revised outputs, and creates instruction proposals. All personality comes from the **soul** (`soul_md`).

- When generating revised outputs in Phase 4, pull the agent's published soul and use its Voice, Personas, Reply Archetypes, and Boundaries sections.
- When detecting patterns in Phase 3 and proposing soul updates in Phase 7, the proposal should target the soul's personality sections (voice calibration, persona adjustments, boundary refinements) — not add personality to the skill itself.
- Instruction proposals are about evolving the soul, not the skill.

## NEVER Do These Things

- **NEVER use `/api/v1/` or `/api/v2/` routes.** All endpoints are `/v0/`.
- **NEVER guess header names.** Use exact casing: `X-API-Key`, `X-Tenant-Id`, `X-Machine-Key-Id`, `X-Machine-Secret`.
- **NEVER store auth headers in a bash variable** like `AUTH="-H ..."` — it breaks quoting. Always write each `-H` flag inline.
- **NEVER assume a POST succeeded.** Check the HTTP status code on every request.
- **NEVER proceed past bootstrap if the smoke test fails.** Stop and tell the user what broke.
- **NEVER retry the same failing curl with different header casing or variations.** If auth fails, check the env vars and the api-contract reference.
- **NEVER hardcode voice or personality guidance in this skill.** Pull it from the soul.

## Curl Template

Every API call uses this header pattern. Copy-paste it — do not improvise:

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

Source env vars, validate they exist, then **test connectivity**:

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

# Smoke test: hit the list-revisions endpoint and confirm 200
# For self-hosted gateways requiring client app binding, add:
#   -H "X-API-Key: ${OPENCLAW_API_KEY}" \
SMOKE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/agents/${OPENCLAW_AGENT_ID}/revision-requests?status=pending&limit=1")

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
- `403 MACHINE_AGENT_MISMATCH` → key bound to wrong agent. Check `OPENCLAW_AGENT_ID`.
- `TENANT_CONTEXT_REQUIRED` → `X-Tenant-Id` header missing or empty. Check `OPENCLAW_TENANT_ID`.
- Connection refused / DNS errors → verify `OPENCLAW_API_URL` and service health.

### Phase 1 — Fetch Pending Revision Requests

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/agents/${OPENCLAW_AGENT_ID}/revision-requests?status=pending"
```

- If `items` is empty → print "No pending revision requests." → exit
- Filter: only items where `trigger_message_ids` is non-empty (has user feedback)
- Print summary table: `| # | Approval ID | Created | Trigger Messages |`

### Phase 2 — Fetch Full Context (parallel)

Fetch the soul and per-revision context in parallel:

1. **Agent soul:** `GET /v0/integrations/claw-runtime/policies/soul_md?agent_id=${OPENCLAW_AGENT_ID}` — parse `data.published.content` for the agent's voice, personas, archetypes, and boundaries. If no published soul, use generic defaults.
2. **Approval detail:** `GET /v0/approval-requests/{approval_id}` (per revision)
3. **Feedback thread:** `GET /v0/approval-requests/{approval_id}/messages` (per revision)
4. **Feedback digest:** `GET /v0/agents/{OPENCLAW_AGENT_ID}/feedback-digest?limit=100`

All use the same header pattern from the curl template above. Verify each returns HTTP 200.

### Phase 3 — Ask-Cascade Pattern Analysis

Internal analysis (Claude reasons, doesn't ask user yet):

- For each revision: extract trigger messages from the thread, categorize feedback:
  - **Tone** — too formal, too casual, wrong register
  - **Content** — factually wrong, missing info, irrelevant
  - **Scope** — too long, too short, over/under-promises
  - **Style** — formatting, structure, word choice
  - **Rejection** — complete rewrite needed
- Cross-revision: are multiple feedbacks expressing the same theme?
- Verdict: `ONE_OFF` (fix individual replies) or `PATTERN` (soul update candidate)

First user question (strategic, via `/ask-cascade` discipline):

> "I found N pending revisions. Here's the pattern I see: [summary]. Is this a one-off fix or should we also update the agent's instructions?"

Options: "One-off fix" | "Fix + update instructions" | "Let me review first"

### Phase 4 — Generate Revised Outputs

For each revision request, generate:

- `edited_content` — the revised reply incorporating feedback
- `content` — brief edit description (e.g. "Made tone more casual per feedback")

Use all available context:
- **The soul** from Phase 2 — apply the voice, persona match, archetype selection, and boundary checks
- Original proposal from approval detail (`context.payload`)
- Feedback messages (trigger messages from thread)
- Prior `edit_diff` messages in thread (previous revision attempts)
- Pattern analysis from Phase 3
- Feedback digest patterns (what gets approved vs denied)

When revising, the feedback tells you WHAT to change. The soul tells you HOW to talk while making that change.

For batches > 3 revision requests, use `/divide-and-conquer` to launch parallel sub-agents.

### Phase 5 — Fulfill (with response validation)

For each revision request, POST the fulfillment and **verify the response**:

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  -H "Content-Type: application/json" \
  "${OPENCLAW_API_URL}/v0/approval-requests/${APPROVAL_ID}/messages/fulfill" \
  -d "{
    \"content\": \"<edit description>\",
    \"edited_content\": \"<revised reply>\",
    \"revision_request_id\": \"<rev-req-id>\",
    \"expected_version\": <version from approval detail>,
    \"idempotency_key\": \"$(uuidgen)\"
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
echo "Status: $STATUS"
echo "Body: $BODY"
```

**Response validation:**
- `201` → success. Record it.
- `401 MACHINE_KEY_NOT_FOUND` → key ID is unknown in this tenant/app context.
- `401 UNAUTHORIZED` → machine secret is wrong.
- `403 MACHINE_KEY_EXPIRED` → key expired; rotate/re-provision before retry.
- `403 MACHINE_KEY_REVOKED` → key revoked; provision a fresh key.
- `403 APP_BINDING_MISMATCH` → missing/wrong `X-API-Key` on self-hosted gateways.
- `409 VERSION_CONFLICT` → re-fetch approval detail for current version, retry once.
- `409 REVISION_REQUEST_STALE` → request already fulfilled/closed. Treat as terminal; don't retry.
- `409 REVISION_REQUEST_EXPIRED` → TTL expired. Tell user and stop retrying.
- `409 IDEMPOTENCY_CONFLICT` → same idempotency key reused with different payload. Generate a new key and retry once.
- Any other non-2xx → **STOP. Print the full response. Do not retry blindly.**

Print results table:

```
| Approval ID | Status | Detail |
|-------------|--------|--------|
| abc-123     | ✓ 201  | Tone adjusted |
| def-456     | ✗ 409  | Version mismatch |
```

### Phase 6 — Re-Pull and Verify

Re-fetch `GET /v0/agents/{OPENCLAW_AGENT_ID}/revision-requests?status=pending`

- If empty: "All revisions fulfilled."
- If non-empty: show remaining, offer retry (may be version conflicts)

### Phase 7 — Calibration Loop

Ask user:

1. "Did we get the revisions right? (Check the portal — cards should show updated suggestions within 5 seconds.)"
2. If pattern was detected in Phase 3: "Should we update the soul/instructions? Here's what I'd change: [diff preview]"

Responses:
- "Not right" → loop back to Phase 4 with user's additional guidance
- "Update soul" → create an instruction proposal via the API:

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  -H "Content-Type: application/json" \
  "${OPENCLAW_API_URL}/v0/instruction-proposals" \
  -d "{
    \"scope\": \"agent\",
    \"title\": \"<short title>\",
    \"summary\": \"<pattern description from Phase 3>\",
    \"evidence_ref\": \"<approval_id or revision_request_id if applicable>\",
    \"payload\": {<the instruction delta as JSON>},
    \"idempotency_key\": \"$(uuidgen)\"
  }")
```

  Print the proposal ID and payload summary. Tell user:
  > "Instruction proposal `{id}` created. Approve or reject it via the portal or `POST /v0/instruction-proposals/{id}/decisions`."

  **Machine key must have scope `instruction_proposal.create`.** If denied, check for `MACHINE_SCOPE_DENIED` (add scope) versus `MACHINE_KEY_EXPIRED`/`MACHINE_KEY_REVOKED` (rotate/re-provision key).

- "Looks good" → proceed to Phase 8

### Phase 8 — Summary

```
## Revision Response Summary

- Revisions fulfilled: N
- Patterns detected: [list or "none"]
- Soul update: [applied/deferred/not needed]
- Next steps: [any manual actions needed]
```

## Key Rules

1. **Only touch items with unaddressed user feedback** — skip revision requests where `trigger_message_ids` is empty
2. **Machine auth only** — all API calls use machine key headers, never human auth
3. **Idempotent fulfillment** — always generate unique `idempotency_key` per attempt
4. **Version-aware** — use `expected_version` from the approval detail; handle 409 conflicts gracefully
5. **Agent-scoped** — machine key can only read/write its own agent's approvals
6. **Validate every response** — never assume a request succeeded without checking the HTTP status code

## Cross-References

- `/ask-cascade` — question ordering discipline for Phase 3 user interaction
- `/divide-and-conquer` — parallel sub-agents for Phase 4 when batch > 3
- `references/api-contract.md` — full endpoint specs, response shapes, error codes
