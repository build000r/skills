# Client Overlay Template

Copy this into a local gitignored file:

- `skillbox-config/clients/{client}/overlay.yaml`

The overlay is merged at build time into `context.yaml` which downstream skills consume.

Required fields:

```yaml
name: your-project
cwd_match: /absolute/path/prefix
agent_id: your-agent-name          # disambiguates when multiple overlays match same cwd
objective_default: prospecting
handoff_type: approval-portal       # public default; approval-portal | engagement-queue | db-insert (private operator mode only)
handoff_command: /your-next-step    # null if handoff_type handles routing directly
```

## What Goes Here vs. What Goes in the Soul

| This file (client overlay) | The soul (`soul_md`) |
|-------------------|---------------------|
| Search queries per persona per platform | Persona definitions (name, pain, voice) |
| Subreddit/community targets | Reply archetypes and mix guidance |
| Ranking weights | Engagement principles |
| Exclusion regex and bio keyword filters | Boundary reasoning ("never engage with X because...") |
| Platform scope and API key requirements | Platform tone calibration |
| Handoff schema | Voice and personality |

**Rule:** If swapping this overlay changes how the agent *talks*, something is in the wrong place. This file should only change what the agent *searches for* and where.

## Configuration

### Persona Query Packs

Map personas (defined in the soul) to search queries. Persona names here should match the soul's persona IDs.

- reddit:
  - query: "..."
    subreddit: "..."
    time_filter: week
    limit: 25
- hn:
  - query: "..."
    days_back: 7
    limit: 25
- twitter:
  - query: "..."
    limit: 20
    days_ago: 1
- linkedin:
  - query: "..."
    total_posts: 20
    sort_by: date_posted
    days_ago: 1

### Freshness Policy (Strongly Recommended)

Define a strict freshness contract for fast-reply growth workflows:

```yaml
freshness_policy:
  twitter_max_age_hours: 6
  linkedin_max_age_hours: 6
  recency_priority_hours: [2, 4, 6]  # first bucket wins
  drop_unparseable_timestamps: true
  allow_stale_fallback: false
```

If the objective is fast engagement, do not widen beyond 6h unless explicitly approved.

### Run Cadence

Use explicit scheduling so discovery stays aligned with quick-reply goals:

```yaml
run_cadence:
  preferred_interval_hours: 4     # default recommendation
  budget_interval_hours: 12       # lower-cost fallback (2x/day)
```

### Exclusion Patterns

Mechanical filters only. Personality-level exclusions ("never engage with competing companies because...") live in the soul.

- Bio keyword skip list
- CTA language regex
- Account-type filters (recruiter, aggregator)

### Ranking Weights

Provide weights totaling 100.

- intent: 35
- relevance: 25
- freshness: 20
- engagement: 20

### Platform Scope

List available platforms and their API key requirements.

### Comment Mining Targets (Optional)

If the domain involves engagement on IG/TikTok comment sections, list curated accounts
whose COMMENTERS (not the account owners) are real customers.

```yaml
comment_mining_targets:
  instagram:
    persona_E: [@handle1, @handle2, ...]
    persona_A: [@handle3, ...]
  tiktok:
    persona_E: [handle1, handle2, ...]
    persona_A: [handle3, ...]
comment_signal_regex:
  default: "(looking for|need help|who do you use)"
  persona_E: "(your private domain-specific signal regex)"
```

Scripts: `search_instagram_comments.sh`, `search_tiktok_comments.sh`

Keep account lists and signal regexes in client overlay files only (`skillbox-config/clients/{client}/overlay.yaml`). When running the public scripts, pass the regex via `--signal-regex` or `COMMENT_SIGNAL_REGEX` rather than committing domain-specific patterns into tracked files.

### Ask-Cascade Questions

Provide top-down decision prompts (strategic first):

1. Objective and success metric
2. Persona priority
3. Platform budget/scope
4. Freshness strategy (strict max-age and stale fallback policy)
5. Candidate volume and strictness
6. Handoff target
