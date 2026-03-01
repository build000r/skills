---
name: unclawg-feed
description: >
  Runtime-safe feed workflow for Larry. Uses only uc_feed wrapper commands to
  smoke test auth, read soul policy, and submit social-reply approval requests.
metadata: { "openclaw": { "emoji": "📬", "requires": { "bins": ["uc_feed"] } } }
---

# /unclawg-feed

Convert candidate posts into approval requests through OpenClaw APIs.

## Hard Constraints

- Use `uc_feed` only.
- Do not run raw `curl` directly.
- Keep all writes in approval-request flow.

## Commands

```bash
uc_feed smoke
uc_feed soul --agent-id "${OPENCLAW_AGENT_ID}"
uc_feed submit --input /tmp/candidate.json
```

## Input Contract

`--input` JSON must match the social-reply approval payload expected by `/v0/approval-requests/social-reply`.
