# Beads (`br`) Cross-Skill Contract

This file is the single source of truth for how skills in this repo
(`divide-and-conquer`, `domain-planner`, `domain-reviewer`,
`domain-scaffolder`, `smart`) integrate with
[beads_rust](https://github.com/Dicklesworthstone/beads_rust) — `br`, the
local-first, agent-first issue tracker.

When a skill needs to model "the work the swarm/loop is doing," the work lives
in `br` issues. Markdown artifacts (`WORKGRAPH.md`, `SMART_RECOMMENDATION_CHAIN.md`,
audit reports) become **rendered views** of `br` state, not the source of truth.

## Install + Bootstrap

```bash
# One-time install
curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/beads_rust/main/install.sh?$(date +%s)" | bash

# Per-repo, one-time
br init                                 # creates .beads/ at repo root
br agents --add --force                 # idempotent: drops/updates AGENTS.md instructions

# Verify
br --version && br where
```

The `.beads/` directory is committed to git. SQLite + JSONL coexist; commit
the JSONL (`.beads/issues.jsonl`) and the policy (`.beads/policy.yaml`).
Do not commit `.beads/*.db` (binary) or `.beads/.br_recovery/`.

Recommended `.gitignore` lines:

```
.beads/*.db
.beads/*.db-shm
.beads/*.db-wal
.beads/.br_recovery/
```

## Tier-1 Attribution (Required for Swarms)

Every agent invocation that mutates `br` state MUST stamp who did it. Skills
should set these env vars on entry and pass them through to spawned panes:

```bash
export BR_AGENT_NAME="<skill-name>"          # e.g. divide-and-conquer, domain-scaffolder
export BR_HARNESS="claude-code"              # or codex, ntm, etc.
export BR_MODEL="claude-fable-high"             # actual model handling the call
export BR_ACTOR="${USER:-agent}"             # for `--actor`
```

`divide-and-conquer` workers prepend these via the node prompt. `domain-*`
skills set them when entering each mode.

## Naming Convention

`br` derives the workspace prefix from the repo directory at `br init` time
(e.g. `htma`, `recipe-ios`). Issue IDs are `{prefix}-{slug}-{hash}`. The
examples below show `{prefix}` — your real prefix is whatever `br where`
prints under `prefix:`.

| Surface | Convention | Example |
|---|---|---|
| Slice (multi-node delivery) | `--type epic --slug {slice-name}` | `{prefix}-epic-key-insights-7f3a` |
| Subgoal controller | `--type task --labels slice:{slice},subgoal:{slug},subgoal-role:controller` | `{prefix}-subgoal-auth-hardening-4e71` |
| Execution node | `--slug exec-{NNN}-{kebab-title}` `--parent {epic-id}` | `{prefix}-exec-001-backend-api-9c2e` |
| Audit finding | `--type bug --parent {node-id}` `--labels finding:{kind}` | `{prefix}-finding-permissions-mismatch-1a4b` |
| Smart recommendation | `--type task --labels chain:smart` | `{prefix}-smart-2026-05-10-d8e1` |

Use `--labels` consistently:

- `concern:{slug}` — the node's concern (backend-api, frontend-widget, etc.)
- `repo:{slug}` — repo the node owns
- `wave:{n}` — which execution wave the node belongs to
- `risk:{none|human|external}` — risk gate
- `slice:{name}` — slice tag for cross-cutting queries
- `subgoal:{name}` — non-blocking delegation scope inside a slice
- `subgoal-role:{controller|leaf}` — whether the issue is the durable
  subgoal controller or normal executable work inside that subgoal
- `subgoal-depth:{n}` — child-orchestrator depth; default is `1`
- `plan:{slug}`, `plan-role:{…}`, `plan-state:{…}`, `plan-evidence:{…}` —
  the accepted `no-ragrets` planning vocabulary; see
  [Accepted Plan Vocabulary](#accepted-plan-vocabulary-no-ragrets--divide-and-conquer)

Subgoal labels are grouping and delegation metadata, not dependency edges.
Every subgoal controller and leaf must also keep the root `slice:{name}` label
so the root orchestrator can query, validate, and close the whole slice without
reconstructing state from NTM sessions or markdown artifacts.

## Accepted Plan Vocabulary (`no-ragrets` → `divide-and-conquer`)

`no-ragrets` owns recursive executive planning and produces a Beads graph;
`divide-and-conquer` owns execution and **consumes** that graph. This section is
the single canonical definition of the interface between them. The producer
stamps these labels and notes scalars; the consumer reads them and never
remints, flattens, or relabels the accepted plan.

| Label | Applies to | Values |
|---|---|---|
| `plan:{root-slug}` | every node in the plan, including the root | one slug per plan |
| `plan-role:{role}` | every node, exactly one | `root`, `branch`, `execution-leaf`, `integration`, `review`, `historical-evidence` |
| `plan-state:{state}` | the root only | `draft`, `synthesized`, `handoff-ready` |
| `plan-evidence:{kind}` | provenance nodes | `historical-only` |

Notes scalars on every plan node:

```text
planning_parent: {bead-id|none}
supports: {comma-separated SC-* and PC-* IDs}
local_criteria: {comma-separated PC-* IDs|none}
produces: {named artifact or proof}
```

The root additionally carries `synthesis_receipt:`, `plan_score:`, and
`hard_gate_result:`.

Role semantics are a hard contract, not documentation:

- **Dispatchable roles** are exactly `plan-role:execution-leaf`,
  `plan-role:integration`, and `plan-role:review`. Only these may enter an
  executable ready frontier.
- **Grouping roles** are `plan-role:root` and `plan-role:branch`. They carry the
  outcome contract and criterion coverage and must never be dispatched, even
  when `br ready` returns them. A ready grouping node is a graph defect to
  repair, not work to hand a worker.
- **`plan-role:historical-evidence`** (and any node labeled
  `plan-evidence:historical-only`) is read-only provenance. It never dispatches
  and never counts toward criterion coverage — a criterion supported only by
  historical evidence still reads as uncovered.
- A node with no `plan-role:*` label, or with more than one, is rejected. The
  ambiguity is repaired in the graph, not guessed at by the consumer.

`plan-state:handoff-ready` is the execution gate. `no-ragrets` sets it only
after proving grouping nodes cannot be dispatched and every ready execution node
is hydrated. A consumer must refuse to dispatch a `draft` or `synthesized` plan.

Consume an accepted plan through the helper rather than raw `br ready`:

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py \
  ready --plan {root-slug} --require-handoff-ready
```

It preserves `br`'s dependency readiness (the frontier still comes from
`br ready`), then applies OR-semantics role filtering in helper code because
`br`'s multi-label behavior is not proven to be AND across versions. Verified
live: `br ready --json` rows can omit `labels` and `notes` entirely, so rows are
re-hydrated through `br show` before any label check — filtering the raw row
drops the whole frontier and reads as "nothing to do." It exits `0` only when
the plan is admissible and `2` otherwise, and emits:

| Key | Meaning |
|---|---|
| `root`, `plan_state`, `handoff_ready` | the single accepted root and its gate state |
| `admitted` | hydrated, concurrently-safe dispatch contracts |
| `deferred` | admissible nodes held back by a write-scope collision |
| `serialization_edges` | the `br dep add` ordering each collision requires |
| `excluded_historical` | provenance nodes that were skipped, not rejected |
| `rejected` | `{id, reason, detail, repair}` per defect |
| `coverage` | `declared` / `covered` / `uncovered` / `by_criterion`, historical excluded |
| `ok` | true only when there are no rejections |

Rejection reasons are stable identifiers: `plan_root_missing`,
`plan_root_duplicate`, `plan_state_not_handoff_ready`, `plan_role_missing`,
`plan_role_ambiguous`, `plan_role_not_dispatchable`, `plan_role_unknown`,
`concern_label_missing`, `hydration_incomplete`, `hydration_failed`,
`run_dir_placeholder`, `expected_assignee_placeholder`, `plan_query_failed`,
`plan_frontier_query_failed`. Every one carries a `repair` string the consumer
can run in place.

An accepted plan is written before any swarm exists, so `run_dir` and
`expected_assignee` are always hydrated at admission time. Template stand-ins
(`<absolute-run-dir>`, `TBD`, `none`, `worker-id`, `${VAR}`, relative paths) are
rejected rather than dispatched.

Plan roles and subgoal roles are different axes. `plan-role:branch` is a
*recursive planning* grouping node produced by `no-ragrets`;
`subgoal-role:controller` is a *divide-and-conquer execution* delegation
boundary. A branch is never a controller, and admission never converts one into
the other.

## Lifecycle Mapping

| Lifecycle event | Command |
|---|---|
| Plan node accepted | `br q --slug … --type task --parent {epic} --priority 1 --labels … --silent` |
| Add a dependency | `br dep add {child} {parent}` |
| Node assigned or worker starts the node | `br update {id} --claim` (atomic: assignee + in_progress) |
| Worker reports `blocked` | `br update {id} -s blocked --notes "{reason}"` |
| Worker reports done | `br close {id} --reason "{summary}" --suggest-next --robot` |
| Wave complete (advance) | `br ready --json` (plain) or `br scheduler --robot` (ranked) |
| Slice retire | `br epic close-eligible --robot` |
| Final flush before commit | `br sync --flush-only` |

`br update --claim` is the canonical start signal because it is atomic — no
race between two panes claiming the same node. Skills MUST use it instead of
`br update -s in_progress`. For externally orchestrated swarms, the
orchestrator may and often should claim on behalf of the assigned worker before
dispatch, then verify `br show {id}` reports `status=in_progress` and the
expected assignee before edits begin.

`br close --suggest-next` returns the newly unblocked frontier in the same
call; the orchestrator should consume that envelope and dispatch the next
wave without re-querying.

## Commit Policy

`.beads/issues.jsonl` is committed. Skills run `br sync --flush-only` before
the final integration commit so the JSONL reflects the SQLite state. The
JSONL is git-mergeable: concurrent panes in a swarm produce diff-friendly
appends, not conflicts, when each pane stamps its own actor and uses
distinct issue IDs.

Do NOT auto-commit `.beads/` updates inside node workers — only the final
integration/review wave commits. Workers run `br` mutations against the
shared `.beads/` directory but defer the commit to integration.

## Execution-Pack Field Mapping

For Beads-backed orchestration, the executable worker contract lives in the
issue fields and comments. Markdown execution packs are generated views or
evidence attachments only.

| Execution-pack field | Canonical Beads location |
|---|---|
| Original ask / node ask | `description` |
| Repo path, branch/HEAD, run dir | `notes` scalar lines such as `repo_path:`, `branch:`, `run_dir:` |
| Node id/title/status/assignee | issue `id`, `title`, `status`, `assignee` |
| Concern/repo/risk/model/wave/slice | labels such as `concern:*`, `repo:*`, `risk:*`, `model:*`, `wave:*`, `slice:*` plus `notes: model_route:` when a human-readable route is needed |
| Dependencies / ready frontier | `br dep add`, `br ready`, `br scheduler` |
| Writes / ownership boundaries | `design` block headed `writes:` |
| Stop rules and non-goals | `design` blocks headed `stop_rules:` and `non_goals:` |
| Global constraints | `design` block headed `global_constraints:` |
| Done-when / acceptance | `acceptance_criteria` |
| Validation commands | `notes` block headed `validate:` |
| Expected worker attribution | `notes: expected_assignee:` plus `br update --claim` proof |
| Dispatch prompt | rendered from `br_helpers.py render-node-brief <id>` |
| Worker proof / validation output | comments or `WG-*_RESULT.md` evidence attachment referenced from comments |
| Final integration proof | comments, close reason, and optional `DAC_FINAL_RESULT.md` evidence attachment |

### Subgoal Controller Field Mapping

A subgoal controller is a Beads issue that lets a root orchestrator delegate a
filtered ready frontier without making runtime pane state authoritative.
Controller issues are normal `br` issues with the labels above plus the
following fields, and are minted with
`br_helpers.py mint-subgoal {slug} '{title}' --slice {slice}`:

| Controller field | Canonical Beads location |
|---|---|
| Subgoal id | `notes: subgoal_id:` matching `subgoal:{slug}` |
| Parent/root slice | root `slice:{slug}` label and `notes: parent_slice:` when useful |
| Parent invocation run dir | `notes: parent_run_dir:` |
| Subgoal run dir | `notes: subgoal_run_dir:`; usually under `<parent-run-dir>/subgoals/<slug>` |
| Frontier filter | `notes: frontier_filter:` such as `slice:{root},subgoal:{slug}` |
| Child orchestrator identity | `notes: child_orchestrator:` when delegated; blank in multiplexed mode |
| NTM project/session | `notes: ntm_project:` after launch |
| Worker budget | `notes: max_workers:` for this subgoal |
| Recursion/depth cap | `notes: max_subgoal_depth:` when overriding the default depth of `1` |
| Isolation mode | `notes: isolation:` such as `checkout` or `worktree` |
| Status artifact | `notes: status_artifact:` pointing at `SUBGOAL_RESULT.md` |
| Subgoal write scope | `design` block headed `writes:`; outer bound for every leaf in the subgoal |
| Root-owned shared files | `design` block headed `shared_files:`; never child-owned |
| Stop rules and escalation | `design` blocks headed `stop_rules:` and `escalation:` |

Leaf issues inside a subgoal remain normal execution nodes. They add
`subgoal:{slug}` and `subgoal-role:leaf` labels, keep the root `slice:{root}`
label, and still carry concrete `writes`, `done_when`, `validate`, model route,
run directory, and expected assignee fields.

Before any implementation relies on filtered subgoal frontiers, prove the live
`br ready --label A --label B` behavior is AND semantics or apply helper-side
AND filtering after a broader query. If the installed `br` ORs labels or the
behavior is ambiguous, fail closed and do not launch subgoal cohorts.

Before dispatch, `br_helpers.py hydrate-node <id>` should return the fields
needed to render a worker brief. If rich fields are missing, update the Bead
with `br_helpers.py update-node` or `br update`; do not patch the missing
context into `EXECUTION_CONTEXT.md`.

## Legacy Field Mapping (WORKGRAPH.md → br)

| Workgraph field | `br` flag/field |
|---|---|
| `id` | issue ID (auto from `--slug`) |
| `title` | positional title or `--title` |
| `concern` | `--labels concern:{slug}` |
| `repo` | `--labels repo:{slug}` |
| `depends_on` | `br dep add` after creation, or `--deps blocks:id1,blocks:id2` at create |
| `writes` (paths) | `--design "writes:\n  - …"` |
| `done_when` | `--acceptance-criteria` (multiline accepted) |
| `validate_cmds` | `--notes "validate:\n  - …"` |
| `risk_gate` | `--labels risk:{none\|human\|external}` |
| `status` (`todo`) | open (default) |
| `status` (`in_progress`) | `--claim` |
| `status` (`done`) | `br close` |
| `status` (`blocked`) | `br update -s blocked` |
| `status` (`skipped`) | `br close --reason "skipped: {why}"` |

## Required Verification (Skill Authors)

When a skill that declares `requires_beads: true` runs in a repo:

1. `br --version` succeeds (binary on PATH)
2. `br where` reports a `.beads/` directory; if not, run `br init` (and `br agents --add --force`)
3. `br doctor --robot` is clean (or report drift to the user)
4. The skill stamps `BR_AGENT_NAME`/`BR_HARNESS`/`BR_MODEL` before any mutating call
5. Commits include `.beads/issues.jsonl` and `.beads/policy.yaml` only — not `.db` files

`scripts/br_helpers.py` (in this `_shared/scripts/` bundle) wraps all of the
above. Skills should call it rather than re-implementing.

Filtered installs that include a skill depending on these helpers must ship the
sibling `_shared/` bundle with that skill root. Domain-planner helper resolution
checks `<skills-root>/_shared/scripts` first and falls back to
`~/.claude/skills/_shared/scripts`; if neither exists, it reports both expected
locations and the install requirement.

## Related

- Upstream: <https://github.com/Dicklesworthstone/beads_rust>
- Schema introspection: `br schema all --json` (treat as unstable per upstream warning)
- AGENTS.md template: `br agents --check` shows what the upstream installer would write
