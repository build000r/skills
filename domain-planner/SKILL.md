---
name: domain-planner
description: Plan new multi-repo domain slices, assess plan quality, or orchestrate implementation from an accepted slice plan. Use for "plan the X slice", multi-repo feature planning, API contract design, "implement the X slice", or slice-quality review; not for bug fixes, small refactors, or single-repo work.
license: MIT
---

# Domain Planner

Three modes: **Planning** (create specs), **Quality Assessment** (validate/fix specs), and **Orchestration** (implement specs via agents).

## Use This For

- New multi-repo or cross-stack slice planning
- Quality review for an existing slice plan
- Implementation orchestration after a slice plan is accepted

## Do Not Use This For

- Bug fixes, small changes, or single-repo refactors
- Direct scaffolding without a settled slice contract
- Routine implementation-detail debates that belong in scaffolder skills or code review

**Skill root:** `~/.claude/skills/domain-planner/` — all relative paths below resolve from here.

**Shared orchestration rules:** Use
[references/orchestration-contract.md](~/.claude/skills/domain-planner/references/orchestration-contract.md)
for the cross-skill contract on worker ownership, background-task handling, and
the domain suite's `100/100` convergence rule.

## Plan Storage (Mode-Defined)

Plan storage is defined by the active mode file (`~/.claude/skills/domain-planner/modes/{mode}.md`):

```
plan_root: <mode value>
plan_draft: <mode value>
plan_index: <mode value>
session_plans: <mode value>
```

To find a slice: read `{plan_root}/{slice}/`. To check what exists: read `{plan_index}`.
DO NOT search the filesystem for plans.

## Modes (Implementation Context)

Modes provide **implementation-specific** context — which repos to scaffold, what conventions to follow.

Check `~/.claude/skills/domain-planner/modes/` for project-specific configuration. Each mode defines:

- **cwd_match** — directory pattern for auto-detection
- **Repos** — frontend, backend, auth repo names and paths
- **Convention files** — AGENTS.md locations, frontend patterns reference
- **Stack** — backend framework, frontend framework, migration tool

**If no mode matches the current directory:**
1. You can still read/create plans if you provide explicit plan paths.
2. For implementation (orchestration mode), list available modes (from `~/.claude/skills/domain-planner/modes/*.md` filenames) and ask the user which to use.
3. DO NOT search the filesystem. DO NOT spawn Explore agents.

See [references/mode-template.md](~/.claude/skills/domain-planner/references/mode-template.md) for the mode file format.

## Auth Service Requirements (All Modes)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical authentication, payments, and identity layer.

1. Use existing auth service packages first. Do not design or scaffold parallel auth/payments/identity implementations when the auth service already covers the capability.
2. If auth service functionality is missing or blocking, raise an "auth-scope proposal" to the user with the gap, impacted slice, proposed package/API addition, and cross-product benefit.
3. When version drift requires unpublished local changes, temporarily symlink/link packages from local `{auth_packages_root}`. After auth service packages are published live, switch back to published versions and run final checks against the live auth service before closing the slice.

## On Trigger

1. **Detect project context** from mode file (match CWD to `cwd_match` patterns).

2. If slice name not provided, ask: "What's the slice name (snake_case) and one-sentence business value?"

3. **Check if plan already exists** at mode-defined `{plan_root}/{slice}/plan.md`:

   **If plan does NOT exist:**
   - Run `python3 ~/.claude/skills/domain-planner/scripts/init_slice.py {slice_name} --config {mode_file}` to scaffold files
   - Begin Phase 0 landscape, then Phase 0.5 Core Value Gate (Planning Mode)

   **If plan exists, ask the user:**

   **Question:** "Plan exists for {slice}. What do you want to do?"
   **Options:**
   - Implement it (Recommended) — Orchestrate scaffolding + audit until 100/100 COMPLIANT
   - Continue planning — Edit existing plan files
   - Check plan quality — Assess and fix plan files against the quality rubric
   - Check status — Show what's implemented vs planned

   Based on answer:
   - "Implement it" → Jump to **Orchestration Mode** (below)
   - "Continue planning" → Resume at appropriate phase
   - "Check plan quality" → Jump to **Quality Assessment Mode** (Phase 6b assess→fix→re-assess)
   - "Check status" → Show implementation status, suggest next action

## Plan Location

```
{plan_root}/
├── {slice}/
│   ├── plan.md, shared.md, backend.md, frontend.md, flows.md, schema.mmd
│   └── WORKGRAPH.md
└── ...

{plan_draft}/
└── {slice}/
```

`{plan_root}`, `{plan_draft}`, and `{plan_index}` come from the active mode file.

**schema.mmd is REQUIRED** — without it, the slice won't appear in indexes or ERD views.

## Critical Rules

1. **No implementation code** — Specs only (what & why, never how). No file structures, no framework-specific patterns, no column types. Those are the scaffolder's job.
2. **Binary refinement** — Every user story gets "A or B?" questions with reasoning until unambiguous.
3. **Test cases inline** — Each acceptance criterion includes test scenarios (happy path + error cases).
4. **schema.mmd is MANDATORY** — Other files reference it for entity relationships.
5. **Just-in-time reading** — Read the mode's convention files before each phase.
6. **Explicit handoffs** — Reference `domain-scaffolder` with explicit `surface=backend` or `surface=frontend`, plus `domain-reviewer` by name. Mention the legacy wrapper names only when explaining compatibility with older artifacts.
7. **Standard stories first** — Before Phase 1 Discovery, check `~/.claude/skills/domain-planner/references/standard-stories/` for reusable patterns (RBAC, feature flags, onboarding). Start from templates, don't rediscover.
8. **Mode-specific templates** — Use `~/.claude/skills/domain-planner/assets/templates/frontend-{mode}.md` when available (e.g., `frontend-{mode}.md` for mode-specific slices). Fall back to generic `frontend.md`.
9. **Performance envelopes are binding** — When a mode defines performance constraints, convert each target into explicit acceptance criteria and test scenarios across plan files.
10. **Default delivery strategy is big-bang** — Plan the target-state contract directly. Do not add dual routes, backward-compatibility shims, deprecation windows, or legacy endpoint support unless the user explicitly asks.
11. **Separate DB transition planning from API planning** — Only add a DB transition section when production data is at risk. Keep it operationally focused: backup, transactional/idempotent raw SQL execution, verification, and rollback.
12. **Core Value Gate is binding** — Before Phase 1 Discovery, define the primary actor, single user-visible outcome, minimum winning slice, explicit non-goals, and debt avoided by deferring them. If a story does not materially improve that outcome, defer it unless it is required for safety/risk containment or the user explicitly widens scope.
13. **`WORKGRAPH.md` is post-plan only** — It is an execution handoff artifact created after the 6 plan files are accepted. It may include `writes`, dependency edges, validation commands, and risk gates. Do not mix those execution details back into the plan files.

## Questioning Strategy

Ask the user structured multi-choice questions for all binary/multi-choice decisions.

**NEVER ask generic approval questions like:**
- "Does this API contract look correct?"
- "Any changes needed before locking?"

**INSTEAD, identify specific uncertainties and ask about those:**
- "Should `user_id` be required or inferred from auth context?"
- "The notes field — max 500 chars or unlimited?"
- "Return full object or just { id, name }?"

If 95% confident, don't ask — just do it. Only ask when there's genuine ambiguity.

**Every question MUST have a recommended option.** Put it first with "(Recommended)".

**Ask high-level questions first** — they cascade down:
1. Core user-visible outcome → determines the minimum winning slice
2. User story scope → determines endpoints needed
3. Endpoint design → determines table structure
4. Table design → determines access control policies
5. Access control → determines frontend data access patterns

**When to batch** (single question set): Independent questions about the same topic.
**When to ask sequentially**: When answer to Q1 changes what Q2 should ask.

See [references/phase-questions.md](~/.claude/skills/domain-planner/references/phase-questions.md) for detailed question patterns per phase.

## Planning Mode

Use Phases 0-6 below for spec creation, including the binding Phase 0.5 Core Value Gate. Planning outputs must explicitly map auth/payments/identity scope to existing auth service packages and capture missing functionality as auth-scope proposals instead of inventing local auth layers.

## 8-Phase Process

| Phase | Goal | Output | Key Action |
|-------|------|--------|------------|
| 0. Landscape | Understand neighbors | Relationship summary | Read INDEX.md + sibling shared.md |
| 0.5 Core Value Gate | Trim to the minimum winning slice | Core value summary | Cut expensive low-value scope before discovery |
| 1. Discovery | User stories | Draft stories | Binary "A or B?" refinement |
| 2. Contract | **LOCK shared.md** | Endpoints, errors | Confirm JSON shapes |
| 3. Backend | Business rules & permissions | backend.md + schema.mmd | Read mode's backend conventions |
| 4. Frontend | Screens & interactions | frontend.md + flows.md | Read mode's frontend patterns |
| 5. Strategy | Trade-offs | plan.md | Document "why" |
| 6. Sign-off | Create files | All files | released/ or planned/? |

---

### Phase 0: Landscape

**Goal:** Understand where this slice fits in the ecosystem before asking a single discovery question.

**Steps:**

1. **Read INDEX.md** at mode-defined `{plan_index}`
2. **Extract the tag** from the user's description (e.g., "scheduling feature" → `[scheduling]`). If unclear, infer from the slice name or ask.
3. **Find sibling slices** — all INDEX.md rows with the same `[tag]`:
   - Same tag = same domain cluster (e.g., `[protocol]` → protocol-phases, protocol-actions, action_carryover)
   - Same repo tags = shared codebase (e.g., `[auth-service]` slices share the auth layer)
4. **Read `shared.md` of the closest siblings** — understand existing API contracts, entity shapes, and endpoint patterns the new slice will neighbor. Only read 2-3 most relevant, not all.
5. **Check for explicit dependencies** — INDEX.md descriptions contain "Depends:", "Prerequisite for", "extends" notes. Surface any that mention or relate to this slice.
6. **Present a landscape summary** to the user before discovery begins:

```
## Landscape: {new_slice}

**Domain cluster:** [{tag}] — {N} existing slices
**Siblings:** {list with status}
**Existing entities nearby:** {key entities from sibling schema.mmd/shared.md}
**Potential dependencies:** {any explicit or inferred}
**Potential conflicts:** {overlapping endpoints, duplicate entities}
```

7. **Ask relationship questions** (only if genuinely ambiguous):
   - "Does this extend {sibling} or is it independent?"
   - "{sibling} already has a {entity} endpoint — should this slice reference it or create its own?"

**Why this matters:** Without landscape, the planner risks designing API contracts that duplicate existing entities, miss foreign key relationships, or conflict with sibling endpoints. A 2-minute INDEX.md read prevents hours of rework.

---

### Phase 0.5: Core Value Gate

**Goal:** Prevent planning debt by trimming the slice to the smallest user-visible win before discovery expands it.

**Steps:**

1. **Name the primary actor** — the role whose visible win anchors this slice.
2. **Name the single user-visible outcome** — one sentence describing what that actor can newly do or newly avoid.
3. **Define the minimum winning slice** — the smallest set of actions, states, and contract surface needed to deliver that outcome.
4. **List explicit non-goals** — name tempting additions to cut now:
   - admin/config surfaces
   - broad role matrices
   - reporting/export/history unless core to the win
   - abstractions for hypothetical reuse
   - edge-case completeness beyond the top safety failures
5. **State the debt avoided** — for each major cut, note the maintenance, coordination, or model-shift cost avoided by deferring it.
6. **Apply the binding rule** — if a proposed story does not materially improve the primary actor's visible win, defer it unless it is required for safety/risk containment or the user explicitly expands scope.
7. **Escalate placement questions out of band** — if the real uncertainty is adopt-vs-build, repo placement, or extraction, stop and use the `build-vs-clone` skill before continuing. Do not turn the slice plan into a repo-decision document.

**Output format:**

```markdown
## Core Value Gate

- Primary actor: ...
- User-visible outcome: ...
- Minimum winning slice: ...
- Explicit non-goals: ...
- Debt avoided by deferring them: ...
```

Carry this summary into `plan.md` and use it to reject scope creep in Phases 1-5. Do not proceed to Phase 1 until this gate is explicit.

---

### Phase 1: Discovery

**Goal:** Unambiguous user stories with test scenarios.

1. **Check standard stories** — Read `~/.claude/skills/domain-planner/references/standard-stories/` for applicable patterns. If the slice touches auth/RBAC, load `rbac.md` as a starting menu.
2. Start from the Core Value Gate — only keep stories that directly deliver the minimum winning slice or cover its top failure/safety cases.
3. Identify user types via multi-select question (can be multiple roles)
4. Extract stories: "As a [role], I need to [action], so that [outcome]"
5. **Refine with structured questions** — Probe vague terms ("all", "manage") with specific options
6. Add test scenarios per acceptance criterion
7. **Cross-reference siblings** — For each story, check: does a sibling slice already handle part of this? Flag overlaps.

**Red flags requiring refinement:**
- "All" or "everything" → narrow scope
- Vague verbs ("manage", "handle") → specific actions
- Missing edge cases → probe failure scenarios
- **Story overlaps a sibling's scope** → clarify boundary
- **Story adds admin polish, configurability, or abstraction without improving the primary actor's visible win** → defer it

---

### Phase 2: API Contract

**Goal:** Complete shared.md that both teams implement against.

**Cross-reference siblings from Phase 0:**
- Reuse existing entity IDs as foreign keys (don't reinvent `user_id`, `owner_id`, `enrollment_id`)
- Follow sibling endpoint naming conventions (e.g., if siblings use `/v1/{resource}`, don't use `/api/{resource}`)
- Reference sibling error code patterns (e.g., `{SLICE}_NOT_FOUND` convention)
- Do not add endpoints solely for deferred non-goals from the Core Value Gate

For each endpoint confirm: path, method, request/response shapes, error codes. Ask about specific uncertainties (not blanket approval).

After approval: **"CONTRACT LOCKED. Changes require discussion."**

---

### Phase 3: Backend Spec

**Before starting:** Read the mode's backend convention files (AGENTS.md, test philosophy docs).

**Cross-reference siblings from Phase 0:**
- Check sibling `schema.mmd` files for entities this slice should reference (FK relationships, not duplicated tables)
- If a sibling already owns an entity (e.g., `key_insights` owns the insights table), this slice should reference it, not recreate it

Questions to resolve:
- Data history requirements? (default update-in-place CRUD; only add version-chain patterns when explicitly requested)
- Access control policies? (owner-only, shared, lookup)
- Background jobs? (sync vs async for slow operations)
- **FK relationships to sibling entities?** (from Phase 0 landscape)

Output: schema.mmd conceptual ERD + backend.md business rules/permissions.

---

### Phase 4: Frontend Spec

**Before starting:** Read the mode's frontend patterns reference. Use mode-specific template if available (e.g., `frontend-{mode}.md`).

**Skip this phase** if the mode indicates API-only (no frontend).

**Goal:** Clear picture of what each role sees and does.

**Mode-specific templates:** Check `~/.claude/skills/domain-planner/assets/templates/frontend-{mode}.md` for a template tailored to the mode's architecture. Modes may have project-specific sections (portal placement, FeatureGate config, cross-portal visibility) that the generic template lacks.

### Critical Decision: Inline Widget vs Separate Page

Before defining routes, ask: "Does an existing widget already display this data type?"

| If Yes | If No |
|--------|-------|
| Extend the widget with role-based props | Create new page/widget |
| Add inline actions (toggles, modals) | Define new routes |

Features in resource-context views should almost always be **inline widget extensions**, not separate pages. Navigation breaks focus.

### Mode-Specific Phase 4 Questions

Use the questions from the mode file's "Phase 4 Questions" section instead of the generic questions in `~/.claude/skills/domain-planner/references/phase-questions.md`. Mode files define questions tailored to the project's widget system (e.g., portal placement, widget layers, feature gating).

Specify: screens per role, interactions, states, user flows (flows.md). Do NOT specify component structure, widget primitives, or TypeScript types — those are the scaffolder's job.

---

### Phase 5: Strategy

Document trade-offs table and out-of-scope items with rationale.

---

### Phase 6: Sign-off

#### 6a. Write Plan Files

Populate **all 6 required files** from planning session:
- `plan.md` — Strategy, user stories, trade-offs
- `shared.md` — API contracts (endpoints, request/response shapes)
- `backend.md` — Business rules, permissions, edge cases
- `frontend.md` — Screens, interactions, states per role
- `flows.md` — User journeys and state transitions
- `schema.mmd` — **REQUIRED** conceptual ERD

#### 6b. Quality Loop

Run the automated assess→fix→re-assess loop against the [plan quality rubric](~/.claude/skills/domain-planner/references/plan-quality-rubric.md). See [quality-loop-workflow.md](~/.claude/skills/domain-planner/references/quality-loop-workflow.md) for the full workflow.

```
Assess (subagent or inline) → Parse score
├── 100/100 → skip to 6c
└── < 100 → fix issues → re-assess (max 3 rounds)
```

**Assessor:** Fresh-context subagent (Profile A) or inline re-read (Profile B) — scores all 6 files against the 10-dimension rubric (10 pts each, 100 total). Returns structured issues table with file, location, and fix instruction per deduction.

**Fixer:** The orchestrator itself — has full domain context from the planning session. Applies targeted fixes from the issues table, then re-launches the assessor.

**Loop exit:** Score = 100, or 3 iterations reached (escalate remaining issues to user).

After the loop, report the final score before proceeding.

#### 6c. Save Location

Ask: "Save to released/ (locked) or planned/ (draft)?"

#### 6d. Synthesize `WORKGRAPH.md`

After the 6 plan files are accepted and saved, populate `WORKGRAPH.md` as the
execution handoff for downstream orchestration. This file is intentionally
outside the plan-quality rubric: it exists to bridge accepted specs into
parallel implementation waves.

Rules:
- One node per executable concern, not one node per tiny file edit
- Keep nodes concern-scoped: backend API, migration, frontend widget, test hardening
- Use explicit dependency IDs in `depends_on`
- Include `writes` globs or paths so parallel waves can avoid overlap
- Include `done_when` as binary completion criteria
- Include `validate_cmds` for the concrete commands the execution wave should run
- Use `status` values from: `todo`, `in_progress`, `done`, `blocked`, `skipped`

`WORKGRAPH.md` must stay lightweight. It is not a second plan document and it
is not a changelog.

#### 6e. Handoff

Handoff: "Ready to implement? Run the domain-planner skill and select 'Implement it'"

> **External review (optional):** `python3 ~/.claude/skills/domain-planner/scripts/review_plan.py --slice {slice_name} --execute` launches a Codex-based review using the same rubric. Use this for an independent second opinion after the quality loop passes.

---

## Quality Assessment Mode

When user selects "Check plan quality", run the Phase 6b quality loop as a standalone mode using [references/quality-loop-workflow.md](~/.claude/skills/domain-planner/references/quality-loop-workflow.md).

In this mode, `Scope Discipline` is not just generic anti-creep checking: it must explicitly grade whether the plan preserves the Phase 0.5 Core Value Gate and represents the highest-best-use 80/20 slice for the primary actor's visible win.

Auth service checks are mandatory in quality assessment mode for auth/payments/identity slices:
1. Confirm plan files use existing auth service packages from `{auth_packages_root}`.
2. Confirm any missing package capability is documented as an auth-scope proposal.
3. Confirm temporary local symlink/link usage (if needed for unpublished versions) includes final validation against published/live auth service packages.

## Orchestration Mode

When user selects "Implement it" for an existing plan, become the **orchestrator agent**.

Auth service enforcement is mandatory in orchestration mode:
1. Treat `{auth_packages_root}` as the auth/payments/identity source of truth.
2. Require scaffolder agents to reuse existing auth service packages before writing custom auth/payments/identity logic.
3. If an auth service gap is discovered, pause custom replacements and return an auth-scope proposal to the user.
4. If unpublished auth service changes are needed locally, use temporary symlink/link workflow first, then re-validate with published/live auth service packages before marking DONE.

See [references/orchestration-workflow.md](~/.claude/skills/domain-planner/references/orchestration-workflow.md) for the full workflow.

### Overview

```
┌─────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (this agent)                               │
│  Owns: progress checklist, agent coordination            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. Analyze plan to determine scope (which repos)        │
│  2. Launch scaffolder agents (parallel, one per repo)    │
│  3. Wait for completion                                  │
│  4. Launch audit agent (domain-reviewer)                 │
│  5. If issues: launch fix agents, re-audit               │
│  6. Loop until COMPLIANT                                 │
│  7. Update INDEX.md to DONE                              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Agent Coordination

1. **Analyze plan scope** — Read plan.md and the mode's repo configuration to determine which repos need work.

2. **Initialize progress checklist** — One item per repo + audit + completion.

3. **Launch parallel agents, one per repo involved:**
   - Backend repos → each agent uses the `domain-scaffolder` skill with `surface=backend`
   - Frontend repos → each agent uses the `domain-scaffolder` skill with `surface=frontend`
   - Each agent works in its own repo with its own conventions
   - Use the divide-and-conquer pattern: scope by concern, not files

4. **After scaffolding completes, launch an audit agent** using the domain-reviewer skill in audit mode.

5. **Handle audit results:**
   - COMPLIANT (score = 100/100) → mark done, update INDEX.md
   - Issues found → extract handoffs from AUDIT_REPORT.md, launch fix agents only for repos with issues

6. **Re-audit loop** — Max 5 attempts with stall triage, then escalate with a specific blocker report.

7. **Completion** — Update INDEX.md status to DONE, report results to user.

---

## Templates

See `~/.claude/skills/domain-planner/assets/templates/` — copied automatically by `~/.claude/skills/domain-planner/scripts/init_slice.py`.

## Related Skills

- **domain-scaffolder** — Generate backend or frontend code from plan using the explicit surface selection
- **domain-reviewer** — Audit implementation against plan, retire completed slices
- **divide-and-conquer** — Decompose multi-agent work into independent parallel concerns
