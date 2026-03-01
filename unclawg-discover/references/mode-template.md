# Mode Template

Copy this into a local gitignored file:

- `modes/<project>.md`

Required fields:

```yaml
name: your-project
cwd_match: /absolute/path/prefix
agent_id: your-agent-name          # disambiguates when multiple modes match same cwd
objective_default: prospecting
handoff_type: approval-portal       # public default; approval-portal | engagement-queue | db-insert (private operator mode only)
handoff_command: /your-next-step    # null if handoff_type handles routing directly
```

## What Goes Here vs. What Goes in the Soul

| This file (mode) | The soul (`soul_md`) |
|-------------------|---------------------|
| Search queries per persona per platform | Persona definitions (name, pain, voice) |
| Subreddit/community targets | Reply archetypes and mix guidance |
| Ranking weights | Engagement principles |
| Exclusion regex and bio keyword filters | Boundary reasoning ("never engage with X because...") |
| Platform scope and API key requirements | Platform tone calibration |
| Handoff schema | Voice and personality |

**Rule:** If swapping this file changes how the agent *talks*, something is in the wrong place. This file should only change what the agent *searches for* and where.

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
    days_ago: 7
- linkedin:
  - query: "..."
    total_posts: 20
    sort_by: date_posted

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
```

Scripts: `search_instagram_comments.sh`, `search_tiktok_comments.sh`

### Ask-Cascade Questions

Provide top-down decision prompts (strategic first):

1. Objective and success metric
2. Persona priority
3. Platform budget/scope
4. Candidate volume and strictness
5. Handoff target
