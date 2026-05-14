# Workgraph Synthesis (Beads-Backed)

Use this when `divide-and-conquer` should orchestrate execution through the
default swarm runtime but no `br` epic exists yet for the slice. State lives
in `br`; this file describes what *content* each node carries and how to mint
it. Cross-skill conventions live in
[`_shared/references/beads-contract.md`](../../_shared/references/beads-contract.md).

## Run Directory

Still required for generated views and evidence attachments (`EPIC_ID.txt`,
optional rendered `WORKGRAPH.md`, optional generated `EXECUTION_CONTEXT.md`,
`WG-*_RESULT.md`, `DAC_FINAL_RESULT.md`). Do not use `/tmp` when an overlay is
available.

```bash
run_dir="{invocation_root}/{repo_slug}/divide-and-conquer/{run_id}"
mkdir -p "$run_dir"
```

`WORKGRAPH.md` and `EXECUTION_CONTEXT.md` inside the run directory are generated
views, not authoritative contracts. Regenerate `WORKGRAPH.md` any time:

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py render-workgraph \
  --epic "$EPIC_ID" --out "$run_dir/WORKGRAPH.md"
```

If a `br` epic already exists for the slice (typically minted by
`domain-planner` Phase 6e), reuse it. Read its ID from upstream artifacts or
`br list --label slice:{slug} --type epic --json`. Write `EPIC_ID.txt` into
the new run directory instead of duplicating the epic.

## Mint The Epic And Children

```bash
EPIC=$(br create "{slice}: {one-line value}" --slug epic-{slice} \
  --type epic --priority 1 --json | jq -r .id)
echo "$EPIC" > "$run_dir/EPIC_ID.txt"

python3 ~/.claude/skills/_shared/scripts/br_helpers.py mint-node \
  wg-001-{kebab-title} '{Title}' \
  --epic "$EPIC" \
  --concern backend-api \
  --repo current-repo \
  --writes 'src/domain/**' \
  --done-when 'Binary completion check' \
  --validate 'Concrete validation command' \
  --model-route 'Codex gpt-5.5' \
  --repo-path "$PWD" \
  --branch "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || git rev-parse --short HEAD)" \
  --run-dir "$run_dir" \
  --expected-assignee 'dac-worker-001' \
  --stop-rule 'Stop if required edits escape writes' \
  --global-constraint 'No remote push from node workers' \
  --risk none
```

The same fields the old JSON node carried map cleanly: `id` is auto-assigned,
`title` is positional, `concern`/`repo`/`risk` go on `--labels`, `depends_on`
is a sequence of `--depends-on` flags, `writes` becomes the issue's `Design`
block, `done_when` becomes `acceptance_criteria`, `validate_cmds` become
`notes`, `global_constraints` lives in design, and
`model_route`/`repo_path`/`branch`/`run_dir`/`expected_assignee` live in notes
as machine-readable scalar lines. `status: todo` is the default open state.

Rules per node:
- Keep the slice narrow: current execution only, usually 2-8 nodes
- One node per executable concern, not per tiny file edit
- Encode dependencies through `--depends-on` (or `br dep add` after the fact),
  not narrative prose
- Use concrete `--writes` so wave grouping can detect overlap
- Use concrete `--done-when` and `--validate`; placeholder language means the
  node is not ready
- Set `--model-route`, `--repo-path`, `--branch`, and `--run-dir` before dispatch so
  `br_helpers.py hydrate-node` can prove the node is dispatch-ready
- Read-only nodes: omit `--writes` entirely

## When To Trigger `describe`

Trigger a node-level `describe` pass before swarm launch when any of these are
true:
- `--done-when` (acceptance criteria) would otherwise be vague or subjective
- `--validate` is missing or hand-wavy
- The node still has a real scope or behavior decision unresolved
- The worker would need to guess non-goals or ownership boundaries

Do not run `describe` for every node by default. Use it to tighten fuzzy nodes,
then update the issue (`br_helpers.py update-node …`, or raw `br update {id}
--acceptance-criteria … --notes … --design …`) and recompute the ready
frontier with `br_helpers.py ready`.
`update-node` preserves existing generated `writes`, `stop_rules`,
`non_goals`, `global_constraints`, `validate`, `model_route`, `repo_path`,
`branch`, `run_dir`, and `expected_assignee` blocks when a partial update only
changes one of those groups.

## Swarm Node Brief

The canonical worker prompt template — including the lead-owned claim
handshake and `--close --suggest-next` lifecycle — lives directly in the parent
SKILL.md under "Node Worker Prompt Contract." Render it from Beads:

```bash
python3 ~/.claude/skills/_shared/scripts/br_helpers.py hydrate-node <issue-id>
python3 ~/.claude/skills/_shared/scripts/br_helpers.py render-node-brief <issue-id>
```

Do not duplicate the template here, and do not repair missing worker context by
hand-editing `EXECUTION_CONTEXT.md`.

The minimum Beads-backed node brief must carry:
- `br` issue ID
- run directory path (for the `WG-*_RESULT.md` artifact)
- the node's concern, depends_on, writes, done_when, validate, risk_gate
- attribution preamble: `export BR_AGENT_NAME=… BR_HARNESS=… BR_MODEL=…`
- model route: Claude Opus for design-related nodes; Codex gpt-5.5 for
  everything else
- verified claim state: the lead must have run `br update <id> --claim` for
  the assigned worker, and the worker must verify `br show <id>` reports
  `status=in_progress` plus the expected assignee before editing
- the lifecycle commands (`br show` claim verification,
  `br close --reason --suggest-next`, `br update -s blocked --notes …`)

## Result Artifact

Each worker still writes `<NODE_ID>_RESULT.md` (e.g. `WG-001_RESULT.md`) for
prose evidence and validation output. It is an evidence attachment, not the
source of status, write scope, or acceptance criteria. Required sections:
- `Status`: `done | blocked | needs_rework` (mirrors the `br` state but acts
  as belt-and-suspenders if the worker forgot the `br close`)
- `Summary`: what changed
- `Files Changed`: explicit file list
- `Validation`: each command plus pass or fail
- `Workgraph Notes`: any suggested graph edits (the orchestrator decides
  whether to apply via `br update` or by minting/closing issues)
- `Blockers`: only when relevant

The orchestrator independently re-runs `validate_cmds` and reconciles `br`
state before treating the node `done`.

These node result files belong in the same invocation run directory as
`EPIC_ID.txt` and any rendered views, not in the repo root.

## Mini Example

A valid 4-node slice for a review-driven skill update:

```text
WG-001 review latest usage traces     writes: (none)                  ready
WG-002 patch skill contract           writes: skill/SKILL.md          blocked on WG-001
WG-003 add supporting reference       writes: skill/references/**     blocked on WG-001
WG-004 validate updated skill         writes: (none)                  blocked on WG-002, WG-003
```

In `br`:

```bash
W1=$(python3 br_helpers.py mint-node wg-001-review 'Review latest usage traces' \
       --epic "$EPIC" --concern review --repo current-repo \
       --done-when 'Findings written' --validate 'echo done')
W2=$(python3 br_helpers.py mint-node wg-002-patch 'Patch skill contract' \
       --epic "$EPIC" --concern skill-edit --repo current-repo \
       --writes 'skill/SKILL.md' --depends-on "$W1" \
       --done-when 'Edits applied' --validate 'quick_validate.py')
W3=$(python3 br_helpers.py mint-node wg-003-ref 'Add supporting reference' \
       --epic "$EPIC" --concern skill-edit --repo current-repo \
       --writes 'skill/references/**' --depends-on "$W1" \
       --done-when 'Reference added' --validate 'quick_validate.py')
python3 br_helpers.py mint-node wg-004-validate 'Validate updated skill' \
       --epic "$EPIC" --concern validate --repo current-repo \
       --depends-on "$W2" --depends-on "$W3" \
       --done-when 'quick_validate passes' --validate 'quick_validate.py'
```

The wave model is the same:
- `WG-001` launches first (read-only)
- `WG-002` and `WG-003` can run in the same wave because their `--writes` do
  not overlap
- `WG-004` waits until the patch wave completes, then validates the merged
  result. `br ready` will surface it automatically once both predecessors close.
