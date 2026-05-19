---
name: domain-reviewer
description: "Three modes: audit active implementations against plan, retire completed slices into lean COMPLETED.md summaries, and retire-session consolidation of DONE session plans. Use for review/audit slice, what's left checks, retire/close out/finalize slice, or retire session plans workflows."
license: MIT
---

# Domain Reviewer

Three modes: **Audit** (autonomous loop), **Retire** (post-completion), and **Retire-Session** (session plan consolidation).

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using domain-reviewer`.

Preferred format: `Using domain-reviewer in <mode|resolving> mode for <slice|slice-resolution>.`

Do not change or omit that prefix.

## Use This For

- Auditing an implementation against an existing slice plan
- Retiring a completed slice into lean completion docs
- Consolidating DONE session plans into domain-level completion artifacts

## Do Not Use This For

- Initial slice planning or API-contract discovery
- Direct scaffolding of backend or frontend code from a plan
- Generic repo review with no plan artifact to compare against

**Skill root:** `~/.claude/skills/domain-reviewer/` — all relative paths below resolve from here.

**Shared orchestration rules:** Use
[references/orchestration-contract.md](~/.claude/skills/domain-reviewer/references/orchestration-contract.md)
for the cross-skill contract on worker ownership, background-task handling,
public retirement naming, and the domain suite's `100/100` convergence rule.

## Operator Companion Gates

Use [`_shared/references/domain-companion-gates.md`](../_shared/references/domain-companion-gates.md)
for optional operator-level gates around this public skill.

- Use `reality-check-for-project` for "what's left", retire, closeout, or
  status checks where the real question is whether shipped code delivers the
  project vision, not only whether one plan is locally satisfied.
- Use `no-ragrets` before turning audit findings into remediation Beads: name
  the future failure being avoided and the evidence that the fix graph will
  prevent it.
- Use `beads-br` for finding/fix issue creation, claims, blockers, closeout,
  and sync mechanics.
- Use `beads-workflow` when audit findings or reality-check results need to
  become a multi-issue remediation graph rather than one direct fix issue.
- Use `beads-bv` before launching fix waves to check dependency order, ready
  frontier, blocked nodes, and stale priority.

These companion skills may be operator-private or globally installed. Keep them
as body-level gates in this public skill unless an operator-private overlay
intentionally makes them hard dependencies.

## Auth Service Requirements (All Modes)

The shared auth/payments/identity service (`{auth_packages_root}` from the client overlay) is the canonical authentication, payments, and identity layer.

1. Audit and retire decisions must treat existing auth service packages as the source of truth for auth/payments/identity behaviors.
2. If implementation needs functionality not covered by current auth service packages, require an "auth-scope proposal" instead of accepting local replacement layers.
3. If local unpublished auth service versions are used via symlink/link, require final verification against published/live auth service packages before considering a slice fully compliant.

## Delivery Strategy Guardrails (All Modes)

1. Default expectation is big-bang target-state delivery.
2. Flag unrequested compatibility mechanics (legacy endpoints, dual routing, adapter layers, shadow write/read paths) as scope violations.
3. If production data is affected, require a dedicated DB transition section with backup, raw `psql` execution plan, transactional/idempotent safety, verification, and rollback.

- **Audit:** Autonomous audit→fix→retire loop — runs worker phases through `/divide-and-conquer`/NTM, converges to 100/100, then retires
- **Retire:** Investigate completed slices, categorize user stories, clean up bloat
- **Retire-Session:** Roll DONE session plans into domain COMPLETED.md files, archive originals

## Fresh-Eyes Review Contract

Audit mode is not a one-shot review. The initial audit, every post-fix
re-review, and any high-risk hardening review must run with fresh context. The
worker must read the plan, implementation, standards, and prior report from
disk instead of relying on the orchestrator's memory.

The default worker substrate is `divide-and-conquer` backed by
`vibing-with-ntm`. If no worker substrate is available, stop and surface the
missing prerequisite instead of replacing review gates with local self-review.
When audit findings require fixes, convert them into `br` issues and route the
ready fix frontier through `/divide-and-conquer`; do not launch bespoke fix
subagents directly from this skill.

## Execution Runtime

This skill requires a worker substrate for audit, re-review, and fix phases:

- **Default:** `divide-and-conquer` + `vibing-with-ntm` for worker dispatch,
  reservations, monitoring, collection, and fresh-eyes reviews.
- **Named transports:** `/codex:rescue` or helper scripts may be used only when
  `/divide-and-conquer` or the user explicitly selects them as the worker
  transport.
- **Unavailable substrate:** stop and surface the missing prerequisite. Do not
  run audit/re-review/fix phases in-process.

Terminology bridge used throughout this skill:

| This skill says | Means |
|-----------------|-------|
| "Task agent" / "subagent" | Worker phase execution unit |
| "Spawn" | Dispatch through `/divide-and-conquer`/NTM; named transports are explicit fallbacks |
| "Orchestrator" | The active agent/session coordinating loop decisions |

### Worker Runtime Setup

When using a worker-capable runtime:

1. Run one orchestrator plus scoped workers (audit, fix-backend, fix-frontend, retire).
2. Give each worker explicit owned paths (for example `backend/**` vs `frontend/**`).
3. Keep shared files single-owner/sequential (orchestrator-owned).
4. No extra worktrees required; workers collaborate in the same repository.
5. Reuse [references/codex-mcp-orchestration-template.md](~/.claude/skills/domain-reviewer/references/codex-mcp-orchestration-template.md) for standard worker prompts.

### Codex Worker Delegation (via `codex-plugin-cc`)

When `/divide-and-conquer` selects Codex as the worker transport and the
`codex-plugin-cc` plugin is loaded, delegate worker phases via `/codex:rescue`
instead of shelling out to Python scripts:

```
# Audit worker (xhigh for thorough review)
/codex:rescue --model gpt-5.5 --effort xhigh \
  Audit the {slice} slice implementation against its plan. \
  {paste constructed worker prompt from codex-mcp-orchestration-template.md}

# Fix workers (xhigh effort for bounded implementation)
/codex:rescue --model gpt-5.5 --effort xhigh \
  Apply backend fixes for {slice} from handoff block: \
  {paste backend handoff block from AUDIT_REPORT.md}

# Re-review worker (xhigh for thorough re-assessment)
/codex:rescue --model gpt-5.5 --effort xhigh \
  Re-review the {slice} slice after fixes (re-review #{iteration}). \
  {paste constructed re-review prompt}
```

Add `--background` when running fix workers in parallel or when the orchestrator can continue productively.

The `launch_codex_worker.py` and `run_codex_audit_loop.py` scripts remain
available as standalone worker transports for environments without the plugin.

## Plan Storage

Plan storage is resolved from the skillbox client overlay. Each client defines plan paths in its `overlay.yaml`, and the `focus` command generates a resolved `context.yaml` with absolute paths:

```yaml
# context.yaml (auto-generated by skillbox focus)
plans:
  plan_root: /path/to/clients/{client}/plans/released
  plan_index: /path/to/clients/{client}/plans/INDEX.md
  session_plans: /path/to/clients/{client}/plans/sessions
  session_plan_index: /path/to/clients/{client}/plans/sessions/INDEX.md
```

To find a slice: read `{plan_root}/{slice}/`. To check what exists: read `{plan_index}`.
DO NOT search the filesystem for plans.

## Client Context (Skillbox)

Implementation context — repos, conventions, stack — comes from the skillbox client overlay (`skillbox-config/clients/{client}/overlay.yaml`).

The overlay defines:

- **cwd_match** — directory pattern for auto-detection
- **plans** — plan_root, plan_index, session_plans, session_plan_index
- **backend** — repo, domain_path, migration_tool, migration_path
- **frontend** — repo, features_path, types_path, api_only
- **auth** — packages_root, python_packages, npm_packages
- **Tag-to-domain mapping** — maps plan tags to domain folders (for retire-session mode)
- **Commit conventions** — message formats for audit and retire commits

Before manual `rg`/`sed`/`find` inspection, capture the active overlay and
slice-plan state with the shared context snapshot helper:

```bash
python3 ~/.claude/skills/_shared/scripts/domain_context_snapshot.py --cwd "$PWD" --slice {slice_name} --pretty
```

Use the JSON output to identify plan roots, implementation repos, convention
references, required plan-file presence, and existing workflow artifacts such as
`AUDIT_REPORT.md` or `COMPLETED.md`. Only fall back to freehand shell inspection
for concrete files the snapshot surfaces as relevant.

**If no client overlay matches the current directory:**
1. Tell the user no overlay matches and create one using the skillbox-quickstart scan + generate flow before proceeding.
2. If the user declines overlay creation, you can still run workflows with explicit plan paths via CLI arguments.
3. For retire mode, implementation context can be minimal, but plan storage paths are still required.
4. For audit mode, list available client overlays and ask the user which to use when auto-detection fails.
5. DO NOT search the filesystem. DO NOT launch extra discovery workers.

## Mode Detection

| User Says | Mode | Read |
|-----------|------|------|
| "review", "audit" | Audit | [references/orchestration-workflow.md](~/.claude/skills/domain-reviewer/references/orchestration-workflow.md) |
| "retire", "close out", "consolidate", "clean up", "finalize" + slice name | Retire | [references/retire-workflow.md](~/.claude/skills/domain-reviewer/references/retire-workflow.md) |
| "`retire-claude-plans`", "retire session plans", "consolidate session plans", "clean up session plans" | Retire-Session | [references/retire-session-workflow.md](~/.claude/skills/domain-reviewer/references/retire-session-workflow.md) |

**After detecting mode, read the corresponding workflow reference file and follow it.**

> **Note:** "re-review" and "check fixes" are no longer user-triggered — they happen automatically within the audit orchestration loop.

## Context Detection

**On trigger, detect project context from the skillbox client overlay** (match CWD to `cwd_match` patterns).

The client overlay specifies:
- Which repos to audit (backend, frontend, or both)
- Where implementation code lives (path patterns per layer)
- Which convention files define compliance standards
- Where plan artifacts are stored

**Before auditing, read the client overlay's convention files** for the compliance standards to check against.

## On Trigger

1. Start with a stable first progress update:
   - `Using domain-reviewer in <mode|resolving> mode for <slice|slice-resolution>.`
2. **Detect mode** from the user's words and current context (see Mode Detection table above).
3. **Resolve the slice before asking**:
   - explicit slice name in the request
   - explicit plan path or current `AUDIT_REPORT.md` / `COMPLETED.md` handoff artifact
   - one clear slice implied by the current mode, cwd, or upstream handoff context
4. Ask the user for a slice only when there are multiple plausible slices or none can be resolved safely.
5. **Read the corresponding workflow reference file**
6. Follow that workflow's step-by-step process

### Audit Mode: Orchestrator Behavior

In audit mode, **you are the orchestrator**. Use worker phases for heavy work
through NTM/divide-and-conquer or another named worker transport:

1. Read client overlay context + reference files (audit-workflow.md, audit-template.md, convention files)
2. Enter the autonomous loop (see orchestration-workflow.md)
3. Run audit/re-review worker phase with full instructions and clean inputs
4. Parse scores from AUDIT_REPORT.md after each cycle
5. Dispatch fix worker phase(s) when score < 100, using canonical `domain-scaffolder` handoffs with explicit `surface=backend` or `surface=frontend`
6. Enforce auth service compliance in auth/payments/identity scope: no local replacement layer, gaps captured as auth-scope proposals, local-link flow finalized on published/live packages
7. Enforce delivery strategy compliance: no unrequested legacy compatibility code; DB-transition runbook required when production data is impacted
8. On convergence (= 100/100): transition to retirement — **you do this yourself** (you have context budget)
9. On max iterations (5): escalate to user with current score + remaining issues

## Concurrency Contract

When running multiple workers in parallel in the same repository:

- Assign explicit owned file scopes per worker.
- Shared files have a single owner (typically orchestrator), edited sequentially only.
  - Examples: `package.json`, lockfiles, root configs, shared index files.
- Workers must not run destructive git operations or revert teammate changes.
  - Forbidden unless explicitly requested by user: `git reset --hard`, `git checkout --`, mass revert commands.
- If a worker needs to touch another scope, it asks for a handoff instead of editing directly.

## Severity Levels

| Level | Impact | Example |
|-------|--------|---------|
| Critical | Blocks deploy | Zero test coverage, security hole |
| High | Major deviation | Placeholder returning fake data |
| Medium | Notable gap | Signature changed without docs update |
| Low | Minor issue | Inline loading state vs shared component |

## Centralized Plan Tracking

Plans, COMPLETED.md, AUDIT_REPORT.md, and INDEX.md all live under the client overlay's `plan_root`:
```
{plan_root}/{slice}/
```

Implementation code lives in context-specific repos, but plan artifacts remain centralized by client overlay.

**If the released folder for a slice doesn't exist yet** (e.g., slice was built ad-hoc without formal planning), create it before writing COMPLETED.md or AUDIT_REPORT.md.

## Automated Handoffs (Audit Mode)

In audit mode, handoffs to fix workers are **automated by the orchestrator**
through `/divide-and-conquer` and Beads — no manual copy-paste needed.

The orchestrator:
1. Reads the `## Agent Handoffs` section from AUDIT_REPORT.md
2. Canonicalizes each implementation handoff to `domain-scaffolder` with explicit surface, slice, plan path, and client-overlay-specific references
3. Augments each handoff block with client-overlay-specific paths and convention file references
4. Runs worker phase(s) with the constructed prompts through `/divide-and-conquer` and the ready Beads frontier
5. Backend and frontend fix workers run in parallel when both have issues and scopes are disjoint

The handoff blocks in AUDIT_REPORT.md should reference the canonical
`domain-scaffolder` skill with explicit surface selection for greenfield work.
Older audit artifacts may still mention the legacy wrapper names, but the
orchestrator should normalize them back to the canonical scaffolder when
constructing worker prompts.

| Issue Type | Worker Gets | Key Context |
|------------|---------------|-------------|
| Backend fixes | Canonical `domain-scaffolder surface=backend` handoff + backend convention file paths + plan paths | TDD-first, domain structure |
| Frontend fixes | Canonical `domain-scaffolder surface=frontend` handoff + frontend patterns reference path + plan paths | Component patterns, hooks |

## Related Skills

- [[skill-issue]]
- **domain-planner** -- Creates the plans this skill audits
- **domain-scaffolder** -- Generates backend or frontend code from plan using explicit surface selection
- **divide-and-conquer** -- Decompose multi-agent work into independent parallel concerns
- **no-ragrets** -- Optional operator gate for remediation success and regret-avoidance checks
- **reality-check-for-project** -- Optional operator gate for strategic code/docs/Beads alignment
- **beads-workflow** -- Optional operator gate for multi-issue remediation graph conversion
- **beads-br** -- Optional operator gate for `br` issue lifecycle mechanics
- **beads-bv** -- Optional operator gate for Beads graph health, priority, and ready-frontier review
