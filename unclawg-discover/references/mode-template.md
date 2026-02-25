# Mode Template

Copy this into a local gitignored file:

- `modes/<project>.md`

Required fields:

```yaml
name: your-project
cwd_match: /absolute/path/prefix
objective_default: prospecting
handoff_command: /your-next-step
```

## Configuration

### Personas

List persona priorities and fit rules.

### Query Packs

Define per-platform queries.

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

### Exclusion Rules

List project-specific competitor/vendor filters.

### Ranking Weights

Provide weights totaling 100.

- intent: 35
- relevance: 25
- freshness: 20
- engagement: 20

### Output Contract

Define required candidate fields and any extra downstream metadata.

### Ask-Cascade Questions

Provide top-down decision prompts (strategic first):

1. Objective and success metric
2. Persona priority
3. Platform budget/scope
4. Candidate volume and strictness
5. Handoff target
