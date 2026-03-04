---
name: unclawg-discover
description: >
  Multi-platform customer discovery for any domain. Searches Reddit, Hacker News,
  Twitter/X (Apify), and LinkedIn (Apify), filters noise, and outputs a ranked
  engagement feed with normalized candidate records for downstream workflows.
  Use when: "/unclawg-discover", "find customers", "find leads",
  "find outreach candidates", "find posts to reply to", "build engagement queue",
  "find unclawg customers", "find agent builder leads",
  "buildooor leads".
metadata:
  openclaw:
    emoji: "🔎"
    requires:
      bins:
        - uc_discover
---

# /unclawg-discover

Build a high-signal customer feed from public social channels.

This skill is a **generic core**. Project-specific strategy, queries, voice, and
handoff contracts belong in local `modes/` files (gitignored).

## Runtime Security Profile (AI Default)

- Treat this tracked skill as an AI runtime skill, not an operator shell runbook.
- Use wrapper command `uc_discover` only.
- Do not run `scripts/search_*.sh`, raw `curl`, or ad-hoc `python` from this skill.
- If `uc_discover` is missing, fail closed and ask for wrapper installation.

## Prerequisites

- `APIFY_API_KEY` (required for Twitter/X and LinkedIn scripts)
- `uc_discover` wrapper installed and allowlisted in runtime config

If env vars are missing in non-interactive shells:

```bash
export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

## Wrapper Command Contract

Required wrapper command:
- `uc_discover` with platform subcommands and strict schema validation.

Command mapping:

```bash
uc_discover reddit --query "<query>" --subreddit <subreddit> --time-filter week --limit 25
uc_discover hn --query "<query>" --days 7 --limit 25
uc_discover twitter --query "<query>" --days 1 --limit 20
uc_discover linkedin --query "<query>" --days 1 --limit 20 --sort-by date_posted
```

## Freshness-First Default (X + LinkedIn)

For audience growth and fast replies, use a strict recency contract:

- Hard cutoff: only keep posts with age `<= 6 hours` on Twitter/X and LinkedIn.
- Recency bias: heavily prioritize newest posts (0-2h first, then 2-4h, then 4-6h).
- No stale fallback by default: do not widen past 6h unless the user explicitly overrides.
- Timestamp quality gate: if post age cannot be parsed, treat it as stale and drop it.

Recommended run cadence:

- Primary recommendation: every 4 hours (6 runs/day).
- Budget fallback: 2 runs/day (every 12 hours), still with 6h hard cutoff.

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

## Soul / Mode / Skill Separation

| Layer | What it owns | Files |
|-------|-------------|-------|
| **Soul** (`soul_md` via API) | Voice, tone, personas (with voice calibration), reply archetypes, engagement principles, boundaries | Fetched from `/v0/integrations/claw-runtime/policies/soul_md` |
| **Mode** (`modes/*.md`, gitignored) | Query packs, subreddit targets, ranking weights, exclusion regex, platform scope, handoff schema | Local `modes/<project>.md` |
| **Skill** (this file) | API calls, script execution, data flow, error handling | `SKILL.md` + `scripts/` |

**This skill is personality-agnostic.** It searches, filters, scores, and outputs candidates. How the agent *talks* is the soul's job. What the agent *searches for* is the mode file's job.

If no soul is published, fall back to `references/voice-guide.md` (generic defaults).

## NEVER Do These Things

- **NEVER hardcode project/company strategy in tracked core files.** Keep it in `modes/*.md`.
- **NEVER put voice, tone, or personality guidance in mode files.** That belongs in the soul.
- **NEVER submit actions directly from discovery.** Discovery outputs candidates; execution is downstream.
- **NEVER skip source links or raw post text.** Every candidate needs provenance.
- **NEVER skip quality gates.** Use the checklist in `references/feed-quality-checklist.md`.

## Core Assets

- `scripts/search_reddit.sh`
- `scripts/search_hn.sh`
- `scripts/search_twitter.sh`
- `scripts/search_linkedin.sh`
- `scripts/search_linkedin_jobs.sh` (optional extension channel)
- `scripts/search_indeed.sh` (optional extension channel)
- `scripts/search_youtube.sh`
- `scripts/search_tiktok.sh`
- `scripts/search_instagram_comments.sh`
- `scripts/search_tiktok_comments.sh`
- `scripts/reddit_user_socials.sh`
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
command -v uc_discover >/dev/null || {
  echo "Missing required wrapper: uc_discover"
  echo "Install/allowlist wrapper before running /unclawg-discover."
  exit 1
}
```

### Phase 1 - Strategic Intake (Ask-Cascade Order)

Use high-level decisions first, then detail decisions.

1. Objective: prospecting, audience-growth, content-sourcing, recruiting, other.
2. Persona cluster: who exactly are we looking for.
3. Channel scope: Reddit-only vs multi-platform.
4. Freshness strategy: strict max-age (default 6h) and stale fallback policy.
5. Throughput: target candidate count and freshness window.
6. Handoff target: where this feed goes next.

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
uc_discover reddit --query "<query>" --subreddit <subreddit> --time-filter week --limit 25
```

#### Hacker News (free)

```bash
uc_discover hn --query "<query>" --days 7 --limit 25
```

#### Twitter/X (Apify)

```bash
uc_discover twitter --query "<query>" --days 1 --limit 20
```

#### LinkedIn (Apify)

```bash
uc_discover linkedin --query "<query>" --days 1 --limit 20 --sort-by date_posted
```

### Phase 3.5 - Comment Mining (Optional)

If the active mode file includes `comment_mining_targets`, mine comment sections
of curated accounts for real customer signals.

1. Check mode file for `comment_mining_targets` section.
2. If present, run the appropriate scripts against listed accounts:
   - Instagram: `scripts/search_instagram_comments.sh <handle1> [handle2] ...`
   - TikTok: `scripts/search_tiktok_comments.sh <handle1> [handle2] ...`
3. Score comments by signal density (health pain-point language regex).
4. Merge comment-sourced candidates into the main candidate pool before Phase 4 filtering.
5. Comment-sourced candidates use the POST/VIDEO as the engagement target (comment there to reach real customers in the thread).

**Cost note:** Comment mining uses Apify credits. Confirm with user before running if budget is a concern.

### Phase 3.6 - Hiring-Board Extension (Optional, Non-Wrapper)

Use only when runtime policy allows local script execution and the active mode
explicitly calls for hiring-board discovery.

```bash
scripts/search_linkedin_jobs.sh "<query>" 20 C
scripts/search_indeed.sh "<position>" "remote" 20
```

Treat these as slower-moving research channels. Keep conversational channels
(Twitter/X + LinkedIn posts) on strict recency gates for quick replies.

### Phase 4 - Filter and Score

1. **Deduplicate** — use platform-appropriate strategy:
   - Twitter/X, Reddit, HN: `unique_by(.url)` (URLs are reliable)
   - LinkedIn: `unique_by(.text[0:100] + .author_name)` (URLs are often empty)
2. Remove competitor/vendor noise using `references/competitor-signals.md`.
3. Remove low-evidence posts (missing meaningful text or too short).
4. **Hard freshness gate (X + LinkedIn):**
   - Drop any candidate older than 6 hours.
   - Drop candidates with unparseable/missing post timestamps.
   - Sort surviving X + LinkedIn candidates by recency first, then engagement.
5. **LinkedIn extra filter:** Apply aggressive keyword regex on `.text` field to
   remove job spam, hiring posts, LinkedIn puzzles, and viral non-technical content.
   The LinkedIn scraper returns ~99% noise — filter BEFORE scoring to save time.
6. Score survivors by:
   - explicit pain or intent
   - decision-maker likelihood
   - recency
   - engagement signal
   - fit to objective/persona

Recency bucket scoring for X + LinkedIn (default):

- `0-2h`: highest priority
- `2-4h`: high priority
- `4-6h`: medium priority
- `>6h`: reject

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

### Phase 7 - Save + Handoff

Default mode is in-memory output only (no local writes). Save to disk only if
runtime policy explicitly allows write tools.

Route by `handoff_type` from the active mode file:

- **`approval-portal`** → Invoke `/unclawg-feed` (API approval flow; no SSH required).
- **`engagement-queue`** → Save to `briefs/` directory (future, not implemented).
- **`db-insert`** → Phase 7A (private operator mode only; not for public/default use).
- **unset / null** → In-memory output only, present to user.

For public distributions and users without infrastructure access, keep
`handoff_type: approval-portal`.

### Phase 7A - Private Operator Extension (Optional)

Use only when `handoff_type: db-insert` is intentionally set in a local,
gitignored operator mode.

1. Present candidate table for user confirmation (user may drop rows, edit angles).
2. On confirmation, batch INSERT via SSH to prod DB:

```sql
INSERT INTO social_engagement_queue
  (id, platform, post_url, post_author, post_title, post_caption,
   post_metrics, posted_at, persona, htma_angle,
   status, created_at, updated_at)
VALUES (gen_random_uuid(), ...)
ON CONFLICT (post_url) DO NOTHING;
```

3. Use the `ssh-info` skill to resolve the current SSH target and Docker DB container, then run the insert from that runtime context.
   Keep real hosts, users, and container names out of tracked files.

4. Verify row count after insert.
5. Report: rows inserted, rows skipped (conflict), total in queue.

## Known Platform Issues

### LinkedIn: Low Signal-to-Noise (Critical)

**Actor:** `apimaestro/linkedin-posts-search-scraper-no-cookies` (4.14 rating)

**Problem:** This actor returns generic LinkedIn feed content regardless of search query.
Exact-phrase matching does not work — queries like `"AI agent governance human approval"` return
Indian job spam, TCS hiring posts, LinkedIn puzzles, and viral non-technical content.
Observed signal rate: **<1% relevant content** across 500+ results from 16 queries.

**Impact:** LinkedIn discovery via this actor is unreliable for targeted prospecting.
Do not promise high LinkedIn candidate volumes to users.

**Workarounds:**
1. Filter aggressively post-collection using keyword regex on `.text` field
2. Use broader, single-keyword queries (`"AI agent"`, `"agentic AI"`) and accept lower precision
3. For high-value LinkedIn targeting, fall back to manual curation (user pastes specific post URLs)
4. Consider alternative actors that use authenticated LinkedIn sessions for better search quality

**Dedup:** This actor returns empty `url` fields on most posts. **NEVER use `unique_by(.url)`**
for LinkedIn results. Use composite key instead:
```bash
jq 'unique_by(.text[0:100] + .author_name)' results.json
```

### Twitter/X: Works Well

**Actor:** `api-ninja/x-twitter-advanced-search` (4.93 rating)

Twitter search returns accurate keyword-matched results. Exact phrases work. Typical signal
rate is 40-80% relevant content depending on query specificity. Very niche phrases
(e.g., `"crewai agent safety control"`) may return 0 results — broaden the query if needed.

## Notes

- **Persona voice** lives in the soul, not in mode files. Mode files only map persona IDs to search queries.
- Keep project-specific keywords and query packs in `modes/`.
- Keep core scripts and references reusable across domains.
- If discovery quality degrades, tune mode-level ranking weights before touching core logic.
- If reply quality degrades, tune the soul (voice, archetypes, persona calibration) — not the mode or skill.
- For public packaging, use `scripts/package_public.sh` to exclude local `modes/` overlays.
