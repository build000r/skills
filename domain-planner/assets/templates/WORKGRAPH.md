# {slice_name} Workgraph

> Post-plan execution handoff for the accepted `{slice_name}` slice.
> Keep the 6 plan files spec-only. Put execution decomposition, dependency edges,
> validation commands, and write ownership here after sign-off.

---

## Status Rules

- `todo` - not started; becomes ready when all dependencies are `done` or `skipped`
- `in_progress` - currently owned by an execution wave
- `done` - completed and validated
- `blocked` - waiting on an external prerequisite or decision
- `skipped` - intentionally not executed in this slice

If two nodes overlap in `writes`, they do not belong in the same parallel wave.

---

## Nodes

```json
{
  "nodes": []
}
```

---

## Node Contract

Each node in the JSON block must use this shape:

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | Yes | Stable node ID, e.g. `WG-001` |
| `title` | Yes | Short executable unit |
| `concern` | Yes | Concern owner, e.g. `backend-api`, `frontend-widget`, `migration`, `tests` |
| `repo` | Yes | Repo or surface this node belongs to |
| `depends_on` | Yes | Array of node IDs that must be `done` or `skipped` first |
| `writes` | Yes | Array of paths/globs this node expects to mutate |
| `done_when` | Yes | Array of binary completion checks |
| `validate_cmds` | Yes | Array of commands the implementation wave should run |
| `risk_gate` | Yes | `none` or a short description of what must be confirmed first |
| `status` | Yes | `todo`, `in_progress`, `done`, `blocked`, or `skipped` |

Prefer 4-12 meaningful nodes for a normal slice. If the graph grows beyond that,
you are probably decomposing too finely.
