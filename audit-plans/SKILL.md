---
name: audit-plans
description: Audit domain plans and session plans with audit, prioritize, investigate, focus, and quick modes. Use for backlog hygiene, plan status checks, dependency review, consolidation work, or deciding what to work on next.
---

# Audit Plans

Five modes: **audit** (default), **quick**, **prioritize**, **investigate**, and **focus**.

This skill is intentionally generic. Tracked files describe the reusable workflow; workspace-specific paths, repo groupings, and validation commands live in a gitignored mode file.

**Companion skills:**
- `/domain-reviewer retire {slice}` for consolidating completed domain slices
- `/domain-reviewer retire-claude-plans` for consolidating completed session plans

**Shared orchestration rules:** use
[references/orchestration-contract.md](references/orchestration-contract.md)
for background-task handling and worker ownership.

## Mode Contract

Before reading or mutating any real plan catalog, load `modes/config.sh` if it exists.
If it does not exist, ask the user for the missing locations instead of guessing.

Create a local mode from
[references/mode-template.sh](references/mode-template.sh). `modes/` is gitignored and must stay untracked.

Expected exports:

- `PLAN_ROOT`: top-level directory that contains the plan catalog
- `RELEASED_INDEX`: released/current domain-plan index
- `PLANNED_INDEX`: planned/future domain-plan index
- `SESSION_INDEX`: session-plan index
- `SESSION_PLAN_GLOB`: glob for session plan files, for example `"${PLAN_ROOT}/session-plans/*.md"`
- `PLAN_DIRS`: space-separated domain-plan roots to audit, for example `"${PLAN_ROOT}/released ${PLAN_ROOT}/planned"`
- `MERMAID_VALIDATE_CMD` (optional): command to validate diagrams in the catalog
- `FOCUS_RELATED_REPOS` (optional): newline-separated `repo=repo1,repo2` mappings for focus mode

Optional conventions:

- domain slice folders may contain `plan.md`, `shared.md`, `backend.md`, `frontend.md`, or `COMPLETED.md`
- session plans may use `parent:` frontmatter pointing to a slice name or slice path
- index rows may include `STATUS`, `PRIORITY`, and free-text descriptions with domain/repo tags

## Mode Selection

| Trigger | Mode | Action |
|---------|------|--------|
| `/audit-plans` | Audit | Dashboard: status, integrity, hierarchy, sequencing, cleanup suggestions |
| `/audit-plans quick` | Quick Check | Single-plan relevance and index placement check |
| `/audit-plans prioritize` | Prioritize | Deep-read plans, verify statuses against code, assign priorities |
| `/audit-plans prioritize [billing]` | Prioritize (scoped) | Same, filtered to a domain tag |
| `/audit-plans prioritize app-api` | Prioritize (scoped) | Same, filtered to a repo tag |
| `/audit-plans investigate` | Investigate | Deep-read active + upcoming plans, verify implementation status, propose execution order |
| `/audit-plans investigate --include-done` | Investigate (all) | Include completed plans for a full recheck |
| `/audit-plans focus` | Focus | Auto-detect repo from cwd, output prioritized user story backlog |
| `what are we working on next here` | Focus | Same, natural-language trigger |
| `what's next` / `what's the plan here` | Focus | Same, natural-language trigger |
| `is this plan relevant anymore` | Quick Check | Same, one-plan relevance and indexing check |
| `investigate backlog depth` | Investigate | Same, implementation verification pass |
| `verify implementation status` | Investigate | Same, deep status + dependency review |
| `recalibrate priorities` | Investigate | Same, non-done status and ordering review |

**For prioritize mode:** read [references/prioritize-mode.md](references/prioritize-mode.md).
**For investigate mode:** read [references/investigate-mode.md](references/investigate-mode.md).
**For focus mode:** read [references/focus-mode.md](references/focus-mode.md).

Key prioritize rules:

- same priority number means concurrent and intentionally parallel
- verify `IN_PROGRESS` plans against code before preserving that status
- clear stale priorities from `DONE` plans
- present proposed priority edits before applying them

## Quick Check Mode

Use this for fast, single-plan relevance and indexing checks instead of a full catalog audit.

1. Read every configured index and locate the target plan.
2. Report indexed location, `STATUS`, `PRIORITY`, date, and description.
3. Verify the referenced plan path exists.
4. Flag immediate integrity issues:
   - unindexed plan
   - index points to missing file or folder
5. Read only the target plan's opening section for dependency context (`Depends on:` / `parent:`).
6. Return one of:
   - `KEEP`
   - `ARCHIVE CANDIDATE`
   - `BLOCKED`
7. Keep output concise:
   - no mermaid validation unless the plan itself is diagram-focused
   - no bulk remediation list
   - if broader cleanup is needed, hand off to full audit mode

## Files

All real file locations come from the active mode.

- **Released index:** `${RELEASED_INDEX}`
- **Planned index:** `${PLANNED_INDEX}`
- **Session index:** `${SESSION_INDEX}`
- **Domain plan roots:** `${PLAN_DIRS}`
- **Session plans:** `${SESSION_PLAN_GLOB}`

Never hardcode repo-specific plan roots in tracked files.

## Workflow

1. Load mode config or ask for the missing catalog locations.
2. If `MERMAID_VALIDATE_CMD` is set, launch it in the background.
3. Read all configured indexes.
4. Parse rows and compare them against the real plan files/folders.
5. Build a dependency graph from `Depends on:` and `parent:` references.
6. Audit status consistency and FUTURE/PLANNING sequencing.
7. Group session plans under their parent slice when possible.
8. Display summary with hierarchy, blocker, and sequencing issues.
9. Collect background validation results if a validator was started.
10. Offer concrete fixes or next actions.

## Background Diagram Validation

If the mode provides `MERMAID_VALIDATE_CMD`, start it immediately and let it run while the main audit proceeds.

Example mode value:

```bash
export MERMAID_VALIDATE_CMD='cd "$PLAN_ROOT" && npm run docs:validate-mermaid'
```

Why background: diagram validation can take several seconds and should not block index or dependency review.

### Collecting Results

After the index and dependency pass, retrieve the background task output and summarize only failures.

Look for:

- success lines for valid diagrams and ignore them
- failing diagram paths plus parse errors or line numbers

### Fixing Broken Diagrams

When broken diagrams are found, offer to fix them.

Auto-fix worker brief:

```text
Fix the diagram at {path}.

Error: {error_message}

1. Read the file.
2. Repair the syntax or structure issue.
3. Re-run the configured diagram validation command.
4. Return the exact change and the verification result.
```

## Integrity Checks

### Detecting Unindexed Domain Plans

Use the mode's directory roots and index links instead of hardcoded paths.

1. Enumerate plan directories under each entry in `PLAN_DIRS`.
2. Extract linked slice names from the corresponding index.
3. Report folders that exist on disk but are absent from the index as **UNINDEXED**.

### Detecting Orphaned Session Plans

1. Enumerate session plan files from `SESSION_PLAN_GLOB`.
2. Extract linked plan names from `SESSION_INDEX`.
3. Report files that exist on disk but are absent from the index as **ORPHANED**.

## Parent-Child Hierarchy And Dependency Graph

### Building The Graph

For each domain slice, read the plan header and look for:

1. `Depends on:` references
2. a `## Dependencies` section
3. domain or repo tags in the index description

For each session plan, read the opening frontmatter:

- `parent: standalone` means independent
- `parent: null` means unassigned and should be flagged
- `parent: path/to/slice` means child of that slice
- `parent: slice_name` means shorthand reference to a domain slice

### Hierarchy Validation

Flag these issues:

| Issue | Severity | Example |
|-------|----------|---------|
| Broken parent ref | ERROR | Session plan points to non-existent slice |
| Missing parent frontmatter | WARN | Session plan has no `parent:` field |
| `parent: null` | INFO | Plan needs domain assignment |
| Dependency on non-existent slice | ERROR | `Depends on: auth-foundation` but no such slice exists |
| Circular dependency | ERROR | A depends on B and B depends on A |
| FUTURE depends on FUTURE with no ordering | WARN | Blocker chain exists but priority order is missing |

### Hierarchy Display

Show the graph as an indented tree grouped by domain tag when tags exist.

```text
## Plan Hierarchy

### [billing]
  invoice-foundation (DONE) -- base
  payment-reconciliation (IN_PROGRESS P1) -- depends on: invoice-foundation
    settlement-ledger-followup (FUTURE) -- session child

### [auth]
  access-control (FUTURE P2) -- base
  tenant-roles (FUTURE P3) -- depends on: access-control

### Unaffiliated
  speedy-spark (FUTURE P4) -- standalone session plan
```

Rules:

- group by the first domain tag when one exists
- indent dependency chains and child session plans
- show status and priority inline
- place standalone or untagged plans in an unaffiliated section

## Sequencing Audit

Priority rules:

1. blockers must never rank below their dependents
2. independent work can share a priority number
3. `IN_PROGRESS` work stays at the front unless it is actually done or stale
4. `DONE` plans should not keep active priority numbers

When the catalog violates those rules, explain the exact conflict and propose a corrected order before editing any index.
