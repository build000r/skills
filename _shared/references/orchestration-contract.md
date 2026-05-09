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

### End-To-End Delivery Default

When the user asks to implement a domain slice, the orchestrator owns the whole
delivery chain. It must not stop after writing a plan, launching a first worker,
or producing a partial audit unless a real blocker requires a human decision.

Default completion means:

1. accepted plan or plan-quality pass
2. implementation/scaffolding across every in-scope repo
3. fresh-context audit and re-review loops to `100/100`
4. post-audit hardening for the touched code paths when configured
5. retirement/closeout artifacts
6. clean commit batching across touched repos
7. final report with scores, validation, commits, and leftovers

Pause only for materially ambiguous ownership, external blockers, missing
canonical dependencies, destructive operations, or an explicit user override.

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
- Codex-delegated review: use `/codex:rescue` (via `codex-plugin-cc`) with
  `--model gpt-5.4 --effort xhigh` for detached review gates. Add
  `--background` for long-running work; check with `/codex:status` and
  `/codex:result`

## Fresh-Eyes Review Gates

Use fresh-context review whenever the runtime supports it. At minimum, the
initial implementation audit and each post-fix re-review should run as a worker
that reads the plan, code, standards, and prior report from scratch. For high
risk or cross-repo slices, add an independent hardening/review worker after
`100/100` plan compliance and before retirement.

In single-agent runtimes, simulate fresh eyes by closing the prior phase,
re-reading the required inputs from disk, and reviewing from the written
artifacts rather than memory.

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
- For Codex-delegated review, use `/codex:rescue --background` and collect
  results via `/codex:result`
- Collect background results through the runtime handle or the plugin's
  status/result commands; do not hard-code one platform primitive as if it were
  universal

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
