# Prioritize Mode

Deep-read plans for a scope, verify `IN_PROGRESS` statuses against code, then assign or reassign priorities.

## Trigger

`/audit-plans prioritize [scope]`

Scope options:

- domain tag such as `[billing]` or `[auth]`
- repo tag such as `app-api`, `app-web`, or `ops-console`
- `all` or omitted for the entire catalog

## Priority Model

- lower number means higher priority
- same priority means intentionally concurrent
- `IN_PROGRESS` plans keep the earliest numbers because they are already underway
- `DONE` plans should not retain active priorities

## Workflow

### Phase 1: Collect Plans In Scope

1. Read `RELEASED_INDEX`, `PLANNED_INDEX`, and `SESSION_INDEX`.
2. Filter to the requested scope.
3. Collect all `IN_PROGRESS`, `FUTURE`, and `PLANNING` plans.
4. Also collect completed plans that still have stale priority markers.

### Phase 2: Verify `IN_PROGRESS` Statuses

For each `IN_PROGRESS` plan, launch a read-only verifier on that plan or on a small disjoint batch.

Worker brief:

```text
Determine if the plan at {plan_path} has been fully implemented.

1. Read the relevant plan file(s).
2. Identify the key deliverables.
3. Search the codebase for evidence:
   - functions, routes, jobs, components, migrations, or docs named in the plan
   - recent git activity tied to the deliverables
4. Return one verdict:
   - DONE
   - IN_PROGRESS
   - STALE
Include specific evidence paths and unresolved items.
```

For domain slices, read `plan.md` plus any adjacent `shared.md`, `backend.md`, or `frontend.md` files.
For session plans, read the full markdown file.

### Phase 3: Present Status Findings

Report findings in three buckets:

- confirmed `IN_PROGRESS`
- actually `DONE`
- stale or inactive

Ask before editing any status fields.

### Phase 4: Build Priority Graph

For remaining active and future plans:

1. parse `Depends on:` and `parent:` references
2. identify concurrency groups with no dependency relationship
3. separate foundational work from feature work and polish work

### Phase 5: Assign Priorities

Rules:

1. keep active `IN_PROGRESS` work at the top
2. blockers must rank ahead of dependents
3. independent work may share the same priority
4. cross-repo plans should be ranked by unblock value, not by repo name alone

Output shape:

```text
## Proposed Priority Assignment

### Keep Running
| Plan | Priority | Rationale |
|------|----------|-----------|
| payment-reconciliation | P1 | Already active and unblocked |

### Next Up
| Plan | Priority | Concurrent With | Rationale |
|------|----------|-----------------|-----------|
| access-control | P2 | reporting-foundation | Enables downstream auth work |

### Clear Stale Priorities
| Plan | Old Priority | Status | Action |
|------|--------------|--------|--------|
| invoice-foundation | P1 | DONE | Clear priority |
```

### Phase 6: Apply Changes

If the user approves:

1. update the affected index rows
2. clear stale priorities from completed plans
3. summarize the exact edits made

## Concurrency Detection

Two plans can share a priority only when all of these are true:

- neither depends on the other
- they do not target the same high-conflict area
- parallel work will not create obvious merge or sequencing risk

If concurrency is plausible but uncertain, present it as a question instead of silently assuming parallel safety.

## Edge Cases

- no non-done plans: report that there is nothing to prioritize
- circular dependency: flag it as an error and do not assign priorities
- incomplete plan file: use index metadata plus the available plan text and lower confidence accordingly
