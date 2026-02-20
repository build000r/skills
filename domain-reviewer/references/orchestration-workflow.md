# Orchestration Workflow

Autonomous audit→fix→retire loop. The orchestrator stays thin and runs worker phases for heavy work, then transitions to retirement on convergence.

Worker execution is runtime-dependent:

- **Subagent-capable runtime:** delegate each worker phase to a fresh worker/subagent.
- **Single-agent runtime:** execute the worker phase inline in the current session.
- In both cases, follow the same inputs/outputs and loop decisions.

Parallel execution contract (same repository, no extra worktrees required):

- Backend and frontend fix workers may run in parallel only when file ownership is disjoint.
- Shared files are single-owner/sequential (orchestrator-owned).
- Workers must not revert/reset teammate changes.

## Configuration

| Setting | Value |
|---------|-------|
| Target | 100% |
| Stall detection | Score improved < 2 pts between iterations, or same issues reappear |
| Max iterations | 5 (hard ceiling) |
| On 100% | Orchestrator runs retirement itself |
| On stall | Triage remaining issues, auto-proceed or escalate (see Stall Triage) |
| On max iterations | Force stall triage regardless |

## Prerequisites

Before entering the loop:

1. **Detect mode** from CWD (read mode file)
2. **Get slice name** from user if not provided
3. **Extract from mode file:**
   - `plan_root`, `plan_index` paths
   - Backend/frontend implementation locations
   - Convention/standards file paths
   - Commit conventions
4. **Read reference files** to have on hand for constructing worker prompts:
   - `references/audit-workflow.md` (audit steps for worker phase)
   - `references/audit-template.md` (report template for worker phase)
   - Mode's convention files (for including in worker context)

## Auth Service Guardrails (Required)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the source of truth for the audit loop.

1. Workers must treat existing auth service packages as mandatory for auth/payments/identity scope.
2. If missing functionality is discovered, workers must request an auth-scope proposal instead of approving local replacement implementations.
3. If local symlink/link auth service versions are used during fixes, workers must require final validation against published/live packages before closure.

## The Loop

```
iteration = 0

while iteration < 5:

    ┌─ AUDIT PHASE ─────────────────────────────────────┐
    │                                                     │
    │  if iteration == 0:                                 │
    │    Run AUDIT worker phase (delegate or inline)      │
    │    (reads plan + code + standards from scratch)     │
    │  else:                                              │
    │    Run RE-REVIEW worker phase (delegate or inline)  │
    │    (reads previous report + git diff + plan)        │
    │                                                     │
    │  Worker writes/updates AUDIT_REPORT.md              │
    │  Worker updates INDEX.md                            │
    │  Worker commits                                     │
    └─────────────────────────────────────────────────────┘
                          │
                          ▼
    ┌─ SCORE CHECK ─────────────────────────────────────┐
    │                                                     │
    │  Read {plan_root}/{slice}/AUDIT_REPORT.md           │
    │  Parse: "Overall Compliance Score: **XX/100**"      │
    │  Append score to trajectory list                    │
    │                                                     │
    │  if score == 100: break → RETIREMENT                │
    │  if stall detected: break → STALL TRIAGE            │
    └─────────────────────────────────────────────────────┘
                          │
                          ▼
    ┌─ FIX PHASE ───────────────────────────────────────┐
    │                                                     │
    │  Extract "## Agent Handoffs" section from report    │
    │                                                     │
    │  Run fix worker phase(s) (parallel if both):        │
    │    - Backend fix worker (if backend handoff exists) │
    │    - Frontend fix worker (if frontend handoff exists)│
    │                                                     │
    │  Fix workers read report, fix issues, commit         │
    └─────────────────────────────────────────────────────┘
                          │
                          ▼
                    iteration++
                    (loop back to AUDIT PHASE)
```

## Constructing Worker Prompts

### Initial Audit Worker (iteration 0)

Construct the initial audit worker prompt by combining:

1. **Directive:** "Audit the `{slice}` slice implementation against its plan."
2. **Mode context:** All paths from the mode file (plan root, implementation locations, convention file paths)
3. **Full audit instructions:** Paste Steps 1-9 from `references/audit-workflow.md` with mode-specific paths substituted
4. **Report template:** Paste `references/audit-template.md` so the worker knows the exact output format
5. **Severity levels:** From SKILL.md
6. **Auth service guardrails:** Existing package reuse, gap-proposal requirement, and local-link to published/live validation flow

**Prompt structure:**
```
Audit the {slice} slice implementation against its plan.

## Context
- Plan files: {plan_root}/{slice}/
- Backend code: {backend_path}
- Frontend code: {frontend_path}
- Backend standards: {convention_files}
- Frontend standards: {patterns_reference}
- Plan index: {plan_index}

Auth service guardrails:
- Enforce existing `{auth_packages_root}` for auth/payments/identity scope.
- If functionality is missing, require a auth-scope proposal.
- If local symlink/link package usage exists, require final validation on published/live Auth service packages.

## Audit Steps
{Paste Steps 1-9 from audit-workflow.md, paths substituted}

## Report Template
{Paste audit-template.md}

## Commit
After writing the report and updating INDEX.md:
git add {plan_root}/{slice}/AUDIT_REPORT.md {plan_index}
git commit -m "audit({slice}): {verdict} - score {XX}/100"

If backend was audited with uncommitted implementation:
cd {backend_repo} && git add -A && git commit -m "audit({slice}): baseline for re-review"
```

### Re-Review Worker (iteration > 0)

Run re-review worker phase using this prompt:

```
Re-review the {slice} slice after fixes were applied (re-review #{iteration}).

## Context
{Same mode context as initial audit}

## Instructions
1. Read the plan files at {plan_root}/{slice}/ (plan.md, shared.md, backend.md, frontend.md, flows.md)
2. Read the convention/standards files: {list from mode}
3. Read the existing AUDIT_REPORT.md at {plan_root}/{slice}/AUDIT_REPORT.md
4. Run `git diff` in relevant repos to see changes since last audit commit
5. For EACH issue in the previous audit/re-review:
   - Mark as FIXED / PARTIALLY FIXED / NOT ADDRESSED
   - Include evidence (file:line references)
6. Check for NEW issues introduced by fixes
7. Append a "Re-Review #{iteration}" section to AUDIT_REPORT.md (see template below)
8. Recalculate the Overall Compliance Score
9. Update INDEX.md status at {plan_index} if verdict changed
10. If issues remain, include updated Agent Handoff blocks
11. Commit: "audit({slice}): re-review #{iteration} - score {XX}/100"
12. Re-check Auth service compliance: package reuse, gap proposals, and local-link to published/live validation requirements

## Re-Review Section Template

### Re-Review #{N} - {YYYY-MM-DD}

**Baseline commit:** `{commit-hash}` ({repo})
**Changes reviewed:** `git diff {baseline}..HEAD`

**Issues Resolved:**
- [x] {Issue from previous audit} - Fixed in `{file:line}`

**Issues Remaining:**
- [ ] {Issue} - Not addressed / Partially fixed

**New Issues Found:**
- {New issue introduced by fix, if any}

**Updated Score:** **{XX}/100** (was {YY}/100)
**Updated Verdict:** {COMPLIANT | MOSTLY COMPLIANT | NEEDS WORK}

**Updated Handoffs:** {Include if issues remain, or "None - all issues resolved"}
```

### Fix Workers (fix phase)

Extract the handoff block from the `## Agent Handoffs` section of AUDIT_REPORT.md. There may be separate blocks for backend and frontend.

**For backend issues** — run backend fix worker phase:
```
{Backend handoff block from AUDIT_REPORT.md, verbatim}

Additional context:
- Read these convention files before making changes: {backend convention files from mode}
- Backend code location: {backend path from mode}
- Plan files: {plan_root}/{slice}/
- Auth service: reuse existing `{auth_packages_root}` auth/payments/identity packages; if missing functionality, create a auth-scope proposal instead of local replacement logic
- After fixing, commit with: "fix({slice}): {brief description of fixes}"
- Write/fix tests FIRST, then fix implementation (TDD-first).
```

**For frontend issues** — run frontend fix worker phase:
```
{Frontend handoff block from AUDIT_REPORT.md, verbatim}

Additional context:
- Read the frontend patterns reference: {patterns file from mode}
- Frontend code location: {frontend path from mode}
- Plan files: {plan_root}/{slice}/
- Auth service: reuse existing `{auth_packages_root}` auth/payments/identity packages; if missing functionality, create a auth-scope proposal instead of local replacement logic
- After fixing, commit with: "fix({slice}): {brief description of fixes}"
```

**Run backend and frontend fix workers in parallel** when both have issues and path ownership is disjoint.

## Parsing the Score

After each audit/re-review worker phase completes, read `{plan_root}/{slice}/AUDIT_REPORT.md`.

Find the line:
```
### Overall Compliance Score: **XX/100**
```

Extract `XX` as an integer. Append to the score trajectory list.

**If the report doesn't contain a parseable score**, treat as 0 and log a warning — the audit worker phase may have failed.

### Stall Detection

After parsing each score, check for stall conditions:

- **No progress:** Score improved by < 2 points from previous iteration
- **Recurring issues:** The same issue descriptions appear in ≥2 consecutive reports
- **Hard ceiling:** 5 iterations reached

If any stall condition is met and score < 100, proceed to Stall Triage instead of the fix phase.

## Convergence → Retirement

When score = 100:

1. The orchestrator has been thin throughout the loop — its context contains only: skill instructions + mode context + a few score reads
2. **Transition directly to retirement** by following `references/retire-workflow.md`
3. The orchestrator does the retirement itself (not delegated) because:
   - Retirement involves user interaction (deferred item resolution status)
   - The orchestrator has plenty of context budget remaining
   - It naturally has awareness of the slice's journey
4. After retirement completes, report the full journey to the user:
   - Initial audit score
   - Number of fix iterations
   - Final score
   - Retirement summary (stories complete/deferred)

## Stall Triage

When a stall is detected, the orchestrator triages remaining issues **inline** (not delegated):

### Categorize Each Remaining Issue

Read the latest AUDIT_REPORT.md and classify every open finding:

| Category | Criteria | Auto-action |
|----------|----------|-------------|
| **ACTIONABLE** | New issue, or fix hasn't been attempted yet | Retarget fix worker with sharper, more specific instructions |
| **REGRESSING** | Was fixed in a prior iteration, broke again | Retry once with combined context (both the fix and what broke); if fails again → escalate |
| **STALE** | Fix attempted ≥2 times with no progress | Accept if Low severity; escalate if Medium+ |
| **EXTERNAL** | Requires out-of-scope dependency (Auth service gap, upstream API, missing package) | Document as blocker, escalate with specific proposal |

### Auto-Proceed Rules

Based on the triage:

- **All remaining are Low-severity STALE** → accept, document in AUDIT_REPORT.md as "Accepted — cosmetic/low-impact", transition to Retirement
- **ACTIONABLE items exist** → retarget fix workers with more specific instructions (include failure context from prior attempts), resume the loop
- **Only EXTERNAL or Medium+ REGRESSING remain** → contextual escalation (see below)

### Contextual Escalation

When escalation is required, present a **specific, actionable** stall report — not a generic menu:

```
## Stall: {slice} (iteration {N}, score {XX}/100)

**Score trajectory:** {e.g., 72 → 88 → 94 → 94}

| Issue | Severity | Category | Recommendation |
|-------|----------|----------|----------------|
| {description} | {sev} | {category} | {what to do} |

**Recommended path:** {e.g., "Accept the 2 Low items, escalate the Auth service gap as an auth-scope proposal."}
Proceeding with that unless you redirect.
```

The orchestrator **proceeds with its recommendation after presenting it**. The user only needs to intervene if they disagree.

### Scope Discipline

Stall triage stays scoped to the slice. It must NOT:
- Suggest replanning the slice
- Propose architectural changes outside the slice boundary
- Open new work items in sibling slices
- Expand scope to "while we're here" improvements

If remaining issues genuinely require plan revision, the escalation says so explicitly and **stops**.

## Orchestrator Discipline

The orchestrator MUST stay thin. It should ONLY:

- Read mode/reference files (once, at the start)
- Run worker phases with constructed prompts (delegated or inline)
- Read AUDIT_REPORT.md to parse scores and extract handoffs
- Make loop decisions (continue/converge/escalate)
- Run retirement (final phase, when context is still fresh)

The orchestrator MUST NOT:

- Read implementation code directly when using delegated workers (that's the audit worker's job)
- Fix code directly when using delegated workers (that's the fix worker's job)
- Carry audit details between iterations (each worker run should start fresh from inputs)
- Re-read convention files between iterations (only needed for prompt construction)
