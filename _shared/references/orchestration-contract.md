# Orchestration Contract

Canonical cross-skill contract for human, orchestrator, worker, background-task,
and handoff behavior across the domain skill suite and its companion skills.

Use this file for shared rules. Keep skill-local workflow files focused on
skill-specific inputs, outputs, and domain logic.

## Scope

Use this contract when working on:

- `domain-planner` orchestration and plan-quality loops
- `domain-reviewer` audit and retire-session workflows
- `domain-scaffolder` completion handoffs
- `audit-plans` background validation and retirement handoffs
- `divide-and-conquer` parallel worker ownership and detached review handoffs
- `codex-tmux` detached review transport and background waiter behavior

## Canonical Names

- Public batch retirement command: `/domain-reviewer retire-claude-plans`
- Compatibility triggers: `retire session plans`, `consolidate session plans`,
  `clean up session plans`, and legacy `/domain-reviewer retire-claude`
- Canonical misc collector domain: `misc-session-work`
- Internal mode names may stay descriptive, for example `Retire-Session`, but
  public command naming should use `retire-claude-plans`

## Roles

### Human

The human decides when:

- a domain assignment is genuinely ambiguous
- deferred-item resolution affects roadmap meaning
- archival or cleanup changes documentation shape
- an external blocker requires scope or dependency decisions
- a sub-100 audit result should be accepted anyway

Research first. When asking, provide evidence, user impact, and a recommended
option. Do not ask generic approval questions.

### Orchestrator

The orchestrator owns:

- progress tracking
- shared-file ownership
- worker dispatch and phase boundaries
- score parsing and loop control
- escalation and final reporting

The orchestrator stays thin. It should prefer fresh-context workers for heavy
work when the runtime supports delegation.

### Workers

Workers own only their assigned concern and write scope. Workers must:

- respect single-owner file boundaries
- avoid revert/reset operations on teammate changes
- follow handoff instructions exactly
- return structured results or a clear blocker

## Runtime Profiles

Pick the runtime profile your environment supports:

- Subagent-capable runtime: delegate worker phases with fresh context
- Single-agent runtime: execute the same phases inline with explicit re-reads
- Detached long-running review: use `codex-tmux` instead of inventing a new
  background protocol

Skill-local docs may name concrete tools, but should not redefine the shared
role model or success criteria.

## Concurrency Contract

- Parallel work is allowed only when write scopes are disjoint
- Shared files are orchestrator-owned and edited sequentially
- Scope work by concern or domain, not arbitrary file lists
- Do not launch dependent workers in the same batch
- Read-only parallelism is preferred when discovery can be separated safely

## Ask Vs Auto-Proceed

- Do not ask for generic approval between plan and launch
- Do ask when ambiguity changes behavior or ownership materially
- Do ask before archival, destructive cleanup, or cross-domain reassignment
- Do not auto-retire or mark `DONE` below the canonical convergence target

## Background Task Contract

- Use background validation or detached review only when the foreground path can
  continue productively
- Use the runtime's native background-task handle when available
- Otherwise use a detached `codex-tmux` session for long-running review gates
- Collect background results through the runtime handle or the detached
  session's status/result commands; do not hard-code one platform primitive as
  if it were universal

## Scoring And Convergence

For the domain suite, the canonical pass target is:

- Plan quality loop: `100/100`
- Implementation audit loop: `100/100`

Implications:

- Do not mark a slice `DONE` below `100/100`
- Do not auto-retire below `100/100`
- Stall triage below `100/100` may retarget workers or escalate, but it must
  not silently convert remaining findings into a pass
- If a user explicitly accepts a sub-100 result, document that as an override;
  do not present it as normal convergence

## Handoff Artifacts

When a workflow emits or consumes handoff artifacts, keep ownership explicit:

- `WORKGRAPH.md`: execution dependency graph and write ownership
- `AUDIT_REPORT.md`: findings, score, and worker handoffs
- scaffolder completion handoff: emitted files, validation commands, and audit
  handoff
- `COMPLETED.md`: post-completion user-story summary

Each artifact should have one clear owner at each phase.
