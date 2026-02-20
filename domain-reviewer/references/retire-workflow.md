# Retire Workflow

For DONE slices: investigate user stories, consolidate learnings, archive stale files.

## When to Use Retire Mode

- Slice status is DONE in INDEX.md
- Implementation deployed and stable
- No active work expected
- Goal: lean archive focused on user impact, not code details

## Retire Process Overview

```
1. Verify slice is DONE (abort if not, suggest audit instead)
2. Extract user stories from plan.md
3. Investigate each story - is it actually complete?
4. Categorize: COMPLETE / DEFERRED / NEEDS_DISCUSSION
5. Research ambiguities, suggest resolutions
6. Ask user only when genuinely unclear
7. Generate COMPLETED.md (user-story-centric)
8. Archive stale files (with user confirmation)
```

## Step 1: Verify Status

Check the mode's `plan_index` for slice status:
- **DONE** -> Proceed with retire
- **IN_PROGRESS** -> "This slice is still in progress. Run audit mode instead?"
- **FUTURE** -> "This slice hasn't been started. Nothing to retire."
- **Not in INDEX.md** -> Ask user: "This slice isn't tracked in INDEX.md. Should I add it?"

## Step 2: Extract User Stories

**If plan.md exists** in the released folder, read it and extract user stories. Look for:
- Explicit "User Stories" or "Acceptance Criteria" sections
- "As a [user], I can [action]" patterns
- Feature bullets that describe user-facing behavior
- "Out of scope" items (these are pre-deferred)

**If NO plan.md exists** (slice was built ad-hoc or audited retroactively):
- Extract user stories from the implementation code (router endpoints, service methods, tests)
- Check AUDIT_REPORT.md if one exists (may document what was implemented)
- Look for deferred items via code comments (`deferred to`, `v2`, `TODO`)
- Look at code comments referencing other slices for cross-dependencies

Create a checklist:
```
[] US-1: User can create support thread
[] US-2: User can view their threads
[] US-3: Real-time message updates
[] US-4: File attachments (marked "v2" in plan)
[] US-5: Email notifications on new messages
```

## Step 3: Investigate Each Story

For each user story, research:

1. **Search codebase** for implementation evidence:
   - Routes/endpoints that serve this feature
   - UI components that render it
   - Tests that verify it

2. **Check for completeness signals:**
   - Feature works end-to-end (route -> service -> UI)
   - Has test coverage
   - No TODO/FIXME comments related to it
   - No placeholder/mock implementations

3. **Check for incompleteness signals:**
   - Partial implementation (backend done, frontend missing)
   - Commented-out code
   - Tests marked skip/pending
   - TODO comments referencing this story

4. **Check plan annotations:**
   - Marked "out of scope" or "v2" -> Pre-deferred
   - Marked "stretch goal" -> May be incomplete
   - Marked "blocked by X" -> Check if blocker resolved

## Step 4: Categorize Stories

Based on investigation, categorize each:

| Category | Criteria | Action |
|----------|----------|--------|
| **COMPLETE** | Full implementation, tests pass, no TODOs | Document in "What Users Can Now Do" |
| **DEFERRED** | Explicitly marked v2/future in plan, OR user confirms deferral | Document in "What's Deferred" with resolution status |
| **NEEDS_DISCUSSION** | Ambiguous - partial impl, unclear status, inconsistencies | Ask user with suggested resolution |

### Deferred Item Resolution States

For each DEFERRED item, determine its resolution status:

| Status | Marker | When to Use |
|--------|--------|-------------|
| **Open** | (no marker) | Still might be done later - default state |
| **Resolved** | `-> **Resolved** in \`{slice}\` ({date})` | Completed in a different slice |
| **Dismissed** | `-> **Dismissed** - {reason}` | Explicitly won't do (deprioritized, superseded, not aligned with product) |

**Ask user for each deferred item:**
```
Question: "What's the resolution status of '{deferred item}'?"
Options:
  - "Still open (Recommended)" - May be done in future, will appear in active deferred scans
  - "Resolved elsewhere" - Already completed in another slice, which one?
  - "Dismissed" - Won't do this, remove from active consideration
```

**Why this matters:**
- Kanban UI and agent scans filter to items **without** resolution markers
- "Resolved" and "Dismissed" items are archived-in-place but hidden from active views
- Reduces noise from stale deferred items that were completed elsewhere or abandoned

## Step 5: Handle Ambiguities

When a story is ambiguous, **research first, then ask with a suggestion**.

**Research approach:**
- Check git history: was work started then stopped?
- Check related slices: did this move elsewhere?
- Check if goal was achieved differently than planned

**Ask with suggestion:**

```
Question: "Email notifications (US-5) - I found partial implementation but it's not wired up. What happened?"
Options:
  - "Defer to v2 (Recommended)" - Mark as deferred, partial code stays, documented as future work
  - "Mark abandoned" - Remove from plan, this approach won't be pursued
  - "Keep as active work" - Don't retire yet, this needs to be finished first
```

**Always frame by user impact:**
- "This means users won't get notified when new messages arrive"
- "Impact: users must manually check for updates"

## Step 6: Generate COMPLETED.md

After categorization is confirmed, generate COMPLETED.md.

**See [completed-template.md](completed-template.md) for template.**

**Story count format (REQUIRED):**
```
**Stories:** X✓ Y→
```
Example: `**Stories:** 5✓ 8→`

Do NOT use prose like "5 complete, 8 deferred". The symbol format:
- Matches INDEX.md format `(X✓ Y→)`
- Enables automated parsing
- Is visually scannable

Key principles:
- **User stories, not code** - "Users can create threads" not "ThreadService.create() implemented"
- **Impact of deferrals** - Why it matters to users, not why it was hard to build
- **Resolution status on deferrals** - Mark as open (no marker), resolved, or dismissed
- **Decisions that matter** - Choices that affect user experience or future development
- **Gotchas for future work** - Things the next developer should know

**Deferred items format:**
```markdown
## What's Deferred

- **Shopping list generation** - Converting recipe ingredients to a shopping list
  (no marker = still open)

- **User favorites** - Personal recipe bookmarking
  -> **Resolved** in `recipe-personalization` (2026-02)

- **CSV export** - Export data as CSV
  -> **Dismissed** - Decided PDF-only covers all use cases
```

## Step 6b: Cross-Slice Resolution Updates

When this slice completes work that was deferred in another slice, update the old COMPLETED.md:

1. **Identify cross-slice resolutions:**
   - Check plan.md for "resolves deferred from X" notes
   - Ask user: "Does this slice complete any previously-deferred items from other slices?"

2. **Update old COMPLETED.md files:**
   ```markdown
   # In the OLD slice's COMPLETED.md, find the deferred item and add:

   - **Email notifications** - Sending emails on new messages
     -> **Resolved** in `email-templates` (2026-01)
   ```

3. **Format:** `-> **Resolved** in \`{this-slice}\` ({YYYY-MM})`

4. **Commit separately:** Make cross-slice updates a separate commit for clarity:
   ```bash
   git add {plan_root}/{old-slice}/COMPLETED.md
   git commit -m "resolve({old-slice}): mark '{item}' resolved in {new-slice}"
   ```

**Why this matters:**
- Keeps deferred lists clean across slices
- Prevents duplicate work (agent won't suggest already-done items)
- Creates traceable history of where work landed

## Step 7: Archive Stale Files

All archival happens in the centralized released folder: `{plan_root}/{slice}/`

**If the released folder doesn't exist** (slice had no formal plan), create it first:
```bash
mkdir -p {plan_root}/{slice}/_archived
```

After COMPLETED.md is generated, propose archival:

```
{plan_root}/{slice}/
+-- COMPLETED.md          (CREATE)
+-- shared.md             (KEEP - API contract, if exists)
+-- schema.mmd            (KEEP - ERD reference)
+-- _archived/
    +-- plan.md           (MOVE - if exists)
    +-- backend.md        (MOVE - if exists)
    +-- frontend.md       (MOVE - if exists)
    +-- flows.md          (MOVE - if exists)
    +-- AUDIT_REPORT.md   (MOVE - if exists)

Proceed with archival? [Yes / Abort]
```

**Important rules:**
- **Always archive plan.md** (if it exists) - Deferred items are documented in COMPLETED.md now
- Original plan is preserved in `_archived/plan.md` for historical reference
- Only archive after user confirms
- Never delete - always move to `_archived/`
- For slices without plan files, the released folder may only contain COMPLETED.md (that's fine)

## Step 8: Domain Hygiene Checks

Before finalizing, verify domain organization:

### 8a. Verify Domain Tag

Check INDEX.md for the slice's domain tag (e.g., `[auth]`, `[comms]`):

1. **Tag exists and matches** -> Good, continue
2. **Tag missing** -> Suggest adding based on functionality
3. **Tag seems wrong** -> Ask user: "This slice is tagged [comms] but seems more like [auth]. Should I update?"

**Domain tags are project-specific** -- see the mode file's tag-to-domain mapping for the full list.

### 8b. Find Related Slices

Search for slices that:
1. **Share the same domain tag** - e.g., all slices with the same tag
2. **Are referenced in plan.md** - "depends on X", "blocked by Y"
3. **Share database tables** - Check schema.mmd for overlapping entities
4. **Have deferred stories that belong elsewhere** - e.g., "email notifications" deferred here might belong in a notifications slice

For each related slice found:
- Add to "Related Work" section of COMPLETED.md
- Note the relationship type (same domain, shared tables, deferred handoff)

### 8c. Check for Orphaned Deferrals

For each DEFERRED story, check if another slice should own it:

```
Deferred: Email notifications on new messages
-> Search: Is there a notifications slice? An email_templates slice?
-> If yes: "This deferred story might belong in [email_templates]. Add cross-reference?"
-> If no: Keep in this slice's deferred list, note "No existing slice for this"
```

## Step 9: Update INDEX.md

Update the mode's `plan_index`.

Keep status as DONE, update description with story counts:

Before:
```
| 2026-01-15 | [support_thread](./support_thread/) | DONE | 1 | [comms] User messaging (3✓ 2→) |
```

After:
```
| 2026-01-22 | [support_thread](./support_thread/) | DONE | 1 | [comms] User messaging (3✓ 2→) |
```

**Story count format:** `(X✓ Y→)` where X = complete, Y = deferred

Only add counts if COMPLETED.md was generated (indicates consolidation).

**If slice not in INDEX.md:** Add a new row.

## Output Format

Present findings to user in this order:

```markdown
## support_thread - Retirement Review

### User Stories (3✓ 2→)

**Complete:**
V **Create support threads** - Users initiate threads with other users
V **View threads** - Users see all threads they're part of
V **Real-time updates** - Messages appear instantly

**Deferred (need resolution status):**
-> **File attachments** (marked v2 in plan)
  - Impact: Users must share files via other channels
  - Resolution: [Still open] [Resolved in ___] [Dismissed]

-> **Email notifications**
  - Found: Partial implementation in notifications module
  - Impact: Users don't know when to check for messages
  - Suggestion: Mark resolved in email_templates (already implemented there)
  - Resolution: [Still open] [Resolved in email_templates] [Dismissed]

**Needs Discussion:**
? **Push notifications** (ambiguous status)
  - Found: TODO comment but no implementation
  - Impact: Users miss real-time updates on mobile
  - Resolution: [Still open] [Resolved in ___] [Dismissed]

---

### Domain Hygiene

**Domain tag:** [comms] (correct)
**Repos:** backend, frontend

**Related slices in [comms]:**
- chatroom - same domain, both use message threading
- email_templates - potential home for deferred notifications

**Deferred story handoffs:**
- "Email notifications" -> suggest cross-reference to email_templates

---

After resolving ambiguities, I'll generate COMPLETED.md and propose file archival.
```

## Questioning Strategy

Ask the user when:
- Story status genuinely unclear after investigation
- Multiple reasonable interpretations exist
- User decision affects other slices
- **Determining resolution status for deferred items**

**Always include:**
- What you found (evidence)
- User impact (why it matters)
- Suggested resolution (your recommendation)
- Related context (other slices affected)

**Don't ask when:**
- Plan explicitly marks item as v2/deferred
- Implementation clearly complete with tests
- Item clearly missing with no partial work

**Resolution status question pattern:**
```
Question: "What happened to '{deferred item}'?"
Options:
  - "Still open (Recommended)" - May be done later, stays in active deferred list
  - "Resolved in {suggested-slice}" - Already done elsewhere, I'll update that slice's COMPLETED.md
  - "Dismissed" - Won't do, mark as explicitly abandoned
```
