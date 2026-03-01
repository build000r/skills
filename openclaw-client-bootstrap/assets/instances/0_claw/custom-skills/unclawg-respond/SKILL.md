---
name: unclawg-respond
description: >
  Runtime-safe revision handling for Larry. Uses only uc_respond wrapper commands
  to list pending revisions and fulfill approved edits.
metadata: { "openclaw": { "emoji": "🔁", "requires": { "bins": ["uc_respond"] } } }
---

# /unclawg-respond

Process pending revision requests and send fulfill messages.

## Hard Constraints

- Use `uc_respond` only.
- Do not run raw `curl` directly.
- Only submit fulfill payloads after user-confirmed edits.

## Commands

```bash
uc_respond smoke
uc_respond list --status pending
uc_respond fulfill --approval-id <approval_id> --revision-id <revision_id> --input /tmp/revision.json
```
