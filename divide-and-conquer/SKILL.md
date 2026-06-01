---
name: divide-and-conquer
description: Decompose complex work into a Beads-backed execution graph with generated `WORKGRAPH.md` views, then run an NTM-style swarm by ready frontier with no write overlap. Use before parallel execution for large-ish, UI-facing, multi-file, multi-domain, naturally parallel, naturally orchestrated, subgoal-oriented, or review-sensitive tasks.
license: MIT
metadata:
  requires_beads: true
---

# Divide and Conquer

Decompose a task into a `br` epic with child issues, then execute that graph
through an NTM-managed swarm. Autonomous: analyze -> load or mint the epic
in `br` -> write/tighten the full node contract in Beads -> spawn a wave swarm
using `br ready`/`br scheduler` -> dispatch Beads-rendered node briefs (each
carrying a `br` issue ID) -> monitor -> collect evidence attachments ->
reconcile `br` state -> advance waves -> run final integration review
(close-eligible epic, flush JSONL) -> commit `.beads/issues.jsonl` with the
slice changes -> report. Markdown files are generated views or evidence
attachments only. No approval gates.

For massive runs, this skill can add a subgoal tier between the root slice and
leaf execution nodes. A subgoal is a Beads-backed delegation boundary over a
filtered ready frontier, represented by a durable subgoal controller issue plus
`slice:{root}` and `subgoal:{slug}` labels. Use subgoals when a single
orchestrator would otherwise serialize independent frontiers or fill its
context tending one child process at a time.

## Default Marker

Start with a stable first progress message such as:

`Using \`divide-and-conquer\` to build the ready frontier, spawn an execution swarm, and hand the workgraph off wave by wave.`

Shared cross-skill rules live in
[references/orchestration-contract.md](references/orchestration-contract.md).
Use that file for worker ownership, background-task collection, and detached
handoff semantics.

Before building the graph or spawning a swarm, apply the `no-ragrets`
Edge-Capture Contract: name the nearest valuable artifact or decision, name the
proof that would show it improved, gather enough evidence to move confidently
in source order, and justify the coordination cost of each worker wave. Bias
toward useful agent coverage for non-trivial work; do not shrink the graph just
to save tokens. If the artifact or proof is unclear but the initiative is still
promising, route the uncertainty through `wiki-duel`, `dueling-idea-wizards`,
`describe`, or a small discovery wave instead of stopping for human
solidification.

Beads node synthesis and describe-style node contract guidance live in
[references/workgraph-synthesis.md](references/workgraph-synthesis.md).
Subgoal synthesis and split patterns live in the same reference set; the shared
definition and label grammar live in
[`_shared/references/orchestration-contract.md`](../_shared/references/orchestration-contract.md)
and [`_shared/references/beads-contract.md`](../_shared/references/beads-contract.md).

## Beads Is the Source of Truth

Every divide-and-conquer run uses [beads_rust (`br`)](https://github.com/Dicklesworthstone/beads_rust)
as the canonical store for nodes, dependencies, status, and the ready frontier.
`WORKGRAPH.md` is now a **rendered view** of `br` state, not the authoritative
artifact. Cross-skill conventions (naming, labels, lifecycle, attribution env
vars, commit policy) live in
[`_shared/references/beads-contract.md`](../_shared/references/beads-contract.md).

Bootstrap on entry (idempotent):

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py ensure
export BR_AGENT_NAME=divide-and-conquer BR_HARNESS=claude-code BR_MODEL="$CLAUDE_MODEL"
```

Use the helper rather than raw `br` calls so attribution and JSON envelopes are
consistent across panes. The helper exposes: `ensure`, `status`, `ready`,
`scheduler`, `mint-node`, `update-node`, `hydrate-node`, `render-node-brief`,
`claim`, `block`, `done`, `render-workgraph`, `flush`.

After minting the graph, immediately run `br ready --json` or the helper
equivalent and verify that intended first-wave child nodes are actually ready.
Some `br` versions model `--parent` as a dependency edge, which can make child
issues appear blocked by the open epic. If that happens, do not dispatch from a
stale mental model. Use labels/external refs for epic grouping, remove or avoid
the blocking parent-child edge for actionable nodes, or use a scheduler mode
that explicitly understands non-blocking hierarchy before spawning workers.

This skill now defaults to an external NTM swarm for execution. Do not fall
back to ad hoc local subagents or `/codex:rescue` as the primary path unless
the user explicitly asks to bypass the swarm. If `ntm` is unavailable, stop and
surface the missing prerequisite instead of silently degrading.

Because execution is swarm/NTM-coordinated, `vibing-with-ntm` is mandatory for
every divide-and-conquer run. Activate it through `sbp` when needed, then follow
its operator, reservation, transport, and review-loop guidance.

Before any `ntm spawn`, prove the NTM project name resolves to the repo you
intend to edit. NTM derives pane working directories from
`projects_base/session_name`; a wave name that does not map to the target repo
can launch workers in a sibling or empty checkout. This root preflight belongs
to `divide-and-conquer` because it is an execution-safety gate, not a live
operator-tending concern. See [NTM Project Root Preflight](#ntm-project-root-preflight).

Use this skill for large-ish, UI-facing, multi-file, naturally parallel, or
review-sensitive tasks even when the user did not explicitly ask for a swarm.
Cheap cwd/workflow routing, worker-request cleanup, and read-only
clerk/preflight sidecars should use Grok through the shared Grok CLI routing
lanes in `../_shared/references/orchestration-contract.md` when available:
`voice-to-text` dispatcher first, Swimmers hidden Grok session when a maintained
sidecar is useful, and direct headless Grok only for bounded one-shots. NTM does
not currently provide a `--grok` spawn flag, so Grok is a sidecar route rather
than an NTM pane class. Design-related execution nodes must run on Claude Opus;
non-design execution nodes must run on Codex unless the user explicitly
overrides the routing. Require a final fresh-eyes reviewer pass before
completion.

## Model Routing Is Mandatory

Route every ready node before spawning workers:

- **Grok dispatcher or sidecar for routing/preflight.** The `voice-to-text`
  dispatcher is the preferred cheap router for cwd selection, skill-tag
  extraction, request cleanup, broad evidence bucketing, and other read-only
  clerk work. When the node needs a maintained Grok session, use the Swimmers
  hidden-session lane with `spawn_tool: "grok"`; for a bounded one-shot, use
  direct headless Grok with a prompt file. Record `Model route: Grok dispatcher`
  for pure routing/preflight and `Model route: Grok CLI sidecar` for a
  Grok-authored read-only evidence artifact. Do not pass `--grok` to
  `ntm spawn`; current NTM Grok participation is sidecar-only. Do not treat a
  Grok dispatcher result as authority to bypass Beads hydration, ownership,
  validation, or the final review gate. For task-selection heuristics and CASS
  query examples, see
  [references/grok-sidecar-selection.md](references/grok-sidecar-selection.md).
- **Claude Opus only for design-related work.** Treat a node as design-related
  when it touches UI/UX, visual design, design systems, frontend screen or
  component layout, CSS/tokens, responsive behavior, screenshots, visual
  parity, product interaction copy, or fresh-eyes review of those surfaces.
  Dispatch these nodes to `--cc=N:opus`. If Opus is unavailable, stop and
  report the routing blocker instead of assigning the node to Codex.
- **Codex for everything else.** Backend, API, data, tests, docs, scripts,
  refactors, validation, ops, and integration nodes default to Codex with
  `gpt-5.5`: `--cod=N:gpt-5.5`.
- Ambiguous nodes are design-related if visual/product interaction quality is a
  material acceptance criterion. Split mixed nodes before launch when the model
  routing would otherwise be unclear.
- Record the selected route in the Beads dispatch contract and worker prompt:
  `Model route: Grok dispatcher`, `Model route: Grok CLI sidecar`,
  `Model route: Claude Opus`, or `Model route: Codex gpt-5.5`.

## Related Skills

- [[skill-issue]]
- `no-ragrets` for the Edge-Capture Contract before broad work, reusable workflow
  changes, or worker-wave execution
- `ntm` for command reference, session inspection, and swarm debugging
- `vibing-with-ntm` for swarm orchestration patterns, pane hygiene, and
  transport-layer recovery when the problem is NTM rather than the workgraph
- `codex-tmux` only when the user explicitly wants a detached single-worker
  fallback instead of an NTM swarm
- `modes-of-reasoning-project-analysis` and `dueling-idea-wizards` as sibling
  swarm-heavy skills with stronger NTM operator patterns worth borrowing

## Artifact Storage

Execution artifacts belong alongside the active client overlay in
`skillbox-config`, not in the repo root and not in `/tmp`.

Repo hygiene is a hard requirement. New divide-and-conquer waves MUST NOT write
or ask workers to write `WORKGRAPH.md`, `EXECUTION_CONTEXT.md`,
`WG-*_RESULT.md`, `DAC_FINAL_RESULT.md`, `.dac/`, or `.ntm/` inside the product
repo unless the user explicitly asks for a repo-local proof artifact. Product
repos should receive product changes and intentional `.beads/issues.jsonl`
updates only.

Resolve client context with the shared helper first:

```bash
python3 ~/.claude/skills/_shared/scripts/resolve_context.py "$PWD" --format json
```

Then resolve the invocation artifact root using this order:

1. `workflow_builder.invocation_root` from the resolved context
2. `client_dir + /invocations` when `client_dir` is present
3. Stop and surface the missing overlay/artifact-root prerequisite

Treat relative roots as relative to `client_dir`. If the resolver returns
absolute paths, use them directly.

Create one run directory per execution:

```text
{invocation_root}/{repo_slug}/divide-and-conquer/{run_id}/
```

Where:
- `repo_slug` = matched repo id from the overlay when available, otherwise the
  basename of the working repo
- `run_id` = timestamped execution id such as `2026-04-09T16-22-31Z`

Store these optional/generated artifacts in the run directory:
- `EPIC_ID.txt` — the `br` epic ID for this run; sole pointer back to the source-of-truth state in `.beads/`
- `WORKGRAPH.md` — generated view (regenerate with `br_helpers.py render-workgraph --epic {id} --out <absolute-run-dir>/WORKGRAPH.md`); never edit by hand
- `EXECUTION_CONTEXT.md` — optional generated dispatch summary rendered from Beads; never the authoritative worker contract
- `WG-*_RESULT.md` — per-node worker evidence attachments (changed files, validation output, blockers); status and contract remain in `br`
- `DAC_FINAL_RESULT.md` — final integration evidence summary
- any copied monitor notes or wave summaries

If the slice already has a `br` epic with open children, treat that epic as the
durable graph: list its children with `br_helpers.py ready --label slice:{name}`
and skip re-minting nodes. Always create a fresh invocation run directory for
this execution's artifacts and write `EPIC_ID.txt` pointing at the reused
epic.

Live pane state, transcript tails, attention-feed output, restarts, rate-limit
status, queue-dry checks, and swarm tending notes belong to `vibing-with-ntm`
and the NTM runtime. Export only the concise evidence needed for reconciliation
into this run directory. Do not mirror the full NTM session into the product
repo.

## Modes

Modes customize decomposition for specific projects: split boundaries, swarm
sizing heuristics, naming conventions, validation commands, and preferred
worker mix. Stored in `modes/` (gitignored, never committed).

### How Modes Work

Project-specific configuration (split boundaries, swarm sizing heuristics,
validation commands, wave labels, reviewer preferences, and artifact roots)
lives in the client overlay: `skillbox-config/clients/{client}/overlay.yaml` ->
auto-generated `context.yaml`.

### Client Config Resolution (Step 0)

1. Look for `context.yaml` in the working tree (generated from the client overlay)
2. If found, load project-specific settings automatically
3. If not found, tell the user no overlay matches and create one using the skillbox-quickstart scan + generate flow before proceeding
4. If no `skillbox-config/` exists, create one; do not fall back to generic decomposition

## Swarm Runtime (Default)

`divide-and-conquer` uses the same external swarm posture as
`modes-of-reasoning-project-analysis`: the lead agent owns selection,
dispatch, monitoring, collection, and synthesis; the swarm workers do the node
execution.

### Runtime knobs

| Argument | Default | Description |
|----------|---------|-------------|
| `--project=NAME` | derived from cwd + wave id | NTM swarm project name |
| `--cc=N:opus` | auto | Claude Opus panes for design-related nodes |
| `--cod=N:gpt-5.5` | auto | Codex panes for the current wave |
| `--gmi=N` | 0 | Optional Gemini panes |
| Grok sidecars | 0 | External Grok CLI lanes via `voice-to-text`/Swimmers or direct headless Grok; not an `ntm spawn` flag |
| `--max-workers=N` | 10 | Hard cap per wave |
| `--wave-timeout-min=N` | 45 | Hard timeout for a wave before collect-and-triage |
| `--monitor-cron` | every 3 minutes | Swarm health checks and nudges |

### Worker sizing rules

- Size each wave from the current ready frontier, not from the full graph
- Default to one worker per ready node
- If the frontier exceeds `--max-workers`, split it into multiple subwaves
- Keep Grok dispatcher/preflight/sidecar nodes read-only unless the user
  explicitly asks for Grok to own a writer node with a concrete write scope
- Route design-related execution nodes to Claude Opus and non-design execution
  nodes to Codex
- Use `gpt-5.5` whenever you set a Codex model explicitly
- Fall back to `gpt-5.4` or `gpt-5.3-codex` only when the runtime rejects 5.5,
  quota/account limits require it, or the user asks for a cheaper/lower model
- Default to `high`; use `medium` only for clearly bounded read-only nodes and
  `xhigh` for integration review or ambiguous repairs

## Subgoal Mode

Use subgoal mode when the root ready frontier is too large or too naturally
parallel for one lead to supervise as a single wave sequence. The purpose is to
run multiple independent child frontiers at the same time while keeping Beads as
the source of truth and keeping final integration root-owned.

Do not use subgoals for ordinary 2-8 node slices, strict dependency chains, or
work whose subgoal-level write scopes overlap. In those cases, widen the normal
ready frontier, split into subwaves, or keep the graph sequential.

### Subgoal Shape

Represent each subgoal with:

- one **subgoal controller** issue labeled `slice:{root}`,
  `subgoal:{slug}`, and `subgoal-role:controller`
- leaf execution issues labeled `slice:{root}`, `subgoal:{slug}`, and
  `subgoal-role:leaf`
- controller notes fields for `subgoal_id:`, `frontier_filter:`,
  `parent_run_dir:`, `subgoal_run_dir:`, `child_orchestrator:`,
  `ntm_project:`, `max_workers:`, `max_subgoal_depth:`, `isolation:`, and
  `status_artifact:`
- controller design blocks for `writes:`, `shared_files:`, `stop_rules:`, and
  `escalation:`

The root `slice:{root}` label must remain on every controller and leaf. Do not
model subgoals as parent-child readiness edges unless the installed `br`
version has been proven to support non-blocking hierarchy.

### Subgoal Admission

Before launching a subgoal cohort:

1. Prove the live `br ready --label slice:{root} --label subgoal:{slug}`
   behavior is AND semantics, or apply helper-side AND filtering after a broader
   query. If this cannot be proven, fail closed and do not launch subgoals.
2. Partition the ready frontier by `subgoal:{slug}` and exclude leaves without
   the root `slice:{root}` label.
3. Verify subgoal-level `writes:` do not overlap across the active cohort and no
   active leaf depends on another active subgoal.
4. Treat `shared_files:` as root-owned and sequential. Child orchestrators may
   propose edits to shared files but may not apply them.
5. Run `vibing-with-ntm`'s `swarm-load-guard.sh` once for the whole workspace
   run and admit only as many subgoals and leaf workers as the global budget can
   support. Do not re-run the load check independently inside each subgoal and
   treat every local pass as permission to spawn.

### Execution Modes

Default mode is **meta-lead multiplexing**:

- The root lead keeps one context but admits several ready subgoal controllers
  at once.
- It launches or tends one compact NTM session per active subgoal, each scoped
  by that controller's `frontier_filter:`.
- It monitors controller state and concise subgoal status, not every child leaf
  pane tail.

Escalation mode is **delegated child orchestration**:

- Use this only when subgoal count, depth, or context pressure is already too
  high for meta-lead multiplexing.
- The initial child substrate is NTM child orchestrator sessions; do not add a
  second substrate until the NTM path has a proven recovery contract.
- The root claims the controller issue for the child orchestrator before
  dispatch and verifies the claim with `br show`.
- The child orchestrator may claim, block, and close only leaf issues matching
  both `slice:{root}` and its assigned `subgoal:{slug}`.
- The child writes `SUBGOAL_RESULT.md` inside `subgoal_run_dir:` and proposes
  any cross-subgoal graph change there instead of mutating topology directly.

Optional isolation:

- `isolation: checkout` is the default.
- `isolation: worktree` is appropriate when static write-scope proof is weak or
  the subgoal is large. Worktrees move overlap risk to a loud merge/integration
  step; they do not make overlapping edits impossible. Define a single
  root-owned `.beads/` mutation policy before using worktrees.

### Subgoal Completion

Never accept a subgoal as done from controller status, child prose, or
`SUBGOAL_RESULT.md` alone. The root accepts completion only after an independent
gate proves:

```text
br ready --label slice:{root} --label subgoal:{slug} is empty
AND no in-flight leaf set changed for at least two operator ticks
AND expected validation and SUBGOAL_RESULT.md evidence exist
AND the latest child output has no unresolved blocker or convergence-warning language
```

Then the root performs cross-subgoal integration, validates shared files, flushes
Beads, runs the final review wave, and commits. Subgoal workers and child
orchestrators do not commit.

### NTM Project Root Preflight

Run this before every wave spawn, including review waves:

```bash
repo_root="$(git rev-parse --show-toplevel)"
pwd
rg '^projects_base' ~/.config/ntm/config.toml
ntm list --json
```

Then verify the proposed `$WAVE_PROJECT` resolves to `repo_root`. If
`projects_base/$WAVE_PROJECT` is not the target checkout, do not spawn the wave
by basename. Fix the NTM project mapping first, choose a supported session name
that maps to the actual repo, or block the Beads node with the exact root
resolution problem.

Record the result in the dispatch contract:

```text
NTM root preflight:
- repo_root: <absolute git root>
- wave_project: <ntm session name>
- projects_base mapping: <verified target path or blocker>
- result: pass | blocked
```

`ntm spawn` success, an idle pane, or a worker saying it is in the right repo is
not sufficient proof. After dispatch, verify pane output or a robot inspection
shows the node brief landed in the intended checkout before counting the node
as in flight.

## Process

### 1. Analyze the Task

Read the conversation to understand:
- What the user wants accomplished
- What files or systems are involved
- What dependency edges matter
- Whether the task is actually ready for orchestration

### 2. Decide Whether a Workgraph Is Relevant

Use a workgraph when any of these are true:
- The task has 2+ plausible concern-owned execution nodes
- Dependency edges matter to launch order
- The user explicitly wants an orchestrated or parallel split
- You need a durable artifact to explain and reuse the split across waves

If the work collapses to one concern or a strict dependency chain, do not
invent fake parallelism. The graph can still be useful for sequencing, but the
execution should stay narrow.

If the split itself is unclear, use `ask-cascade` on the first blocking
strategic fork before inventing nodes or launching a swarm.

### 3. Decide Whether Subgoals Are Relevant

Before minting or dispatching a very large graph, decide whether normal waves
are enough:

- If the ready frontier is at or below `--max-workers`, writes are disjoint, and
  one lead can tend one session, use the normal ready-frontier path.
- If the work naturally separates by repo, service, domain, layer, or read-only
  investigation group, and those groups can advance independently, add subgoal
  controllers.
- If the work is a strict discovery -> act chain or shares migrations,
  generated files, global runtime state, or a single validation bottleneck, keep
  it inside one frontier and encode dependencies instead of inventing subgoals.

When subgoals are relevant, mint or tighten the controller issues before leaf
dispatch. The controller is the durable boundary; NTM session names and
`SUBGOAL_RESULT.md` artifacts are derived views/evidence.

### 4. Load or Synthesize the Beads Epic

Before inventing a split, check whether the slice already has a `br` epic with
open children:

```bash
frontier_json="$(python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:{slug})"
```

If the epic exists and the ready frontier is non-empty:
- Treat the helper's output as the default launch proposal
- Respect each issue's `writes` (in `--design`) even if the user asked broadly
- Do not pull blocked or deferred issues into the same wave

If no epic exists and orchestration is still relevant:
- Create an invocation run directory under the resolved invocation root
- Mint the epic and child nodes via `br_helpers.py mint-node`, following the
  field mapping in
  [`_shared/references/beads-contract.md`](../_shared/references/beads-contract.md):
  `--concern`, `--repo`, `--writes`, `--done-when`, `--validate`, `--risk`,
  `--depends-on`, `--epic`. Synthesis prose lives in
  [references/workgraph-synthesis.md](references/workgraph-synthesis.md);
  treat it as guidance for what *content* each node carries, not where state lives.
- Keep the slice focused on this execution, usually 2-8 nodes
- Write `EPIC_ID.txt` to the run directory, then regenerate `WORKGRAPH.md` as a
  view: `br_helpers.py render-workgraph --epic $(cat <absolute-run-dir>/EPIC_ID.txt) --out <absolute-run-dir>/WORKGRAPH.md`
- Immediately run `br_helpers.py ready --label slice:{slug}` and treat the
  result as wave 1

The rendered `WORKGRAPH.md` is a scratch view, not a second plan document.
State changes flow through `br update`/`br close`; never hand-edit the markdown.

### 5. Tighten Fuzzy Nodes Before Swarm Launch

Use `describe` only when a node is still fuzzy, not as mandatory ceremony for
every node.

When a ready node still has vague `done_when`, `validate_cmds`, or non-goals:
- Do not launch a writer yet
- Run a node-local `describe` pass or fresh review to tighten the contract
- If the review exposes a real strategic decision, route that one blocking
  question through `ask-cascade`
- Update the issue in place: `br update {id} --acceptance-criteria '…' --notes 'validate: …' --design '…'`
- Re-query the frontier with `br_helpers.py ready --label slice:{slug}` before launching the wave

### 6. Hydrate the Beads Dispatch Contract

Before spawning the swarm, make Beads hold the complete dispatch contract. A
ready node is not launchable until `br show {id} --json` or
`br_helpers.py hydrate-node {id}` exposes:
- original ask or node description
- repo path, branch/HEAD, and run directory
- current dependencies, blocked state, and ready frontier membership
- `writes`, `done_when`, `validate_cmds`, `risk_gate`, non-goals, and stop rules
- global constraints: no remote push, no cross-repo edits, no write-scope theft
- model route per node: Grok dispatcher for read-only router/preflight nodes,
  Grok CLI sidecar for Grok-authored read-only artifacts, Claude Opus for
  design-related nodes, Codex gpt-5.5 for other execution nodes
- expected Beads assignee per node (`BR_AGENT_NAME`) and the exact claim
  verification command

Use Beads-first helper commands:

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py hydrate-node <issue-id>
python3 ~/.claude/skills/_shared/scripts/br_helpers.py render-node-brief <issue-id>
```

If `hydrate-node` reports missing dispatch fields, update the issue first with
`br_helpers.py update-node` or `br update`; do not patch the missing context into
`EXECUTION_CONTEXT.md`. That file may be rendered for humans or transport
debugging, but workers must receive a Beads-rendered node brief.

### 7. Spawn the Wave Swarm

For each ready frontier wave, launch an NTM swarm sized to that wave.

```bash
frontier_json="$(python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:${SLICE_SLUG})"
# Optional: ranked by br's evidence-aware scheduler instead of plain priority
# frontier_json="$(python3 ~/.claude/skills/_shared/scripts/br_helpers.py scheduler)"

ntm spawn "$WAVE_PROJECT" \
  --cc="${NUM_DESIGN}:opus" --cod="${NUM_NON_DESIGN}:gpt-5.5" \
  --no-user \
  --stagger-mode=smart
```

If either count is zero, omit that flag rather than spawning an empty worker
class. Never satisfy a design-related node by increasing `NUM_NON_DESIGN`.
Grok sidecar nodes are launched after the same Beads claim handshake, through
the `voice-to-text`/Swimmers Grok lane or a direct headless Grok one-shot, and
are tracked by their issue ID plus result artifact. Do not inflate the Codex
count to cover a Grok-routed node, and do not wait on `ntm --robot-*` as proof
that a Grok sidecar completed.

Wait for the swarm to be ready:

```bash
ntm --robot-wait="$WAVE_PROJECT" --condition=idle --timeout=120
```

Prefer wave-scoped swarm names such as
`dac-<repo>-wave-01`, `dac-<repo>-wave-02`, and `dac-<repo>-review`.

Optionally render `EXECUTION_CONTEXT.md` inside the run directory after the
Beads contract is complete. Treat it as a cached view for humans and transport
debugging. Never hand-edit it to add worker-only context.

Before dispatch, verify the run directory is outside the product repo root and
under the resolved invocation root. If it resolves to the repo root, `.dac/`,
`.ntm/`, `/tmp`, or any untracked repo-local scratch directory, stop and repair
the artifact root before spawning workers.

### Transport Hygiene

If the swarm transport looks wrong, fix that before blaming the node brief.

- After each dispatch, verify the target pane actually switched onto the new
  brief. `ntm send` reporting success is not enough.
- If a pane still shows an unrelated prior task, a stale generic prompt, or an
  idle shell after dispatch, treat it as contaminated. Respawn that pane and
  resend the node brief before advancing the wave.
- Prefer artifact-aware checks over coarse activity labels: a node is not
  meaningfully in flight until its expected absolute
  `<absolute-run-dir>/WG-*_RESULT.md` path is plausible and the pane output matches the
  assigned node.
- When the failure surface is NTM itself rather than decomposition or prompt
  quality, consult `vibing-with-ntm` or `ntm` if available instead of
  improvising ad hoc transport rituals.

### 8. Dispatch Node-Specific Prompts

Send each worker a unique node prompt. Stagger dispatch by 15-20 seconds to
avoid thundering-herd effects:

```bash
for pane in <pane indexes for this wave>; do
  ntm send "$WAVE_PROJECT" --pane="$pane" "$(cat <<'PROMPT'
  <INSERT NODE-SPECIFIC PROMPT>
  PROMPT
  )"
  sleep 18
done
```

### Lead-Owned Claim Handshake

Do not rely on worker prose or prompts to make `bv`/`br` state truthful. The
lead must claim every node for the intended worker before allowing real edits.

For each node, immediately before sending the node brief:

```bash
BR_AGENT_NAME="<worker-id>" BR_HARNESS="ntm" BR_MODEL="<model-id>" \
  br update "<issue-id>" --claim --json

br show "<issue-id>" --json \
  | jq -e '.[0].status == "in_progress" and .[0].assignee == "<worker-id>"'
```

If this verification fails, do not dispatch the pane. Repair the claim and send
the brief only after `br show` confirms `status=in_progress` and the expected
assignee. `ntm send` success, active pane output, modified files, or a worker
saying "claimed" are not sufficient.

Before any closeout, verify the issue is still attributed. If a worker closed a
node with a blank assignee, repair attribution with `br update <id> --assignee
<worker-id> --json` and add a comment explaining the reconciliation.

Every worker prompt MUST include:
1. A node brief rendered from Beads (`br_helpers.py render-node-brief <id>`)
2. The exact `br` issue ID for the node, plus the absolute run directory path
   for evidence artifacts
3. The node's `concern`, `depends_on`, `writes`, `done_when`, `validate_cmds`,
   and `risk_gate` (read these from `br show {id}` if not inlined)
4. The hard ownership rule: edit only the declared `writes`
5. The lifecycle commands and claim gate:
   - The lead has already claimed the issue for this worker; on entry the
     worker must run `br show {id} --json` and confirm `status=in_progress`
     with its `BR_AGENT_NAME`
   - If the claim is missing or assigned to someone else, the worker must stop
     and report instead of editing
   - On blocked: `br update {id} -s blocked --notes "{reason}"`
   - On done: `br close {id} --reason "{summary}" --suggest-next --json`
6. The attribution preamble: `export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model>` before any `br` mutation
7. The artifact boundary: write evidence only to the absolute run directory,
   never to the product repo root, `.dac/`, `.ntm/`, or `/tmp`
8. The stop rule: if required edits escape `writes`, leave the issue in_progress, write the smallest Beads graph change proposal in the result artifact, and do NOT close the issue
9. The result artifact contract below

### Node Worker Prompt Contract

Use a compact brief like this:

```text
You own one divide-and-conquer node inside an execution swarm.

Source of truth: br (run `br show <issue-id>` for the live contract)
Issue ID: <prefix>-wg-001-<slug>-<hash>
Run directory: <absolute path under skillbox-config invocation root>
Concern: <concern>
Depends on: <ids already satisfied, or None>
Writes: <expected paths/globs, or None>

Underlying ask:
<plain-language user outcome for this node>

Done when:
- <binary completion check>

Validate:
- <command>

Risk gate:
- none | <gate>
Model route:
- Grok dispatcher for read-only router/preflight nodes
- Grok CLI sidecar for Grok-authored read-only evidence artifacts
- Claude Opus for design-related nodes
- Codex gpt-5.5 for other execution nodes
Expected Beads assignee:
- <worker-id>

Non-goals:
- <explicitly out of scope>

Rules:
- export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model> before any br call
- On entry: verify the lead's claim with `br show <id> --json`; do not edit
  until it shows `status=in_progress` and `assignee=<worker-id>`
- Work only inside the repo and inside your declared write scope
- Do not commit; the integration wave commits everything together
- Do not create repo-local orchestration artifacts. No repo-root
  `WORKGRAPH.md`, `EXECUTION_CONTEXT.md`, `WG-*_RESULT.md`,
  `DAC_FINAL_RESULT.md`, `.dac/`, or `.ntm/`.
- If you need edits outside `writes`, do NOT close the issue. Report the
  smallest Beads graph update needed and leave status=in_progress for the orchestrator
- Run your validate commands before declaring success
- On done: `br close <id> --reason "<summary>" --suggest-next --json` and write
  `<absolute-run-dir>/WG-001_RESULT.md` with the required sections
- On blocked: `br update <id> -s blocked --notes "<reason>"` and write the
  blocker section in `<absolute-run-dir>/WG-001_RESULT.md`
```

### Node Result Artifact

Every worker MUST write `<NODE_ID>_RESULT.md` such as `WG-001_RESULT.md` in the
absolute invocation run directory. If the worker cannot write there, it must
stop and report the artifact-root blocker instead of writing a fallback file in
the product repo, `.dac/`, `.ntm/`, or `/tmp`:

```markdown
# WG-001 Result

## Status
done | blocked | needs_rework

## Summary
One paragraph on what changed.

## Files Changed
- path/to/file

## Validation
- Command: <validate command>
- Result: pass | fail
- Notes: <short output summary>

## Workgraph Notes
- Suggested graph update, if any

## Blockers
- Only if blocked or needs_rework
```

### 9. Monitor the Wave

Set up monitoring immediately after dispatch:

```
CronCreate(
  cron: "*/3 * * * *",
  recurring: true,
  prompt: "Check divide-and-conquer wave $WAVE_PROJECT. Run:
    1. ntm --robot-is-working=$WAVE_PROJECT
    2. ntm --robot-tail=$WAVE_PROJECT --lines=80
    3. test <absolute-run-dir> -ef \"$(git rev-parse --show-toplevel)\" && echo BAD_RUN_DIR || true
    4. ls -la <absolute-run-dir>/WG-*_RESULT.md 2>/dev/null
    5. br show <each-active-issue-id> --json

  For each active node, determine:
  (a) working / idle / stuck / rate-limited?
  (b) has it produced its WG-*_RESULT.md file?
  (c) if output exists, is validation explicit or hand-wavy?
  (d) does br show status=in_progress with the expected assignee?

  ACTIONS:
  - If a node is open/unassigned after dispatch: stop/nudge the pane, repair
    the claim, and do not count the node as in-flight until br confirms it
  - If worker idle + no result: remind it of its node and result file
  - If worker stuck for 2 checks: send an unblock prompt tied to the node
  - If result is superficial: demand explicit validation and file list
  - If all nodes in the wave are done, blocked, or timed out: cancel this cron and report

  Report concisely: N done, N working, N blocked, quality observations."
)
```

### Nudge Prompts

**Generic nudge (idle, no result):**

```bash
ntm send "$WAVE_PROJECT" --pane="$N" "You own node WG-00N. Finish the node, run its validate commands, and write WG-00N_RESULT.md only at <absolute-run-dir>/WG-00N_RESULT.md. Do not create repo-root, .dac, .ntm, or /tmp fallback artifacts. Stay inside the declared write scope."
```

**Depth nudge (result lacks proof):**

```bash
ntm send "$WAVE_PROJECT" --pane="$N" "<absolute-run-dir>/WG-00N_RESULT.md is not sufficient yet. Add the exact files changed, explicit validation commands, and whether the node is done, blocked, or needs_rework. Do not write evidence files in the product repo."
```

**Boundary nudge (scope drift):**

```bash
ntm send "$WAVE_PROJECT" --pane="$N" "Do not code past your declared write scope. If the node truly needs broader edits, stop and propose the smallest Beads graph change instead."
```

### 10. Collect Results and Advance the Graph

Once the wave has produced results, or the timeout is reached:

1. Cancel the monitoring cron
2. Capture final pane state:
   ```bash
   ntm --robot-tail="$WAVE_PROJECT" --lines=200
   ```
3. Read every `<absolute-run-dir>/WG-*_RESULT.md` for the active wave completely.
   Treat repo-root, `.dac/`, `.ntm/`, or `/tmp` result files as misplaced
   evidence that must be moved to the run directory before reconciliation.
4. Cross-reference each issue's current state with `br show {id}`. The lead
   should already have claimed each issue before dispatch; never trust worker
   prose, pane activity, or file changes alone.
5. Independently run each node's `validate_cmds` yourself before treating it as
   `done`
6. Reconcile `br` state to the verified outcome:
   - Still open/unassigned but work landed: repair attribution first with
     `BR_AGENT_NAME=<worker-id> br update {id} --claim --json`, then close only
     after validation passes
   - Closed with blank assignee: repair attribution with `br update {id}
     --assignee <worker-id> --json` and add a reconciliation comment
   - Validation passed: leave it closed (or run `br close {id} --reason …` if
     the worker forgot)
   - Real blocker: `br update {id} -s blocked --notes "{verified blocker}"`
   - Needs rework: `br reopen {id}` — the issue returns to the ready frontier
7. Re-render the view:
   `python3 ~/.claude/skills/_shared/scripts/br_helpers.py render-workgraph --epic $(cat <absolute-run-dir>/EPIC_ID.txt) --out <absolute-run-dir>/WORKGRAPH.md`
8. Re-query the frontier: `python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:{slug}`
9. Launch the next ready wave

Do not mark a node done based only on a worker's self-report.

### 11. Repeat Until the Graph Is Exhausted or Truly Blocked

Continue wave by wave until one of these is true:
- All execution nodes are `done`
- The remaining graph is genuinely blocked on a user decision or external system
- Validation failures show the graph itself needs to be rewritten before more work

If a node's result reveals a better decomposition, update the graph before the
next wave instead of forcing the old split.

### 12. Run a Final Integration and Review Wave

After all execution nodes are complete, run one final integration wave through
the same swarm runtime. Do not default to `/codex:rescue`.

Spawn a small review swarm, usually 1-2 workers:

```bash
ntm spawn "$REVIEW_PROJECT" --cc=1:opus --cod=1:gpt-5.5 --no-user --stagger-mode=smart
ntm --robot-wait="$REVIEW_PROJECT" --condition=idle --timeout=120
```

Reviewer prompt:
- Read the original task, live Beads state via `br show` / `hydrate-node`, the
  rendered `WORKGRAPH.md` view if present, and the current `git diff`
- Confirm the graph intent matches the repo state
- Run relevant build, test, lint, and typecheck commands
- Fix only integration bugs or validation failures
- For UI, UX, visual, design-system, screenshot, or ambiguous review-heavy work,
  use Claude Opus for the fresh-eyes review of the final diff and validation
  evidence. Do not substitute Codex for design review unless the user
  explicitly overrides the hard route.
- Run `br epic close-eligible --json` to retire the slice's epic if every child
  is closed; surface any leftover open child as the blocker
- Run `python3 ~/.claude/skills/_shared/scripts/br_helpers.py flush` so
  `.beads/issues.jsonl` reflects current state
- Commit if there are clean, scoped changes to save (include `.beads/issues.jsonl`,
  exclude `.beads/*.db*`)
- Write `<absolute-run-dir>/DAC_FINAL_RESULT.md`

`DAC_FINAL_RESULT.md` MUST end with:

```json
{
  "commit_hash": "<hash or null>",
  "summary": "<1-2 sentence summary>",
  "files_changed": <number>,
  "status": "success" | "error"
}
```

### 13. Report to User

When the final review result is available:

- If `commit_hash` is present, show the commit and file summary
- If no commit was made, say why
- If the graph is blocked, report the exact blocking node and the smallest next
  decision needed

## Rules

- `br` (the slice's epic + child issues in `.beads/`) is the execution source of truth
- `WORKGRAPH.md` is a generated view; never hand-edit it — re-render with `br_helpers.py render-workgraph`
- State changes flow through `br update`/`br close`, not markdown rewrites
- Invocation artifacts (`EXECUTION_CONTEXT.md`, `WG-*_RESULT.md`, `DAC_FINAL_RESULT.md`, `EPIC_ID.txt`) still live under the overlay-backed invocation root in `skillbox-config`, but only `EPIC_ID.txt` is a pointer to source-of-truth Beads state; the rest are generated views or evidence attachments
- Never create new repo-local `.dac/`, `.ntm/`, repo-root `WG-*_RESULT.md`,
  repo-root `WORKGRAPH.md`, repo-root `EXECUTION_CONTEXT.md`, or repo-root
  `DAC_FINAL_RESULT.md` files. Existing legacy files may be read as historical
  evidence, but new waves use the overlay-backed invocation root.
- Ready frontier comes from `br_helpers.py ready` or `scheduler`; do not pre-dispatch blocked nodes
- Subgoal frontiers require both `slice:{root}` and `subgoal:{slug}` filters;
  prove multi-label `br ready` AND semantics or use helper-side AND filtering
  before launch
- Subgoal controller issues are durable delegation boundaries. NTM session
  names and `SUBGOAL_RESULT.md` files are derived evidence, not topology
- The root owns subgoal creation, shared files, cross-subgoal graph shape,
  final integration, final validation, Beads flush, and commit
- Child orchestrators may claim/close/block only leaf issues in their assigned
  `slice:{root},subgoal:{slug}` frontier and must propose cross-subgoal changes
  to the root instead of mutating topology directly
- Do not accept a subgoal as done from controller status or child prose; run the
  independent completion gate before rollup
- `writes` ownership is a hard boundary, not a suggestion
- Default to NTM swarm execution; do not substitute local ad hoc workers
- Cwd/workflow routing, skill-tag extraction, cleaned-request drafting, and
  read-only clerk/preflight nodes should use the `voice-to-text` Grok
  dispatcher when available; Grok-authored sidecar artifacts should use
  Swimmers hidden Grok sessions or direct headless Grok and reconcile through
  the normal Beads/result-artifact contract
- Design-related nodes and design/fresh-eyes review nodes must use Claude Opus;
  non-design execution nodes must use Codex gpt-5.5 by default
- The lead must claim every dispatched node for the assigned worker and verify
  `status=in_progress` plus assignee before edits begin; unclaimed pane activity
  does not count as in-flight work
- One worker per ready node; one wave per ready frontier
- If the frontier is too large, batch it; do not oversubscribe the swarm
- Prefer 2-8 meaningful nodes; 10 is the hard cap per wave
- Use `describe` only for fuzzy nodes
- Use `ask-cascade` only for the first blocking strategic ambiguity
- Every worker gets its `br` issue ID, the run directory path, the verified
  claim/assignee, and the lifecycle commands (`br show` claim check,
  `--reason --suggest-next`)
- Workers stamp `BR_AGENT_NAME`/`BR_HARNESS`/`BR_MODEL` before any `br` mutation
- Node workers do not commit; only the final integration review commits, and it includes `.beads/issues.jsonl` while excluding `.beads/*.db*`
- Independently run `validate_cmds` and reconcile `br` state before treating any node `done`
- If `ntm` or `br` is missing or broken, stop and surface the prerequisite gap
- Sequential waves are fine; fake parallelism is not
