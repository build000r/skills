---
name: unclawg-internet
description: >
  Self-service OpenClaw onboarding with soul interview. Registers the user, creates their agent,
  provisions machine keys, conducts an ask-cascade soul interview to define voice/personas/target market,
  writes the soul draft and discovery mode file, and outputs the env block.
  Use when: "/unclawg-internet", "set me up", "connect to openclaw",
  "get started", "onboard me", "sign up for openclaw", "I want approval gates"
---

# /unclawg-internet

Get set up with OpenClaw — account, agent, soul, and discovery config in one sitting.

## What This Produces

1. OpenClaw account + API keys
2. Agent identity file (`.claude/agents/<agent-id>.env`)
3. Soul draft (`soul_md` policy document via API)
4. Discovery mode file (`modes/<project>.local.md` for `/unclawg-discover`)
5. Browser auto-logged into the approval portal

## NEVER Do These Things

- **NEVER show the machine key secret more than once.** It cannot be retrieved after creation.
- **NEVER store passwords or secrets in any file the user didn't ask for.**
- **NEVER skip the confirmation before creating the account.**
- **NEVER run search/research in the main conversation context.** Always delegate to Task tool subagents (see Rule below).

## Subagent Rule

**All search, web fetch, and research operations MUST be delegated to Task tool subagents.** This preserves the main conversation context for the soul interview flow. Examples:

- Looking up a user's website/product to understand their business → subagent
- Searching for competitor landscape → subagent
- Fetching example content from platforms the user mentions → subagent
- Validating URLs or checking platform availability → subagent

The main conversation should only contain: questions, user answers, confirmations, and artifact writes.

## Config

```
OPENCLAW_PORTAL_URL=https://unclawg.com
SPAPS_URL=https://api.unclawg.com
APPROVAL_API_URL=https://api.unclawg.com
# Optional only for self-hosted gateways that do not inject server-side app binding:
OPENCLAW_API_KEY=
TENANT_ID=d0000000-0000-0000-0000-000000000001
# Proof-of-humanity fallback contacts (used when signup is pending):
OPENCLAW_PROOF_PRIMARY_X=@your-primary-proof-handle
OPENCLAW_PROOF_SECONDARY_X=https://x.com/your-backup-proof-handle
```

`SPAPS_URL` is the Unclawg auth facade (`/api/auth/*`), not a direct client call to SPAPS.
On `api.unclawg.com`, the gateway injects `X-API-Key` server-side, so do not ask users for `SPAPS_API_KEY`.

## References

- **[references/soul-interview.md](references/soul-interview.md)** — Full soul interview cascade (Phase B, Rounds 1-5). Read when entering the interview phase.
- **[references/artifact-templates.md](references/artifact-templates.md)** — Soul draft templates, mode file template, smoke test, and summary output (Phase C/D). Read when writing artifacts.
- **`/unclawg-admin`** — Operator waitlist triage (Step 4c). Separate skill for approving/denying signups that return `pending_human_proof`.
- **[references/default-soul.md](references/default-soul.md)** — Default soul template for users who skip the interview.

---

## Phase 0 — Detect Existing Setup

Before starting onboarding, check if the user is already set up (partially or fully).

### Check for existing identity

```bash
ls .claude/agents/*.env 2>/dev/null
```

If identity files exist, read each one and extract `OPENCLAW_AGENT_ID`, `OPENCLAW_MACHINE_KEY_ID`.

### Verify the machine key works

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -H "X-Machine-Key-Id: ${KEY_ID}" \
  -H "X-Machine-Secret: ${KEY_SECRET}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  "${APPROVAL_API_URL}/v0/approval-requests/social-reply" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"action\": \"social_reply_approval\",
    \"resource_type\": \"social_post\",
    \"resource_id\": \"test://setup-check-$(date +%s)\",
    \"expires_at\": \"$(date -u -v+1m +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+1 minute' +%Y-%m-%dT%H:%M:%SZ)\",
    \"proposed_reply\": \"Setup verification ping.\",
    \"candidate\": {
      \"source_platform\": \"other\",
      \"source_post_url\": \"https://example.com/setup-check\",
      \"source_post_text\": \"Setup verification\",
      \"discovered_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
```

### Check for missing pieces

```bash
ls modes/${AGENT_ID}.local.md 2>/dev/null
```

### Triage result

Show the user what's present and what's missing:

```
Existing setup found:

  Agent ID:   ${AGENT_ID}
  Key ID:     ${KEY_ID}
  Identity:   .claude/agents/${AGENT_ID}.env
  Key valid:  ✓ (or ✗ — expired/revoked, needs re-provisioning)
  Soul:       [written / not yet]
  Mode file:  [found / missing]
```

Then offer to fill gaps:

- **Key invalid** → need to re-authenticate and provision a new key (jump to Step 4, 409 path)
- **Soul missing** → jump to Phase B (read `references/soul-interview.md`)
- **Mode file missing** → jump to Phase C Step 8 (read `references/artifact-templates.md`)
- **Everything present and valid** → "You're all set. Run `/unclawg-discover` to start finding people."

Skip any phase that's already complete. Do not re-run the full onboarding.

---

## Phase A — Account Provisioning

### Step 1 — Ask Email

Ask one question:

> "What email should we use for your OpenClaw account?"

### Step 2 — Pick Agent Name

Ask:

> "Name your agent — this is the ID that shows up in the approval portal. Examples: `my-trading-bot`, `content-writer`, `code-deployer`"

Default suggestion: derive from the current repo name or working directory.

### Step 3 — Confirm

Show what's about to happen:

```
Ready to set up:
  Email:    user@example.com
  Agent:    my-trading-bot
  Portal:   ${OPENCLAW_PORTAL_URL}

This creates your account and provisions API keys.
A temporary password is generated automatically for this setup.
Continue?
```

### Step 4 — Register Account (via Unclawg auth facade)

```bash
# Generate a strong onboarding password in-memory (do not persist to disk)
ONBOARD_PASSWORD=$(openssl rand -base64 18)

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${SPAPS_URL}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${USER_EMAIL}\",
    \"password\": \"${ONBOARD_PASSWORD}\"
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
```

If using a self-hosted gateway that requires client-supplied app binding, add:
`-H "X-API-Key: ${OPENCLAW_API_KEY}"`.

- `201`:
  1. Extract `ACCESS_TOKEN` from `data.tokens.access_token` and `REFRESH_TOKEN` from `data.tokens.refresh_token`.
  2. If either token is missing/null, immediately login using the generated onboarding password:

```bash
LOGIN_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${SPAPS_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${USER_EMAIL}\",
    \"password\": \"${ONBOARD_PASSWORD}\"
  }")

LOGIN_STATUS=$(echo "$LOGIN_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
LOGIN_BODY=$(echo "$LOGIN_RESPONSE" | sed '/HTTP_STATUS:/d')
```

  3. Require `LOGIN_STATUS=200` and extract `ACCESS_TOKEN`/`REFRESH_TOKEN` from `LOGIN_BODY`.
  4. If login fallback also fails, send a **magic link** as last resort:

```bash
MAGIC_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${SPAPS_URL}/api/auth/magic-link" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${USER_EMAIL}\",
    \"redirect_url\": \"${OPENCLAW_PORTAL_URL}/auth/cli-callback\"
  }")
```

  5. If magic link sends (200), tell the user:
     "Check your email for a sign-in link from OpenClaw. Click it to log in to the portal."
  6. Then prompt: "Once you're logged in, paste your password here so I can provision your agent keys."
     (The user can set a password via the portal sidebar or `/forgot-password` page.)
  7. When the user provides a password, login via API to get tokens and continue to Step 5.
- `202` with `data.status = pending_human_proof` → **Stop onboarding here (no key provisioning yet).**
  1. Tell user signup was created but is pending proof-of-humanity review.
  2. Show `pending_approval_id` (if present) and `proof_of_humanity` instructions from API response.
  3. Tell user to DM proof of humanity on X to `${OPENCLAW_PROOF_PRIMARY_X}` (fallback `${OPENCLAW_PROOF_SECONDARY_X}`).
  4. Tell user API keys are blocked until approval is marked approved.
  5. Do **not** run Step 4b or Step 5. **Do still run Phase B (Soul Interview)** — read `references/soul-interview.md`.
  6. For admin triage of waitlist entries, tell the operator to use `/unclawg-admin`.
- `409` or email exists → **Do NOT bail.** Handle gracefully:
  1. Tell user: "Account already exists for that email."
  2. Ask: "Want me to send a magic link so you can sign in instantly?"
  3. If yes, send magic link:

```bash
MAGIC_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${SPAPS_URL}/api/auth/magic-link" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${USER_EMAIL}\",
    \"redirect_url\": \"${OPENCLAW_PORTAL_URL}/auth/cli-callback\"
  }")
```

  4. Tell user: "Check your email — click the sign-in link to open the portal."
  5. Then ask: "Do you know your password? I need it to provision agent keys."
     - If yes: login via `POST ${SPAPS_URL}/api/auth/login`, extract tokens, continue to Step 5.
     - If no: tell them to set one at `${OPENCLAW_PORTAL_URL}/forgot-password` (offers magic link or reset), then come back with the password.
  6. If user does not want CLI continuation, direct them to `${OPENCLAW_PORTAL_URL}/approvals` and stop.
- Other error → print it, stop

**Note:** For new signups, `ONBOARD_PASSWORD` exists in-memory only for this run. Do not write it to disk.

### Step 4b — Auto-Login via Token Handoff

Immediately after obtaining tokens (from register response or login fallback), open the portal with token handoff. The `/auth/cli-callback` route stores tokens in the browser and redirects to `/approvals`.

```bash
# JWT tokens are base64url — no URL-encoding needed
open "${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}" 2>/dev/null \
  || xdg-open "${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}" 2>/dev/null \
  || echo "Open this URL to log in: ${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}"
```

Tell the user: "Opening the portal in your browser — you're logged in automatically."

**Important:** Open the browser immediately after registration. The access token expires in 1 hour, but the callback page auto-refreshes stale tokens via the refresh token.

### Step 5 — Provision Machine Key (Only after approved signup)

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${APPROVAL_API_URL}/v0/claw-governance/machine-keys" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"label\": \"onboard-$(date +%Y%m%d)\",
    \"scopes\": [
      \"approval_request.create.social_reply\",
      \"approval_revision.fulfill\",
      \"agent_feedback_digest.read\",
      \"instruction_proposal.create\"
    ],
    \"ttl_days\": 90
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
```

If using a self-hosted gateway that requires client-supplied app binding, add:
`-H "X-API-Key: ${OPENCLAW_API_KEY}"`.

- `201` → extract `key_id` and `key_secret` from `data.key`
- `403` → scope issue, print error
- Other → print error, stop

### Step 6 — Output the Env Block

Print this exactly — the user copies it into their `.env` or shell profile:

```
# ── OpenClaw Configuration ──────────────────────
# Add these to your project's .env or ~/.zshrc

OPENCLAW_API_URL=${APPROVAL_API_URL}
OPENCLAW_TENANT_ID=${TENANT_ID}
OPENCLAW_AGENT_ID=${AGENT_ID}
OPENCLAW_MACHINE_KEY_ID=${KEY_ID}
OPENCLAW_MACHINE_SECRET=${KEY_SECRET}
# Optional for non-default gateways:
OPENCLAW_API_KEY=${OPENCLAW_API_KEY}

# ⚠️  Save OPENCLAW_MACHINE_SECRET now.
#     It cannot be retrieved again.
#     If lost, rotate via the portal.
# ─────────────────────────────────────────────────
```

Ask before writing any file with secrets:

> "Save this identity to `.claude/agents/${AGENT_ID}.env` for auto-discovery?"

Only if the user says yes, save the identity file for skill auto-discovery:

```bash
mkdir -p .claude/agents
cat > .claude/agents/${AGENT_ID}.env << ENVEOF
OPENCLAW_API_URL=${APPROVAL_API_URL}
OPENCLAW_TENANT_ID=${TENANT_ID}
OPENCLAW_AGENT_ID=${AGENT_ID}
OPENCLAW_MACHINE_KEY_ID=${KEY_ID}
OPENCLAW_MACHINE_SECRET=${KEY_SECRET}
OPENCLAW_API_KEY=${OPENCLAW_API_KEY}
ENVEOF
```

Tell the user: "Saved to `.claude/agents/${AGENT_ID}.env` — other skills like `/unclawg-feed` and `/unclawg-respond` will auto-discover it."

Then print the summary:

```
Account provisioned.

  Portal:     ${OPENCLAW_PORTAL_URL}
  Agent ID:   ${AGENT_ID}
  Key ID:     ${KEY_ID}
  Expires:    90 days from now
  Identity:   .claude/agents/${AGENT_ID}.env

Now let's define your agent's soul.
```

If this run created a new account, show once:
```
  Temporary Password: ${ONBOARD_PASSWORD}
  Tip: Rotate it later at ${OPENCLAW_PORTAL_URL}/forgot-password.
```

---

## Phase B — Soul Interview (Ask-Cascade)

Read **[references/soul-interview.md](references/soul-interview.md)** for the full interview flow (Rounds 1-5).

---

## Phase C — Write Artifacts

Read **[references/artifact-templates.md](references/artifact-templates.md)** for soul draft templates, mode file template, smoke test, and summary output.

---

## Phase D — Summary

See the summary template in **[references/artifact-templates.md](references/artifact-templates.md)** (bottom section).
