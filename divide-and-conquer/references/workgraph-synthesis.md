# Workgraph Synthesis

Use this when `divide-and-conquer` should orchestrate execution through the
default swarm runtime but no durable `WORKGRAPH.md` exists yet.

## Temporary Path

Create an invocation run directory under the active client overlay first, then
place a canonical `WORKGRAPH.md` inside it. Do not use `/tmp` when an overlay is
available.

Expected shape:

```text
{invocation_root}/{repo_slug}/divide-and-conquer/{run_id}/WORKGRAPH.md
```

Example:

```bash
workgraph_dir="{invocation_root}/{repo_slug}/divide-and-conquer/{run_id}"
mkdir -p "$workgraph_dir"
workgraph_path="$workgraph_dir/WORKGRAPH.md"
```

Keep the filename `WORKGRAPH.md` so the artifact matches the existing parser and
cross-skill conventions. Do not commit the temp file unless the user explicitly
asks to preserve the graph.

If a durable workgraph already exists in a plan directory, do not copy it over
blindly. Read it in place and write a pointer file like `WORKGRAPH_SOURCE.txt`
into the invocation run directory instead.

## What Goes In The Temp Graph

Use the same node shape as the durable domain-planner workgraph:

```json
{
  "nodes": [
    {
      "id": "WG-001",
      "title": "Short executable unit",
      "concern": "backend-api",
      "repo": "current-repo",
      "depends_on": [],
      "writes": ["path/or/glob/**"],
      "done_when": ["Binary completion check"],
      "validate_cmds": ["Concrete validation command"],
      "risk_gate": "none",
      "status": "todo"
    }
  ]
}
```

Rules:
- Keep the graph narrow: current execution slice only, usually 2-8 nodes
- One node per executable concern, not per tiny file edit
- Encode dependencies in `depends_on`, not narrative prose
- Use concrete `writes` so wave grouping can detect overlap
- Use concrete `done_when` and `validate_cmds`; placeholder language means the
  node is not ready
- Use `writes: []` only for truly read-only nodes

## When To Trigger `describe`

Trigger a node-level `describe` pass before swarm launch when any of these are
true:
- `done_when` would otherwise be vague or subjective
- `validate_cmds` are missing or hand-wavy
- The node still has a real scope or behavior decision unresolved
- The worker would need to guess non-goals or ownership boundaries

Do not run `describe` for every node by default. Use it to tighten fuzzy nodes,
then rewrite the node and recompute the ready frontier.

## Swarm Node Brief

Every wave worker prompt should carry the workgraph path and node ownership.

Template:

```text
You own one divide-and-conquer workgraph node inside an execution swarm.

Workgraph: <path-to-WORKGRAPH.md> (durable | temp)
Node: <WG-001> - <title>
Concern: <concern>
Depends on: <ids already satisfied, or None>
Writes: <paths/globs, or None>

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
- Stay inside the repo and the declared write scope
- Do not commit
- If the node really needs broader edits, stop and propose the smallest WORKGRAPH edit
- Write `WG-001_RESULT.md` with status, files changed, and validation proof
```

## Result Artifact

Each worker should write `<NODE_ID>_RESULT.md` such as `WG-001_RESULT.md`:
- `Status`: `done | blocked | needs_rework`
- `Summary`: what changed
- `Files Changed`: explicit file list
- `Validation`: each command plus pass or fail
- `Workgraph Notes`: any suggested graph edits
- `Blockers`: only when relevant

The orchestrator independently re-runs `validate_cmds` before marking the node
done.

These node result files belong in the same invocation run directory as the
temp `WORKGRAPH.md`, not in the repo root.

## Mini Example

This is a valid temp graph shape for a review-driven skill update:

```text
WG-001 review latest usage traces     writes: []                      ready
WG-002 patch skill contract           writes: skill/SKILL.md          blocked on WG-001
WG-003 add supporting reference       writes: skill/references/**     blocked on WG-001
WG-004 validate updated skill         writes: []                      blocked on WG-002, WG-003
```

The graph makes the wave model explicit:
- `WG-001` launches first as a read-only execution node
- `WG-002` and `WG-003` can run in the same wave only if their writes do not overlap
- `WG-004` waits until the patch wave completes and then validates the merged result
