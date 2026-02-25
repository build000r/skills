---
name: unclawg-discover
description: >
  Multi-platform customer discovery for any domain. Searches Reddit, Hacker News,
  Twitter/X (Apify), and LinkedIn (Apify), filters noise, and outputs a ranked
  engagement feed with normalized candidate records for downstream workflows.
  Use when: "/unclawg-discover", "/find-customers", "find customers", "find leads",
  "find outreach candidates", "find posts to reply to", "build engagement queue".
---

# /unclawg-discover

Build a high-signal customer feed from public social channels.

This skill is a **generic core**. Project-specific strategy, queries, voice, and
handoff contracts belong in local `modes/` files (gitignored).

## Prerequisites

- `APIFY_API_KEY` (required for Twitter/X and LinkedIn scripts)
- `jq`, `curl`, `python3`
- Skill folder available at either:
  - `~/.claude/skills/unclawg-discover`, or
  - `<repo>/.claude/skills/unclawg-discover`

If env vars are missing in non-interactive shells:

```bash
export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

## Mode System (Required for Project-Specific Behavior)

Local mode overlays live in `modes/*.md` and are intentionally gitignored.

- Use `references/mode-template.md` to create a project mode.
- Use `references/mode-example-checklist.md` for a complete example shape.
- Resolve active mode with:

```bash
scripts/select_mode.sh "$(pwd)"
```

Resolution rules:

1. If exactly one mode matches `cwd_match`, use it.
2. If none match, run the generic flow below.
3. If multiple match, ask user which mode file to apply.

## NEVER Do These Things

- **NEVER hardcode project/company strategy in tracked core files.** Keep it in `modes/*.md`.
- **NEVER submit actions directly from discovery.** Discovery outputs candidates; execution is downstream.
- **NEVER skip source links or raw post text.** Every candidate needs provenance.
- **NEVER skip quality gates.** Use the checklist in `references/feed-quality-checklist.md`.

## Core Assets

- `scripts/search_reddit.sh`
- `scripts/search_hn.sh`
- `scripts/search_twitter.sh`
- `scripts/search_linkedin.sh`
- `scripts/search_log.sh`
- `scripts/select_mode.sh`
- `scripts/package_public.sh`
- `references/personas.md`
- `references/competitor-signals.md`
- `references/target_profiles.md`
- `references/voice-guide.md`
- `references/feed-quality-checklist.md`

## Execution Flow

### Phase 0 - Bootstrap

```bash
SKILL_DIR="${HOME}/.claude/skills/unclawg-discover"
[ ! -d "$SKILL_DIR" ] && SKILL_DIR="$(pwd)/.claude/skills/unclawg-discover"
cd "$SKILL_DIR"
chmod +x scripts/*.sh
```

### Phase 1 - Strategic Intake (Ask-Cascade Order)

Use high-level decisions first, then detail decisions.

1. Objective: prospecting, audience-growth, content-sourcing, recruiting, other.
2. Persona cluster: who exactly are we looking for.
3. Channel scope: Reddit-only vs multi-platform.
4. Throughput: target candidate count and freshness window.
5. Handoff target: where this feed goes next.

Apply `references/feed-quality-checklist.md` while collecting these choices.

### Phase 2 - Load Mode or Build Temporary Plan

If a mode file is resolved, use its:

- query pack per platform
- inclusion/exclusion signals
- ranking weights
- output format
- handoff contract

If no mode exists, assemble a temporary plan from `references/personas.md` and
ask for explicit confirmation before running paid queries (Apify).

### Phase 3 - Run Discovery

Run 2-4 focused queries per selected platform.

#### Reddit (free)

```bash
scripts/search_reddit.sh "<query>" <subreddit> week 25
```

#### Hacker News (free)

```bash
scripts/search_hn.sh "<query>" 7 25
```

#### Twitter/X (Apify)

```bash
scripts/search_twitter.sh "<query>" 20 7
```

#### LinkedIn (Apify)

```bash
scripts/search_linkedin.sh "<query>" 20 date_posted
```

### Phase 4 - Filter and Score

1. Remove competitor/vendor noise using `references/competitor-signals.md`.
2. Remove low-evidence posts (missing URL or meaningful text).
3. Score survivors by:
   - explicit pain or intent
   - decision-maker likelihood
   - recency
   - engagement signal
   - fit to objective/persona

### Phase 5 - Normalize Output

For each candidate, produce:

- `source_platform`
- `source_post_url`
- `source_post_text`
- `source_author_handle` (optional)
- `source_author_name` (optional)
- `source_post_id` (optional)
- `persona_hint` (optional)
- `intent_signal` (optional)

Also include:

- `summary`
- `reply_strategy`
- `action`
- `evidence` (short note: why this was selected)

### Phase 6 - Quality Gate and Present

Before finalizing, run the checklist in `references/feed-quality-checklist.md`.

Return:

- ranked table of candidates
- top 3 immediate outreach targets
- top 3 content/influence targets
- rejected-pattern summary (what was filtered out)

### Phase 7 - Optional Save + Handoff

```bash
mkdir -p briefs
DATE=$(date +%Y%m%d)
OUT="briefs/${DATE}_feed.md"
```

Save only when requested.

Handoff should reference mode contract when available (for example, a feed-submission skill).

## Notes

- Keep project-specific keywords, personas, and brand voice in `modes/`.
- Keep core scripts and references reusable across domains.
- If discovery quality degrades, tune mode-level ranking weights before touching core logic.
- For public packaging, use `scripts/package_public.sh` to exclude local `modes/` overlays.
