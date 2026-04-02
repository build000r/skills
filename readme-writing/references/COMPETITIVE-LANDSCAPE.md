# Competitive Landscape Research

Use `gh` CLI to pull live signals from comparable repos, then build honest positioning artifacts.

---

## The Workflow

```
1. Identify 5-8 comparable repos (direct competitors + adjacent tools)
2. Pull live metrics from each
3. Sample recent issues for pain signals
4. Build comparison table + market map
5. Write the honest advisory back to the user
```

---

## Step 1: Identify Comparable Repos

Search GitHub for repos in the same space:

```bash
# Find repos by topic
gh search repos "remote development" --sort stars --limit 20 --json fullName,stargazersCount,description

# Or by specific known repos
for repo in coder/coder gitpod-io/gitpod daytonaio/daytona e2b-dev/E2B loft-sh/devpod; do
  gh api "repos/$repo" --jq '{name: .full_name, stars: .stargazers_count, issues: .open_issues_count, pushed: .pushed_at, description: .description}'
done
```

---

## Step 2: Pull Live Metrics

```bash
# Compact overview of each repo
gh api repos/OWNER/REPO --jq '{
  stars: .stargazers_count,
  forks: .forks_count,
  open_issues: .open_issues_count,
  pushed: .pushed_at,
  created: .created_at,
  license: .license.spdx_id,
  language: .language,
  topics: .topics
}'

# Batch version for multiple repos
for repo in coder/coder gitpod-io/gitpod daytonaio/daytona; do
  echo "--- $repo ---"
  gh api "repos/$repo" --jq '{stars: .stargazers_count, open_issues: .open_issues_count, pushed: .pushed_at}'
done
```

---

## Step 3: Sample Issues for Pain Signals

This is where the real insight lives. Issue titles tell you what users actually struggle with.

```bash
# Recent open issues
gh issue list --repo OWNER/REPO --state open --limit 20 --json title,labels,createdAt

# Issues with most reactions (pain points people care about)
gh issue list --repo OWNER/REPO --state open --limit 50 --json title,reactionGroups,url \
  | jq '[.[] | {title, reactions: ([.reactionGroups[].users.totalCount] | add), url}] | sort_by(-.reactions) | .[0:10]'

# Issues by label (find categories of pain)
gh issue list --repo OWNER/REPO --state open --label bug --limit 20 --json title,createdAt

# Search for specific pain patterns
gh search issues "ssh connection" --repo OWNER/REPO --limit 10 --json title,url
```

### What to look for in issues

| Signal | What it means |
|--------|---------------|
| SSH/connection issues | Platform complexity leaking to users |
| "self-hosted" requests | Users want to own their infrastructure |
| Agent/AI integration asks | Market is moving toward agent-native |
| State persistence bugs | Ephemeral-first tools struggling with durability |
| Config/setup friction | Ceremony is too high |

---

## Step 4: Build the Comparison Table

### Basic comparison (for the README)

```markdown
## Comparison

| Option | Best for | Strength | Gap this project fills |
|--------|----------|----------|----------------------|
| **This project** | [specific use case] | [honest differentiator] | -- |
| **Competitor A** | [their sweet spot] | [what they do well] | [what they miss] |
| **Competitor B** | [their sweet spot] | [what they do well] | [what they miss] |
```

### Market Map (for VISION.md)

Pick two axes that reveal positioning. Common useful axes:

- Platform heft (thin tool ... heavy platform)
- Agent-native focus (human-first ... agent-first)
- Durability (ephemeral ... persistent)
- Operational ceremony (low ... high)
- Scope (environment only ... full workstation)

```markdown
## Market Map

Axes: X = platform heft, Y = agent-native focus

```text
10 |  .    .    .    .    .    .    .   DT    .    .
 9 |  .    .    .    .    .   E2B   .    .    .    .
 8 |  .   SB    .    .    .    .    .    .    .    .
 7 |  .    .    .    .    .    .    .    .    .    .
 6 |  .    .    .    .    .    .    .   CDR   .    .
 5 |  .    .    .    .    .    .    .    .    .    .
 4 |  .    .    .    .    .    .    .    .   GP    .
 3 |  .    .    .    .   DP    .    .    .    .    .
 2 |  .   DBX  OVS  CS    .    .    .    .    .    .
 1 |  .    .    .    .    .    .    .    .    .    .
   + --------------------------------------------------
       1    2    3    4    5    6    7    8    9   10
```

| Label | Repo | Read |
|-------|------|------|
| `SB` | this project | Thin and strongly agent-oriented |
| `DBX` | `jetify-com/devbox` | Thin, environment-focused |
| ...
```

---

## Step 5: The Honest Advisory

After the README is written and the landscape is mapped, present findings to the user. This is not a section in the README — it is a conversation.

### Template

```
## Where This Project Sits (Honest Take)

### What the data shows
- [Repo] has [N] stars and [M] open issues. Recent issue themes: [X, Y, Z].
- [Repo] has [N] stars. Users are asking for [specific feature] which this project [does/doesn't] address.
- The common pain across adjacent tools is: [pattern from issue sampling].

### What this project does well
- [Specific strength backed by comparison data, not aspiration]

### Where this project could build on existing work
- **[Tool/library]** already solves [problem] well. Instead of rebuilding, consider composing with it.
- **[Tool/library]** has [feature] that covers [gap]. Worth integrating rather than competing.

### If we want to truly add value, consider these directions
1. **[Direction]** — [Specific gap from issue data]. No one in the landscape is doing this well yet.
2. **[Direction]** — [Adjacent repos] are struggling with [X]. This project's [Y] is a natural fit.
3. **[Direction]** — [Underserved user segment] keeps appearing in [repo] issues but gets deprioritized.

### What to avoid becoming
- [Category that an adjacent tool already owns and does well]
- [Scope expansion that would turn this into a platform competitor without platform resources]
```

---

## Evidence Gathering Checklist

```
□ Pulled stars/issues/activity for 5+ comparable repos
□ Sampled 10+ recent issues from top 3 competitors
□ Identified recurring pain themes across repos
□ Built comparison table with honest strengths AND gaps
□ Market map with meaningful axes (not vanity positioning)
□ Named specific tools/libraries to compose with, not rebuild
□ Named 2-3 directional bets backed by issue evidence
□ Named what the project should NOT become
```
