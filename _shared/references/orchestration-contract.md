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

### Handoff-First Root Boundary

When a worker substrate is available, the root orchestrator must hand execution
Beads to workers or subgoal controllers instead of personally doing leaf-node
work. The root may inspect enough code to select, tighten, claim, dispatch, and
verify a node, but implementation, audit sweeps, random-fix sequences, and
fresh-eyes review belong to assigned workers with explicit Beads ownership.

Root-owned work is limited to:

- selecting the next ready frontier from Beads/BV
- tightening fuzzy node contracts before dispatch
- claiming Beads on behalf of specific workers
- launching/tending worker sessions and subgoal controllers
- reconciling artifacts, validation, and Beads state
- doing final integration, shared-file arbitration, commit acceptance, and user
  closeout

The root may apply a tiny emergency patch only when it is needed to unblock the
swarm, is faster than launching a worker, and is recorded as root-owned
integration work. It must not turn that exception into a leaf-work loop.

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

### NTM Root Preflight

Before spawning an NTM-backed implementation or review wave, the orchestrator
must prove the session name resolves to the intended checkout. NTM derives pane
working directories from `projects_base/session_name`; a convenience wave name
can otherwise launch workers in the wrong repo.

Minimum check:

```bash
repo_root="$(git rev-parse --show-toplevel)"
rg '^projects_base' ~/.config/ntm/config.toml
ntm list --json
```

If `projects_base/<session-name>` does not resolve to `repo_root`, do not spawn
by basename. Fix the mapping, choose a supported session name, or block the
work item with the exact root-resolution failure. A successful `ntm spawn`,
idle pane, or worker self-report is not sufficient proof; verify the node brief
landed in the intended checkout before counting the node in flight.

When a skill can choose models, record the route and authority separately in
the Bead or dispatch contract before launch. Route NTM runtime orchestration —
frontier reads, claims of accepted leaves, dispatch, tending, harvest, and
convergence — to a Grok 4.6 plugin controller. Runtime orchestration is not
planning: Grok must escalate decomposition, dependency design, acceptance-
criteria authorship, plan synthesis, architecture, ambiguity, and final
acceptance. Route those planning/authority roles, plus no-ragrets bead
composition, domain-planner sessions and quality loops, system design,
high-impact code or architecture decisions, ambiguous repairs, integration
review, commit acceptance, and final-say review to Codex `gpt-5.6-sol` at
`medium` by default. Use SOL `max` for pivotal/high-consequence planning or
when Grok/another model is demonstrably struggling. If SOL is unavailable,
route the same planning/authority roles to Codex
`gpt-5.6-terra` with `ultra` effort. Route design-related
execution nodes to Grok 4.6 design/UX through `--grok=N:grok-4.6` and record the
route. Use Codex `gpt-5.6-sol` with `max` for pivotal route-blocker triage;
ordinary authority remains SOL medium. Design-related includes UI/UX, visual design, design systems,
CSS/tokens, responsive behavior, screenshots, visual parity, product
interaction copy, and fresh-eyes review of those surfaces. For bounded
task-runner work, prefer Grok 4.6 when the owning Bead names the exact
write scope or read-only artifact, validation, stop rules, review owner, and
final authority. Good task-runner work includes cwd/workflow routing, skill-tag
extraction, cleaned-request drafting, read-only clerk/preflight work,
mechanical scripting, fixtures/docs cleanup, generated-command cleanup,
classification into a declared artifact, and scoped commit batching. Use the
workspace `voice-to-text` Grok dispatcher for cheap routing/preflight, the NTM
Grok plugin when interactive pane preflight passes, Swimmers or the local
Grok 4.6 route for maintained task-runner sessions, and direct headless Grok
with a prompt file for bounded one-shots. If Grok 4.6 stalls, emits no
artifact, fails validation, leaves scope, or needs judgment it does not own,
escalate authority questions to Codex `gpt-5.6-sol` max; route design/UX work
to Grok 4.6 design/UX and record the route failure.

### Grok routing — NTM orchestrator/plugin preferred, sidecar backup

**Preferred (interactive swarms):** NTM agent plugin at `~/.config/ntm/agents/grok.toml`.
Every actively orchestrated NTM swarm should reserve one Grok 4.6 plugin pane
as its runtime controller. The installed plugin is already Grok 4.6; spawn with
`ntm spawn <session> --grok=1`
(alias `--grk`). Send with
`ntm send <session> --panes=N` — there is no `ntm send --grok`. Agents must
run the fix-if-broken checklist in `skills-private/ntm/references/GROK-ROUTING.md`
before treating sidecars as the default.

**Backup (headless, routing, or broken plugin):** sidecar lanes below. Use when
plugin preflight fails, work is read-only/headless, or automation cannot rely on
NTM pane typing (plugin Grok panes report as `user` in `--robot-*`).

### Grok CLI sidecar lanes (backup)

When the plugin route is unsuitable or failed repair, use one of these explicit
sidecar/task-runner lanes and reconcile the output back into the owning workflow:

- **Availability preflight:** verify `command -v grok` and inspect the current
  CLI shape with `grok --help` before promising a Grok lane. If the route needs
  Swimmers, verify the Swimmers service/client path separately; a working Grok
  binary alone does not prove hidden-session dispatch works.
- **Dispatcher lane:** use the workspace sibling `voice-to-text` dispatcher for
  cheap cwd selection, skill-tag extraction, cleaned worker requests, and other
  read-only routing/preflight decisions. It runs Grok headlessly with
  `--prompt-file`, JSON output, no subagents, disabled web search, and a
  read-only sandbox. Treat this as routing evidence, not execution authority.
- **Swimmers hidden-session lane:** when a Grok worker needs a maintained
  session or should receive follow-up prompts, spawn it through Swimmers with
  `spawn_tool: "grok"` (or the `voice-to-text` Swimmers client helper). Swimmers
  already uses prompt files for the initial request and honors `SWIMMERS_DISPATCHER_GROK_BIN`
  for the Grok binary override (defaults to `grok` on PATH).
- **Direct headless lane:** for a bounded one-shot analysis, run Grok CLI
  directly with a prompt file and capture the response into the caller's normal
  artifact path. Keep it read-only unless the caller has an explicit write
  scope and validation contract.
- **Grok 4.6 task-runner lane:** for narrow writer tasks such as mechanical
  scripts, fixtures, docs cleanup, generated command cleanup, classification
  artifacts, deterministic codemods, or `$commit` batching, prefer the locally
  configured Grok 4.6 route when the Bead names exact writes, validation
  commands, stop rules, a Codex `gpt-5.6-sol` review owner, and final acceptance
  authority. Composer/Grok may create a commit in a scoped `$commit` node, but
  Codex `gpt-5.6-sol` owns acceptance and any amend or follow-up decision.

Direct prompt-file one-shot shape:

```bash
grok --prompt-file "$PROMPT_FILE" \
  --cwd "$REPO_ROOT" \
  --always-approve \
  --max-turns 20
```

For read-only work, put the read-only rule, allowed commands, and expected
artifact path inside `$PROMPT_FILE`. Prefer a declared output file over streamed
stdout. Recent Grok CLI observations showed top-level `--output-format
plain|json` can fail silently; use prompt-file plus an expected artifact unless
the local `grok --help` and a smoke run prove a different shape works.

Record the route in the caller's dispatch contract:

```text
Model route: Grok NTM plugin       # preferred interactive swarm pane
Model route: Grok 4.6 NTM orchestrator  # runtime controller; never planning
Model route: Grok dispatcher       # backup pure routing/preflight
Model route: Grok CLI sidecar      # backup bounded read-only analysis/ideation
Model route: Grok CLI writer       # legacy narrow writer; prefer Grok 4.6 task-runner
Model route: Grok 4.6 task-runner  # narrow writer or commit-runner node
Model route: Grok 4.6 design/UX    # design/UI/visual/fresh-eyes design work
Model route: Codex gpt-5.6-sol medium  # ordinary planning and authority
Model route: Codex gpt-5.6-sol max escalation  # pivotal planning or another model struggling
Model route: Codex gpt-5.6-terra ultra fallback  # same authority roles when SOL is unavailable
```

Grok NTM plugin panes exist in tmux but are often misclassified as `user` in
`ntm --robot-*` state. Sidecar lanes do not show up as NTM panes at all.
For either non-canonical route, verify completion through pane capture, Swimmers
session state, direct process exit/output, expected artifact files, and the
workflow's source of truth (`br`, report checklist, or equivalent) before
counting work done.

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

## Subgoal Tier

For massive slices, a root orchestrator may delegate a label-filtered subset of
the Beads graph to a subgoal controller. A subgoal is a delegation boundary over
an independently runnable ready frontier, not a second source of truth, an NTM
session name, a markdown heading, or a dependency edge by default.

Subgoals are appropriate when a single root loop would otherwise serialize
independent frontiers. They are not appropriate for a strict dependency chain or
for sibling work that cannot prove write-scope separation.

Canonical roles:

- **Root orchestrator:** owns subgoal creation, cross-subgoal dependency shape,
  shared files, global load budget, final integration, final validation, Beads
  flush, and commit.
- **Subgoal controller:** durable Beads issue that carries the subgoal identity,
  write scope, frontier filter, run directory, child-orchestrator assignment,
  concurrency budget, isolation mode, and status artifact.
- **Child orchestrator:** optional NTM-backed operator for one subgoal. It may
  claim, block, and close only leaf issues matching both the root `slice:*` and
  its assigned `subgoal:*` label.
- **Leaf worker:** normal execution worker scoped to one Beads node inside the
  subgoal frontier.

Required invariants:

- Subgoal grouping uses labels and controller issues. Do not rely on
  parent-child issue hierarchy as a readiness dependency unless the installed
  Beads version has been proven to support non-blocking hierarchy.
- Every subgoal leaf and controller must retain the root `slice:{slug}` label
  and add exactly one `subgoal:{slug}` label. The root slice label is what makes
  global rollup and final integration queryable.
- A child orchestrator may not create, delete, or reassign subgoals, edit shared
  files, or mutate cross-subgoal topology directly. It writes the smallest graph
  change proposal into the subgoal result artifact and leaves the affected work
  open or blocked for the root.
- Launch multiple subgoals only when their subgoal-level write scopes are
  disjoint, no active leaf depends on another active subgoal, and the workspace
  load budget covers the planned child orchestrators plus leaf workers.
- The load gate is global to the workspace run, not per subgoal. Re-running a
  per-subgoal load check and spawning every admitted cohort can recreate the
  same proof-starvation failures that swarm load guards exist to prevent.
- The default maximum depth is one child-orchestrator layer below the root.
  Deeper nesting requires an explicit max-depth override in the controller
  issue and a reason recorded in the run artifact.

Convergence rolls up from subgoals, but controller status is only evidence. The
root accepts a subgoal as converged only after an independent gate proves:

```text
filtered ready frontier is empty
AND no in-flight leaf set has changed for at least two operator ticks
AND expected subgoal artifacts and validation evidence exist
AND the latest child output has no unresolved blocker or convergence-warning language
```

Skill-local implementations may add stronger checks, such as scoped `git diff`
or `git log` probes, but they must not accept a subgoal solely because a child
worker or controller says it is done.

Nested restart ownership:

- In default multiplexed mode, the root owns every pane because there are no
  child orchestrator sessions.
- In delegated mode, the root owns the child orchestrator session as a
  controller-level resource. The child orchestrator owns its own leaf worker
  panes. Root recovery may replace a dead child orchestrator; it should not
  nudge individual child leaf panes unless stopping runaway work or recovering a
  dead controller.

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

Swarm runtime evidence belongs in the overlay-backed invocation root or the NTM
runtime, not in product repo roots. New domain/DAC waves should not create
repo-local `.dac/`, `.ntm/`, loose `WG-*_RESULT.md`, `EXECUTION_CONTEXT.md`,
`WORKGRAPH.md`, or `DAC_FINAL_RESULT.md` files unless the user explicitly asks
for a repo-local proof artifact. Use `vibing-with-ntm` for live pane state,
operator ticks, stuck-pane recovery, queue-dry checks, and concise session
exports.
