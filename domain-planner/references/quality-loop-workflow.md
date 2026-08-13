# Quality Loop Workflow

Automated assess→fix→re-assess loop for plan files before sign-off. Runs after all 6 plan files are written (Phase 6b) and converges to 100/100 against the [plan-quality-rubric.md](plan-quality-rubric.md).

Shared cross-skill rules live in
`~/.claude/skills/_shared/references/orchestration-contract.md`. This file only
covers planner-specific plan-quality behavior.

This mirrors the domain-reviewer's audit→fix→re-audit loop but targets **plan quality** instead of implementation compliance.

## Table of Contents

- [Step 1: Route Assessor](#step-1-route-assessor)
- [Step 2: Parse Score](#step-2-parse-score)
- [Step 3: Fix Issues](#step-3-fix-issues)
- [Step 4: Re-Assess (Loop)](#step-4-re-assess-loop)
- [Step 5: Report](#step-5-report)

---

## Execution Profiles

Like domain-reviewer, this workflow is worker-transport aware, but not
self-review neutral. The assessor must be a fresh-context worker routed through
`/divide-and-conquer`.

- **Default: `/divide-and-conquer`/NTM worker** — Route the assessor as a
  ready Bead. Fresh context eliminates confirmation bias from having just
  written the plan. Orchestrator fixes inline (has full domain context).
- **Codex transport** — Use `/codex:rescue` only when `/divide-and-conquer` or
  the user explicitly selects Codex as the worker transport. Orchestrator still
  fixes inline.

Single-agent inline scoring is not an acceptable substitute. If no worker
substrate is available, stop and report the missing prerequisite.

| Role | Who | Why |
|------|-----|-----|
| Assessor | Fresh `/divide-and-conquer` worker, optionally using Codex as selected transport | Fresh eyes — no bias from having written the plan |
| Fixer | Orchestrator (this agent) | Has full domain context, codebase access, planning session history |

### Profile B: Codex-Delegated Assessment

When `/divide-and-conquer` selects Codex as the worker transport and the
`codex-plugin-cc` plugin is loaded, delegate the assessor prompt to Codex:

```
/codex:rescue --model gpt-5.6-sol --effort medium \
  Assess the {slice} plan against the plan quality rubric. \
  Read the rubric: {skill_root}/references/plan-quality-rubric.md \
  Read all 6 plan files in {plan_dir}/. \
  Score each of the 10 dimensions (10 points each, 100 total). \
  Follow the rubric deduction scale and output format exactly. \
  Return the assessment with **Score: XX/100** and the issues table. \
  Rules: be adversarial, cite specific files, include actionable fix instructions, \
  only deduct for rubric violations.
```

If GPT-5.6 SOL is unavailable, rerun the same assessor with
`--model gpt-5.6-terra --effort ultra`. The Grok 4.6 NTM controller may launch
and tend this assessor but never substitutes its own planning judgment.
SOL uses `medium` by default. For pivotal/high-consequence planning or after
another model has struggled, rerun SOL with `--effort max`; do not select Terra
for difficulty alone.

Add `--background` if the selected transport supports it, then retrieve the
assessment through that transport. Parse the score and issues table the same as
the default worker path (Step 2).

**When to prefer Codex transport:** When you want a cross-model second opinion
and `/divide-and-conquer` can route the worker that way. The default D&C/NTM
worker is faster for the iterative fix loop; Codex transport is best for the
final external review pass.

## Auth Service Checks (Quality Assessment Mode)

When the slice touches auth/payments/identity, treat `{auth_packages_root}` as mandatory scope:

- Plan files must identify existing auth service packages as the auth/payments/identity source of truth.
- Plans must reuse existing auth service packages before proposing local substitutes.
- Any missing auth service functionality must be captured as an auth-scope proposal (gap + proposed package/API + benefit).
- If unpublished auth service version changes are assumed, plans must document temporary local symlink/link usage plus final validation against published/live auth service packages.

## Delivery Strategy Checks (Quality Assessment Mode)

- Big-bang target-state planning is default.
- Do not accept unrequested legacy compatibility mechanics (dual endpoints, deprecation bridges, parallel old/new contracts).
- If existing production data is impacted, require a dedicated DB transition section (backup, raw `psql` runbook, transaction/idempotency safety, rollback).

---

## Step 1: Route Assessor

The assessor reads all 6 plan files + the rubric and produces a structured assessment.

### Assessor Prompt (for fresh worker execution)

```
Assess the {slice} plan against the plan quality rubric.

Read the rubric: {skill_root}/references/plan-quality-rubric.md

Read all 6 plan files:
- {plan_dir}/plan.md
- {plan_dir}/shared.md
- {plan_dir}/backend.md
- {plan_dir}/frontend.md
- {plan_dir}/flows.md
- {plan_dir}/schema.mmd

Score each of the 10 dimensions (10 points each, 100 total).
Follow the rubric's deduction scale and output format exactly.

Return the assessment in the format specified by the rubric's
"Assessment Output Format" section.

Rules:
- Be adversarial — assume scaffolder agents will implement with NO context beyond these files
- Every deduction must cite a specific file and location
- Every deduction must include an actionable fix instruction
- Do NOT suggest improvements — only deduct for rubric violations
- Enforce Phase 0.5 Core Value Gate discipline: deduct when the slice is not the highest-leverage minimum winning cut, or when admin/config/reporting/abstraction scope outweighs the primary actor's visible win
- For auth/payments/identity scope, enforce auth service package usage and auth-scope gap-proposal requirements
- Enforce big-bang default: deduct unrequested legacy compatibility/transition plans; require separate DB transition section only when production data is affected
```

### Default: `/divide-and-conquer` Worker

Create or claim a plan-quality assessor Bead and route it through
`/divide-and-conquer` with the assessor prompt above. Do not hand-launch a
generic worker outside the Beads frontier from this workflow.

### Worker Unavailable

If no worker substrate is available, stop. Do not score the plan inline, and do
not proceed to human checkpoint, save-location sign-off, or `br` epic minting.

---

## Step 2: Parse Score

Extract the overall score from the assessment output.

**Parse target:** The line matching `**Score: XX/100**`

Decision:

| Score | Action |
|-------|--------|
| 100/100 | Skip to Step 5 (report PASS) |
| < 100 | Continue to Step 3 (fix issues) |

Also extract the issues table — each row becomes a fix task:

```
| # | Dimension | Points Lost | File | Issue | Fix |
```

---

## Step 3: Fix Issues

The orchestrator (this agent) applies fixes from the issues table. The orchestrator has full context: domain knowledge, codebase access, and planning session history.

### Fix Strategy

Process issues in order of severity (most points lost first):

1. **Read the target file** cited in the issue row
2. **Apply the fix** described in the Fix column
3. **Cross-check** — if the fix changes a type/constant/endpoint, grep the other 5 files for the same term and update those too (maintain single source of truth)

### Fix Rules

- Fix ONLY the issues identified by the assessor — no drive-by improvements
- After each fix, note what changed for the re-assessment
- If a fix is ambiguous or requires a design decision, ask the user (don't guess)

---

## Step 4: Re-Assess (Loop)

After fixes are applied, run the assessor again (Step 1) with fresh context.

### Loop Control

```
max_iterations = 3
iteration = 1

while score < 100 and iteration <= max_iterations:
    assess()          # Step 1
    parse_score()     # Step 2
    if score == 100:
        break
    fix_issues()      # Step 3
    iteration += 1

if iteration > max_iterations and score < 100:
    stall_triage()
    escalate_to_user()
```

### Escalation (iteration > 3, score < 100)

Present remaining issues to the user:

```
Plan quality loop: {score}/100 after {iteration} rounds.

Remaining issues:
| # | Dimension | File | Issue |
|---|-----------|------|-------|
| ... | ... | ... | ... |

These may require design decisions. How to proceed?
- Fix manually then re-run fresh-worker assessment (Recommended) — address each remaining issue with your input, then continue until 100/100
- Another worker round — run one more fix+assess cycle with sharper instructions
- Save draft with known gaps — allowed only as a draft; do not mint the `br` execution epic
```

---

## Step 5: Report

Report the final quality score before proceeding to human checkpoint (Phase 6c).
Only `100/100` permits Phase 6e execution-epic minting.

### On PASS (100/100)

```
Plan quality: 100/100 ✓
{iterations_used} assessment round(s). All 10 dimensions clean.
```

### On Accepted (< 100, user chose to proceed)

```
Plan quality: {score}/100
{iterations_used} assessment round(s). {remaining_count} known issues remain.
Saved as draft only; execution epic not minted.
```

---

## Integration with Phase 6

This workflow slots into Phase 6 between writing files (6a) and the human
checkpoint (6c):

```
Phase 6: Sign-off
├── 6a. Write all 6 files (existing behavior)
├── 6b. Quality Loop (THIS WORKFLOW)
│   ├── Assess → Parse → Fix → Re-assess (max 3 rounds)
│   └── Report final score; block execution below 100/100
├── 6c. Human checkpoint MMDX review
├── 6d. Save location (released/ vs planned/)
├── 6e. Mint br epic + child issues only after 100/100
└── 6f. Handoff
```

The quality loop replaces the previous `review_plan.py` call in the skill's Phase 6 flow. Profile B (Codex-delegated via `/codex:rescue`) is the preferred external review path when the `codex-plugin-cc` plugin is installed. The `review_plan.py` script remains available as a standalone fallback for environments without the plugin, but it does not replace the fresh-worker gate.
