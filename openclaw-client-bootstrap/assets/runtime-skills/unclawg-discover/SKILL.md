---
name: unclawg-discover
description: >
  Runtime-safe multi-platform discovery for Larry. Uses only uc_discover wrapper
  commands for Reddit, Hacker News, Twitter/X (Apify), and LinkedIn (Apify).
metadata: { "openclaw": { "emoji": "🔎", "requires": { "bins": ["uc_discover"] } } }
---

# /unclawg-discover

Find candidate posts for outreach and approvals using wrapper-only discovery.

## Hard Constraints

- Use `uc_discover` only.
- Do not run raw `curl`, `bash`, or `python`.
- No local write/persistence unless operator explicitly enables write tools.
- Keep Twitter/X + LinkedIn discovery strict-recent: max post age 6 hours.
- Prioritize earliest posts first (0-2h > 2-4h > 4-6h).

## Commands

```bash
uc_discover reddit --query "ai agent guardrails" --subreddit LocalLLaMA --time-filter week --limit 25
uc_discover hn --query "human in the loop ai agent" --days 7 --limit 25
uc_discover twitter --query "polymarket bot human approval" --days 1 --limit 20
uc_discover linkedin --query "ai agent guardrails" --days 1 --limit 20 --sort-by date_posted
```

## Freshness + Cadence Defaults

- Hard reject Twitter/X + LinkedIn candidates older than 6h.
- Drop candidates with unparseable timestamps.
- Default run rhythm: every 4h (preferred) or every 12h (2x/day budget mode).

## Output Contract

Return ranked candidates with source URL, short evidence, and a recommended next action.
