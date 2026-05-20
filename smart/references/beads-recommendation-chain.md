# Smart Beads Recommendation Chain

`smart` stores recommendation-chain and loop-state links as `br` issues in the
active git repo. This file is the `smart`-specific companion to the shared
contract in `~/.claude/skills/_shared/references/beads-contract.md`.

## Bootstrap

Run this after confirming the checkout is on `main`:

```bash
git branch --show-current
python3 ~/.claude/skills/_shared/scripts/br_helpers.py ensure
export BR_AGENT_NAME=smart BR_HARNESS="${BR_HARNESS:-claude-code}" BR_MODEL="${CLAUDE_MODEL:-${OPENAI_MODEL:-unknown}}"
```

If `git rev-parse --show-toplevel` fails, do not create `.beads/` in a parent
workspace directory. Answer without durable chain state and name the missing git
repo as the blocker.

## Issue Shape

Each `/smart` invocation creates or updates one smart-chain issue:

```bash
br create "{move headline}" \
  --slug smart-{YYYYMMDD}-{short-topic} \
  --type {task|research|decision} \
  --priority {0|1|2|3} \
  --labels chain:smart,loop:{loop_id},loop-status:{status},hardening:{yes|no} \
  --json
```

Use `type=decision` when the move is a recommendation only, `type=research`
when the loop is waiting on research, and `type=task` when the move initiates or
tracks implementation. Use `priority=0` for shipping blockers, `1` for the
normal highest-leverage move, `2` for important but non-blocking moves, and `3`
for low urgency.

`br create` accepts only the small creation surface. After creating the issue,
write the rich fields with `br update`:

```bash
br update {id} \
  --description "{move plus why_now}" \
  --design "$SMART_CHAIN_DESIGN" \
  --notes "$SMART_CHAIN_NOTES" \
  --acceptance-criteria "$SMART_CHAIN_SUCCESS_CRITERIA" \
  --json
```

## Field Mapping

Store the `/smart` closeout fields in stable places:

| `/smart` field | `br` field |
|---|---|
| `The move` | issue title and description |
| `Chain context` | notes: `chain_context:` |
| `repo_head`, `compared_to` | design: `repo_state:` |
| `modes_report`, `modes_takeaway` | notes: `modes:` |
| `Repo signals` | design: `repo_signals:` |
| `Integrity gap` | design: `integrity_gap:` |
| `CRAP status` | notes: `crap_status:` |
| `Hardening decision` | labels `hardening:yes|no` plus design |
| `Skill combo` | notes: `skill_combo:` |
| `First step` | notes: `first_step:` |
| `Loop goal` | design: `loop_goal:` |
| `Success criteria` | `--acceptance-criteria` |
| `Loop status` | label `loop-status:{status}` and issue status |
| `Question being resolved` | notes: `question:` |
| `Resolution route` | notes: `resolution_route:` |
| `Human ask justification` | notes: `human_ask_justification:` |
| `Resume condition` | notes: `resume_condition:` |
| `Completion gate` | label `completion:{state}` plus notes |
| `Reality check takeaway` | notes: `reality_check:` |

Keep notes compact but structured. Prefer YAML-like headings over prose blocks
so the next agent can skim with `br show`.

## Status Mapping

| `/smart` loop status | `br` action |
|---|---|
| `one-shot 1/1` | create, update, then `br close --reason "recommendation delivered"` |
| `completed` | `br close --reason "{completion proof}"` |
| `iteration N/M` | keep open; add/update `loop:{id}` and `loop-status:iteration-N-M` labels |
| `resolving-question-agentically` | keep open; notes name the route and evidence needed |
| `waiting-on-human` | `br update -s blocked --notes "resume_condition: ..."` |
| `waiting-on-research` | `br update -s blocked --notes "research route: ..."` |
| `blocked` | `br update -s blocked --notes "{blocker and resume_condition}"` |

Do not close an implementation-tracking smart issue until the completion gate
has passed. If validation is green but commit or reality-check is pending, keep
the issue open and label it `completion:pending` or `completion:commit-blocked`.

## Loading Prior Context

Use this sequence:

```bash
br list --label chain:smart --all --json
br show {latest-smart-id} --json
```

The latest issue is the highest-confidence chain link. Legacy markdown files,
harness memories, and scratch folders are drift evidence only unless they are
explicitly rendered from the current `br` state.

For active loop resumption, prefer open smart issues first:

```bash
br list --label chain:smart --status open --json
br list --label chain:smart --status blocked --json
```

If multiple open loop issues exist, choose the one whose `loop:{id}` or title
matches the user's current focus. If two issues tie and the next move is
genuinely ambiguous, route to `/wiki-duel` rather than guessing.

## Rendering Markdown Views

`SMART_RECOMMENDATION_CHAIN.md` and `SMART_GOAL_CHAIN.md` are optional generated
views. Render them only when requested or when a downstream human artifact still
expects markdown.

Every generated view starts with:

```markdown
> Generated from `br list --label chain:smart --all --json`.
> Do not edit by hand. Update `br` issues and regenerate.
```

Do not use rendered markdown to make the next `/smart` decision.
