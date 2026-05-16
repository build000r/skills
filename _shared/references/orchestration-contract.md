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

The orchestrator stays thin. It uses fresh-context workers for heavy work
through `divide-and-conquer`, NTM, or another explicit worker substrate.

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

For Beads-backed swarms, an assigned node is not in flight until `br show`
confirms `status=in_progress` with the expected assignee. Skill-local
orchestrators should claim nodes on behalf of the selected worker before
dispatch when the worker substrate cannot guarantee immediate Beads mutation.

## Runtime Substrate

Domain orchestration assumes a worker substrate. The default execution route is
`divide-and-conquer` backed by `vibing-with-ntm`; other explicit worker
transports are acceptable only when the skill-local workflow names them.

- NTM/divide-and-conquer: dispatch work by ready frontier with explicit
  ownership and fresh-context review workers
- Codex-delegated review: use `/codex:rescue` only as a named worker transport,
  not as a self-review fallback. Add `--background` for long-running work; check
  with `/codex:status` and `/codex:result`
- Missing worker substrate: stop and surface the missing prerequisite instead
  of executing audit, implementation, or hardening phases without worker isolation

When a skill can choose models, use the cheapest reliable router first:
cwd/workflow routing, skill-tag extraction, cleaned-request drafting, and
read-only clerk/preflight work should route through the workspace
`voice-to-text` Grok dispatcher when available. Route design-related execution
nodes to Claude Opus and route non-design execution nodes to Codex by default.
Design-related includes UI/UX, visual design, design systems, CSS/tokens,
responsive behavior, screenshots, visual parity, product interaction copy, and
fresh-eyes review of those surfaces.

## Fresh-Eyes Review Gates

Fresh-context review is mandatory. At minimum, the initial implementation audit
and each post-fix re-review run as a worker that reads the plan, code,
standards, and prior report from scratch. For high risk or cross-repo slices,
add an independent hardening/review worker after `100/100` plan compliance and
before retirement.

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

- `br` epic + child issues: execution dependency graph, ready frontier, write
  ownership, validation, risk gates, and the canonical worker dispatch contract
- `WORKGRAPH.md`: optional generated view of `br` state; never the mutable
  source of execution state
- `EXECUTION_CONTEXT.md`: optional generated dispatch summary; never the place
  to repair missing worker-only context
- `WG-*_RESULT.md`: worker evidence attachment; it can support reconciliation
  but cannot override `br` status, write scope, or acceptance criteria
- `AUDIT_REPORT.md`: findings, score, and worker handoffs
- scaffolder completion handoff: emitted files, validation commands, and audit
  handoff
- `COMPLETED.md`: post-completion user-story summary

Each artifact should have one clear owner at each phase.
