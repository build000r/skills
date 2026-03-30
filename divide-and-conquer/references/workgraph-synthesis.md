# Workgraph Synthesis

Use this when `divide-and-conquer` should orchestrate parallel work but no
durable `WORKGRAPH.md` exists yet.

## Temporary Path

Create a temp directory first, then place a canonical `WORKGRAPH.md` inside it.
Example:

```bash
workgraph_dir="$(mktemp -d "${TMPDIR:-/tmp}/dac-workgraph-XXXXXX")"
workgraph_path="$workgraph_dir/WORKGRAPH.md"
```

Keep the filename `WORKGRAPH.md` so the artifact matches the existing parser and
cross-skill conventions. Do not commit the temp file unless the user explicitly
asks to preserve the graph.

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
- Encode dependencies in `depends_on`, not in narrative prose
- Use concrete `writes` so wave grouping can detect overlap
- Use concrete `done_when` and `validate_cmds`; placeholder language means the
  node is not ready

## When To Trigger `describe`

Trigger a node-level `describe` pass before launch when any of these are true:
- `done_when` would otherwise be vague or subjective
- `validate_cmds` are missing or hand-wavy
- The node has a real scope or behavior decision still unresolved
- The worker would need to guess the non-goals

Do not run `describe` for every node by default. Use it to tighten fuzzy nodes,
then rewrite the node and recompute the ready frontier.

## Describe-Style Worker Brief

Every worker prompt should carry the workgraph path and node ownership.

Template:

```text
You own one workgraph node.

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

If anything above is ambiguous enough that you would guess, stop and return the
single smallest ask-cascade question or a proposed WORKGRAPH edit instead of
coding past it.
```

## Mini Example

This is a valid temp graph shape for a review-driven skill update:

```text
WG-001 review latest usage traces     writes: None                      ready
WG-002 patch skill contract           writes: skill/SKILL.md            blocked on WG-001
WG-003 add supporting reference       writes: skill/references/**       blocked on WG-001
WG-004 validate updated skill         writes: None                      blocked on WG-002, WG-003
```

The graph makes the dependency explicit:
- `WG-001` can run first as Explore/read-only work
- `WG-002` and `WG-003` can run in parallel only if their writes do not overlap
- `WG-004` waits until the patch wave completes
