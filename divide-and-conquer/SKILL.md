---
name: divide-and-conquer
description: Decompose complex work into an executable `WORKGRAPH.md`, then run an NTM-style swarm by ready frontier with no write overlap. Use before parallel execution for large-ish, UI-facing, multi-file, multi-domain, naturally parallel, naturally orchestrated, or review-sensitive tasks.
license: MIT
metadata:
  requires_beads: true
---

# Divide and Conquer

Decompose a task into a `br` epic with child issues, then execute that graph
through an NTM-managed swarm. Autonomous: analyze -> load or mint the epic
in `br` -> tighten fuzzy nodes -> spawn a wave swarm using `br ready`/`br scheduler`
-> dispatch node briefs (each carrying a `br` issue ID) -> monitor -> collect
-> reconcile `br` state -> advance waves -> run final integration review
(close-eligible epic, flush JSONL) -> commit `.beads/issues.jsonl` with the
slice changes -> report. `WORKGRAPH.md` exists as a generated view only.
No approval gates.

## Default Marker

Start with a stable first progress message such as:

`Using \`divide-and-conquer\` to build the ready frontier, spawn an execution swarm, and hand the workgraph off wave by wave.`

Shared cross-skill rules live in
[references/orchestration-contract.md](references/orchestration-contract.md).
Use that file for worker ownership, background-task collection, and detached
handoff semantics.

Temp workgraph synthesis and describe-style node briefs live in
[references/workgraph-synthesis.md](references/workgraph-synthesis.md).

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
`scheduler`, `mint-node`, `claim`, `block`, `done`, `render-workgraph`, `flush`.

This skill now defaults to an external NTM swarm for execution. Do not fall
back to ad hoc local subagents or `/codex:rescue` as the primary path unless
the user explicitly asks to bypass the swarm. If `ntm` is unavailable, stop and
surface the missing prerequisite instead of silently degrading.

Because execution is swarm/NTM-coordinated, `vibing-with-ntm` is mandatory for
every divide-and-conquer run. Activate it through `sbp` when needed, then follow
its operator, reservation, transport, and review-loop guidance.

Use this skill for large-ish, UI-facing, multi-file, naturally parallel, or
review-sensitive tasks even when the user did not explicitly ask for a swarm. For
UI work or ambiguous review-heavy work, include Claude Opus in the worker or
reviewer mix when the runtime exposes model selection, and require a final
fresh-eyes reviewer pass before completion.

## Related Skills

- [[skill-issue]]
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

Store these artifacts in the run directory:
- `WORKGRAPH.md` — generated view (regenerate with `br_helpers.py render-workgraph --epic {id} --out WORKGRAPH.md`); never edit by hand
- `EXECUTION_CONTEXT.md` — the execution pack handed to every worker
- `WG-*_RESULT.md` — per-node worker reports (still required for prose evidence the swarm cannot keep in `br` notes)
- `DAC_FINAL_RESULT.md` — final integration summary
- `EPIC_ID.txt` — the `br` epic ID for this run; sole pointer back to the source-of-truth state in `.beads/`
- any copied monitor notes or wave summaries

If the slice already has a `br` epic with open children, treat that epic as the
durable graph: list its children with `br_helpers.py ready --label slice:{name}`
and skip re-minting nodes. Always create a fresh invocation run directory for
this execution's artifacts and write `EPIC_ID.txt` pointing at the reused
epic.

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
| `--cc=N` | auto | Claude Code panes for the current wave |
| `--cod=N:gpt-5.5` | auto | Codex panes for the current wave |
| `--gmi=N` | 0 | Optional Gemini panes |
| `--max-workers=N` | 10 | Hard cap per wave |
| `--wave-timeout-min=N` | 45 | Hard timeout for a wave before collect-and-triage |
| `--monitor-cron` | every 3 minutes | Swarm health checks and nudges |

### Worker sizing rules

- Size each wave from the current ready frontier, not from the full graph
- Default to one worker per ready node
- If the frontier exceeds `--max-workers`, split it into multiple subwaves
- Bias Codex panes toward write-heavy waves and Claude panes toward ambiguity,
  research, or integration-heavy waves
- Use `gpt-5.5` whenever you set a Codex model explicitly
- Fall back to `gpt-5.4` or `gpt-5.3-codex` only when the runtime rejects 5.5,
  quota/account limits require it, or the user asks for a cheaper/lower model
- Default to `high`; use `medium` only for clearly bounded read-only nodes and
  `xhigh` for integration review or ambiguous repairs

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

### 3. Load or Synthesize the Beads Epic

Before inventing a split, check whether the slice already has a `br` epic with
open children:

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:{slug} > /tmp/dac-ready.json
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
  view: `br_helpers.py render-workgraph --epic $(cat EPIC_ID.txt) --out WORKGRAPH.md`
- Immediately run `br_helpers.py ready --label slice:{slug}` and treat the
  result as wave 1

The rendered `WORKGRAPH.md` is a scratch view, not a second plan document.
State changes flow through `br update`/`br close`; never hand-edit the markdown.

### 4. Tighten Fuzzy Nodes Before Swarm Launch

Use `describe` only when a node is still fuzzy, not as mandatory ceremony for
every node.

When a ready node still has vague `done_when`, `validate_cmds`, or non-goals:
- Do not launch a writer yet
- Run a node-local `describe` pass or fresh review to tighten the contract
- If the review exposes a real strategic decision, route that one blocking
  question through `ask-cascade`
- Update the issue in place: `br update {id} --acceptance-criteria '…' --notes 'validate: …' --design '…'`
- Re-query the frontier with `br_helpers.py ready --label slice:{slug}` before launching the wave

### 5. Build the Execution Context Pack

Before spawning the swarm, assemble a compact execution pack:
- Original user ask
- Repo path and branch or HEAD
- Workgraph path and whether it is durable or temp
- Invocation run directory path in `skillbox-config`
- Current ready frontier and blocked nodes
- Global constraints: no remote push, no cross-repo edits, no write-scope theft
- Project validation posture: build, test, lint, typecheck, or smoke commands
- Known risk gates or user caveats

Every wave prompt inherits this pack.

### 6. Spawn the Wave Swarm

For each ready frontier wave, launch an NTM swarm sized to that wave.

```bash
frontier_json="$(python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:${SLICE_SLUG})"
# Optional: ranked by br's evidence-aware scheduler instead of plain priority
# frontier_json="$(python3 ~/.claude/skills/_shared/scripts/br_helpers.py scheduler)"

ntm spawn "$WAVE_PROJECT" \
  --cc="$NUM_CC" --cod="${NUM_COD}:gpt-5.5" \
  --no-user \
  --stagger-mode=smart
```

Wait for the swarm to be ready:

```bash
ntm --robot-wait="$WAVE_PROJECT" --condition=idle --timeout=120
```

Prefer wave-scoped swarm names such as
`dac-<repo>-wave-01`, `dac-<repo>-wave-02`, and `dac-<repo>-review`.

Write the execution context pack to `EXECUTION_CONTEXT.md` inside the run
directory before the first dispatch.

### Transport Hygiene

If the swarm transport looks wrong, fix that before blaming the node brief.

- After each dispatch, verify the target pane actually switched onto the new
  brief. `ntm send` reporting success is not enough.
- If a pane still shows an unrelated prior task, a stale generic prompt, or an
  idle shell after dispatch, treat it as contaminated. Respawn that pane and
  resend the node brief before advancing the wave.
- Prefer artifact-aware checks over coarse activity labels: a node is not
  meaningfully in flight until its expected `WG-*_RESULT.md` path is plausible
  and the pane output matches the assigned node.
- When the failure surface is NTM itself rather than decomposition or prompt
  quality, consult `vibing-with-ntm` or `ntm` if available instead of
  improvising ad hoc transport rituals.

### 7. Dispatch Node-Specific Prompts

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

Every worker prompt MUST include:
1. The execution context pack
2. The exact `br` issue ID for the node, plus the run directory path for prose artifacts
3. The node's `concern`, `depends_on`, `writes`, `done_when`, `validate_cmds`,
   and `risk_gate` (read these from `br show {id}` if not inlined)
4. The hard ownership rule: edit only the declared `writes`
5. The lifecycle commands the worker MUST run:
   - On entry: `br update {id} --claim` (atomic in_progress)
   - On blocked: `br update {id} -s blocked --notes "{reason}"`
   - On done: `br close {id} --reason "{summary}" --suggest-next --json`
6. The attribution preamble: `export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model>` before any `br` mutation
7. The stop rule: if required edits escape `writes`, leave the issue in_progress, write a workgraph change proposal in the result artifact, and do NOT close the issue
8. The result artifact contract below

### Node Worker Prompt Contract

Use a compact brief like this:

```text
You own one divide-and-conquer node inside an execution swarm.

Source of truth: br (run `br show <issue-id>` for the live contract)
Issue ID: <prefix>-wg-001-<slug>-<hash>
Run directory: <path under skillbox-config>
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

Non-goals:
- <explicitly out of scope>

Rules:
- export BR_AGENT_NAME=<role> BR_HARNESS=<harness> BR_MODEL=<model> before any br call
- On entry: `br update <id> --claim` (atomic in_progress)
- Work only inside the repo and inside your declared write scope
- Do not commit; the integration wave commits everything together
- If you need edits outside `writes`, do NOT close the issue. Write the
  proposal in WG-001_RESULT.md and leave status=in_progress for the orchestrator
- Run your validate commands before declaring success
- On done: `br close <id> --reason "<summary>" --suggest-next --json` and write
  `WG-001_RESULT.md` in the invocation run directory with the required sections
- On blocked: `br update <id> -s blocked --notes "<reason>"` and write the
  blocker section in WG-001_RESULT.md
```

### Node Result Artifact

Every worker MUST write `<NODE_ID>_RESULT.md` such as `WG-001_RESULT.md` in the
invocation run directory:

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

### 8. Monitor the Wave

Set up monitoring immediately after dispatch:

```
CronCreate(
  cron: "*/3 * * * *",
  recurring: true,
  prompt: "Check divide-and-conquer wave $WAVE_PROJECT. Run:
    1. ntm --robot-is-working=$WAVE_PROJECT
    2. ntm --robot-tail=$WAVE_PROJECT --lines=80
    3. ls -la <run_dir>/WG-*_RESULT.md 2>/dev/null

  For each active node, determine:
  (a) working / idle / stuck / rate-limited?
  (b) has it produced its WG-*_RESULT.md file?
  (c) if output exists, is validation explicit or hand-wavy?

  ACTIONS:
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
ntm send "$WAVE_PROJECT" --pane="$N" "You own node WG-00N. Finish the node, run its validate commands, and write WG-00N_RESULT.md into the invocation run directory now. Stay inside the declared write scope."
```

**Depth nudge (result lacks proof):**

```bash
ntm send "$WAVE_PROJECT" --pane="$N" "WG-00N_RESULT.md in the invocation run directory is not sufficient yet. Add the exact files changed, explicit validation commands, and whether the node is done, blocked, or needs_rework."
```

**Boundary nudge (scope drift):**

```bash
ntm send "$WAVE_PROJECT" --pane="$N" "Do not code past your declared write scope. If the node truly needs broader edits, stop and propose the smallest WORKGRAPH change instead."
```

### 9. Collect Results and Advance the Graph

Once the wave has produced results, or the timeout is reached:

1. Cancel the monitoring cron
2. Capture final pane state:
   ```bash
   ntm --robot-tail="$WAVE_PROJECT" --lines=200
   ```
3. Read every `WG-*_RESULT.md` in the run directory for the active wave completely
4. Cross-reference each issue's current state with `br show {id}` — workers
   *should* have run `br update --claim` and `br close --suggest-next`, but
   never trust the worker's prose alone
5. Independently run each node's `validate_cmds` yourself before treating it as
   `done`
6. Reconcile `br` state to the verified outcome:
   - Validation passed: leave it closed (or run `br close {id} --reason …` if
     the worker forgot)
   - Real blocker: `br update {id} -s blocked --notes "{verified blocker}"`
   - Needs rework: `br reopen {id}` — the issue returns to the ready frontier
7. Re-render the view: `python3 ~/.claude/skills/_shared/scripts/br_helpers.py render-workgraph --epic $(cat EPIC_ID.txt) --out WORKGRAPH.md`
8. Re-query the frontier: `python3 ~/.claude/skills/_shared/scripts/br_helpers.py ready --label slice:{slug}`
9. Launch the next ready wave

Do not mark a node done based only on a worker's self-report.

### 10. Repeat Until the Graph Is Exhausted or Truly Blocked

Continue wave by wave until one of these is true:
- All execution nodes are `done`
- The remaining graph is genuinely blocked on a user decision or external system
- Validation failures show the graph itself needs to be rewritten before more work

If a node's result reveals a better decomposition, update the graph before the
next wave instead of forcing the old split.

### 11. Run a Final Integration and Review Wave

After all execution nodes are complete, run one final integration wave through
the same swarm runtime. Do not default to `/codex:rescue`.

Spawn a small review swarm, usually 1-2 workers:

```bash
ntm spawn "$REVIEW_PROJECT" --cc=1 --cod=1:gpt-5.5 --no-user --stagger-mode=smart
ntm --robot-wait="$REVIEW_PROJECT" --condition=idle --timeout=120
```

Reviewer prompt:
- Read the original task, the rendered `WORKGRAPH.md` view, the live state via
  `br_helpers.py render-workgraph --epic $(cat EPIC_ID.txt)`, and the current
  `git diff`
- Confirm the graph intent matches the repo state
- Run relevant build, test, lint, and typecheck commands
- Fix only integration bugs or validation failures
- For UI or ambiguous review-heavy work, use Claude Opus when the runtime exposes
  model selection and perform a fresh-eyes review of the final diff and
  validation evidence
- Run `br epic close-eligible --json` to retire the slice's epic if every child
  is closed; surface any leftover open child as the blocker
- Run `python3 ~/.claude/skills/_shared/scripts/br_helpers.py flush` so
  `.beads/issues.jsonl` reflects current state
- Commit if there are clean, scoped changes to save (include `.beads/issues.jsonl`,
  exclude `.beads/*.db*`)
- Write `DAC_FINAL_RESULT.md` in the invocation run directory

`DAC_FINAL_RESULT.md` MUST end with:

```json
{
  "commit_hash": "<hash or null>",
  "summary": "<1-2 sentence summary>",
  "files_changed": <number>,
  "status": "success" | "error"
}
```

### 12. Report to User

When the final review result is available:

- If `commit_hash` is present, show the commit and file summary
- If no commit was made, say why
- If the graph is blocked, report the exact blocking node and the smallest next
  decision needed

## Rules

- `br` (the slice's epic + child issues in `.beads/`) is the execution source of truth
- `WORKGRAPH.md` is a generated view; never hand-edit it — re-render with `br_helpers.py render-workgraph`
- State changes flow through `br update`/`br close`, not markdown rewrites
- Invocation prose artifacts (`EXECUTION_CONTEXT.md`, `WG-*_RESULT.md`, `DAC_FINAL_RESULT.md`, `EPIC_ID.txt`) still live under the overlay-backed invocation root in `skillbox-config`
- Ready frontier comes from `br_helpers.py ready` or `scheduler`; do not pre-dispatch blocked nodes
- `writes` ownership is a hard boundary, not a suggestion
- Default to NTM swarm execution; do not substitute local ad hoc workers
- One worker per ready node; one wave per ready frontier
- If the frontier is too large, batch it; do not oversubscribe the swarm
- Prefer 2-8 meaningful nodes; 10 is the hard cap per wave
- Use `describe` only for fuzzy nodes
- Use `ask-cascade` only for the first blocking strategic ambiguity
- Every worker gets its `br` issue ID, the run directory path, and the lifecycle commands (`--claim`, `--reason --suggest-next`)
- Workers stamp `BR_AGENT_NAME`/`BR_HARNESS`/`BR_MODEL` before any `br` mutation
- Node workers do not commit; only the final integration review commits, and it includes `.beads/issues.jsonl` while excluding `.beads/*.db*`
- Independently run `validate_cmds` and reconcile `br` state before treating any node `done`
- If `ntm` or `br` is missing or broken, stop and surface the prerequisite gap
- Sequential waves are fine; fake parallelism is not
