# Investigate Mode

Use this when the user wants a full plan recalibration:

- verify every active and upcoming plan against code
- decide what is actually done versus not done
- suggest a concrete execution order and priority update

## Trigger

- `/audit-plans investigate`
- `/audit-plans investigate [billing]`
- `/audit-plans investigate app-api`
- `/audit-plans investigate --include-done`
- natural language such as `investigate backlog depth`, `verify implementation status`, or `recalibrate priorities`

`/audit-plans investigate` excludes `DONE` plans by default.
Use `--include-done` only when the user wants a full recheck.

## Required Scope

- default: every `IN_PROGRESS`, `FUTURE`, and `PLANNING` row across all configured indexes
- scoped: only rows matching the requested domain tag or repo tag
- exclude `DONE` unless explicitly requested

## Workflow

1. Launch the optional diagram validator exactly as in base audit mode.
2. Build the candidate set from the configured indexes.
3. Split the candidate set into disjoint batches when parallel review is worthwhile.
4. For each batch, run a read-only verification brief:

```text
Investigate each plan in this batch and verify implementation progress in code.

Return only:
- plan name
- status verdict: DONE, IN_PROGRESS, STALE, or BLOCKED
- evidence file paths
- unresolved items
```

5. Per-plan verification rubric:
   - domain slice plans: read `plan.md` plus nearby supporting docs, then search code for each deliverable
   - session plans: read the full file, then search for the named artifacts and parent context
6. Merge findings and normalize verdicts:
   - `DONE`: all key deliverables are present
   - `IN_PROGRESS`: clear partial implementation exists
   - `STALE`: marked active but lacking recent or meaningful code evidence
   - `BLOCKED`: depends on missing or incomplete prerequisite work
7. Rebuild the sequencing graph from `Depends on:` and `parent:`.
8. Produce a recommended execution order and priority adjustment.
9. Summarize integrity issues and ask before editing any index.

## Output Format

```text
## Investigate Results

### Status Summary
| Plan | Type | Current | Evidence | Primary Blocker | Suggested Next |
|------|------|---------|----------|-----------------|----------------|
| payment-reconciliation | Domain | IN_PROGRESS | api/payments/*, ui/reports/* | none | Keep status |
| tenant-roles-followup | Session | BLOCKED | none | access-control incomplete | Revisit after blocker |

### Execution Order
1. access-control — unblocks the rest of the auth chain
2. payment-reconciliation — already active and close to done
3. tenant-roles — dependency clears after access-control

### Priority Proposal
| Plan | Suggested Priority | Basis | Confidence |
|------|--------------------|-------|------------|
| access-control | P1 | blocker for downstream auth work | high |
| payment-reconciliation | P1 | already in progress | high |
| tenant-roles | P2 | depends on access-control | high |
```

Append diagram or integrity failures only when they exist.

## Suggested Actions

- apply the proposed priorities
- show the proposal as an edit plan first
- keep current priorities unchanged
- hand completed slices to `domain-reviewer` for consolidation

## Edge Cases

- if every candidate is already done, say so clearly
- if evidence is ambiguous, lower confidence and show the missing proof
- if a plan's parent is missing, flag it as an integrity issue before reprioritizing it
