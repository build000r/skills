---
name: skill-issue
description: Create, update, review, and package skills for AI coding agents. Also manages client overlays (create, list, validate, match, migrate). Use when asked to "create a skill", "make a skill", "new skill", "skill template", "design a skill", "build a skill", "review this skill", "improve this skill based on past runs", "when did we last use this skill", or when working with SKILL.md files, frontmatter, bundled resources (scripts/, references/, assets/), .skill packaging, or Claude/Codex transcript-driven skill reliability. Also triggers on "how do I make a skill", "skill best practices", "skill structure", "skill reliability", "operator evidence", "create an overlay", "list overlays", "check my overlays", "which overlay matches", "migrate overlays", or requests to extend an agent's capabilities with reusable workflows.
license: Complete terms in LICENSE.txt
---

# Skill Creator

Create effective skills for AI coding agents: modular packages that extend agents with specialized workflows, domain expertise, and reusable tools.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using skill-issue`.

Preferred format: `Using skill-issue to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix. Reliability review tooling treats it as a stable invocation marker.

## Use This For

- Creating, updating, packaging, or reviewing reusable agent skills
- Transcript-driven skill reliability work based on real invocation history
- Working on SKILL.md files, bundled scripts/references/assets, or skill packaging

## No-Ragrets Companion Gate

For skill creation, review, or update work, use `no-ragrets` as the forward-and-retro success contract when it is available or explicitly tagged.

Before editing, define the expected future agent behavior the skill should cause:

- the future outcome the operator wants
- the evidence that outcome happened
- the specific future regret the skill should prevent

After drafting or patching the skill, run the retroactive realism check:

- Would a competent future agent following this `SKILL.md` realistically reach the expected outcome?
- Are trigger phrases, first progress marker, dependencies, stop conditions, and validation commands sufficient without hidden context?
- Does the edit prevent the named regret, or only describe it?

If the check fails, patch the skill again before validation or report the exact blocker.

## Mode Selection

Pick the branch before editing:

| Request shape | Branch | Default action | Verification |
|---------------|--------|----------------|--------------|
| "create a skill", "new skill", "skill template" | create/update | choose placement, initialize or patch the owning skill | `scripts/quick_validate.py <skill>` |
| "review this skill", "when did we last use it", "improve from past runs" | reliability review | use the configured transcript evidence backend first, run `review_skill_usage.py` as the local scanner, build evidence packets/opportunities, then patch one repeated failure family | regenerate packets/opportunities and validate |
| "$cass $skill-issue $lube", "rank improvements", "high leverage lube opportunities" | portfolio triage | self-heal named companion skill visibility if needed, then run `scripts/rank_skill_improvements.py` and create Beads for the top actionable cards | Beads exist and top cards map to owning skill files |
| "create/check/match/migrate overlay" | overlay mode | use `manage_overlays.py`, then print the overlay diagnostic block below | `manage_overlays.py match --cwd ... --json` |
| "I do not see skill X", "expected skill missing" | visibility miss | invoke SBP recalibration/activation instead of falling back to memory or repo artifacts | show the SBP command result |

For mixed requests, preserve roles: `cass` or the configured evidence backend
mines prior-session evidence, `skill-issue` owns skill changes, and `lube`
frames friction into durable unblockers. If a named companion skill is not
already visible in the current repo/session, run the Missing Skill Visibility
flow below before falling back or asking the operator to activate it manually.

## Do Not Use This For

- One-off prompts or workflows that are not meant to become reusable skills
- Generic repo maintenance with no skill artifact involved
- Pure prompt review when the target is the user rather than the skill contract

## Client Overlays

Client overlays customize skill creation for specific organizations or projects — naming conventions, required sections, publishing targets, testing workflows, and review processes. Managed through the skillbox client overlay system.

### How Client Overlays Work

Each client overlay lives in one of two roots:

- Repo-local, git-reviewable overlays: `.buildooor/skillbox-config/clients/{client}/overlay.yaml`
- Shared/private fallback overlays: `skillbox-config/clients/{client}/overlay.yaml`

Use the repo-local `.buildooor/` root when the overlay explains project trajectory, generated plans, validation contracts, or skillbox structure that should be reviewable in that repo's git history. Use the shared fallback root for operator-wide private defaults, cross-repo overlays, or material that must stay outside a public project. Overlays contain org-specific configuration: skill naming patterns, required SKILL.md sections, publishing targets, validation commands, standard bundled resources, and review/approval workflow.

### Overlay Selection (Step 0)

1. Check for available client overlays in `.buildooor/skillbox-config/clients/` and `skillbox-config/clients/`, walking upward from cwd
2. Each overlay has a `cwd_match` field — a path prefix to match against cwd
3. Prefer the most specific `cwd_match`; when specificity ties, prefer the closest repo-local `.buildooor/` overlay over shared fallback overlays
4. If cwd still matches multiple overlays at the same priority, ask the user which overlay to use
5. **If no overlay matches or none exist, ask before creating one.** Default to read-only diagnostics (`list`, `match`, `validate`) until the user confirms creation. Do not fall back to generic defaults.

### Overlay Miss → Create Flow

When no overlay matches the current working directory:

1. Tell the user: no matching client overlay found for `{cwd}` and ask whether to create one now
2. If the user approves, infer a `CLIENT_ID` from the cwd (repo name, project name, or ask)
3. Run the skillbox-quickstart scan + generate flow to create the overlay:

```bash
python3 ~/.claude/skills/skillbox-quickstart/scripts/scan_environment.py --json > /tmp/skillbox-scan.json
cat /tmp/skillbox-scan.json | python3 ~/.claude/skills/skillbox-quickstart/scripts/generate_overlay.py \
  --client-id {CLIENT_ID} --json > /tmp/skillbox-recommendation.json
```

4. Review the generated overlay with the user, then install it in the repo-local root unless the user explicitly wants a shared/private fallback overlay:

```bash
mkdir -p .buildooor/skillbox-config/clients/{CLIENT_ID}
cp /tmp/overlay.yaml .buildooor/skillbox-config/clients/{CLIENT_ID}/overlay.yaml
```

5. Re-run Step 0 — the new overlay should now match

If the user does not approve creation, keep the run read-only and report that overlay-backed execution is blocked until creation is authorized.

This keeps every skill invocation overlay-backed. Generic/manual fallbacks mask configuration gaps that compound across sessions.

Client overlays are managed outside reusable skill contracts. Repo-local overlays may be committed when sanitized and useful for project history; shared fallback overlays remain outside project repos for private/operator-wide defaults.

### Repo-Local Symlink Bridge

For existing projects, it is acceptable to create a transition symlink at
`.buildooor/skillbox-config/clients/{client}` that points to the current legacy
overlay directory. Prefer the closest existing overlay source:

1. If the repo already has `skillbox-config/clients/{client}/`, link to that
2. Otherwise link to the shared `~/repos/skillbox-config/clients/{client}/`

This gives tools the repo-local `.buildooor/` shape immediately. It does not
make overlay content reviewable in the project git history by itself; only the
symlink is tracked. When trajectory matters, sanitize and copy the overlay into
`.buildooor/skillbox-config/clients/{client}/overlay.yaml` as a real file.

## Skill Contract Placement

Before creating or moving a `SKILL.md`, choose the repository that owns the
contract:

- `opensource/skills` owns public, portable skill contracts and generic bundled
  resources that should work for other operators.
- `../../skills-private` (relative to repos under `opensource/`) owns reusable private skill contracts:
  operator-specific workflows, private business context, private repo maps,
  client names, internal prompts, non-public references, and skills that should
  not be prepared for public release yet.
- `.buildooor/skillbox-config/clients/<client>/` owns repo-local per-client
  overlays, generated context, publishing targets, validation commands, paths,
  and client-specific defaults that should be reviewable alongside the project.
  Keep secrets and machine-local values out of committed overlays.
- `skillbox-config/clients/<client>/` owns shared/private per-client overlays, generated
  context, publishing targets, validation commands, paths, secrets references,
  and client-specific defaults. It is not the home for reusable `SKILL.md`
  contracts.
- `skillbox` owns runtime delivery of skills: installation, sync, bundles,
  distribution, default skill curation, and operator tooling. Do not put the
  canonical skill contract there unless the skill is intentionally bundled as a
  runtime-local operator surface.

If a requested skill would leak private context in a public repo, create or
update it in `../../skills-private` first. Extract a public version into
`opensource/skills` only after sanitizing names, paths, examples, assets, and
references into a generic contract.

## Overlay Mode

Use this mode when the user wants to manage client overlays directly: "create an overlay", "list overlays", "check my overlays", "which overlay matches", "migrate overlays", or when another skill delegates overlay creation on a miss.

### Mode Detection

| User Says / Context | Action |
|---------------------|--------|
| "create an overlay", "add a client" | `create` |
| "list overlays", "show clients" | `list` |
| "check overlays", "validate overlays" | `validate` |
| "which overlay matches", "what client am I" | `match` |
| "migrate overlays", "update overlay format" | `migrate` |
| Another skill hits an overlay miss | `create` (ask-first; no auto-write) |

### Actions

#### create

Create a new client overlay. Two paths depending on context:

Before running either create path, ask for explicit confirmation to write `.buildooor/skillbox-config/clients/{CLIENT_ID}/overlay.yaml` unless an explicit `--config-root` is being used for a shared/private fallback overlay.

**Quick create** (minimal — when the miss is blocking another skill):

```bash
scripts/manage_overlays.py create --client-id {CLIENT_ID} --cwd {CWD} --json
```

This writes a minimal `overlay.yaml` with just the `cwd_match` set. Enough to unblock the calling skill. Enrich later.

**Full create** (scan-backed — when the user explicitly asks to set up an overlay):

```bash
python3 ~/.claude/skills/skillbox-quickstart/scripts/scan_environment.py --json > /tmp/skillbox-scan.json
cat /tmp/skillbox-scan.json | python3 ~/.claude/skills/skillbox-quickstart/scripts/generate_overlay.py \
  --client-id {CLIENT_ID} --output /tmp/overlay-draft
```

Review the draft with the user, then install:

```bash
mkdir -p .buildooor/skillbox-config/clients/{CLIENT_ID}
cp /tmp/overlay-draft/overlay.yaml .buildooor/skillbox-config/clients/{CLIENT_ID}/overlay.yaml
```

After either path, verify:

```bash
scripts/manage_overlays.py match --cwd {CWD} --json
```

When reporting overlay results, always include this diagnostic block so matching
does not get confused with write location:

```text
Overlay diagnostic
- matched overlay:
- repo-local .buildooor root:
- shared fallback root:
- actual write path:
```

If a command matched a broad shared overlay but wrote invocation artifacts to
`.claude/skills`, `.codex/skills`, or another non-overlay path, say both facts.
Overlay selection is not proof that outputs were written inside the overlay.

#### list

```bash
scripts/manage_overlays.py list --json
```

Shows all overlays, their `cwd_match` patterns, repo count, and version.

#### validate

```bash
scripts/manage_overlays.py validate --json
```

Checks structure, required fields, and path existence. Reports errors and warnings per overlay.

If the overlay declares wikis (a sibling `clients/{client}/wikis.yaml`), validate covers file-level structure only — it does NOT enforce cross-overlay wiki hierarchy reciprocity. That check belongs to the wiki skill. When editing an overlay that adds, removes, or reparents a wiki, follow up with `/wiki list` (renders the registered tree and flags any `parent:` declaration without a matching `children:` on the parent, or any `children:` entry without a matching `parent:` on the child). Hierarchical wikis (root → domain → product, or similar multi-tier shapes) require both sides of every parent/child edge to be declared in their respective per-client `wikis.yaml` overlays.

#### match

```bash
scripts/manage_overlays.py match --cwd {CWD} --json
```

Returns which overlay(s) match a given working directory. Exit 0 = match found, exit 1 = no match.

#### migrate

```bash
scripts/manage_overlays.py migrate --to-version {N} --json
```

Reports which overlays need migration. Does not auto-migrate — presents the list for the agent to handle per-overlay.

### Sibling Skill Delegation

When any skill hits an overlay miss, it should delegate to skill-issue's overlay mode rather than implementing its own creation flow. The contract:

1. Skill detects no overlay matches cwd
2. Skill tells the user: "No matching client overlay for `{cwd}`. Do you want me to create one?"
3. If the user confirms, skill runs the quick create path (or invokes skill-issue if available)
4. If the user does not confirm, skill stays in read-only mode and reports the block
5. If created, skill re-runs overlay selection — should now match

Skills that already stop on miss (deploy, ssh-info, dev-sanity) should add this ask-first create step before stopping.

### Missing Skill Visibility

If an agent says an expected skill is not active, not visible, not found, or
that it will fall back to repo artifacts, memory, or git history because a skill
is missing, route to SBP first. Do not replace the missing skill with an ad hoc
fallback unless SBP recalibration or activation fails.

```bash
sbp skill activate {skill} --cwd "$PWD" --dry-run
sbp skill activate {skill} --cwd "$PWD"
```

### Companion Skill Auto-Activation

When this skill's selected branch names a companion skill (`cass` or a
configured evidence backend for transcript evidence, `lube` for friction
closeout, `sbp` for visibility repair) or the user explicitly tags a companion
skill in the same request, treat a missing local skill link as self-healing
project setup.

1. Check visibility in the current repo:

```bash
sbp skills --issues-only --no-global --format json
```

2. If the companion skill is absent but known to SBP, run a project-local
activation. Review the dry-run for only local `.claude/skills` and
`.codex/skills` links to an existing source, then apply it:

```bash
sbp skill activate {skill} --cwd "$PWD" --dry-run
sbp skill activate {skill} --cwd "$PWD"
```

3. Use the returned activation packet or the linked `SKILL.md` in the same
turn. Do not make the operator run `sbp skills add {skill}` by hand.
4. Keep the repair local to the current repo. Do not perform broad global
installs, global prune, or unrelated fleet cleanup for a companion-skill miss.
5. If activation fails, report the exact command and error, then continue with
the narrowest safe fallback.

If SBP is unavailable, report that visibility calibration is blocked and keep
the fallback explicitly degraded.

## Core Principles

### Concise is Key

The context window is a public good. Only add context the agent doesn't already have. Challenge each piece: "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match specificity to the task's fragility:

- **High freedom (text instructions)**: Multiple valid approaches, context-dependent decisions
- **Medium freedom (pseudocode/parameterized scripts)**: Preferred pattern exists, some variation acceptable
- **Low freedom (specific scripts)**: Fragile operations, consistency critical, exact sequence required

### Skill Structure

Every skill has a required `SKILL.md` (YAML frontmatter + markdown body) and optional bundled resources (`scripts/`, `references/`, `assets/`).

Optional frontmatter field `depends_on:` (YAML list of skill ids) declares cross-skill contracts this skill relies on. The `scripts/check_skill_deps.py` helper reads this field when a skill changes to find dependents whose interface surfaces (commands, phase headers, file paths) may drift. Example:

```yaml
name: skill-issue
depends_on:
  - cass          # Step 1b delegates transcript mining
```

For directory structure details, resource types, progressive disclosure patterns, and what NOT to include, see [references/skill-structure.md](references/skill-structure.md).

### Coverage-Awareness Index (`SKILLS_COVERAGE.yaml`)

`~/.claude/skills/SKILLS_COVERAGE.yaml` is a single-operator coverage index
with one entry per skill id and a `status` of `present`, `absent`,
`excluded`, or `pending`. `generate_skill_portfolio_opportunities.py` reads
it at startup: `excluded` entries hard-zero any matching creation card, and
`absent` entries surface as tracked gaps in the report. Write `excluded`
when you decide against building a skill (include `reason` and `decided`)
so the miner stops re-proposing it. See the file header for the schema.

### Cross-Skill Contract Drift

When a platform or package contract changes, do not stop at the first `SKILL.md` you touch. Check for sibling skills that encode the old contract in:

- scanner scripts
- rubrics
- output templates
- examples and canned commands
- reference files that summarize package behavior

If the changed skill is part of a larger ecosystem, update the dependent skills in the same batch or call out the drift explicitly. Treat those files as one artifact, not separate chores.

### Soft Optimization Scores

When creating, updating, or reviewing a skill that depends on subjective
judgment, make the judgment optimizable. Define 3 to 7 soft dimensions, score
each from 0 to 1000, weight them, roll them into an overall score, and report
the loss that should be reduced next.

Use [references/soft-score-rubric.md](references/soft-score-rubric.md) as the
default review rubric. Keep two questions separate:

- `skill_quality_score`: how good the skill is as an executable agent workflow
- `optimization_readiness_score`: whether the skill itself contains a usable
  scoring/loss model for its subjective decisions

Do not let the number replace evidence. A score is useful only when dimensions,
anchors, weights, loss contributors, and decision effects are explicit enough
for the next agent to optimize against.

## Skill Creation Process

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, assets)
3. Initialize the skill (run init_skill.py)
4. Edit the skill (implement resources and write SKILL.md)
5. Validate and package the skill (run package_skill.py)
6. Iterate based on real usage
7. Publish to marketplaces (optional) — see `references/publishing.md`

Follow these steps in order, skipping only if clearly not applicable.

## Reliability Review Mode

Use this mode when the user wants to improve a skill from real transcript evidence instead of intuition: "review this skill", "how is this skill doing", "when did we last use this skill", "look at past invocations", or "reduce unnecessary checkpoints."

This mode reads from the configured transcript evidence surface first, then uses
local Claude/Codex JSONL scanning as a fallback or complement. It writes a
lightweight last-seen marker, builds operator evidence packets from repeated
transcript failures, and saves review snapshots for trend reporting.

Treat real user-triggered skill invocations as the experiment corpus. Do not fabricate synthetic reruns by default. Patch from live traces, ship once, then watch the next real invocation window.

### Transcript Evidence Backend

Prefer a configured evidence front door over hand-walking raw log stores. In
operator environments this may be `sbp cass`, `cass`, or another private
overlay-provided command that searches a central index derived from raw JSONL
archives. The public skill contract stays generic: it names the search behavior,
not any operator bucket, endpoint, machine path, access key, secret key, token,
or private env file.

Credential and storage rules:

- Public `SKILL.md` files must never include object-store bucket names,
  endpoints, account IDs, credential file paths, access keys, secret keys, API
  tokens, or private host paths.
- Private overlays, ignored env files, or runtime-specific wrappers own archive
  credentials and storage topology.
- `skill-issue` consumes transcript evidence through search commands and local
  scanner scripts. It does not upload to, restore from, or administer raw
  archive storage.
- Raw JSONL archives are source-of-truth storage. Cass or any other search
  database is a derived index and can be stale, rebuilt, or unavailable.
- If the configured evidence backend is unhealthy or unavailable, report the
  degraded mode and proceed with local transcript scanning when available.

Evidence backend probe pattern:

```bash
if command -v sbp >/dev/null 2>&1; then
  sbp cass status --json || true
elif command -v cass >/dev/null 2>&1; then
  cass status --json || true
fi
```

### Review Flow

1. Scan transcript history for a target skill with the local scanner:

```bash
scripts/review_skill_usage.py --skill skill-issue --source both --limit 50 > /tmp/skill-issue-review.json
```

By default, this resumes from `~/.claude/skill-markers/<skill>.json` using the previous review's `reviewed_until` timestamp. On the first run for a skill, it falls back to `--since month`. Pass an explicit `--since ...` to override, or `--since marker` to force marker-resume behavior.

This writes `~/.claude/skill-markers/<skill>.json` by default with the latest detected invocation date plus the review window cursor. Use `--no-marker` only when you explicitly need read-only behavior.

Optional, when you need deterministic raw tool tallies for evals, count the underlying tool calls directly:

```bash
scripts/count_tool_invocations.py --skill skill-issue --source both --since month
scripts/count_tool_invocations.py --source both --since week
```

This counts raw Codex `function_call` entries and Claude `tool_use` blocks, sorted by count then tool name.

1b. **Mine cross-session patterns via the configured evidence backend** (complements the transcript scan above):

Use `sbp cass` when it exists because it can route to a private, centralized
transcript index without exposing archive credentials in this public skill.
Otherwise use the `cass` skill directly. This surfaces signal the
single-transcript scanner misses, especially ritual detection, cross-project
usage, and prompt drift.

```bash
# If cass is not already visible and direct cass is needed, self-heal the repo-local link first.
sbp skill activate cass --cwd "$PWD" --dry-run
sbp skill activate cass --cwd "$PWD"

# Check the configured evidence backend health.
if command -v sbp >/dev/null 2>&1; then
  sbp cass status --json
elif command -v cass >/dev/null 2>&1; then
  cass status --json | jq '{healthy, fresh: .index.fresh, stale: .index.stale, db: .database.exists}'
else
  echo "No configured transcript evidence backend found; use local transcript scanner only." >&2
fi

evidence_search() {
  query="$1"
  limit="${2:-50}"
  fields="${3:-minimal}"
  if command -v sbp >/dev/null 2>&1; then
    sbp cass search --json --fields "$fields" --limit "$limit" "$query"
  elif command -v cass >/dev/null 2>&1; then
    cass search "$query" --json --fields "$fields" --limit "$limit"
  else
    return 127
  fi
}

# Find all sessions mentioning this skill (lexical, minimal output).
evidence_search "SKILL_NAME" 50 minimal

# Filter to user prompts (lines 1-3) for invocation pattern analysis
evidence_search "SKILL_NAME" 50 minimal | jq '[.hits[] | select(.line_number <= 3)]'

# Detect rituals: prompts repeated 10+ times = working methodology
evidence_search "SKILL_NAME" 100 minimal \
  | jq '[.hits[] | select(.line_number <= 3) | .title[0:80]] | group_by(.) | map({prompt: .[0], count: length}) | sort_by(-.count) | .[0:10]'

# Find correction signals near skill invocations
evidence_search "SKILL_NAME" 50 minimal \
  | jq '[.hits[] | select(.line_number > 3 and .line_number < 20)]'
# Then view hits with corrections ("no", "not that", "stop", "wrong").
```

**What to extract from evidence results:**
- **Ritual count** (>10 = working pattern): If users repeat the same prompt shape to invoke this skill, that's the real trigger — compare it against the skill's `description` field. Mismatch = discoverability gap.
- **Prompt drift**: If the same user rephrases their invocation across sessions, the skill's trigger conditions or docs may be unclear. Feed into `contract-clarity` evidence packets.
- **Cross-project spread**: Use backend-supported workspace aggregation when
  available to see which projects use this skill. Single-project usage may
  indicate the skill is too specialized for its current generality level.
- **Correction clusters**: Sessions where user prompts after invocation contain corrections feed directly into `correction_rate` and `contract-clarity` packet families.

If the configured evidence backend or Cass index is unhealthy or unavailable,
note it and proceed with transcript-only data. Do not block the review on Cass
availability.

2. Read the generated JSON and focus on reliability signals:
- `ack_rate`: how often the run included an explicit `Using <skill>` marker
- `validation_rate`: how often the run executed a concrete verification command
- `checkpoint_rate`: how often the agent asked for confirmation/checkpoint prompts
- `risk_gating_rate`: how often users explicitly signaled that the run should have paused for clarification, approval, or outside review before a risky step
- `correction_rate`: how often the user redirected the run after it started
- `completion_rate`: how often the transcript reached a clear completion event

2a. Score the target skill with the soft optimization rubric. This complements
transcript evidence; it does not replace it.

```bash
scripts/score_skill_contract.py <path/to/skill-folder> --json > /tmp/<skill>-soft-score.json
```

For catalog-wide audits, run:

```bash
scripts/score_skill_contract.py . --catalog --json > /tmp/skill-soft-score-catalog.json
```

Read [references/soft-score-rubric.md](references/soft-score-rubric.md) and
include a soft score block in the review:

```text
Soft score review
- skill_quality_score:
- optimization_readiness_score:
- review_score:
- review_loss:
- top_loss_contributors:
- scoring_concept_verdict:
- best_next_patch:
```

If `optimization_readiness_score < 600`, explicitly say that the skill lacks an
adequate scoring/loss concept even if the normal reliability metrics look good.
If the score is 600-799, name the missing dimensions, anchors, formula, loss
framing, or decision linkage that would move it above 800.
Treat catalog `exemptions` as reviewable exceptions, not skipped work: each
mechanical exemption must have a reason and validator in
`references/soft-score-exemptions.json`.

3. Build operator evidence packets before patching the skill:

```bash
scripts/generate_skill_evidence_packets.py --input /tmp/skill-issue-review.json --json > /tmp/skill-issue-packets.json
```

This turns repeated transcript failures into packetized review artifacts with:
- a failure family (`verification-gap`, `contract-clarity`, `checkpoint-defaults`, etc.)
- an expected contract
- representative traces
- a historical reference slice with holdout examples
- target files and a watch metric
- a post-ship observation window for future real invocations

Read [references/operator-evidence-loop.md](references/operator-evidence-loop.md) for the packet structure and graduation rules.

4. Use one packet to drive the next change instead of editing from vibes:
- Low `ack_rate` / `observability-gap`: require a stable first commentary marker so invocation discovery does not depend on path heuristics
- Low `validation_rate` / `verification-gap`: add or tighten the required verification block in the skill
- High `checkpoint_rate` / `checkpoint-defaults`: move repeated preferences into client overlays or default rules so humans are only asked when information is missing or risky
- High `risk_gating_rate` / `risk-gating-gap`: add explicit pause points for irreversible or high-risk branches so the skill asks first or routes to the right reviewer before proceeding
- High `correction_rate` / `contract-clarity`: tighten trigger language, non-goals, or ask-cascade guidance
- Repeated raw shell stems (`rg`, `sed`, `find`, etc.) / `automation-gap`: bundle scripts/references instead of relying on freehand shell work
- `invocation_miss`: user did manually what this skill covers but no trigger/ack/path signal fired — sharpen description and trigger phrases
- `trigger_mismatch`: `user_trigger` matched without `assistant_ack` — description is over-matching; narrow it or expand the skill body
- `output_rejected`: user correction with no `task_complete` — tighten non-goals and default output shape
- `output_corrected`: user correction after `task_complete` — fold the recurring correction into defaults or validation
- `wrong_skill_invoked`: user redirected to a different slash-command — add non-goals referencing the sibling skill and tighten the description

5. If you ship a packet-driven change, ask before writing to the packet ledger. If approved, log the shipment and expected watch window:

```bash
scripts/log_skill_packet_decision.py \
  --input /tmp/skill-issue-packets.json \
  --packet-id verification-gap-global \
  --review /tmp/skill-issue-review.json \
  --notes "tightened verification block in closeout"
```

This appends to `~/.claude/skill-packet-ledger.jsonl` with the packet id, expected contract,
watch metric baseline, and the next live observation window. The ledger is for shipped changes
against real traffic, not synthetic replay runs.

### Required Verification (Packet-Driven Updates)

Before handing back a packet-driven SKILL.md update, run all required checks:

1. Validate the edited skill:

```bash
scripts/quick_validate.py <path/to/skill-folder>
```

2. Regenerate evidence packets from the current review input and confirm packet generation still succeeds:

```bash
scripts/generate_skill_evidence_packets.py --input /tmp/<skill>-review.json --json > /tmp/<skill>-packets.verify.json
```

3. If ledger logging was explicitly approved, verify the packet id in `~/.claude/skill-packet-ledger.jsonl` matches the shipped change; otherwise state that logging was intentionally skipped.

Do not hand the run back until these checks are complete and passing.

6. Save the review for trend tracking:

```bash
scripts/save_skill_review.py --input /tmp/skill-issue-review.json
```

This appends to `~/.claude/skill-review-history.jsonl`.

7. Show the trend when history exists:

```bash
scripts/show_skill_trend.py --skill skill-issue --weeks 8
```

8. Mine deterministic opportunity cards from the post-invocation review:

```bash
scripts/generate_skill_opportunities.py --input /tmp/skill-issue-review.json
```

This ranks concrete improvement ideas such as verification gaps, over-checkpointing,
missing risk gates, contract-clarity problems, and automation gaps so `skill-issue`
can iterate on the highest-leverage changes first.

For broad improvement-backlog requests, run the one-shot wrapper instead of
manually stitching together the portfolio scan and per-skill reviews:

```bash
scripts/rank_skill_improvements.py --skills cass,skill-issue,lube --since month
```

Use `--full` when you need the underlying reports, or keep the default compact
ranked rows when the next step is Bead creation and a focused patch.

9. When the question is portfolio-level rather than "improve this one skill", run the catalog-wide miner:

```bash
scripts/generate_skill_portfolio_opportunities.py --source both --since month
```

Use this when you want to find:
- repeated manual workflows that should become new skills
- requests that look like an existing skill but are not activating it reliably
- overlapping skills that should likely collapse into one canonical skill plus client overlays or aliases

This is a cross-skill scan. It reads all top-level skills in the current skills root and all matching
Claude/Codex sessions in range, then ranks `skill-creation-opportunity`,
`skill-discoverability-gap`, and `skill-consolidation-opportunity` cards.

10. After enough new real invocations arrive, rerun the review and compare the watch metric to the
logged baseline:

- Prefer the next 5-20 real invocations of that skill, or a 1-2 week window for lower-volume skills
- Judge success from live post-ship behavior, not from synthetic reruns of canned prompts
- Only reach for fuller evals when the contract and historical reference slice have stabilized

Do not jump straight from aggregate rates to a patch. Build or read one operator evidence packet first, and do not treat synthetic reruns as the default source of truth.

### Evidence Rules

- Prefer `assistant_ack` and `skill_path` as strong invocation evidence.
- Treat raw user mentions as weak evidence unless paired with a path touch or explicit ack marker.
- If the review finds no Claude Code matches, say so clearly instead of implying cross-provider coverage.
- Optimize suggestions for one goal: remove human checkpoints except where human input is genuinely required.
- Treat interruption-like cues as weak evidence by themselves; prefer explicit user language like "wait", "ask first", "before sending", or "bring X in the loop" before labeling a missing risk gate.
- Prefer repeated trace clusters over a single memorable anecdote when deciding what to patch next.
- Treat evidence packets as the default bridge from review metrics to concrete edits; use full eval suites only when the contract and historical reference slice have stabilized.

### Step 1: Understand the Skill

Skip only when usage patterns are already clearly understood.

Gather concrete examples of how the skill will be used — from the user or by generating examples and validating with feedback. Ask about functionality scope, usage examples, and trigger phrases. Don't overwhelm with questions; start with the most important and follow up.

### Step 2: Plan Reusable Contents

**Choose a searchable name first.** Two searchable keywords, `[domain]-[action]` pattern, lowercase with hyphens. Test: "What would someone search for?" See `references/publishing.md` for detailed naming guidance.

Then analyze each example: consider how to execute from scratch, and identify what scripts, references, and assets would help when repeating these workflows.

Example: A `pdf-editor` skill for "Help me rotate this PDF" — rotating requires the same code each time → include `scripts/rotate_pdf.py`.

### Step 3: Initialize the Skill

Skip if the skill already exists and only needs iteration or packaging.

```bash
scripts/init_skill.py <skill-name> --path <output-directory> [--minimal]
```

Creates a template skill directory with SKILL.md, example `scripts/`, `references/`, and `assets/`. Use `--minimal` when you already know what you're building. Customize or remove generated example files as needed.

### Step 4: Edit the Skill

The skill is for another agent instance. Include non-obvious procedural knowledge, domain-specific details, and reusable assets.

#### Consult Design Pattern Guides

- **Multi-step processes**: Read references/workflows.md
- **Consistent output formats**: Read references/output-patterns.md
- **Complete example**: Read references/example-minimal-skill.md
- **Publishing**: Read references/publishing.md
- **Soft scoring / loss models**: Read references/soft-score-rubric.md

#### Add Optimization Scoring When Judgment Is Soft

When the skill asks agents to judge taste, quality, priority, elegance,
usefulness, robustness, risk, or other soft dimensions, include a compact
optimization score contract. It should name the objective, dimensions, scale
anchors, weights, formula, loss framing, decision effects, and anti-gaming
notes. Use [references/soft-score-rubric.md](references/soft-score-rubric.md)
as the default pattern.

Skip the scoring block only when the skill is purely mechanical and already has
a deterministic pass/fail validator. For mixed skills, add scoring only to the
judgment-heavy branch.

#### Sprite Variant Contract (Character Diversity + Compatibility)

When creating or updating sprite-generation skills, enforce this contract:

- Keep runtime naming/API contract fixed:
  - Files: `active.svg`, `drowsy.svg`, `sleeping.svg`, `deep_sleep.svg`
  - Field names: `active`, `drowsy`, `sleeping`, `deep_sleep`
- Keep directory convention fixed for the target runtime (project local): `.sprite-runtime/sprites/`
- Preserve state semantics:
  - `active`: awake/engaged
  - `drowsy`: transitional low-energy
  - `sleeping`: asleep
  - `deep_sleep`: deepest rest state
- Encourage visual diversity per repo/domain:
  - Distinct palettes tied to repo branding
  - Distinct silhouettes/accessories/motifs (not only recolors)
  - Keep readability at small sizes
  - If sibling repos share a base character, include a structural identity marker group (`<g id="backend-id">` / `<g id="frontend-id">`) in every state, not just palette shifts
- Make sprite SVGs self-contained when using logo/image wrappers:
  - Avoid external image refs like `<image href=\"/logo.png\">` or `./logo.png`
  - Prefer embedded data URIs so assets render when injected cross-origin/cross-app
- Do not break loaders to achieve style changes. Creativity is applied inside the fixed naming + state contract.

Quick validation before shipping:
```bash
for s in active drowsy sleeping deep_sleep; do
  test -f ".sprite-runtime/sprites/${s}.svg" || echo "missing ${s}.svg"
done

# Should output nothing for self-contained SVG packs
rg -n '<image[^>]+href="/' .sprite-runtime/sprites
rg -n '<image[^>]+href="./' .sprite-runtime/sprites

# Optional but required when differentiating sibling repos (for example frontend vs backend)
MARKER_ID="backend-id"
for s in active drowsy sleeping deep_sleep; do
  rg -q "<g id=\"${MARKER_ID}\"" ".sprite-runtime/sprites/${s}.svg" || echo "missing marker ${s}.svg"
done

# Marker must be in the primary body window (not a tiny corner stamp)
for s in active drowsy sleeping deep_sleep; do
  perl -0777 -e '
    my ($file,$id)=@ARGV;
    local $/; open my $fh, "<", $file or die $!;
    my $svg=<$fh>;
    $svg =~ m{<g id="\Q$id\E"[^>]*>(.*?)</g>}s or die "missing marker group\n";
    my $g=$1;
    my @x = ($g =~ /x="(\d+)"/g); my @y = ($g =~ /y="(\d+)"/g);
    die "marker has no coords\n" unless @x && @y;
    my ($minx,$maxx)=($x[0],$x[0]); for (@x){$minx=$_ if $_<$minx; $maxx=$_ if $_>$maxx;}
    my ($miny,$maxy)=($y[0],$y[0]); for (@y){$miny=$_ if $_<$miny; $maxy=$_ if $_>$maxy;}
    die "marker out of body window: $minx,$maxx,$miny,$maxy\n" if $minx < 160 || $maxx > 352 || $miny < 160 || $maxy > 368;
    my $motif_cells = () = $g =~ /class="m"/g;
    die "marker motif too subtle: $motif_cells\n" if $motif_cells < 6;
  ' ".sprite-runtime/sprites/${s}.svg" "${MARKER_ID}" || echo "marker-check-fail ${s}.svg"
done
```

#### Reliability Hardening Gate (Ops / Deploy Skills)

If the skill touches deployment, auth, env sync, or production debugging, include an explicit anti-footgun section before finalizing.

Required checks:
- Add a preflight checklist that catches stale GitHub secrets vs local env files.
- If a change introduces new credential scopes/headers/env vars, document whether rollout requires one deploy or a two-phase deploy.
- Add a concrete failure-signature map (`HTTP code + error code`) for auth failures, not just generic "unauthorized" language.
- If the skill contains shell scripts, ensure no-arg behavior prints usage cleanly (no `${1:?}` crash UX).
- Include at least one command-first verification path for behavior and one side-effect/state verification path.

Recommended shell-script sanity checks:
```bash
# Syntax
for f in <skill>/scripts/*.sh; do bash -n "$f"; done

# No-arg UX should return usage text and non-zero
for f in <skill>/scripts/*.sh; do "$f" >/tmp/out 2>/tmp/err || true; head -n1 /tmp/out /tmp/err; done
```

#### Open-Source Readiness (Privacy Gate)

Before committing or packaging any skill for public release, scrub ALL files (SKILL.md, scripts/, references/, assets/) for:

- **Personal info**: Names, emails, phone numbers, social handles (@handle)
- **Secrets**: API keys, tokens, passwords, connection strings — even in examples
- **Hardcoded paths**: `/Users/<name>/`, `/srv/<workspace>/`, `~/repos/<specific-project>`
- **Business names**: Company names, product names, internal project names, domain names (*.yourcompany.com)
- **Real IPs/hostnames**: Server IPs, internal DNS names, container names tied to deployments
- **Referral/affiliate links**: URLs with tracking parameters (`fpr=...`, `ref=...`, etc.)
- **Business intelligence**: Customer lists, personas, targeting criteria, pricing, competitor data

**Client overlays are safe when sanitized** — repo-local overlay history belongs in `.buildooor/skillbox-config/clients/` when it explains project trajectory. Private, machine-local, or cross-repo defaults belong in shared `skillbox-config/clients/` outside the project. Never commit secrets, real credentials, private host data, or machine-only absolute paths.

**Pattern**: Use `{placeholder}` syntax for values that vary per deployment. Scripts should accept CLI args or client overlay config instead of hardcoded defaults. Reference files should use generic examples ("auth service", "your-project") instead of real names.

**Quick check**: `grep -rE 'your-real-company|/Users/you|real-ip|@yourhandle' <skill-dir>/` before committing.

#### Open-Source Skill Architecture

Skills intended for public repos use a dual-layer pattern: **generic tracked
skill files + sanitized repo-local overlays + optional private fallback overlays**.
If the `SKILL.md` itself is private, keep it in `../../skills-private`; do not
force it into this public pattern until it has been sanitized into a portable
contract.

```
my-skill/                      ← public (git tracked)
├── SKILL.md                   ← generic instructions, {placeholder} variables
├── references/                ← generic patterns, workflows
├── scripts/                   ← generic utilities
└── assets/templates/          ← generic templates
    ├── default.md             ← tracked
    └── my-project.md          ← gitignored (project-specific template)

.buildooor/                    ← project-local, git tracked when sanitized
└── skillbox-config/clients/my-project/
    └── overlay.yaml           ← project trajectory, validation contracts, non-secret paths

skillbox-config/clients/my-project/  ← shared/private fallback outside project
└── overlay.yaml               ← secrets references, operator-wide defaults, machine-local paths
```

**The SKILL.md reads client overlay config at runtime** to fill in `{placeholder}` values:
- `{auth_packages_root}` → overlay provides `../auth-service/packages`
- `{plan_root}` → overlay provides `~/.claude/plans/my-project`
- `{backend_repo}` → overlay provides `~/repos/my-api`

Anyone cloning the public repo gets a working generic skill plus the sanitized repo-local operating contract. Private fallback overlays can still enrich the run without hiding project trajectory from git history.

#### Repo-Level .gitignore for Skill Collections

For repos containing multiple skills, the root `.gitignore` should cover:

```gitignore
# Python artifacts
__pycache__/
*.pyc

# Build artifacts
*.skill
*.zip
dist/

# Project-specific skills that should never be public
my-private-skill/

# Project-specific asset variants (template naming convention)
# Example: gitignore frontend-*.md but track frontend.md
my-skill/assets/templates/frontend-*.md
!my-skill/assets/templates/frontend.md
```

**Key patterns:**
- Use `skillname/` entries for entire skills that must stay private
- Use `!` exceptions to track generic templates while ignoring project-specific variants
- Private deployment data (instance configs, deployed IPs) should have dedicated gitignore entries
- Project-specific operating contracts live in `.buildooor/skillbox-config/clients/` when they are sanitized and worth tracking with the repo
- Private fallback config lives in shared skillbox client overlays, not in reusable skill contracts

#### Sanitization Workflow (Existing Repo → Public)

When preparing an existing skill repo for open source:

1. **Audit tracked files**: `git ls-files | xargs grep -lE 'project-name|internal-domain|api-key-name'`
2. **Extract project content → client overlays**: Move project-specific references from SKILL.md body into repo-local overlays (`.buildooor/skillbox-config/clients/{client}/overlay.yaml`) when sanitized history matters, or shared private overlays (`skillbox-config/clients/{client}/overlay.yaml`) when the data must stay outside the project. Replace with `{placeholder}` syntax referencing overlay config.
3. **Genericize examples**: Replace domain-specific slice names with generic ones ("task_assignments"). Replace internal service names with generic terms ("backend API"). Keep generic role names (operator, admin, user).
4. **Verify gitignore coverage**: Ensure project-specific templates and deployment data are excluded. Commit sanitized `.buildooor/` overlays only when they should be reviewable with the project; keep private fallback overlays out of the project repo.
5. **Final audit**: `git ls-files | xargs grep -lE 'project|company|internal'` — zero tolerance for the real names.
6. **Check git history**: If project names exist in past commits, consider `git filter-repo` or starting a clean history.

#### Handling API Keys and Secrets

Never hardcode API keys. Use `$ENV_VAR` references in curl/script templates and document the required variable.

Users should set keys in their shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export MY_API_KEY
```

**Known issue:** The `env` field in `~/.claude/settings.json` does not reliably expand variables in Bash tool commands. Shell profile exports work correctly.

In SKILL.md, document requirements like:

```markdown
## Prerequisites
Add to `~/.zshrc`: `export MY_API_KEY`
```

#### Local Development with Symlinks

Store skill source in a version-controlled repo, then symlink into each agent's skills directory (Claude + Codex) for discovery:

```bash
ln -s ~/repos/skills/my-skill ~/.claude/skills/my-skill
ln -s ~/repos/skills/my-skill ~/.codex/skills/my-skill
```

In this repo specifically, use `./scripts/link-skills.sh` to link all skills into both directories automatically.

The marketplace plugin version (if installed) takes precedence over local skills directories — use a different name to avoid conflicts.

#### Implement Resources First

Start with `scripts/`, `references/`, and `assets/` files identified in Step 2. This may require user input (e.g., brand assets, documentation). Test added scripts by running them. Delete unneeded example files from initialization.

#### Write SKILL.md

**Writing guidelines:** Use imperative/infinitive form.

**Frontmatter** (YAML):
- `name` (required): The skill name
- `description` (required): Primary triggering mechanism. Include what the skill does AND specific triggers/contexts. All "when to use" goes here — not in the body (which only loads after triggering).
  - Example for a `docx` skill: "Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. Use when working with .docx files for: creating, editing, tracked changes, comments, or any document task."
- `license`, `allowed-tools`, `metadata`: Optional

**Body** (Markdown): Instructions for using the skill and its bundled resources. Keep under 500 lines — split to reference files when approaching this limit.

### Step 5: Validate and Package

Validate during development:

```bash
scripts/quick_validate.py <path/to/skill-folder>
```

Packaging writes a distributable artifact. Ask for confirmation before running `package_skill.py`. If confirmation is not given, stop at validation and report the exact packaging command.

Package when complete:

```bash
scripts/package_skill.py <path/to/skill-folder> [output-directory]
```

Packaging validates automatically, then creates a `.skill` file (zip with .skill extension). Fix any validation errors and re-run.
When the skill lives in a Git worktree, packaging also excludes any paths ignored by Git (repo root or skill-local), so private overlays and other gitignored artifacts stay out of the bundle.

For ops/deploy skills, do an additional manual quality pass:
- Run every documented preflight command at least once.
- Run at least one intentional failure-path probe and verify the troubleshooting guidance matches the real error.

### Risk-Tiered Review Gate

Every proposed SKILL.md edit gets a risk tier before review. Classify with
`scripts/skill_risk_classifier.py --old <current> --new <proposed> --skill-id <id>`
(exit code: 0=low, 1=medium, 2=high). The classifier auto-bumps to `high` when
`scripts/check_skill_deps.py` reports cross-skill interface drift.

| Tier | What changed | Gate |
|------|--------------|------|
| **low** | Prose, examples, reference files | `quick_validate.py` must pass; low-risk edits may be applied without an explicit ask |
| **medium** | `description` field, phase/step ordering, script logic | LLM self-review + one human confirm before apply |
| **high** | `allowed-tools`, destructive commands (`rm -rf`, `sudo`, `git push`, etc.), safety rules, hooks config, or cross-skill interface drift | Mandatory human approval; never auto-apply |

Do not lower the tier to keep flow. If review capacity is saturated, pause
the proposal queue rather than relaxing the gate.

### Commit/Push Branch (Tier-Gated)

Treat an explicit current-run commit request as authorization to run `git add`
and `git commit` for the relevant scope. Examples include `commit`,
`/commit`, `checkpoint`, `save progress`, `commit it`, `commit everything`,
and `commit and continue`.

When commit authorization is present, do not ask again for commit approval and
do not warn about an unsolicited commit. Switch to the `commit` skill, classify
the dirty tree, scrub local-only or private artifacts, stage the intentional
batch, and commit it.

Only pause before committing when the staged set would include unrelated work,
credentials, private data, unresolved conflicts, or files whose intent cannot
be established from the current request and repo evidence.

Do not run tag, push, release, publishing, or PR creation commands unless the
user explicitly asks for that branch in the current run. Commit authorization
does not authorize those follow-on operations.

If commit is not authorized, finish with local edits plus verification output
and report the pending commit command instead of executing it.

### Step 6: Iterate

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Update SKILL.md or bundled resources
4. Test again

If you hit a production near-miss or rollback-causing mistake, treat the skill update as part of the fix:
1. Add the symptom/cause/fix to the skill's troubleshooting reference.
2. Add the prevention command/checklist to the main SKILL.md preflight section.
3. Re-run the updated checklist to prove it catches the original failure mode.

### Step 7: Publish (Optional)

Never publish by default. Ask for explicit approval before any repo creation, package upload, release creation, marketplace submission, or promotion action.

1. Create a public GitHub repo
2. Add a README.md (for humans, not Claude)
3. Add a `.zip` package: `zip -r skill-name.zip SKILL.md scripts/ references/`
4. Promote to drive downloads (downloads = ranking)

**Read `references/publishing.md`** for the complete checklist and promotion strategies.

## Environment Management

Beyond individual skills, skill-issue can audit your entire Claude environment.

### Audit

Scan `~/.claude/` and project directories, generate a context registry, and produce a health report:

```bash
scripts/audit_context.py                                 # Scan ~/repos, write to ~/.claude/context/
scripts/audit_context.py --scan-root ~/projects          # Custom scan root
scripts/audit_context.py --report-only                   # Print report without writing registry
scripts/audit_context.py --scan-root ~/repos --scan-root ~/work  # Multiple roots
```

The audit discovers: projects with `.claude/` config, CLAUDE.md files, MCP servers, project-level hooks and skills, global skills (symlinked, packaged, local), and client overlays.

Issues detected: secrets in MCP configs, broken skill symlinks, stale empty `.claude/` directories, duplicate MCP definitions across projects, client overlays targeting nonexistent paths, parent CLAUDE.md inheritance.

Registry output goes to `~/.claude/context/` with `manifest.yaml`, `projects/*.yaml`, `mcps/*.yaml`, and `machines/*.yaml`.

### Init

Bootstrap `~/.claude/context/` for a new machine or add a single project:

```bash
scripts/init_context.py                              # Interactive machine setup
scripts/init_context.py --non-interactive            # Accept all defaults
scripts/init_context.py --project ~/repos/my-app     # Add one project to existing registry
scripts/init_context.py --scan-root ~/projects       # Custom scan root
```

Full init walks through: machine name, scan roots, project discovery, and registry creation. Use `--project` to add a single project without re-scanning everything.

### Sync

Detect drift between the registry and filesystem:

```bash
scripts/sync_context.py                    # Check for drift (exit code 1 if drift found)
scripts/sync_context.py --check            # Same as above
scripts/sync_context.py --update           # Re-scan and update registry
```

Drift detection compares: project paths still exist, config files unchanged (by content hash), skills added/removed, hooks changed, MCP servers changed. Exit code 0 means no drift, 1 means drift detected.
