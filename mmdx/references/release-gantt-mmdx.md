# Release Gantt MMDX Pattern

Use this pattern when a user needs to unblock a release, beta, deploy, or review flow and the state is spread across code, docs, CI, external dashboards, and human-only operations.

## Shape

- Entry chart: `gantt` for the timeline or `stateDiagram-v2` for gate state.
- Child chart: `flowchart` for proof status or exact next action.
- Child chart: `sequenceDiagram` for entitlement, auth, support, rollback, or reviewer flows.
- Child chart: `quadrantChart` only when prioritizing product-fit polish after the release gates are visible.

## What To Link

Link only items that help a human or agent act:

- `P0 Local proof`
- `P0 Human Apple step`
- `P0 Physical smoke`
- `P1 External review`
- `P1 Rollback`

Do not link every task. Dense link forests make the chart harder to operate.

## Label Rules

- Use short visible labels exactly as written in the chart.
- Prefix with priority/status when useful: `P0`, `P1`, `OK`, `BLOCKED`, `PARTIAL`.
- Put the owner or evidence in the child chart, not in the entry label.

## Human Touchpoints

Use MMDX to keep mandatory human work small. The child chart should name:

- exact external UI or device action
- account, build, or environment involved
- proof to collect
- resume condition for the agent

If the agent can continue around the human step, show that parallel work in the Gantt instead of stopping the whole plan.

## Verification

Always preflight the stack:

```bash
python3 /path/to/mmdx/scripts/mmd.py path/to/release-map.mmdx --preflight-only
```

For handoff or sharing, print the fragment:

```bash
python3 /path/to/mmdx/scripts/mmd.py path/to/release-map.mmdx --fragment-only --no-preflight
```
