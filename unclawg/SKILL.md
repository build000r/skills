---
name: unclawg
description: >
  Self-service OpenClaw onboarding. Registers the user, creates their agent,
  provisions machine keys, and outputs the env block for their local Claude Code.
  Use when: "/unclawg", "/onboard", "set me up", "connect to openclaw",
  "get started", "onboard me", "sign up for openclaw", "I want approval gates"
---

# /unclawg

Get set up with OpenClaw in under 60 seconds. You'll have approval gates on your local Claude Code agents.

## What This Does

1. Asks your email
2. Creates your account
3. Names your agent
4. Opens the portal in your browser (auto-logged in)
5. Provisions machine keys
6. Gives you the env block to paste

That's it. Your agents now need human approval before acting.

## NEVER Do These Things

- **NEVER show the machine key secret more than once.** It cannot be retrieved after creation.
- **NEVER store passwords or secrets in any file the user didn't ask for.**
- **NEVER skip the confirmation before creating the account.**

## Config

```
OPENCLAW_PORTAL_URL=https://unclawg.com
SPAPS_URL=https://api.unclawg.com
APPROVAL_API_URL=https://api.unclawg.com
SPAPS_API_KEY=<set-me>
TENANT_ID=tenant-prod
```

`SPAPS_URL` is the Unclawg auth facade (`/api/auth/*`), not a direct client call to SPAPS.

## Flow

### Step 1 — Ask

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
Continue?
```

### Step 4 — Register Account (via Unclawg auth facade)

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${SPAPS_URL}/api/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SPAPS_API_KEY}" \
  -d "{
    \"email\": \"${USER_EMAIL}\",
    \"password\": \"$(openssl rand -base64 24)\"
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
```

- `201` → extract from response JSON:
  - `ACCESS_TOKEN` from `data.tokens.access_token`
  - `REFRESH_TOKEN` from `data.tokens.refresh_token`
  - `USER_ID` from `data.user.id`
- `409` or email exists → **Do NOT bail.** Handle gracefully:
  1. Tell user: "Account already exists for that email."
  2. Ask: "Want to add a new agent? Two options:"
     - **Portal**: "Click **+ Add Agent** in the sidebar at `${OPENCLAW_PORTAL_URL}/approvals`"
     - **CLI (continue here)**: "Set a password at `${OPENCLAW_PORTAL_URL}/forgot-password`, then I'll log you in and provision the new agent"
  3. If user picks CLI path:
     - Prompt for agent name (Step 2 above)
     - Prompt for password (they just set via forgot-password)
     - Login: `POST ${SPAPS_URL}/api/auth/login` with email + password → extract `ACCESS_TOKEN` and `REFRESH_TOKEN`
     - Skip to Step 5 (provision machine key with new agent_id)
  4. If user picks Portal path: done — they'll use the Add Agent modal in the sidebar.
- Other error → print it, stop

**Note:** Password is random on initial registration — don't show or store it. The user logs in via token handoff (next step).

### Step 4b — Auto-Login via Token Handoff

Immediately after registration, open the portal with the tokens. The `/auth/cli-callback` route stores them in the browser and redirects to `/approvals`. No password needed.

```bash
# JWT tokens are base64url — no URL-encoding needed
open "${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}" 2>/dev/null \
  || xdg-open "${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}" 2>/dev/null \
  || echo "Open this URL to log in: ${OPENCLAW_PORTAL_URL}/auth/cli-callback?access_token=${ACCESS_TOKEN}&refresh_token=${REFRESH_TOKEN}"
```

Tell the user: "Opening the portal in your browser — you're logged in automatically."

**Important:** Open the browser immediately after registration. The access token expires in 1 hour, but the callback page auto-refreshes stale tokens via the refresh token.

### Step 5 — Provision Machine Key

```bash
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  "${APPROVAL_API_URL}/v0/claw-governance/machine-keys" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "X-API-Key: ${SPAPS_API_KEY}" \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"label\": \"onboard-$(date +%Y%m%d)\",
    \"scopes\": [
      \"approval_request.create.social_reply\",
      \"approval_revision.fulfill\",
      \"agent_feedback_digest.read\"
    ],
    \"ttl_days\": 90
  }")

STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')
```

- `201` → extract `key_id` and `key_secret` from `data.key`
- `403` → scope issue, print error
- Other → print error, stop

### Step 6 — Output the Env Block

Print this exactly — the user copies it into their `.env` or shell profile:

```
# ── OpenClaw Configuration ──────────────────────
# Add these to your project's .env or ~/.zshrc

OPENCLAW_API_URL=${APPROVAL_API_URL}
OPENCLAW_API_KEY=${SPAPS_API_KEY}
OPENCLAW_TENANT_ID=${TENANT_ID}
OPENCLAW_AGENT_ID=${AGENT_ID}
OPENCLAW_MACHINE_KEY_ID=${KEY_ID}
OPENCLAW_MACHINE_SECRET=${KEY_SECRET}

# ⚠️  Save OPENCLAW_MACHINE_SECRET now.
#     It cannot be retrieved again.
#     If lost, rotate via the portal.
# ─────────────────────────────────────────────────
```

Then save the identity file for skill auto-discovery:

```bash
mkdir -p .claude/agents
cat > .claude/agents/${AGENT_ID}.env << 'ENVEOF'
OPENCLAW_API_URL=${APPROVAL_API_URL}
OPENCLAW_API_KEY=${SPAPS_API_KEY}
OPENCLAW_TENANT_ID=${TENANT_ID}
OPENCLAW_AGENT_ID=${AGENT_ID}
OPENCLAW_MACHINE_KEY_ID=${KEY_ID}
OPENCLAW_MACHINE_SECRET=${KEY_SECRET}
ENVEOF
```

Tell the user: "Saved to `.claude/agents/${AGENT_ID}.env` — other skills like `/unclawg-feed` and `/unclawg-respond` will auto-discover it."

Then:

```
You're set up.

  Portal:     ${OPENCLAW_PORTAL_URL}
  Agent ID:   ${AGENT_ID}
  Key ID:     ${KEY_ID}
  Expires:    90 days from now
  Identity:   .claude/agents/${AGENT_ID}.env

Skills will auto-discover this agent.
When your agent needs approval, it'll show up at ${OPENCLAW_PORTAL_URL}.

Tip: Set a password at ${OPENCLAW_PORTAL_URL}/forgot-password so you can add more agents later from the portal sidebar.
```

### Step 7 — Smoke Test (Optional)

Ask: "Want to send a test approval to verify everything works?"

If yes, create a test approval request:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-API-Key: ${SPAPS_API_KEY}" \
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
    \"resource_id\": \"test://onboarding-smoke-test\",
    \"expires_at\": \"$(date -u -v+1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)\",
    \"proposed_reply\": \"This is a test approval from your new agent. If you see this in the portal, everything works.\",
    \"candidate\": {
      \"source_platform\": \"other\",
          \"source_post_url\": \"https://example.com/test\",
      \"source_post_text\": \"Onboarding smoke test\",
      \"discovered_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }
  }"
```

If `201`: "Check your portal — you should see a test card. Approve or dismiss it."
If error: print it and suggest checking the env vars.
