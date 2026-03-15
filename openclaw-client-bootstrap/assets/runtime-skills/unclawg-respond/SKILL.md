---
name: unclawg-respond
description: >
  Runtime-safe revision handling for a configured agent. Uses only uc_respond wrapper commands
  to list pending revisions and fulfill approved edits.
metadata: { "openclaw": { "emoji": "🔁", "requires": { "bins": ["uc_respond"] } } }
---

# /unclawg-respond

Process pending revision requests and send fulfill messages.

## Hard Constraints

- Use `uc_respond` only.
- Do not run raw `curl` directly.
- Default to `reconcile`; do not handcraft fulfill payload files in allowlist mode.
- If `reconcile` is unavailable, stop and request wrapper sync (`uc_respond` is outdated).
- `edit_diff.edited_content` must be publish-ready:
  - no audit marker text (`[Reconciled under soul ...]`, `Feedback addressed: ...`)
  - materially different from the original suggestion (no no-op diff fulfills)

## Commands

```bash
uc_respond smoke
uc_respond list --status pending
uc_respond reconcile --agent-id "${OPENCLAW_AGENT_ID:-example-agent}" --dry-run
uc_respond reconcile --agent-id "${OPENCLAW_AGENT_ID:-example-agent}"
```

## Manual Override (Operator Shell Only)

Use manual fulfill only when an operator provides a prepared JSON payload file.

```bash
uc_respond fulfill --approval-id <approval_id> --revision-id <revision_id> --input /path/to/revision.json
```
