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
uc_feed submit --input-json '{"agent_id":"larry","action":"social_reply_approval",...}'
```

## Input Contract

Use `--input-json` by default in Telegram/runtime contexts to avoid temp-file dependencies.
If needed in operator shell, `--input /path/to/payload.json` is also supported.
