# Phase Questions Reference

Detailed questions and refinement patterns for each planning phase. All multi-choice questions should use a structured multi-choice question format.

## Table of Contents

- [Question Patterns](#question-patterns)
- [Phase 1: Discovery](#phase-1-discovery)
  - [Opening Questions](#opening-questions)
  - [Story Extraction](#story-extraction)
  - [Story Refinement](#story-refinement-critical)
  - [Edge Case Probing](#edge-case-probing)
- [Phase 2: API Contract](#phase-2-api-contract)
  - [Endpoint Design](#endpoint-design)
  - [Request/Response Refinement](#request-field-refinement)
  - [Error Codes](#error-code-design)
- [Phase 3: Backend Spec](#phase-3-backend-spec)
  - [Table Design](#table-design)
  - [History Model](#history-model-explicitly-requested-only)
  - [Production Data Transition](#production-data-transition-only-when-data-impacting)
  - [RLS Policies](#rls-policy-design)
- [Phase 4: Frontend Spec](#phase-4-frontend-spec)
  - [Page Structure](#page-structure)
  - [Component Breakdown](#component-breakdown)
  - [UI States](#ui-state-handling)
- [Phase 5: Strategy](#phase-5-strategy)
- [Phase 6: Sign-off](#phase-6-sign-off)

---

## Question Patterns

### Question Structure

Present each structured multi-choice question in this format:

```
**Question:** "Specific question about uncertainty?"
**Multi-select:** no
**Options:**
- Best choice (Recommended) — Why this is the default
- Alternative — Trade-off or when to pick this
```

**Note:** For Multi-select: yes questions (like user types), don't add "(Recommended)" since multiple can be selected.

### Key Rules
- **Every question MUST have a recommended option** - Put it first with "(Recommended)" in label
- **Ask high-level questions first** - They cascade down and eliminate lower-level questions
- **Batch independent questions** - Up to 4 per round
- **Sequential for dependent questions** - When Q1 answer changes Q2 options
- **Multi-select: yes** - When choices aren't mutually exclusive (e.g., user types)
- **Only ask about genuine uncertainties** - If 95% confident, just do it
- **Default to big-bang delivery** - Do not add legacy/dual-endpoint transition mechanics unless the user explicitly asks for compatibility support

### Question Hierarchy (Ask Top-Down)

High-level decisions cascade down and eliminate whole categories of questions:

```
1. User story scope
   -- "CRUD or view-only?" -> if view-only, skip all mutation questions

2. Endpoint design
   -- "Separate endpoints or combined?" -> determines table relationships

3. Table structure
   -- "History retention required?" -> if not required, use CRUD and skip version-chain design

4. Access patterns
   -- "Owner-scoped or shared?" -> determines RLS complexity
```

Don't ask about column types before confirming user story scope.

### NEVER Ask Generic Approval Questions

Bad:
- "Does this API contract look correct?"
- "Any changes before locking?"
- "Confirm this is right?"

Good (specific uncertainties with recommendation):
- "Should `user_id` be in request body or inferred from auth? (Recommend: infer)"
- "The notes field - max 500 chars or unlimited? (Recommend: 2000)"
- "Return full resource or just { id, name }? (Recommend: full)"

**Pattern:** When drafting a contract/spec, identify 2-3 specific points where you're genuinely unsure, and ask about those. Don't ask for blanket approval.

### Batching Examples

**Good batch** (independent questions about one endpoint):

**Question 1:** "When resource doesn't exist?"
**Multi-select:** no
**Options:**
- 404 error (Recommended) — Return error, let UI handle
- Auto-create — Create empty resource automatically

**Question 2:** "When user lacks permission?"
**Multi-select:** no
**Options:**
- 403 error (Recommended) — Return forbidden status
- Hide (404) — Pretend it doesn't exist

**Question 3:** "When input is invalid?"
**Multi-select:** no
**Options:**
- 400 + field errors (Recommended) — Return detailed validation errors
- Use defaults — Ignore invalid, use sensible defaults

**Bad batch** (Q2 depends on Q1):
```
Q1: "Standard CRUD or append-only history?"
Q2: "Which RLS policy?" <- Options differ based on Q1 answer!
```
Ask these sequentially instead.

---

## Phase 1: Discovery

### Opening Questions

**Q1: Slice Identity** (text question, not multi-choice)
```
"What's the slice name (snake_case) and one-sentence business value?"

Example: "task_assignments - enable managers to assign and track
tasks for team members based on their workload"
```

**Q2: User Types** - Use Multi-select: yes since features often serve multiple user types:

**Question:** "Who uses this feature?"
**Multi-select:** yes
**Options:**
- Operator — Admin dashboards, user management, creating content
- End user — Viewing own data, self-service actions
- System — Background jobs, scheduled tasks, notifications

### Story Extraction

For each user type identified:

```
"What's the primary action for [user type] and why do they need it?"

Convert response to: "As a [role], I need to [action], so that [outcome]"
```

### Story Refinement (CRITICAL)

**Red Flag: Vague Scope ("all", "everything", "manage")**

First determine the highest-level intent, then drill down:

**Question:** "You said 'manage resources'. Did you mean:"
**Multi-select:** no
**Options:**
- Assignment only (Recommended) — Assign existing resources to users - simplest scope
- CRUD operations — Create, edit, delete resources - more complex
- View + filter — Browse and filter, no mutations

**Red Flag: Missing "So That"**

**Question:** "The story '[story]' doesn't have a clear outcome. Why does [role] need this?"
**Multi-select:** no
**Options:**
- To [likely outcome] (Recommended) — Based on similar features
- To [alternative outcome] — If different intent

**Red Flag: Overlapping Stories**

**Question:** "US-1 and US-3 overlap on [area]. Combine or keep separate?"
**Multi-select:** no
**Options:**
- Combine (Recommended) — Simpler contract, single endpoint, less surface area
- Keep separate — More granular, different permissions/flows

### Edge Case Probing

**Batch all edge cases for one user story** (up to 4 questions):

**Question 1:** "For US-[N], when [resource] doesn't exist?"
**Multi-select:** no
**Options:**
- 404 error (Recommended) — Return error, let UI handle
- Auto-create — Create empty resource automatically

**Question 2:** "When user lacks permission?"
**Multi-select:** no
**Options:**
- 403 error (Recommended) — Return forbidden status
- Hide (404) — Pretend it doesn't exist

**Question 3:** "When action conflicts with existing data?"
**Multi-select:** no
**Options:**
- 409 error (Recommended) — Reject and explain conflict
- Overwrite — Replace existing silently

**Question 4:** "When input validation fails?"
**Multi-select:** no
**Options:**
- 400 + field errors (Recommended) — Return detailed validation errors
- Use defaults — Ignore invalid, use sensible defaults

---

## Phase 2: API Contract

### Endpoint Design

For each user story, draft the endpoint then ask about **specific uncertainties only**:

```
"US-[N] endpoint:

[METHOD] /v1/[path]
Request: { [fields] }
Response: { [fields] }
```

Then ask the user about genuine uncertainties (don't ask "is this right?"):

**Question 1:** "Should user_id be in request body or inferred from auth token?"
**Multi-select:** no
**Options:**
- Infer from auth (Recommended) — Cleaner API, can't act on the wrong user
- Explicit in body — Needed if an operator acts on behalf of a user

**Question 2:** "Include updated_at in response?"
**Multi-select:** no
**Options:**
- Yes (Recommended) — Useful for cache invalidation, optimistic locking
- No — Keep response minimal

### Request Field Refinement

**Batch field questions** (up to 4 fields per round):

**Question 1:** "Is 'name' required for POST /v1/[endpoint]?"
**Multi-select:** no
**Options:**
- Required (Recommended) — Must be provided, max 255 chars
- Optional — Can be omitted

**Question 2:** "Is 'description' required?"
**Multi-select:** no
**Options:**
- Optional (Recommended) — Can be omitted, nice-to-have
- Required — Must be provided, max 2000 chars

### Response Shape Refinement

**Question:** "For GET /v1/[endpoint], which response shape?"
**Multi-select:** no
**Options:**
- Full (Recommended) — { id, name, description, relations... } - fewer requests
- Minimal — { id, name, created_at } - faster, less data
- Configurable — ?include=relations - flexible but complex

### Error Code Design

```
"What can go wrong with [endpoint]?

| Scenario | Proposed Code | HTTP Status |
|----------|---------------|-------------|
| Missing auth | NOT_AUTHENTICATED | 403 |
| Wrong user | NOT_AUTHORIZED | 403 |
| Not found | NOT_FOUND | 404 |
| Duplicate | ALREADY_EXISTS | 409 |
| Invalid input | VALIDATION_FAILED | 400 |

Any additional error cases for this endpoint?"
```

---

## Phase 3: Backend Spec

### Before Starting

```
"Before backend planning, I'll read:
- the mode's backend convention files

[After reading] Key conventions that apply:
- [Convention 1]
- [Convention 2]
```

### Table Design

Draft the tables, then ask about **specific design decisions** you're uncertain about:

```
"Based on the contract, proposing:

[Table 1]: { [columns] }
[Table 2]: { [columns] }

See draft ERD in schema.mmd.
```

Then ask specific questions (not "is this right?"):

**Question 1:** "Should notes be TEXT (unlimited) or VARCHAR(2000)?"
**Multi-select:** no
**Options:**
- VARCHAR(2000) (Recommended) — Enforces reasonable limit, better for indexing
- TEXT — No limit, flexible for long-form content

**Question 2:** "Add soft delete (deleted_at) or hard delete?"
**Multi-select:** no
**Options:**
- Hard delete (Recommended) — Simpler, truly removes data
- Soft delete — Recoverable, audit trail, complicates queries

### History Model (Explicitly Requested Only)

**Question:** "Does [table] need explicit historical versions?"
**Multi-select:** no
**Options:**
- Standard CRUD (Recommended) — Update in place; default big-bang path
- Versioned history — prev_id + version pattern, only for explicit audit/regulatory/replay requirements

### Production Data Transition (Only When Data-Impacting)

Only ask this when the plan modifies existing production data.

**Question:** "Do we need an explicit production DB transition section for this slice?"
**Multi-select:** no
**Options:**
- No (Recommended) — Target-state big-bang implementation only, no transition mechanics
- Yes — Add a separate DB transition section (backup, transactional/idempotent raw SQL via psql, verification, rollback)

### RLS Policy Design

Draft RLS policies, then ask about specific access patterns you're uncertain about:

```
"RLS policies:

| Table | Owner | Read Access |
|-------|-------|-------------|
| [table1] | Operator | Owner only |
| [table2] | End user | Owner + their operator |
| [table3] | Lookup | Everyone (read-only) |
```

Ask about genuine uncertainties:

**Question:** "Can operators see each other's [resource] or only their own?"
**Multi-select:** no
**Options:**
- Own only (Recommended) — Standard isolation, simpler RLS
- All operators — Shared resources across the team

### Background Job Decision

**Question:** "Does [operation] need background processing?"
**Multi-select:** no
**Options:**
- Synchronous (Recommended) — Immediate response - simpler, good for fast ops (<500ms)
- Async (background queue) — Background queue - for slow ops, retries, rate limiting

---

## Phase 4: Frontend Spec

> **Mode-specific questions take priority.** Check the mode file's "Phase 4 Questions" section first.
> If the mode defines its own Phase 4 questions (e.g., portal placement, widget layer, feature gating),
> use those instead of the generic questions below. The generic questions are for modes without custom Phase 4 guidance.

### Before Starting

```
"Before frontend planning, I'll read:
- the mode's frontend patterns reference
- the mode-specific frontend template (if available: assets/templates/frontend-{mode}.md)

[After reading] Key patterns that apply:
- Widget system and primitives available
- Data fetching patterns
- State handling patterns
- [Mode-specific: portal architecture, feature gating, etc.]"
```

### Template Selection

Check for mode-specific frontend template:
- `assets/templates/frontend-{mode}.md` — Mode-specific architecture (if available)
- `assets/templates/frontend.md` — Generic (screens, states, role differences)

Use mode-specific template when available — it includes sections the generic template lacks.

### Generic Questions (when mode has no custom Phase 4)

#### Page Structure

```
"Based on the user stories, I propose these pages:

1. [PageName]Page at /[route]
   -> For US-[N]: [purpose]
   -> Sections: [list]

2. [PageName]Page at /[route]
   -> For US-[N]: [purpose]

Questions:
1. Routes correct?
2. Missing any pages?
3. Section breakdown accurate?"
```

#### Component Breakdown

```
"For [Page], I propose these components:

- [Component1] - [purpose], uses WidgetPanel
- [Component2] - [purpose], uses WidgetButton

Questions:
1. Component boundaries correct?
2. Any reusable components across pages?
3. Widget primitive choices appropriate?"
```

#### UI State Handling

```
"For [Component], what UI states do we need?

| State | Display | Primitive |
|-------|---------|-----------|
| Loading | Skeleton/spinner | WidgetLoadingState |
| Empty | 'No items yet' | WidgetEmptyState |
| Error | Error + retry | WidgetErrorState |
| Success | Data list | Custom |

Any additional states?"
```

#### Optimistic Updates

**Question:** "For [action], use optimistic updates?"
**Multi-select:** no
**Options:**
- Wait for server (Recommended) — Show loading then result - safer for creates/deletes
- Optimistic — Update UI immediately, rollback on error - for toggles/favorites

### Mode-Specific Questions

Modes can define custom Phase 4 questions in their mode file under "Phase 4 Questions". Examples of mode-specific concerns:

- **Portal placement** — Which portal(s) does the feature appear in?
- **Widget layer** — Page-level vs dashboard widget vs shared control vs modal?
- **Feature gating** — Role-based, company toggle, system flag, or no gate?
- **Cross-portal behavior** — Single portal, shared component, or different views of same data?
- **Inline vs separate page** — Context-dependent features may work better as inline extensions
- **Component size limits** — Mode may enforce LOC limits per component

Check the active mode file for project-specific Phase 4 guidance before using generic questions.

---

## Phase 5: Strategy

### Trade-off Documentation

```
"Let's document why we chose this approach.

For [decision], the options were:
| Option | Pros | Cons |
|--------|------|------|
| A | [pros] | [cons] |
| B | [pros] | [cons] |

We chose [A/B] because: [rationale]

Accurate?"
```

### Scope Boundaries

```
"What's explicitly OUT of scope for this slice release?

Candidates:
- [ ] [Feature 1] - defer because: [reason]
- [ ] [Feature 2] - defer because: [reason]
- [ ] [Feature 3] - defer because: [reason]

Any additions or changes?"
```

---

## Phase 6: Sign-off

### File Creation

First, ask the user for location:

**Question:** "Save to released/ (locked) or planned/ (draft)?"
**Multi-select:** no
**Options:**
- released/ (Recommended) — Locked spec, ready for implementation
- planned/ — Draft spec, may change before implementation

Then confirm files to create (text summary):
```
"Creating files in {plan_root}/{slice}/:
- plan.md - Strategic context
- shared.md - API contract (LOCKED)
- schema.mmd - ERD (SOURCE OF TRUTH)
- backend.md - Backend spec
- frontend.md - Frontend spec

Plus migration draft:
- the mode's migration path/{timestamp}_{slice}_initial.sql.planning

Proceed?"
```

### Handoff

```
"Planning complete! Next steps:

**Backend Implementation:**
Invoke `domain-scaffolder` skill to generate code from this plan.

**Frontend Implementation:**
Use the mode's frontend patterns reference for component conventions.

**Migration:**
When ready to apply, convert the .planning file per the mode's migration tool and apply."
```
