---
name: domain-reviewer
description: "Three modes: audit active implementations against plan, retire completed slices into lean COMPLETED.md summaries, and retire-session consolidation of DONE session plans. Use for review/audit slice, what's left checks, retire/close out/finalize slice, or retire session plans workflows."
license: MIT
---

# Domain Reviewer

Three modes: **Audit** (autonomous loop), **Retire** (post-completion), and **Retire-Session** (session plan consolidation).

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

## Auth Service Requirements (All Modes)

The shared auth/payments/identity service (`{auth_packages_root}` from the client overlay) is the canonical authentication, payments, and identity layer.

1. Audit and retire decisions must treat existing auth service packages as the source of truth for auth/payments/identity behaviors.
2. If implementation needs functionality not covered by current auth service packages, require an "auth-scope proposal" instead of accepting local replacement layers.
3. If local unpublished auth service versions are used via symlink/link, require final verification against published/live auth service packages before considering a slice fully compliant.

## Delivery Strategy Guardrails (All Modes)

1. Default expectation is big-bang target-state delivery.
2. Flag unrequested compatibility mechanics (legacy endpoints, dual routing, adapter layers, shadow write/read paths) as scope violations.
3. If production data is affected, require a dedicated DB transition section with backup, raw `psql` execution plan, transactional/idempotent safety, verification, and rollback.

- **Audit:** Autonomous audit→fix→retire loop — runs worker phases (subagents if available, inline fallback), converges to 100/100, then retires
- **Retire:** Investigate completed slices, categorize user stories, clean up bloat
- **Retire-Session:** Roll DONE session plans into domain COMPLETED.md files, archive originals

## Execution Profiles

This skill is agent-platform neutral. Pick the profile your runtime supports:

- **Profile A: Subagent-capable runtimes** (Claude Task agents, Agents SDK with worker agents, similar)
  - Run audit/re-review/fix as separate worker runs with fresh context where possible.
  - Orchestrator coordinates handoffs, score parsing, and loop control.
- **Profile B: Single-agent runtimes** (Codex CLI session without subagent primitives)
  - Run the same phases inline in one session.
  - Simulate fresh context by re-reading required files at each phase.
  - Keep phase boundaries explicit: `AUDIT` -> `SCORE CHECK` -> `FIX` -> repeat.

Terminology bridge used throughout this skill:

| This skill says | Means |
|-----------------|-------|
| "Task agent" / "subagent" | Worker phase execution unit |
| "Spawn" | Delegate if runtime supports it; otherwise execute inline |
| "Orchestrator" | The active agent/session coordinating loop decisions |

### Subagent Runtime Setup

When using a subagent-capable runtime:

1. Run one orchestrator plus scoped workers (audit, fix-backend, fix-frontend, retire).
2. Give each worker explicit owned paths (for example `backend/**` vs `frontend/**`).
3. Keep shared files single-owner/sequential (orchestrator-owned).
4. No extra worktrees required; workers collaborate in the same repository.
5. Reuse [references/codex-mcp-orchestration-template.md](~/.claude/skills/domain-reviewer/references/codex-mcp-orchestration-template.md) for standard worker prompts.

### Codex Worker Delegation (via `codex-plugin-cc`)

When the `codex-plugin-cc` plugin is loaded, delegate worker phases to Codex via `/codex:rescue` instead of shelling out to Python scripts:

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

The `launch_codex_worker.py` and `run_codex_audit_loop.py` scripts remain available as standalone fallbacks for environments without the plugin.

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

In audit mode, **you are the orchestrator**. Use worker phases for heavy work (delegate when supported, otherwise execute inline):

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

In audit mode, handoffs to fix workers are **automated by the orchestrator** — no manual copy-paste needed.

The orchestrator:
1. Reads the `## Agent Handoffs` section from AUDIT_REPORT.md
2. Canonicalizes each implementation handoff to `domain-scaffolder` with explicit surface, slice, plan path, and client-overlay-specific references
3. Augments each handoff block with client-overlay-specific paths and convention file references
4. Runs worker phase(s) with the constructed prompts (delegated or inline)
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
