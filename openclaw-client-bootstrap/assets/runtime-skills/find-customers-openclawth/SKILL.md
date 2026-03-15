---
name: find-customers-openclawth
description: >
  Strict-mode OpenClawth lead discovery. Uses only wrapper commands to query
  Reddit, HN, Twitter/X (Apify), and LinkedIn (Apify). No local state writes.
metadata: { "openclaw": { "emoji": "🎯", "requires": { "bins": ["fcoc_search"] } } }
---

# /find-customers-openclawth

Use this skill to find developers and AI users with pain around autonomous actions
that need human-in-the-loop approvals.

## Hard Constraints

- Use `fcoc_search` only.
- Do not run raw `curl`, `bash`, or `python`.
- No local writes.
- Keep only high-signal candidates with clear buying intent.

## Commands

```bash
fcoc_search --platform reddit --query "ai agent human approval" --subreddit LocalLLaMA --time-filter week --limit 30
fcoc_search --platform hn --query "ai agent guardrails" --days 7 --limit 30
fcoc_search --platform twitter --query "autonomous bot approval workflow" --days 1 --limit 20
fcoc_search --platform linkedin --query "human in the loop ai agent" --days 1 --limit 20 --sort-by date_posted
```

## Output Contract

Return ranked candidates with source URL, relevance evidence, and a recommended
next action for approval gating outreach.
