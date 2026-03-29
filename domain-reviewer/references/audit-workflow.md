# Audit Workflow

Shared cross-skill rules live in
`~/.claude/skills/_shared/references/orchestration-contract.md`. This file only
covers reviewer-specific audit procedure and report format.

> **Execution context:** These steps are executed by an audit worker phase coordinated by the orchestrator.
> The orchestrator constructs the worker prompt using these steps with mode-specific paths substituted.
> See `references/orchestration-workflow.md` for the orchestration loop.

## Review Scope

**Plan files always at** `{plan_root}/{slice}/`. **Implementation varies by context.**

Read the mode file for implementation locations. The mode defines a table of layers (backend, frontend, tests) with their path patterns and compliance standard files.

| Layer | Implementation Location | Standards |
|-------|------------------------|-----------|
| Backend | Mode's backend path pattern | Mode's backend convention files |
| Frontend | Mode's frontend path pattern | Mode's frontend patterns reference |
| Tests | Mode's test path patterns | Coverage requirements |

## Step-by-Step Process

### Step 1: Locate and Read the Plan

```
{plan_root}/{slice}/
+-- plan.md           # Strategic context, user stories, trade-offs
+-- shared.md         # API contract (endpoints, schemas, errors)
+-- backend.md        # Business rules, permissions, edge cases
+-- frontend.md       # Screens, interactions, states per role
+-- flows.md          # User journeys and state transitions
+-- schema.mmd        # Conceptual ERD (optional)
```

Extract from each file:
- **plan.md:** User stories, out-of-scope items, key decisions, open questions
- **shared.md:** Every endpoint, request/response shape, error code
- **backend.md:** Business rules, permissions matrix, access control strategy, edge cases, algorithms
- **frontend.md:** Screens per role, interactions, states, inline vs page decisions
- **flows.md:** User journeys per role, decision points, error paths, state transitions

### Step 2: Load Reference Standards

**Before auditing, read the mode's convention files:**

| Standard | Location | What to Check |
|----------|----------|---------------|
| Frontend patterns | Mode's frontend patterns reference | Component library, shared primitives, hooks |
| Backend conventions | Mode's backend convention files | TDD, domain structure, access control, error handling |
| Auth service standards (if configured) | Mode's auth service settings + `{auth_packages_root}` | Auth/payments/identity package reuse, gap proposals, local-link and published/live validation flow |
| Delivery strategy standards | plan.md + backend.md | Big-bang target-state scope; no unrequested legacy compatibility mechanics; DB transition section only when data-impacting |
| Performance envelope (if present) | Mode file + plan.md/backend.md/frontend.md | Latency/throughput SLOs, queue/buffer bounds, backpressure behavior |

### Step 3: Audit Backend (if backend.md exists)

**Check against the mode's backend convention files:**

1. **Domain Structure** - Files exist in correct locations:
   - Models file (ORM entities)
   - Schemas file (request/response shapes)
   - Repository file (database queries)
   - Service file (business logic)
   - Router file (API endpoints)

2. **TDD Compliance** - Tests exist BEFORE or WITH implementation:
   - Service tests (business logic)
   - Route tests (API endpoints)

3. **Access Control Policies** - Match backend.md specification:
   - Uses correct syntax per the mode's access control pattern
   - Proper user context references
   - No incorrect role or policy patterns

4. **Error Handling** - Router catches service errors, returns HTTP errors:
   - Error codes match shared.md "Error Codes" table
   - HTTP status codes are correct (404 for NOT_FOUND, 400 for validation, etc.)

5. **Migration** - Migration file exists and follows naming:
   - Uses the mode's migration naming convention
   - Contains correct access control policy syntax

6. **Performance Envelope Compliance** (if mode or plan declares one):
   - Latency/throughput SLOs are represented in tests or benchmark artifacts
   - Queue/channel/buffer bounds are explicit and enforced
   - Backpressure behavior is implemented and validated under load/slow-consumer conditions
   - Hot-path blocking operations are absent

7. **Auth Service Compliance** (when slice touches auth/payments/identity):
   - Existing auth service packages are used as the source of truth
   - No local replacement auth/payments/identity layer was introduced
   - Missing auth service functionality is documented as an auth-scope proposal
   - If local symlink/link packages were used, final verification against published/live auth service packages is documented

8. **Delivery Strategy Compliance**:
   - Backend implementation matches big-bang target-state contract from plan
   - No unrequested legacy endpoint compatibility, adapter layers, or dual-write/read code
   - If production data is impacted, DB transition runbook is present (backup, raw `psql`, transaction/idempotency, verification, rollback)

### Step 4: Audit Frontend (if frontend.md exists)

**Check against the mode's frontend patterns reference:**

1. **Component Library Usage** - No inline styling patterns:
   - Uses the mode's shared panel/card primitives, not inline divs with class names
   - Uses the mode's loading state component, not custom spinners
   - Uses the mode's error state component with retry support
   - Uses the mode's empty state component for empty lists
   - Uses the mode's button primitives, not inline button styling

2. **Data Fetching** - Query hook patterns:
   - Uses query hooks (not manual state + effect patterns)
   - Uses mutation hooks for writes
   - Correct query keys and cache settings

3. **Storage** - Shared storage hooks:
   - Uses the mode's storage hook pattern, not manual storage access
   - No duplicate storage logic

4. **Component Size** - Under limits:
   - Components < 300 LOC preferred
   - Components > 400 LOC flagged as needing extraction

5. **Async States** - All states handled:
   - Loading state (pending check)
   - Error state (error check with retry)
   - Empty state (empty array/null check)
   - Success state (render data)

6. **Test Coverage** - Tests exist:
   - Component tests for extracted components
   - Hook tests for custom hooks
   - Integration tests for complex flows

7. **Performance Envelope Compliance** (if mode or plan declares one):
   - No polling-first live state when push channel is healthy
   - High-cardinality render strategy follows mode requirements (virtualization/canvas/off-main-thread as specified)
   - Streaming updates are isolated from broad rerender cascades
   - Interaction/frame-time targets are measurable and evidenced

8. **Auth Service Compliance** (when slice touches auth/payments/identity):
   - Frontend auth/payments/identity integration uses auth service packages/SDKs, not ad-hoc local substitutes
   - Any missing auth service functionality is surfaced as an auth-scope proposal
   - Local symlink/link package usage is validated against published/live auth service packages before closure

9. **Delivery Strategy Compliance**:
   - Frontend follows target-state contract only
   - No unrequested legacy API compatibility toggles/adapters/dual client paths

### Step 5: Check Plan Compliance

For EACH item in shared.md/backend.md/frontend.md/flows.md:

| Item | Status | Notes |
|------|--------|-------|
| Endpoint GET /foo | Implemented | Exact match |
| Endpoint POST /bar | Deviation | Changed signature (document why) |
| Business rule: duplicate prevention | Implemented | 409 on duplicate |
| Flow: user creates item | Implemented | Matches flows.md |
| Permission: cross-user denied | Missing | No access control test |
| Auth service usage | Deviation | Local implementation bypasses existing auth service package |
| Legacy compatibility code | Deviation | Added old endpoint adapter not required by plan |
| Tests for service | Missing | 0% coverage |

**Compliance scoring:**
- 100%: Exact match to plan
- 90-99%: Close to plan, but still open because some work remains
- 70-89%: Significant deviations or incomplete
- <70%: Major gaps or missing functionality

### Step 6: Identify Unfinished Work

Create a checklist of:
- [ ] Items in plan marked as TODO
- [ ] Placeholder implementations
- [ ] Missing tests
- [ ] Deferred phases (Phase 3, offline support, etc.)
- [ ] Documentation not updated

### Step 7: Write AUDIT_REPORT.md

Output to: `{plan_root}/{slice}/AUDIT_REPORT.md`

**See [audit-template.md](audit-template.md) for full template.**

Key sections:
1. **Executive Summary** - Overall score, agent/auditor, date
2. **Compliance Scorecard** - Table by category
3. **What Was Implemented Correctly** - Celebrate wins
4. **What Was NOT Implemented** - Missing items
5. **Deviations** - Both problematic and positive
6. **Recommendations** - Prioritized action items
7. **Checklist** - Plan compliance checklist
8. **Agent Handoffs** - Copy-paste blocks for implementor agents

### Step 8: Update INDEX.md Status

Based on the audit verdict, update the slice's status in the mode's `plan_index`.

**Status mapping:**

| Audit Verdict | INDEX.md Status | When |
|---------------|-----------------|------|
| COMPLIANT | `DONE` | Score =100, no critical issues |
| MOSTLY COMPLIANT | `IN_PROGRESS` | Score 90-99%, minor issues remain |
| NEEDS WORK | `IN_PROGRESS` | Score 70-89%, significant gaps remain |
| CRITICAL ISSUES | `DEVIATED` | Blocking issues, security holes, or major deviation from plan |

**INDEX.md row format:**
```markdown
| Date | Feature | Status | Priority | Description |
|------|---------|--------|----------|-------------|
| YYYY-MM-DD | [slice_name](./slice_name/) | STATUS | N | Short description |
```

**If row exists:** Update the Date and Status columns, preserve Priority and Description.

**If row doesn't exist:** Add new row after the header, with:
- Date: Today (YYYY-MM-DD)
- Feature: `[{slice}](./{slice}/)`
- Status: Based on verdict
- Priority: Leave blank (unranked) unless user specifies
- Description: Brief description from plan.md

**Example - updating existing row:**

Before:
```markdown
| 2026-01-05 | [chatroom](./chatroom/) | IN_PROGRESS | 1 | Real-time messaging |
```

After (COMPLIANT verdict):
```markdown
| 2026-01-11 | [chatroom](./chatroom/) | DONE | 1 | Real-time messaging |
```

**Example - adding new row:**
```markdown
| 2026-01-11 | [chatroom](./chatroom/) | DONE | | Real-time user messaging |
```

**Note:** On re-review, update status to `DONE` only when the score reaches `100/100`.

### Step 9: Commit Baseline

After writing the audit report and updating INDEX.md, commit to create a baseline for diff comparison:

```bash
# In plan repo - commit audit report AND index update
git add {plan_root}/{slice}/AUDIT_REPORT.md
git add {plan_index}
git commit -m "audit({slice}): {verdict} - score {XX}/100"
```

If backend was audited and has uncommitted implementation:
```bash
# In backend repo - commit current state as baseline
cd {backend_repo}
git add -A
git commit -m "audit({slice}): baseline for re-review"
```

This baseline enables `git diff` to show exactly what implementors changed.

### Step 10: Output Handoffs

After committing, ensure the AUDIT_REPORT.md contains:
1. The overall compliance score (parseable as `### Overall Compliance Score: **XX/100**`)
2. The `## Agent Handoffs` section with copy-paste blocks for each layer with issues
3. The `## Final Verdict` with status

The orchestrator reads the report, parses the score, and decides whether to run fix worker phases or proceed to retirement. See `references/orchestration-workflow.md`.
