# Orchestration Contract

Use this contract when `audit-plans` needs background work or parallel verification.

## Rules

1. The main thread owns plan-index edits and final synthesis.
2. Background workers are read-only unless the main thread explicitly delegates a repair.
3. Every worker brief must name:
   - the exact plan files it may read
   - whether it may write
   - the required return format
4. Do not launch overlapping write scopes.
5. If a background validator fails to start, continue the audit and note that validation was skipped.

## Recommended Worker Shapes

- **Diagram validator:** read the plan catalog, return only failing files and errors
- **Status verifier:** inspect one plan or a small batch, return verdict plus evidence
- **Diagram fixer:** write only the named diagram file and rerun validation

## Required Return Format

Workers should return compact, mergeable results:

```text
Plan: {name}
Verdict: DONE | IN_PROGRESS | STALE | BLOCKED
Evidence:
- path/to/file
- path/to/other/file
Open questions:
- ...
```

Keep orchestration rules in tracked files generic. Put runtime-specific wrappers or commands in the local mode file.
