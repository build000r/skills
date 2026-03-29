# Orchestration Workflow

Detailed agent coordination for implementing a planned domain slice. This is the expanded version of the Orchestration Mode section in SKILL.md.

Shared cross-skill rules live in
`~/.claude/skills/_shared/references/orchestration-contract.md`. This file only
covers planner-specific orchestration steps.

## Table of Contents

- [Step 1: Analyze Plan Scope](#step-1-analyze-plan-scope)
- [Step 2: Initialize Progress Tracking](#step-2-initialize-progress-tracking)
- [Step 3: Launch Scaffolder Agents](#step-3-launch-scaffolder-agents)
- [Step 4: Wait and Update Progress](#step-4-wait-and-update-progress)
- [Step 5: Launch Audit Agent](#step-5-launch-audit-agent)
- [Step 6: Handle Audit Results](#step-6-handle-audit-results)
- [Step 7: Launch Fix Agents](#step-7-launch-fix-agents)
- [Step 8: Re-Audit Loop](#step-8-re-audit-loop)
- [Step 9: Stall Triage](#step-9-stall-triage)
- [Step 10: Completion](#step-10-completion)

---

## Step 1: Analyze Plan Scope

Read plan.md and the mode's repo configuration to determine which repos need work.

Parse repo tags from the plan index entry (e.g., `[backend, frontend, auth]`) to determine which agents to launch:

| Repo Role | Agent Type | Skill to Use |
|-----------|------------|--------------|
| Backend repo | general-purpose | `domain-scaffolder` with `surface=backend` |
| Frontend repo | general-purpose | `domain-scaffolder` with `surface=frontend` |
| Auth repo (if separate) | general-purpose | `domain-scaffolder` with `surface=backend` |
| Additional backend repos | general-purpose | `domain-scaffolder` with `surface=backend` |

**Each repo gets its own agent** — they have different test setups, patterns, and conventions.

### Auth Service Guardrails (Optional)

`{auth_packages_root}` is the auth/payments/identity source of truth in orchestration mode (when an auth service is configured).

1. Every repo agent must use existing auth service packages for auth/payments/identity concerns.
2. If an agent reports missing auth service functionality, convert it into an auth-scope proposal and escalate to the user instead of inventing local replacements.
3. If unpublished auth service version changes are required, use temporary symlink/link loading from local `{auth_packages_root}`, then switch to published/live versions and run final checks before DONE.
4. Use big-bang delivery by default: do not ask agents to build legacy/dual-endpoint compatibility shims unless explicitly requested.

---

## Step 2: Initialize Progress Tracking

Create a checklist based on repos involved:

```
- [ ] {backend_repo} scaffolding
- [ ] {frontend_repo} scaffolding
- [ ] {auth_repo} scaffolding (if applicable)
- [ ] Audit (attempt 1)
- [ ] All issues resolved
- [ ] INDEX.md updated to DONE
```

---

## Step 3: Launch Scaffolder Agents

Launch agents **in parallel** — one per repo involved. Scope each agent by concern (repo), not by file list.

For each backend repo, launch a general-purpose agent with instructions:

```
Implement the {repo} portion of the {slice} slice.

FIRST: Use the domain-scaffolder skill with `surface=backend` for {slice}

Working directory: {repo_path}
Follow the repo's AGENTS.md patterns. Write tests first (TDD).
Use existing auth service packages where relevant; do not reimplement auth/payments/identity concerns locally.
Do not add legacy endpoint compatibility layers unless the plan explicitly requires them.
When complete, report what was created and any issues encountered.
```

For each frontend repo, launch a general-purpose agent with instructions:

```
Implement the {repo} frontend portion of the {slice} slice.

FIRST: Use the domain-scaffolder skill with `surface=frontend` for {slice}

Working directory: {repo_path}
Follow the project's frontend patterns. Handle all async states.
Use existing auth service packages where relevant; do not reimplement auth/payments/identity concerns locally.
Do not add dual-client or legacy API compatibility paths unless explicitly required by the plan.
When complete, report what was created and any issues encountered.
```

**Key:** All parallel agents MUST be launched in a single message. Agents that depend on prior results (like audit depending on scaffolding) must be launched sequentially.

---

## Step 4: Wait and Update Progress

After each agent completes:
- Parse their output for success/failure
- Update the progress checklist
- If any agent failed critically, ask the user before continuing

---

## Step 5: Launch Audit Agent

Once scaffolding is complete, launch an audit agent:

```
Audit the {slice} implementation against its plan.

Use the domain-reviewer skill in audit mode for {slice}.

Follow all instructions from that skill. Generate AUDIT_REPORT.md.
Return the verdict (COMPLIANT/MOSTLY COMPLIANT/NEEDS WORK) and
list any issues that need fixing.
```

---

## Step 6: Handle Audit Results

Parse the audit agent's response. Read `{plan_root}/{slice}/AUDIT_REPORT.md` and extract the score.

**If score = 100:**
- Jump to Step 10 (Completion)

**If score < 100:**
- Record the score in the score trajectory list (for stall detection)
- Extract handoff blocks from AUDIT_REPORT.md
- Group issues by repo
- Proceed to Step 7

**Never** stop the loop at a score below 100 just because a threshold was met. Every open finding is worth fixing.

---

## Step 7: Launch Fix Agents

Launch fix agents **only for repos that have issues**. One agent per repo with issues.

```
Fix the {repo} issues found in the {slice} audit.

FIRST: Use the domain-scaffolder skill with `surface={backend|frontend}` for {slice}

READ: {plan_root}/{slice}/AUDIT_REPORT.md

Working directory: {repo_path}
Issues to fix:
- {issue_1}
- {issue_2}
- {issue_3}

Write tests for fixes. Report what was fixed.
If a fix is blocked by missing auth service functionality, stop and include an auth-scope proposal instead of adding local auth/payments/identity substitutes.
```

**Key:** Only launch agents for repos that actually have issues. If one repo is clean, skip it.

---

## Step 8: Re-Audit Loop

After fix agents complete:
1. Increment audit attempt counter
2. Launch audit agent again (Step 5)
3. Parse new score, add to trajectory
4. If score = 100 → Step 10 (Completion)
5. If score < 100 → check for stall (Step 9), then loop back to Step 7

**Hard ceiling:** 5 iterations max. If reached, proceed to Step 9 stall triage regardless.

---

## Step 9: Stall Triage

A **stall** is detected when:
- Score did not improve by ≥2 points between consecutive iterations, OR
- The same issues appear in ≥2 consecutive audit reports, OR
- Hard ceiling of 5 iterations is reached

When a stall is detected, the orchestrator triages remaining issues **inline** (not delegated — the orchestrator has the context):

### 9a. Categorize Each Remaining Issue

Read the latest AUDIT_REPORT.md and classify every open finding:

| Category | Criteria | Auto-action |
|----------|----------|-------------|
| **ACTIONABLE** | New issue, or fix hasn't been attempted yet | Retarget fix agent with sharper, more specific instructions |
| **REGRESSING** | Was fixed in a prior iteration, broke again | Retry once with combined context (both the fix and what broke); if fails again → escalate |
| **STALE** | Fix attempted ≥2 times with no progress | Escalate with a specific recommendation; do not mark DONE below 100/100 |
| **EXTERNAL** | Requires out-of-scope dependency (auth service gap, upstream API, missing package) | Document as blocker, escalate with specific proposal |

### 9b. Triage Outcomes

Based on the triage:

- **ACTIONABLE items exist** → retarget fix agents with more specific instructions (include the failure context from prior attempts), loop back to Step 7
- **Only STALE / EXTERNAL / Medium+ REGRESSING remain** → escalate to user (see 9c)

### 9c. Contextual Escalation

When escalation is required, present a **specific, actionable** stall report — not a generic menu:

```
## Stall: {slice} (iteration {N}, score {XX}/100)

**Score trajectory:** {e.g., 72 → 88 → 94 → 94}

| Issue | Severity | Category | Recommendation |
|-------|----------|----------|----------------|
| {description} | {sev} | {category} | {what to do} |

**Recommended path:** {e.g., "Escalate the auth service gap as an auth-scope proposal and keep the slice IN_PROGRESS until the dependency is resolved."}
```

The orchestrator pauses here for user direction. Below `100/100`, it must not
retire the slice or mark it `DONE` without an explicit override.

### 9d. Scope Discipline

Stall triage stays scoped to the slice. It must NOT:
- Suggest replanning the slice
- Propose architectural changes outside the slice boundary
- Open new work items in sibling slices
- Expand scope to "while we're here" improvements

If remaining issues genuinely require plan revision, the escalation says so explicitly and **stops** — it does not attempt to revise the plan inline.

---

## Step 10: Completion

When score = 100:

1. **Auto-retire** — transition directly to retirement by following the domain-reviewer retire workflow. The orchestrator does this itself (not delegated) because it has full journey context and plenty of context budget remaining.

2. Update the plan index:
   ```
   | {date} | [{slice}](./{slice}/) | DONE | {description} |
   ```

3. Mark all checklist items complete.

4. Report the full journey to user:
   ```
   ## {slice}: Done

   **Score:** {final}/100 (trajectory: {list})
   **Iterations:** {N}
   **Retirement:** {stories complete/deferred summary}
   ```

No questions asked at this stage. The slice is done.
