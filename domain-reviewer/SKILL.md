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

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical authentication, payments, and identity layer.

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

### Subagent Runtime Setup (Codex MCP + Agents SDK)

When using a subagent-capable runtime with Codex:

1. Start one Codex MCP server rooted at the target repo (`cwd` = repo root).
2. Run one orchestrator worker plus scoped workers (audit, fix-backend, fix-frontend, retire).
3. Give each worker explicit owned paths (for example `backend/**` vs `frontend/**`).
4. Keep shared files single-owner/sequential (orchestrator-owned).
5. No extra worktrees required; workers collaborate in the same repository.
6. Reuse [references/codex-mcp-orchestration-template.md](~/.claude/skills/domain-reviewer/references/codex-mcp-orchestration-template.md) for standard worker prompts.
7. For prompt generation/launch, use `python3 ~/.claude/skills/domain-reviewer/scripts/launch_codex_worker.py`.
8. For full audit loop automation, use `python3 ~/.claude/skills/domain-reviewer/scripts/run_codex_audit_loop.py`.

## Plan Storage (Mode-Defined)

Plan storage comes from the active reviewer mode file (`~/.claude/skills/domain-reviewer/modes/{mode}.md`):

```
plan_root: <mode value>
plan_index: <mode value>
session_plan_index: <mode value>
```

To find a slice: read `{plan_root}/{slice}/`. To check what exists: read `{plan_index}`.
DO NOT search the filesystem for plans.

## Modes (Implementation Context)

Modes provide implementation context and plan storage paths for reviewer workflows.

Check `~/.claude/skills/domain-reviewer/modes/` for project-specific configuration. Each mode defines:

- **cwd_match** -- directory pattern for auto-detection
- **Implementation locations** -- backend and frontend repos with path patterns
- **Compliance standards** -- backend convention files, frontend patterns reference
- **Tag-to-domain mapping** -- maps plan tags to domain folders (for retire-session mode)
- **Commit conventions** -- message formats for audit and retire commits

**If no mode matches the current directory:**
1. You can still run workflows if explicit plan paths are provided via CLI arguments.
2. For retire mode, implementation context can be minimal, but plan storage paths are still required.
3. For audit mode, list available modes (from `~/.claude/skills/domain-reviewer/modes/*.md` filenames) and ask the user which to use when auto-detection fails.
4. DO NOT search the filesystem. DO NOT launch extra discovery workers.

See [references/mode-template.md](~/.claude/skills/domain-reviewer/references/mode-template.md) for the mode file format.

## Mode Detection

| User Says | Mode | Read |
|-----------|------|------|
| "review", "audit" | Audit | [references/orchestration-workflow.md](~/.claude/skills/domain-reviewer/references/orchestration-workflow.md) |
| "retire", "close out", "consolidate", "clean up", "finalize" + slice name | Retire | [references/retire-workflow.md](~/.claude/skills/domain-reviewer/references/retire-workflow.md) |
| "`retire-claude-plans`", "retire session plans", "consolidate session plans", "clean up session plans" | Retire-Session | [references/retire-session-workflow.md](~/.claude/skills/domain-reviewer/references/retire-session-workflow.md) |

**After detecting mode, read the corresponding workflow reference file and follow it.**

> **Note:** "re-review" and "check fixes" are no longer user-triggered — they happen automatically within the audit orchestration loop.

## Context Detection

**On trigger, detect project context from the mode file** (match CWD to `cwd_match` patterns).

The mode file specifies:
- Which repos to audit (backend, frontend, or both)
- Where implementation code lives (path patterns per layer)
- Which convention files define compliance standards
- Where plan artifacts are stored

**Before auditing, read the mode's convention files** for the compliance standards to check against.

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

1. Read mode file + reference files (audit-workflow.md, audit-template.md, convention files)
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

Plans, COMPLETED.md, AUDIT_REPORT.md, and INDEX.md all live under mode-defined `plan_root`:
```
{plan_root}/{slice}/
```

Implementation code lives in context-specific repos, but plan artifacts remain centralized by mode.

**If the released folder for a slice doesn't exist yet** (e.g., slice was built ad-hoc without formal planning), create it before writing COMPLETED.md or AUDIT_REPORT.md.

## Automated Handoffs (Audit Mode)

In audit mode, handoffs to fix workers are **automated by the orchestrator** — no manual copy-paste needed.

The orchestrator:
1. Reads the `## Agent Handoffs` section from AUDIT_REPORT.md
2. Canonicalizes each implementation handoff to `domain-scaffolder` with explicit surface, slice, plan path, and mode-specific references
3. Augments each handoff block with mode-specific paths and convention file references
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

- **domain-planner** -- Creates the plans this skill audits
- **domain-scaffolder** -- Generates backend or frontend code from plan using explicit surface selection
- **divide-and-conquer** -- Decompose multi-agent work into independent parallel concerns
