# MMDX Human Checkpoint Review

Use this when Phase 6b reaches `100/100`, or any time a human is being asked to
approve, revise, block, or choose where a slice plan should be saved.

## Purpose

`review.mmdx` is the human-facing drilldown surface for a domain plan. It must
capture every decision-grade detail from the current plan while keeping the six
plan files canonical.

Source of truth:
- `plan.md` owns business value, core win, user stories, decisions, non-goals,
  performance envelope, DB transition notes, and open questions.
- `shared.md` owns endpoints, request/response shapes, error codes, runtime
  contract, and shared business-rule names.
- `backend.md` owns backend rules, permissions, data behavior, jobs, and
  backend acceptance scenarios.
- `frontend.md` owns screens, states, interactions, roles, empty/loading/error
  behavior, and frontend acceptance scenarios.
- `flows.md` owns user journeys, service interactions, state transitions, and
  failure paths.
- `schema.mmd` owns entity relationships.
- `WORKGRAPH.md` owns post-sign-off implementation nodes when it exists.

## Required MMDX Stack

Use the `mmdx` skill's chart-stacking contract. The entry chart must be a
decision surface, not a decorative index. Use this stable stack unless a slice
has a clearly better chart family:

| Chart ID | Chart Type | Must Capture |
|----------|------------|--------------|
| `main` | `flowchart LR` | Verdict, source files, and links to the major review areas |
| `core-scope` | `flowchart TD` or `mindmap` | primary actor, visible outcome, minimum winning slice, stories, acceptance coverage, non-goals, deferred debt |
| `contract-data` | `flowchart TD` plus ER detail or linked `erDiagram` | endpoints, request/response shapes, error codes, runtime/backpressure contract, entities, relationships, sibling FKs |
| `runtime-behavior` | `sequenceDiagram`, `stateDiagram-v2`, or `flowchart TD` | flows, backend rules, permissions, frontend states, performance envelopes, DB transition runbook if any |
| `decision-risk` | `quadrantChart` plus detail flowchart when needed | decisions, alternatives rejected, risk severity, confidence, open questions, blockers |
| `execution-handoff` | `gantt` or `flowchart TD` | WORKGRAPH nodes, dependencies, writes ownership, validation commands, risk gates |

Use second-level links only when a child chart is too dense. Good second-level
targets:
- `story-coverage`: every story mapped to acceptance criteria and test scenarios.
- `api-errors`: every endpoint mapped to response shapes and error codes.
- `schema-detail`: the full entity relationship diagram from `schema.mmd`.
- `frontend-detail`: every screen, role, state, and interaction.
- `backend-detail`: every rule, permission, job, and edge case.
- `performance-detail`: each SLO, load assumption, backpressure behavior, and
  verification method.

## Required Link Labels

Keep these labels short, unique, and exactly visible in the source chart:

```json
[
  {"from": "main", "label": "Core win and scope", "to": "core-scope"},
  {"from": "main", "label": "Contract and data", "to": "contract-data"},
  {"from": "main", "label": "Runtime behavior", "to": "runtime-behavior"},
  {"from": "main", "label": "Decision and risk", "to": "decision-risk"},
  {"from": "main", "label": "Execution handoff", "to": "execution-handoff"}
]
```

Add second-level links only after those five are present. Do not link every node
by default; link the nodes a reviewer needs to click to decide approve, revise,
or block.

## Chart-Crimes-Style Visual Grammar

Make the chart argue truthfully:

- **Title as verdict:** the entry chart answers `READY`, `REVISE`, or
  `BLOCKED`, not just `{slice} review`.
- **Subtitle as method:** include a source/method node such as `Source: 6 plan
  files + WORKGRAPH if present`.
- **Dominant recommendation:** the preferred human action has the strongest
  visual class and a status prefix.
- **Direct labels:** label the exact thing that proves the recommendation:
  `READY: 8 stories map to endpoints`, `BLOCKED: 2 open questions affect API`.
- **Sorted risk:** in risk charts, put blockers/high risks closest to the
  verdict path or in the highest-urgency quadrant.
- **Visible disclosure:** include an honesty ledger in a comment or chart node.

Use one color meaning per chart. For checkpoint reviews, color normally means
status/severity:

```mermaid
classDef high fill:#fee2e2,stroke:#dc2626,color:#7f1d1d,stroke-width:2px
classDef med fill:#fef3c7,stroke:#d97706,color:#78350f,stroke-width:2px
classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d,stroke-width:2px
classDef unknown fill:#f3f4f6,stroke:#6b7280,color:#111827,stroke-dasharray: 4 3
classDef neutral fill:#f8fafc,stroke:#64748b,color:#0f172a
classDef decision fill:#ede9fe,stroke:#7c3aed,color:#3b0764,stroke-width:2px
classDef recommended fill:#d1fae5,stroke:#059669,color:#064e3b,stroke-width:3px
```

Never rely on color alone. Every status-bearing node must include a label prefix
such as `READY`, `REVISE`, `BLOCKED`, `HIGH`, `MED`, `OK`, or `UNKNOWN`.

## Completeness Checklist

Before opening the checkpoint, confirm `review.mmdx` contains:

- Every user story and acceptance/test coverage summary.
- Every endpoint, request/response shape family, auth requirement, and error code.
- Every entity and relationship from `schema.mmd`.
- Every backend rule, permission rule, background job, and key edge case.
- Every frontend screen, role, state, interaction, loading/empty/error state.
- Every user journey and failure/recovery path from `flows.md`.
- Every performance SLO, load assumption, backpressure rule, and verification method.
- Every major decision, rejected alternative, and out-of-scope/non-goal.
- Every unresolved open question, risk, human-only gate, and blocker.
- Every WORKGRAPH node, dependency, writes ownership, validation command, and
  risk gate once `WORKGRAPH.md` exists.

## Honesty Ledger

Put this ledger in the MMDX file as an HTML comment near the top:

```markdown
<!-- honesty-ledger
Source: plan.md, shared.md, backend.md, frontend.md, flows.md, schema.mmd, WORKGRAPH.md if present
Unit and denominator: decision-grade plan details; all canonical plan files included
Transform: plan details mirrored into linked Mermaid charts for review
Filter or category selection: only implementation code and file-tree details omitted by spec boundary
Axis/domain: risk charts use confidence x blocking effect; execution charts use dependency order
Caveat: review.mmdx is a checkpoint mirror, not the source of truth
-->
```

If the MMDX omits anything from the source files, state the omission and reason
in the ledger.

## Validation

Run both commands before presenting the checkpoint:

```bash
python3 ~/.claude/skills/mmdx/scripts/mmd.py {plan_root}/{slice}/review.mmdx --preflight-only
python3 ~/.claude/skills/mmdx/scripts/mmd.py {plan_root}/{slice}/review.mmdx --open
```

If the human requests changes, update the canonical plan files first, then
update `review.mmdx`, rerun preflight, and present the refreshed chart stack.
