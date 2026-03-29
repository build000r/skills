# Retire-Session Workflow

For DONE session plans: roll stories into domain COMPLETED.md files, archive originals.

Public command name:
`/domain-reviewer retire-claude-plans`

Legacy phrasing such as `retire session plans` and legacy command spellings may
still be accepted as compatibility triggers, but the documented command name is
`retire-claude-plans`.

## When to Use Retire-Session Mode

- User says "retire session plans", "consolidate session plans", "clean up session plans"
- User runs `/domain-reviewer retire-claude-plans`
- Periodic cleanup of accumulated DONE session plans
- Goal: reduce session plan index bloat while preserving story credit in domain plans

## Critical Safety Rule

**ONLY process plans marked `DONE` in the session plan index.**

- `IN_PROGRESS` - NEVER touch (active work)
- `FUTURE` - NEVER touch (backlog)
- `DEVIATED` - NEVER touch (needs review first)
- `DONE` - **Only these** are candidates for retirement

The user marks plans DONE manually. This mode consolidates those already-completed ones.

## Retire-Session Process Overview

```
1. Read session plan index, filter to DONE status only
2. For each DONE plan:
   a. Check for existing parent: frontmatter
   b. If no parent, parse tags and suggest domain
   c. Present grouped suggestions to user
3. User confirms domain assignments (batch)
4. For confirmed matches:
   a. Append one-liner to domain's COMPLETED.md
   b. Move session plan to session-plans/_archived/
   c. Remove from session plan index
5. For orphans/misc:
   a. Append to misc-session-work/COMPLETED.md
   b. Archive same way
```

## Worker Parallelization Strategy

For large batches (>20 DONE plans), run parallel workers to speed up processing while avoiding race conditions.

This workflow assumes same-repo execution (no extra worktrees required):

- Assign explicit file ownership per worker.
- Shared files (`session_plan_index`, `plan_index`) are orchestrator-owned and edited sequentially.
- Workers must not revert/reset other workers' changes.

### Phase 1: Parallel READ (safe)

Run 4 workers to read plan files in batches -- no conflicts because read-only:

```
Worker 1: Read plans 1-15, extract: name, tags, one-liner summary
Worker 2: Read plans 16-30
Worker 3: Read plans 31-45
Worker 4: Read plans 46-60
```

Each worker outputs a table:
```markdown
| Plan | Tag | One-liner | Parent |
|------|-----|-----------|--------|
```

**Why safe:** Read operations never conflict.

### Phase 2: User Confirmation (sequential)

Present grouped domain suggestions, get user approval. This phase requires human input -- no parallelization possible.

### Phase 3: Parallel WRITE by Domain (safe if isolated)

Each worker owns ONE domain's COMPLETED.md -- no overlap:

```
Worker A: [recipes] -> recipes/COMPLETED.md (6 plans)
Worker B: [insights] -> key-insights/COMPLETED.md (8 plans)
Worker C: [scheduling] + [auth] + smaller domains (10 plans)
Worker D: [misc] -> misc-session-work/COMPLETED.md (28 plans)
```

**Why safe:** Each worker only touches its assigned COMPLETED.md file. No two workers write to the same file.

**Worker prompt template:**
```
Update {domain}/COMPLETED.md by appending session plan stories.

Plans to add:
1. `plan-name` - Description
2. ...

Instructions:
1. Read existing COMPLETED.md
2. Find "## What Users Can Now Do" section
3. Append items using format: `- **[Session] {description}** - Consolidated from session plan (2026-01)`
4. Update story count: find `**Stories:** X✓ Y→` and increment X
5. Write updated file
```

### Phase 4: Sequential Cleanup (must be single-threaded)

These operations touch shared files -- must run sequentially:

1. Move all plan files to `_archived/` (single bash command)
2. Update session plan index (single file -- remove all DONE rows)
3. Update plan index story counts (single file)

**Why sequential:** The session plan index and plan index are single files. Parallel writes would cause race conditions.

### Example Execution

For 52 DONE plans:

| Phase | Workers | Time |
|-------|--------|------|
| Phase 1 (read) | 4 parallel | ~30s |
| Phase 2 (confirm) | sequential | ~10s |
| Phase 3 (write) | 4 parallel | ~45s |
| Phase 4 (cleanup) | sequential | ~15s |

**Total:** ~2 minutes vs ~8 minutes if fully sequential.

### When NOT to Parallelize

- **<10 plans:** Overhead of launching workers exceeds benefit
- **Single domain:** All plans go to same COMPLETED.md -- no parallelism possible
- **User wants granular control:** Step-by-step confirmation for each plan

## Step 1: Inventory DONE Plans

Read the mode's `session_plan_index`:

```markdown
| Date | Plan | Status | Priority | Description |
|------|------|--------|----------|-------------|
| 2026-01-21 | [plan-name](./plan-name.md) | DONE | | [auth] Description here |
```

Filter to rows where Status = `DONE`.

**Check for already-archived:** Skip any plans where the .md file already exists in `_archived/`.

## Step 2: Parse Tags and Suggest Domains

For each DONE plan:

1. **Check for `parent:` frontmatter** in the plan file itself:
   ```markdown
   ---
   parent: {plan_root}/chatroom
   ---
   ```
   If present, use that domain directly.

2. **If no parent, parse tags from description:**
   - Extract `[tag]` patterns from the Description column
   - Look up in the mode's tag-to-domain mapping
   - Suggest the mapped domain

3. **Multiple tags:** Use the first domain-specific tag (ignore repo-level tags).

4. **Tags mapping to `(misc)`:** These go to `misc-session-work` collector.

## Step 3: Present Grouped Suggestions

Group plans by suggested domain and present for confirmation:

```markdown
## Session Plan Retirement - 12 DONE plans to process

### [auth] -> auth (3 plans)

| Plan | Description |
|------|-------------|
| structured-sniffing-diffie | Auth edge case fix + hook consolidation |
| concurrent-humming-rainbow | Auth API-first migration |
| jaunty-leaping-trinket | Admin auth configuration UI |

**Merge these 3 into auth/COMPLETED.md?**

### [recipes] -> recipes (2 plans)

| Plan | Description |
|------|-------------|
| robust-mixing-tower | Add is_uncommon filter + chip suggestions |
| cozy-fluttering-lagoon | Recipe hiding system |

**Merge these 2 into recipes/COMPLETED.md?**

### misc (no domain match) (4 plans)

| Plan | Description |
|------|-------------|
| geo-minerals-research | Geographic mineral deficiency research task |
| lucky-splashing-wave | Coverage output improvements for pytest |
| ...

**Archive these to misc-session-work/COMPLETED.md?**

---

**Options:**
- [Proceed with all suggestions]
- [Let me pick different domains for some]
- [Skip certain plans]
```

Ask the user to confirm:
- Default: proceed with all suggestions
- User can override specific assignments
- User can skip plans they want to keep in the session plan index

## Step 4: Execute Consolidation

For each confirmed plan:

### 4a. Append to Domain COMPLETED.md

**Format for session plan stories:**
```markdown
## What Users Can Now Do

... existing stories ...

- **[Session] {description}** - Consolidated from session plan ({date})
```

The `[Session]` prefix distinguishes session plan work from formal slice stories.

**If COMPLETED.md doesn't exist:** Create it with minimal structure:
```markdown
# {Domain} - Completion Summary

**Domain:** [{tag}]
**Stories:** 0✓ 0→

## What Users Can Now Do

- **[Session] {description}** - Consolidated from session plan ({date})

## What's Deferred

(none from session plans - see formal slice plans)
```

**If COMPLETED.md exists:** Just append to "What Users Can Now Do" section.

### 4b. Archive the Session Plan

Move `{plan-name}.md` to `session-plans/_archived/{plan-name}.md`

Create `_archived/` if it doesn't exist.

### 4c. Remove from Session Plan Index

Delete the row from the index. The archived file serves as the historical record.

## Step 5: Handle misc-session-work

For plans with no clear domain (tags like `[data]`, `[infra]`, `[research]`):

### Create misc-session-work if needed

Location: `{plan_root}/misc-session-work/`

```markdown
# Miscellaneous Session Work - Completion Summary

**Consolidated:** {date}
**Domain:** [misc]
**Stories:** {N}✓ 0→

> This is a collector for standalone session plans that don't fit a formal domain.
> These were tactical improvements, research tasks, or infrastructure work.

## What Users Can Now Do

- **[Session] {description}** - Consolidated from session plan ({date})
- **[Session] {description}** - Consolidated from session plan ({date})
```

### Add to INDEX.md

If `misc-session-work` is new, add row to the mode's `plan_index`:
```markdown
| {date} | [misc-session-work](./misc-session-work/) | DONE | | [misc] Collector for standalone session work |
```

## Step 6: Update Story Counts

After consolidation, update the story count in each affected domain's INDEX.md row:

```markdown
| 2026-01-22 | [auth](./auth/) | DONE | 1 | [auth] Authentication and authorization (5✓ 2→) |
```

The `X✓` count should include the newly added session plan stories.

## Output Format

After completion, summarize:

```markdown
## Session Plan Retirement Complete

**Processed:** 12 DONE plans
**Archived to:** session-plans/_archived/

### Stories Added

| Domain | Plans Rolled In | New Total |
|--------|-----------------|-----------|
| auth | 3 | 8✓ 2→ |
| recipes | 2 | 6✓ 1→ |
| misc-session-work | 4 | 4✓ 0→ |
| scheduling | 2 | 5✓ 3→ |
| key-insights | 1 | 9✓ 4→ |

### Skipped (per user request)

- vast-swimming-sutton - User asked to keep in index

### Session Plan Index

Removed 12 rows. Remaining: 35 plans (8 IN_PROGRESS, 27 FUTURE)
```

## Questioning Strategy

Ask the user when:

1. **Domain assignment unclear:**
   ```
   Question: "Which domain should 'vast-swimming-sutton' (Mobile intake form blur fix) go to?"
   Options:
     - "auth (Recommended)" - Based on [auth] tag
     - "misc-session-work" - Keep as standalone, doesn't fit formal domain
     - "Skip this plan" - Leave in session plan index for now
   ```

2. **Batch confirmation:**
   ```
   Question: "Ready to consolidate 12 DONE session plans into their suggested domains?"
   Options:
     - "Proceed with all" - Merge all 12 plans as suggested above
     - "Let me review each" - Ask me about each domain assignment individually
     - "Abort" - Don't consolidate anything right now
   ```

## Related Files

- **Session plan index:** Mode's `session_plan_index` setting
- **Tag mapping:** Mode's tag-to-domain mapping table
- **Domain plans:** `{plan_root}/*/`
- **Archive location:** `session-plans/_archived/`
