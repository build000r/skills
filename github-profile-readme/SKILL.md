---
name: github-profile-readme
description: >-
  Generate and maintain GitHub profile READMEs (the special username/username
  repo). Mines local repos, cass sessions, and website content to produce a
  builder-focused personal landing page. Use when creating, updating, or
  auditing a GitHub profile README.
---

# GitHub Profile README

> **Core insight:** A profile README is a landing page, not a resume. Lead with
> what you're building now, link to where the real work lives, and let
> everything else fall away.

## The One Rule

**Show what you ship. Hide what you don't.**

Most profile READMEs fail because they:
- List technologies instead of products
- Feature repos that haven't been touched in years
- Use badge walls and stats cards as filler
- Read like a CV instead of a builder's notebook
- Never get updated after the initial commit

---

## Modes

This skill has two modes:

| Mode | Trigger | What it does |
|------|---------|-------------|
| **Generate** | "create my profile README", "write my GitHub profile" | Build from scratch using all available signals |
| **Refresh** | "update my profile README", "is my profile stale" | Audit existing README against recent activity, update stale sections |

---

## Generate Mode

### Step 1: Gather signals

Collect context from these sources in order. Each source is optional — use
what's available.

#### a. Local repos (primary signal)

```bash
# List all local repos with recent git activity (last 90 days)
for dir in ~/repos/*/; do
  if [ -d "$dir/.git" ]; then
    last_commit=$(git -C "$dir" log -1 --format="%ci" 2>/dev/null)
    if [ -n "$last_commit" ]; then
      echo "$last_commit  $(basename "$dir")"
    fi
  fi
done | sort -r | head -20
```

For each active repo, read the top-level README.md or CLAUDE.md to understand
what it does. Classify each as:

- **Public + active**: feature prominently
- **Private + active**: describe the domain/capability without naming the repo
- **Public + dormant**: omit unless it's genuinely notable
- **Private + dormant**: omit entirely

#### b. cass session history (what's top-of-mind)

```bash
# Find recent high-frequency work domains
cass search "*" --aggregate agent,date --limit 1 --json 2>/dev/null

# Search for recent project-specific work
cass search "deploy OR ship OR launch OR release" --json --fields minimal --limit 30 2>/dev/null \
  | jq '[.hits[] | select(.line_number <= 3)] | group_by(.workspace) | map({workspace: .[0].workspace, count: length}) | sort_by(-.count)'
```

Use session frequency as a recency signal — repos with many recent sessions
are what the user is actively building.

#### c. Website content (public identity)

If the user has a personal site, read it to extract:
- How they describe themselves
- What projects they showcase
- What tone and voice they use
- What domains they work in

This is the canonical self-description. The profile README should be
consistent with it, not duplicate it.

#### d. GitHub public repos (what visitors actually see)

```bash
# List public repos with activity signals
gh repo list USERNAME --limit 30 --json name,description,pushedAt,stargazerCount,isPrivate,isFork \
  --jq '.[] | select(.isPrivate == false) | [.name, .description // "—", .pushedAt[:10], "stars:\(.stargazerCount)", if .isFork then "fork" else "original" end] | @tsv'
```

Cross-reference with local repo inspection. A public repo that's active
locally but has no description on GitHub is a missed opportunity.

### Step 2: Draft the README

Use this structure. Every section is optional except the identity block.

```
IDENTITY BLOCK (required)
├─ One-line: who you are and what you build
├─ Link to website (if exists)
└─ Link to current primary project

CURRENTLY BUILDING (the core section)
├─ 2-4 active projects, each with:
│   ├─ One-line description of what it does (not what it is)
│   ├─ Link (to live product, not just repo)
│   └─ Domain tag (health, finance, infra, etc.)
└─ Sorted by recency/activity, not stars

DOMAINS (optional, for closed-source depth)
├─ Brief description of capability areas
├─ Concrete but non-specific ("clinical lab analysis" not "repo-name")
└─ Only include domains with recent activity

OPEN SOURCE (optional, only if notable)
├─ 1-3 repos worth highlighting
├─ Each with what-it-solves framing
└─ Skip forks unless you've made substantial changes

COLOPHON (optional, keep short)
└─ One line about how you work, tools, philosophy
```

### Step 3: Apply the rules

| # | Rule | Why |
|---|------|-----|
| 1 | Lead with what you're building, not what you know | This is a landing page, not a CV |
| 2 | Link to live products, not just repos | Repos are implementation; products are value |
| 3 | Describe domains for closed-source work | Show breadth without exposing private repos |
| 4 | No badge walls | Technology lists are noise; shipped products are signal |
| 5 | No GitHub stats cards | Contribution graphs reward activity, not impact |
| 6 | No "skills" or "technologies" section | Let the projects speak for themselves |
| 7 | Keep it under 40 lines of rendered content | Shorter = more likely to be read and maintained |
| 8 | Use plain text over fancy formatting | Markdown renders differently across clients |
| 9 | Funnel to website, don't replicate it | The README is a teaser, the site is the full story |
| 10 | Every project mentioned must have recent activity | Stale showcases erode trust |

### Step 4: Anti-patterns

| Don't | Do instead |
|-------|-----------|
| "I'm a full-stack developer who..." | "I build [specific thing]" |
| List of 20 technology badges | Nothing — let projects imply the stack |
| Contribution snake animation | Nothing — it's filler |
| "Currently learning X" | Only mention if you're shipping something with X |
| Pinned repos from 2 years ago | Update pins to match current work |
| "Fun fact: I love coffee" | Remove — adds nothing |
| Giant ASCII art header | One line of text is better |

### Step 5: Validate

Run the freshness audit (see Refresh Mode) immediately after generating to
confirm nothing is already stale.

---

## Refresh Mode

### Step 1: Audit current README

```bash
# Read the current profile README
cat ~/repos/USERNAME/README.md 2>/dev/null || echo "No local profile repo found"
```

### Step 2: Check freshness of every project mentioned

For each project referenced in the README:

```bash
# Check last commit date
git -C ~/repos/PROJECT_NAME log -1 --format="%ci" 2>/dev/null

# Check if it's still public
gh repo view USERNAME/PROJECT_NAME --json isPrivate,pushedAt 2>/dev/null
```

Flag any project that:
- Has no commits in the last 90 days
- Has been made private or deleted
- No longer exists locally
- Has shifted focus from what the README describes

### Step 3: Check for new work not represented

```bash
# Find active repos not mentioned in the README
for dir in ~/repos/*/; do
  repo=$(basename "$dir")
  last=$(git -C "$dir" log -1 --format="%ci" 2>/dev/null | cut -d' ' -f1)
  if [ -n "$last" ]; then
    if ! grep -qi "$repo" ~/repos/USERNAME/README.md 2>/dev/null; then
      echo "NOT IN README: $repo (last commit: $last)"
    fi
  fi
done | sort -t: -k2 -r | head -10
```

### Step 4: Produce a refresh diff

Don't rewrite the whole README. Produce a targeted update:
- Remove or demote stale projects
- Add or promote newly active projects
- Update descriptions if the project's focus has shifted
- Keep the user's voice and structure intact

---

## Voice and Tone

The profile README should sound like the user, not like a skill template.

Before writing, check:
1. How the user describes themselves on their website
2. How they write commit messages and PR descriptions
3. The tone of their existing README (if refreshing)

Default to: **direct, lowercase-friendly, builder-not-talker energy.** No
corporate polish. No inspirational quotes. No third-person bio.

If the user's existing voice is different, match that instead.

---

## GitHub Actions (Optional Enhancement)

For users who want auto-freshness, offer a GitHub Action that runs on a
schedule and opens a PR when the README references dormant projects:

```yaml
# .github/workflows/profile-freshness.yml
name: Profile README Freshness Check
on:
  schedule:
    - cron: '0 0 1 * *'  # Monthly
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check project freshness
        run: |
          # Extract repo references from README
          grep -oP 'github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+' README.md | sort -u | while read repo; do
            pushed=$(gh api "repos/${repo#github.com/}" --jq '.pushed_at' 2>/dev/null)
            if [ -n "$pushed" ]; then
              days_ago=$(( ($(date +%s) - $(date -d "$pushed" +%s)) / 86400 ))
              if [ "$days_ago" -gt 90 ]; then
                echo "::warning::$repo last pushed $days_ago days ago"
              fi
            fi
          done
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Only suggest this if the user asks for automation. The skill's refresh mode
is the primary mechanism.

---

## Client Overlay Notes

This skill should use a client overlay when available to understand the user's
repo portfolio structure. The overlay provides the mapping from local repos to
public-facing descriptions.

### Project ecosystems

Some projects span multiple repos but should appear as a single entry in the
profile README. The overlay or local inspection should identify these clusters.

**Rules for ecosystem entries:**

- Lead with the ecosystem name, not the individual repo
- Describe the combined capability in one line
- Do not enumerate every repo — describe what the ecosystem does
- If the ecosystem ships public packages (npm, pypi, crates.io), list those
  as sub-bullets with one-liners and registry links
- Private repos within an ecosystem are described by capability, not by name
- Link to packages/registries rather than private GitHub repos

**Example:**

```markdown
**sweet potato (spaps)** -- centralized auth + payments for multi-wallet and
traditional flows. ships sdks and a cli so other projects don't reinvent auth.

- [`spaps-sdk`](https://www.npmjs.com/package/spaps-sdk) -- typescript client
- [`spaps`](https://pypi.org/project/spaps/) -- python client (pypi)
```

```markdown
**cfo** -- ai-powered accounting infrastructure. mcp server for quickbooks,
client portal, and mobile financial assistant. built for cpas managing
multiple company files.
```

The first example has public packages worth linking. The second is a
multi-repo ecosystem described as a single capability without exposing
individual repo names.

### Overlay-driven decisions

When a client overlay exists, use it to resolve:

- Which repos are public vs private (determines linking strategy)
- Which repos form an ecosystem (determines grouping)
- Which package registries have published artifacts (determines sub-bullets)
- Which domains the user works in (determines closed-source section)
- The user's canonical self-description and website (determines identity block)

When no overlay exists, infer these from local repo inspection: check
`package.json`/`pyproject.toml` for published package names, check GitHub
visibility via `gh`, and group repos that share a name prefix or import
each other.

---

## Reference Index

| I need... | Read |
|-----------|------|
| **Great builder profile examples** | [PROFILE-PATTERNS.md](references/PROFILE-PATTERNS.md) |
| **Freshness audit script** | [scripts/audit_freshness.sh](scripts/audit_freshness.sh) |
