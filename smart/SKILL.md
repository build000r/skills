---
name: smart
description: Identify the single most accretive, highest-leverage next move, then by default define a goal sequence that encompasses it, turn it into a set of no-ragrets beads, and pursue the goal. Use when tagged with /smart, when the user wants to identify the highest-leverage next move, most impactful addition, or smartest thing to do next, when the user asks for smart goal mode, ambitious goal tracker, Gantt or ganntt plan, or when the user wants /smart to continue, iterate, or loop through bounded rounds until a concrete goal or success criterion is met.
depends_on:
  - no-ragrets          # Step 2 wraps each goal in the regret-minimization success contract
  - beads-workflow      # Step 2 converts the goal sequence into a br Beads graph
  - divide-and-conquer  # Step 3 pursues substantial slices through the ready frontier
---

# Smart

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using smart`.

Preferred format: `Using smart to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix. Reliability review tooling treats it as a stable invocation marker.

You've been invoked to deliver the single highest-leverage insight for whatever the user is working on right now.

## Visibility Control Plane

`smart` is the always-global dispatcher. `sbp` is the always-global visibility
control plane. Keep that pair global; route all other skills through repo-local
or overlay-scoped activation unless policy explicitly says otherwise.

When the smartest move needs a sibling skill that is not already visible in the
current repo, use `sbp skill activate <skill> --cwd "$PWD"` to activate the
minimal individual skill needed for this task. Start with `--dry-run` when the
visibility change is not already obvious, then consume the activation packet and
continue through the activated skill. Do not solve missing visibility by making
task skills global.

Defer pack abstractions. If the same skill chain repeats across real runs, capture
the evidence and tighten `skill-scope.yaml` or the relevant skill docs later;
until then, activate individual skills through `sbp`.

Any swarm or NTM-coordinated work must route through `vibing-with-ntm`. Any
large-ish, UI-facing, multi-file, naturally parallel, or review-sensitive task
must route through `divide-and-conquer` before parallel execution. For UI work or
ambiguous review-heavy work, include Claude Opus in the worker or reviewer mix
when the runtime exposes model choice, and require a final fresh-eyes reviewer
pass before completion.

`smart` chooses the next move; `divide-and-conquer` turns substantial execution
into Beads and runs the ready frontier. When a recommendation becomes
implementation, the first execution handoff is to `/divide-and-conquer` so it can
mint or consume the `br` epic/child issues, claim work through `br`, and keep
status in the repo's Beads graph. Do not preserve execution state by writing
standalone smart-chain or workgraph markdown.

### Orchestration Boundary

`smart` owns the decision to orchestrate, not the mechanics of spawning or
tending panes. When the chosen move requires parallel execution, route it to
`/divide-and-conquer` and state the execution guardrails that must hold:

- `divide-and-conquer` owns the Beads graph, write-scope split, model route,
  `projects_base` / session-root preflight, worker claims, and final
  integration review.
- `vibing-with-ntm` owns the live operator loop after a swarm exists: liveness
  checks, rate-limit truth, stuck-pane recovery, queue-dry, convergence, and
  anti-pattern handling.
- `smart` may require a detached or fresh-eyes review as part of the goal, but
  the execution skill decides the worker/reviewer route and verifies the result.
- Do not recommend a raw `ntm spawn` implementation wave from `/smart` unless
  the task is specifically about NTM itself. Use `/divide-and-conquer` for real
  implementation so repo root, model choice, Beads state, and completion proof
  are owned by the execution layer.

## The Question

Ground yourself in everything available — the conversation so far, the codebase, recent git history, any active plans or tasks — then answer this:

> **What is the single smartest, most radically innovative, accretive, useful, and compelling thing you could do or suggest at this point to get us on the right track?**

## Default Operating Procedure

Every `smart` call runs this three-step procedure by default. The accretive
analysis above is the **input**, not the deliverable: do not stop at a single
one-line recommendation when these steps can carry the user further.

1. **Define a goal sequence that encompasses all of that.** Synthesize the
   repo-integrity pass, the single highest-leverage move, and the adjacent
   concerns into an *ordered sequence of goals* that gets the project "on the
   right track" — not one isolated suggestion. Use `smart` goal-mode thinking
   ([references/smart-goal-mode.md](references/smart-goal-mode.md)) to set the
   altitude (`one-shot`, `milestone`, or `program`) and name the lofty end goal,
   the current reality, and the ordered goals between them. The first goal is the
   single smartest move; later goals are the hardening, proof, and follow-through
   that make that move actually land.

2. **Turn it into a set of `$no-ragrets` beads.** Run each goal in the sequence
   through the `no-ragrets` success contract (`Outcome` / `Evidence` /
   `Failure avoided`) and mint it as a `br` bead with dependency edges, so the
   sequence becomes a regret-minimized, self-contained Beads graph. Embed the
   contract in each bead's description and acceptance criteria, label them
   `chain:smart`, and lay in the ready-frontier order with `br dep add`. Use
   `beads-workflow` for the plan→beads conversion and `/divide-and-conquer` to
   mint or consume the epic/child issues for any substantial slice. The Beads/BV
   graph is the durable source of truth; markdown stays a generated view. If
   `.beads/` is unavailable, say durable bead tracking is blocked and stop at the
   goal sequence — do not invent a repo-root, overlay-local, or session-local
   fallback path.

3. **Pursue the goal.** Begin executing the ready frontier instead of handing the
   sequence back as advice. Route bounded single changes to direct local work;
   route large-ish, multi-file, UI-facing, parallel, or review-sensitive slices
   through `/divide-and-conquer` (with `/vibing-with-ntm` for any swarm), honoring
   the Orchestration Boundary below. Drive the Smart Loop Frame until the success
   criteria are met, passing the Completion Gate
   (`validate -> commit -> reality-check-for-project`) before claiming completion,
   or pause with an explicit resume condition.

Collapse the sequence to a single goal/bead only when the smartest move is
genuinely one bounded action (the `no-ragrets` fast path). Otherwise the default
is the full sequence: defined, contracted, and pursued.

## Smart Goal Mode

If the user says `smart goal`, asks for an ambitious goal tracker, or asks for a
Gantt/`ganntt` plan, the single smartest move is to produce a goal-tracking
artifact, not only a one-line recommendation. Read
[references/smart-goal-mode.md](references/smart-goal-mode.md) and build the
tracker from current evidence: today's date, `/reality-check-for-project`,
wiki direction when relevant, build-vs-clone placement calls, `/describe` or
`/domain-planner` where the gap requires them, and an MMDX Gantt stack based on
[assets/templates/smart-goal-gantt-stack.mmdx](assets/templates/smart-goal-gantt-stack.mmdx).

For `higher-level goal`, `lofty goal`, hardening loop, or adjacent-concern requests, choose the goal altitude before choosing the task: preserve the end vision, final success criteria, current iteration proof, adjacent concerns, and granular skill-level handoffs from the smart-goal reference. Hotspots, low-hanging fruit, and quick wins remain valid work paths when they are framed as iterations toward the loftier goal.

## How to Answer

1. **Absorb context first.** Read the conversation history. Resolve the active client context and artifact roots before looking for prior smart or modes state. Then check `git log --oneline -20` and `git diff --stat` for recent momentum. Run a repo-integrity pass over the changed paths, adjacent tests, README/docs, comments, and any active plans or task lists. If the overlay-backed smart chain exists, read the latest link before deciding. If an overlay-backed modes-of-reasoning analysis exists, read its latest output too. Understand what phase the work is in — exploration, building, debugging, shipping.

2. **Scope to what matters now.** If the user included a focus area (e.g., `/smart with regard to auth flow`), narrow to that. Otherwise, identify the current bottleneck or highest-value gap yourself.

3. **Be concrete and actionable.** Don't say "consider improving error handling." Say "add retry with exponential backoff to the webhook delivery in `src/webhooks/deliver.ts:47` — right now a single timeout kills the whole batch." Name files, functions, architectural decisions. If it's a strategic suggestion, name the first concrete step.

4. **Be bold.** This isn't a code review. The user wants the move they haven't thought of — the one that unblocks three other things, or the refactor that makes the next five features trivial, or the simplification that deletes 400 lines. Swing for impact.

5. **One committed direction.** Not a menu of five competing options — pick the single best move and commit to it. That committed move is the spine of the goal sequence in the Default Operating Procedure: it becomes the first goal, then the sequence adds the hardening, proof, and follow-through that make it land. A goal sequence is one direction broken into ordered goals, not five alternatives. If you must caveat, do it in one sentence after the recommendation.

6. **Direct-commit workflow.** Default to direct commits, not pull requests. The operator owns their repos and pushes to main. Only use PR language when the context explicitly involves contributing to someone else's repo with contribution rules. Say "commit" or "change", not "PR".

7. **The codebase is the prompt.** Treat the repository state as primary evidence, not background texture. Before proposing net-new work, explicitly check for docs drift, stale READMEs, weak or missing tests around changed paths, misleading comments, generated slop, dead code, duplicate abstractions, plan drift, and fragile code that has changed without corresponding hardening. If a material integrity gap exists, the default move is to harden that gap first unless you can name concrete repo evidence that another move is higher leverage.

8. **Prefer extending to creating.** Bias toward hardening, extending, or modularizing what already exists. That includes code, docs, skills, and configuration. The smartest move is rarely "build a new thing from scratch" — it's usually "make the thing we have work better, cover more cases, or compose more cleanly." Hardening means: strengthening existing code, filling test gaps, clarifying confusing docs or READMEs, tightening skill descriptions that don't trigger well, fixing misleading comments, improving error messages, or wiring up existing pieces differently. Before suggesting new files, new abstractions, or new repos, check whether the goal can be reached by improving what's already there. The bar for "create" should be materially higher than the bar for "improve."

## Ambiguity Escape Hatch

If there is **any** material ambiguity about which move is actually smartest — competing candidates feel equally strong, the repo signals point in conflicting directions, the right framing is unclear, or you cannot confidently name the single best move — launch `/wiki-duel` instead of guessing.

`/wiki-duel` grounds adversarial reasoning in the accumulated wiki synthesis and pits competing candidate moves against each other, which is exactly what resolves "I see three plausible smartest moves" situations. Prefer it over forcing a confident-sounding pick when confidence is not actually there.

Rules:

- Only commit to a single recommendation when you can name concrete repo evidence that the pick dominates alternatives. Otherwise, `/wiki-duel` is the move.
- When you escalate to `/wiki-duel`, say so explicitly as the recommendation, list the candidate moves that tied, and name the ambiguity (evidence conflict, framing uncertainty, missing context).
- Do not escalate when one move is obviously correct — forced duels waste cycles. The trigger is genuine ambiguity, not general caution.

## Repo Integrity First

Treat the repository as the real prompt. The user request sets direction, but the code, docs, tests, plans, and recent diffs decide what is actually true.

### Repo-Integrity Pass

Before recommending new features, abstractions, or repos, inspect for:

- docs, README, or `SKILL.md` text that contradicts the current code
- changed or fragile paths with weak, missing, or misleading tests
- any supported, measurable hotspot scope where `/crap` reports `FINAL_SCORE >= 30`
- any risky supported scope where `/crap` cannot yet produce a trustworthy numeric score because tests or coverage artifacts are missing
- stale comments, TODO placeholders, generated slop, or examples that no longer run
- duplicate abstractions, dead code, confusing naming, or weak error messages
- plan or task status that disagrees with recent git reality
- recent churn in risky modules without corresponding hardening follow-through

If any of these are materially true, the default recommendation should be a hardening move. Only skip that default when you can point to specific repo evidence showing that another move unlocks more value immediately.

### CRAP Invariant

For languages and scopes that `crap` supports (`rust`, `python`, `typescript`),
treat this as a standing hardening rule:

- `FINAL_SCORE < 30` is the default minimum acceptable hotspot state
- `FINAL_SCORE >= 30` is a material integrity gap, not just a nice-to-have cleanup
- if the scope is risky but `crap` is still `N/A` because the repo lacks a trustworthy test or coverage baseline, that missing baseline is itself the integrity gap
- do not describe a supported hotspot as "hardened enough" while its scoped `FINAL_SCORE` is still `>= 30` unless you are explicitly reporting a blocker

When you mention `crap`, keep the scope honest. A package-scoped or path-scoped
score below `30` is not a repo-wide claim.

### Hardening Decision Rule

When choosing the move, make this decision explicitly:

1. Identify the strongest repo-integrity signals.
2. For supported hotspots, check whether `crap` already shows `FINAL_SCORE >= 30` or whether the baseline is too weak to measure honestly yet.
3. Decide whether the signals are material enough to block trust, shipping, maintenance, or future implementation speed.
4. If yes, recommend the smallest hardening move that most improves trust or leverage.
5. If no, say why hardening is not the best move right now and name the evidence.

## Recommendation Chain Context

Treat `/smart` as a running recommendation chain, not a stateless prompt. The
durable chain lives in repo-local Beads (`br`) issues; markdown chain files are
generated views only. Before you pick the next move:

1. **Resolve the repo and Beads state.** Use `git rev-parse --show-toplevel` and
   the Beads flow in [references/beads-recommendation-chain.md](references/beads-recommendation-chain.md).
   If Beads is unavailable or not initialized, answer without durable chain
   state and say that Beads tracking is blocked. Do not invent repo-root,
   overlay-local, harness-local, or invocation-root markdown state.

2. **Load the prior smart link from `br`.** Prefer open or blocked
   `chain:smart` issues, then the latest closed `chain:smart` issue when the loop
   is not active. Capture the prior move, first step, repo head, modes report
   path, and any caveats or open questions recorded there.

3. **Resolve overlay roots for read-only context and optional rendered views.**
   Use the shared `resolve_context.py` helper from the `_shared` skill bundle.
   `workflow_builder.evaluation_root` may locate modes output. `workflow_builder.invocation_root`
   may locate legacy generated markdown views, but it is not authoritative state
   and must not receive new hand-authored chain entries.

4. **Load the latest modes-of-reasoning output.** Prefer the report path recorded in the last Beads chain link. Otherwise, when an evaluation root is available, check:
   - `{evaluation_root}/{repo_slug}/modes/LATEST_REPORT.txt`
   - the newest `*/MODES_OF_REASONING_REPORT_AND_ANALYSIS_OF_PROJECT.md` under `{evaluation_root}/{repo_slug}/modes/`
   - `{evaluation_root}/{repo_slug}/modes/LATEST_PROGRESS.txt` or the newest `*/MODES_ANALYSIS_PROGRESS.md` under `{evaluation_root}/{repo_slug}/modes/` only to detect an in-flight swarm

   Read at least the Executive Summary, Recommendations, New Ideas and Extensions, and Open Questions from the resolved report. If only progress exists, note that a swarm is in flight but do not treat it as completed guidance.

5. **Compute the delta since the last chain link.** Compare the current repo state to the `repo_head` recorded in the last Beads chain entry. Use `git diff --stat <repo_head>..HEAD`, `git diff --name-only <repo_head>..HEAD`, and the current worktree diff. If the recorded head no longer exists, fall back to the last chain timestamp, recent `git log`, and the current `git diff --stat`.

6. **Use the delta to update, not overwrite.** The new recommendation should explicitly build on or supersede the last smart move and the latest modes report. If you diverge from either one, say why the new diff, answered questions, or changed project phase justifies the change.

7. **No prior chain? Start one in Beads when available.** If there is no
   `chain:smart` issue, make the best recommendation you can from current
   context, treat this run as link 1, and create/update the Beads chain issue
   after answering. If Beads is unavailable, answer normally and note that
   durable smart-chain state is unavailable for this repo.

### Artifact Authority

- Repo-local Beads issues labeled `chain:smart` are the only authoritative
  durable chain for `/smart`.
- `SMART_RECOMMENDATION_CHAIN.md` and `SMART_GOAL_CHAIN.md` are optional
  generated views. Render them from `br` only when explicitly requested or when
  a legacy human handoff still consumes markdown.
- Do not discover prior smart state by scanning `~/.claude/projects`, `.claude/projects`, `~/.codex`, repo-root scratch folders, or other harness/session-local directories. If those files exist, they are drift evidence, not the active chain.
- Never create or update harness-private project memory or chain files as part of `/smart`. This includes `MEMORY.md`, `.claude/projects/*/memory/*`, `.claude/projects/*/smart/*`, `.codex/*/memory/*`, and similar session-local artifacts.
- If overlay-backed roots are unavailable, answer without durable chain state. Do not invent a session-local fallback path.
- If Beads and legacy markdown artifacts both exist, prefer Beads, ignore the
  markdown for decision-making unless it is explicitly generated from current
  `br` state, and call out drift when it materially affected prior runs.

## Smart Loop Frame

Every `/smart` invocation is a loop frame, even when the answer is a single
recommendation. Always define:

1. `loop_goal` — the concrete outcome this recommendation is steering toward.
2. `success_criteria` — the evidence that would prove the move worked.
3. `loop_status` — `one-shot 1/1` by default, or `iteration N/M`,
   `resolving-question-agentically`, `waiting-on-human`,
   `waiting-on-research`, `blocked`, or `completed` when those states apply.
4. `resume_condition` — the exact answer, artifact, command result, repo
   evidence, or next-state condition needed before the loop can continue.

By default, run the Default Operating Procedure: define the goal sequence, mint
the `no-ragrets` beads, and pursue the ready frontier through this loop frame.
Collapse to a one-shot single-move loop only when the smartest move is genuinely
one bounded action — define the evidence that would make it successful and hand
back the first executable step. Enter explicit multi-iteration loop mode when the
user asks to continue, keep going, iterate for `N` rounds, or steer toward a
higher-level goal until a concrete success condition is met.

For high-altitude loops, `loop_goal` and `success_criteria` describe the end vision. Example: `a well-maintained, performant codebase` can be the goal while `/describe`, `/reproduce`, `/crap`, `/mutate`, `/testing-metamorphic`, `/profiling-software-performance`, `/extreme-software-optimization`, `/divide-and-conquer`, and `/vibing-with-ntm` are the iteration routes. A low-hanging-fruit fix can complete the iteration, not the whole loop, unless the final proof and completion gate also pass.

### Question Resolution Rule

Do not ask the human merely because the next move contains uncertainty. Treat
"we need to know X" as a routing problem first.

Before asking the human, try to resolve the question through available agentic
evidence and sibling skills: repo state, recent diffs, docs, tests, plans,
local commands, prior sessions, wiki state, modes reports, and bounded external
research. A human question is allowed only after those routes cannot reasonably
answer the uncertainty.

Use this ladder:

- Prior-session or prior-decision uncertainty -> `/cass`
- Project knowledge may already contain the answer -> `/wiki`
- Project knowledge conflicts or multiple moves tie -> `/wiki-duel`
- Codebase behavior is unclear -> `/codebase-archaeology`, `/reproduce`, or `/describe`
- Pass/fail criteria are the real ambiguity -> `/describe`
- Plan or backlog status is unclear -> `/audit-plans` or `/domain-reviewer`
- Strategic direction needs multiple analytical lenses -> `/modes-of-reasoning-project-analysis` or `/dueling-idea-wizards`
- Market, buyer, ecosystem, or external reality is unclear -> `/power-map` when the customer chain itself is unknown; otherwise `/escalate` first so it can route to `/deep-research-prompt`, `/thesis-gtm`, `web-check`, or skip
- Multiple dependent human-facing questions remain after agentic resolution -> `/ask-cascade`
- Exactly one irreducible factual answer remains -> ask one direct question

A human question may pause execution, but it does not satisfy success criteria
by itself. If asking the human, report `loop_status: waiting-on-human`, name the
agentic routes attempted or ruled out, and state the exact answer needed to
resume. Do not call the loop `completed` merely because the next step needs a
human answer.

## Loop Mode

### Loop Contract

For every `/smart` invocation:

1. Establish a concrete `loop_goal`, concrete `success_criteria`, current `loop_status`, and `resume_condition`.
2. If multi-iteration loop mode is active and the user already gave `N`, respect it unless it would obviously waste effort. If no `N` is given, choose one yourself based on ambiguity and scope: default to `2-4`, never exceed `8` without fresh user input.
3. If the goal or success criteria are fuzzy, use the current iteration to define them sharply enough that later iterations can continue or complete on evidence instead of vibes.
4. If a question blocks the next move, apply the Question Resolution Rule and set `loop_status` to `resolving-question-agentically`, `waiting-on-human`, `waiting-on-research`, or `blocked` rather than ending the loop.
5. After each iteration, recompute the repo delta, repo-integrity pass, verification state, open questions, and latest chain entry before deciding whether another loop is still accretive.
6. Treat any "done" signal from a final task, final Bead, or final worker wave as provisional until the completion gate passes.
7. Complete only when the success criteria are met; otherwise pause with a resume condition or continue with the next accretive move.

### Choosing the Execution Posture

- Use direct local work when the next iteration is a single bounded change or answer.
- Use `/divide-and-conquer` when an iteration is large-ish, UI-facing,
  multi-file, naturally parallel, review-sensitive, or expands into a multi-node
  implementation slice that benefits from a Beads-backed ready frontier.
- Use `vibing-with-ntm` for every swarm or NTM-coordinated run, including
  divide-and-conquer execution, operator tending, review loops, and transport
  recovery.
- Use `ntm` directly only when orchestration itself is the task. For ordinary
  execution waves, route through `/divide-and-conquer` so Beads remain
  authoritative.
- Include Claude Opus for UI or ambiguous review-heavy work when available, and
  do not call the loop complete until a fresh-eyes reviewer pass has checked the
  final diff and validation evidence.
- Do not recurse lazily by repeatedly wrapping `/smart` around itself with no new artifact or verification. Each loop must either sharpen the goal, produce a concrete repo or artifact delta, route an unresolved question, or prove that the success criteria have been met.

### Completion Gate

When an implementation iteration thinks it is finished, especially after a final
`/divide-and-conquer` node or swarm wave, do this before declaring success:

1. Run the move's concrete validation and capture the evidence.
2. Run `/commit` if commit is authorized in the current run. If commit is not authorized, do not call the loop complete; report that the closeout is blocked at the commit gate and name the exact pending commit step.
3. Immediately run `/reality-check-for-project` against the current README, plans, beads, and code so the project is reassessed from the new post-commit state rather than from the optimistic perspective of the just-finished worker.
4. If the reality check says the project still misses the higher-level goal, reopen the loop with the new gap as the next iteration instead of hand-waving completion.

The ordering is deliberate: `validate -> commit -> reality-check-for-project`.
The reality check happens after the commit so the reassessment sees the exact
state the operator would actually inherit.

### Loop Termination

The loop completes only when this becomes true:

- the success criteria are satisfied, any applicable completion gate has passed, and any applicable post-commit reality check agrees that the higher-level goal is actually met

The loop may pause, but must not be reported as complete, when one of these
becomes true:

- the next move requires a human answer after agentic question resolution has been exhausted
- the next move requires external research or an outside dependency that cannot run inside the current invocation
- the next move is blocked by missing credentials, approvals, or unavailable local infrastructure

The loop may stop without completion when one of these becomes true:

- the loop budget is exhausted
- the next best move is no longer materially better than stopping and handing back a crisp summary

When pausing or stopping without completion, say what changed across the loop,
what remains, which question-resolution route was used, and the exact condition
for resuming `/smart`.

## Skill Combo Guidance

`/smart` still chooses **one move**. A skill combo is optional and only exists to
execute that move cleanly. Keep combos bounded at 2-4 steps, pass artifacts
forward, and prefer direct action when a combo adds no leverage.

Read [references/combo-routing.md](references/combo-routing.md) only when the
chosen move naturally needs a multi-step skill chain.

## Skill-Aware Recommendations

Your answer can (but doesn't have to) recommend invoking a sibling skill as the next move. Consider which skill fits the current situation — the right tool often IS the smartest move:

| When the situation looks like... | Consider suggesting... |
|---|---|
| Code is untested, risky, or fragile | `/crap` — hotspot scoring to find where to harden |
| Post-crap, surviving mutants need triage | `/mutate` — mutation testing to close coverage gaps |
| Project lacks a README or docs are stale | `/readme-writing` — craft a proper README |
| Public docs may be wrong or OSS readiness is unclear | `/oss-doc-audit` — audit public docs against the active codebase |
| The bottleneck is understanding an unfamiliar codebase | `/codebase-archaeology` — build a working mental model before deciding |
| You need a ranked audit before choosing the fix | `/codebase-audit` — find the highest-value issues, then spec or implement |
| Multi-repo feature needs coordination | `/domain-planner` — plan the slice across repos |
| A planned slice is ready to build | `/divide-and-conquer` — run the accepted plan through Beads, with `domain-scaffolder` as the worker skill |
| Work is in flight and needs a status check | `/domain-reviewer` — audit progress against plan |
| Complex or long-running implementation needs orchestrated execution | `/divide-and-conquer` — execute the ready frontier as an NTM-backed wave swarm |
| Bug fix or feature lacks clear "done" criteria | `/describe` — define pass/fail test cases first |
| The local dev environment may be the real failure | `/dev-sanity` — run the configured local health checks first |
| Changes are ready but uncommitted | `/commit` — clean, logical commit batches |
| Need to decide build vs. reuse vs. extract | `/build-vs-clone` — ecosystem-aware placement decision |
| Backlog is messy or priorities unclear | `/audit-plans` — plan hygiene and prioritization |
| Past attempts, prompts, or decisions matter | `/cass` — mine session history before deciding or spec'ing |
| A skill itself needs improvement | `/skill-issue` — review and iterate from real usage |
| Work has progressed but you need strategic steering | `/reality-check-for-project` — compare implemented reality against the vision |
| Verification feels manual or hand-wavy | `/reproduce` — command-first verification workflow |
| Repeated shell commands, command-history fossils, or manual local workflow loops are the bottleneck | `/automating-your-automations` — mine history, score automation candidates, and build the highest-value wrapper |
| Multiple dependent human-facing questions remain after agentic resolution | `/ask-cascade` — hierarchical question ordering |
| The problem needs a broad rethink or multiple analytical lenses | `/modes-of-reasoning-project-analysis` — swarm distinct reasoning modes and synthesize the result |
| Claude has been churning, stuck, or needs an independent second pass | `/divide-and-conquer` — route a fresh worker wave; use Codex rescue only as the selected worker transport |
| The wiki may already answer the question, or contradicts itself | `/wiki` — query, ingest, or lint the accumulated knowledge base |
| The wiki's highest-leverage concept needs adversarial synthesis | `/wiki-forge` — stress-test the top concept and file it back |
| The path is uncertain and a cold adversarial brainstorm is warranted (no wiki prior needed) | `/dueling-idea-wizards` — multi-agent adversarial idea generation and scoring |
| UI drift — ad-hoc tokens, duplicate variants, className soup | `/drift-detector` — rank UI drift and produce a consolidation plan |
| Performance is the real integrity gap — hot paths, p95/p99, bottlenecks | `/profiling-software-performance` — rank hotspots by CPU, memory, I/O, contention |
| A ranked hot path is known and needs behavior-preserving optimization | `/extreme-software-optimization` — profile-driven optimization with behavior proofs |
| A SaaS surface is about to ship and needs billing/auth/webhook review | `/security-audit-for-saas` — pre-launch security audit |
| Code is ready but hasn't shipped | `/deploy` — deploy, health-check, or roll back |
| The work is on an agent-facing CLI and UX is the gap | Run a CLI ergonomics pass — tighten compact output, defaults, and shell UX |

### When the blocker is external reality

`/smart` is repo-introspective by default, but sometimes the highest-leverage move isn't inside the code — it's validating a premise against the outside world. Consider these when the bottleneck is an unknown about the market, users, or power structure, not an unknown about the repo:

| Situation | Consider suggesting... |
|---|---|
| A strategic bet depends on current market reality, not code state | `/escalate` — route to `thesis-gtm`, `deep-research-prompt`, `web-check`, or skip with a reason |
| Positioning is unclear — who actually pays, who's the real user | `/power-map` — map industry power dynamics and find the person closest to the dollar |
| Another agent should run a bounded deep-research pass before a decision | `/escalate` — decide whether that pass is warranted before invoking `deep-research-prompt` |

### Domain-specific hardening targets

These extend the Repo-Integrity Skill Map for narrower surfaces:

| Situation | Consider suggesting... |
|---|---|
| The project is (or needs to be) an MCP server with agent-friendly UX | `/mcp-server-design` |
| CLI-to-web auth (PKCE, device code, token lifecycle) is the gap | `/saas-cli-auth-flow` |
| A curl-pipe-bash installer is missing or fragile | `/installer-workmanship` |
| Release history / CHANGELOG has drifted from git reality | `/changelog-md-workmanship` |

### When the gap is uncovered marketing surface

Marketing skills may live in a configured skill source root such as
`~/repos/marketingskills/skills/`. When `/smart`'s integrity pass uncovers a
marketing gap — no landing copy, no onboarding CRO, no pricing thesis, no launch
plan, no SEO presence, no referral loop, no lead magnets, no ad creative, no
email sequences — inspect the available skill inventory for the right marketing
skill rather than inventing one. Representative entries: `launch-strategy`,
`pricing-strategy`, `copywriting`, `onboarding-cro`, `page-cro`, `paid-ads`,
`cold-email`, `email-sequence`, `lead-magnets`, `referral-program`,
`free-tool-strategy`, `ai-seo`, `programmatic-seo`, `site-architecture`,
`content-strategy`, `community-marketing`, `customer-research`,
`competitor-alternatives`, `churn-prevention`, `ab-test-setup`,
`analytics-tracking`, `form-cro`, `popup-cro`, `signup-flow-cro`,
`paywall-upgrade-cro`, `ad-creative`, `social-content`, `schema-markup`,
`sales-enablement`, `revops`, `marketing-psychology`, `marketing-ideas`,
`product-marketing-context`, `copy-editing`.

Don't force a skill recommendation. If the smartest move is "delete this file" or "rename this function," say that. If the move requires a human or team decision, first apply the Question Resolution Rule, then ask only the smallest unresolved question with a resume condition. Skills are tools in the toolbox, not the only answer.

If you have a trustworthy `crap` measurement for a supported hotspot and the
scoped `FINAL_SCORE` is still `>= 30`, bias strongly toward a hardening move
instead of new feature work.

## Repo-Integrity Skill Map

When the repo-integrity pass finds a real gap, name the relevant sibling skills directly instead of gesturing vaguely at "hardening":

| Repo-integrity signal | Prefer suggesting... |
|---|---|
| A changed or risky path lacks crisp pass/fail criteria | `/describe` — define exact done conditions before changing more code |
| A bug or regression claim still feels hand-wavy | `/reproduce` — verify the bug and fix with command-first evidence |
| A hot module looks fragile or weakly covered | `/crap` — rank risky code paths that most need hardening and get the scope below `30` |
| A supported hotspot already measures `FINAL_SCORE >= 30` | `/crap` first, then `/describe` and implementation follow-ons until that scoped score is below `30` or a blocker is explicit |
| A risky scope has no trustworthy numeric CRAP yet | `/crap` for baseline detection, then `/describe`, `/reproduce`, and repo-native test or coverage bootstrap until the score is measurable |
| Tests pass but assertions are shallow or survivability is weak | `/mutate` — expose weak tests and close the gaps |
| The system has an oracle problem or transformations are hard to assert directly | `/testing-metamorphic` — define metamorphic relations instead of brittle point checks |
| You need a ranked integrity sweep before choosing the fix | `/codebase-audit` — audit for the highest-value issues first |
| The code is unfamiliar and drift is hard to evaluate | `/codebase-archaeology` — build a working model before hardening |
| Public docs, examples, or API usage have drifted from the live code | `/oss-doc-audit` — audit docs against reality |
| Docs are technically correct but read like slop or have lost trustworthiness | `/de-slopify` — rewrite them to sound deliberate and human |
| README coverage is missing or stale | `/readme-writing` — rebuild the README from the actual project state |
| The project may be shipping the wrong thing despite implementation progress | `/reality-check-for-project` — compare code, docs, and plan against the stated vision |
| Plans claim motion that git history does not support | `/audit-plans` or `/domain-reviewer` — reconcile plan state with actual progress |
| A skill contract, trigger, or description has drifted from behavior | `/skill-issue` — tighten the skill from repo and transcript evidence |
| UI has ad-hoc tokens, duplicate variants, or className soup | `/drift-detector` — rank UI drift and produce a consolidation plan |
| Performance is the integrity gap — hot paths, p95/p99, bottlenecks | `/profiling-software-performance` — rank hotspots, then `/extreme-software-optimization` to fix |
| A SaaS surface needs billing/auth/webhook review before shipping | `/security-audit-for-saas` — pre-launch security audit |
| An agent-facing CLI has poor defaults or noisy output | Run a CLI ergonomics pass — compact output, strong defaults, clean shell UX |
| Claude has been churning or stuck on the same integrity gap | `/divide-and-conquer` — route the investigation or fix as a fresh Beads-backed worker wave |
| The hardening work is broad enough to need multiple coordinated changes | `/divide-and-conquer` — execute a bounded hardening wave after the gaps are named |

### Overlay and Planning Context

Before making your recommendation, check whether the project has an active client overlay and existing plans:

1. **Find the overlay**: Run the shared `resolve_context.py` helper from the installed or repo-local `_shared` skill bundle to resolve the active client. The overlay tells you conventions, paths, and workflows already in place.

2. **Check for plans**: If the overlay defines a `plan_root`, scan it for existing slice plans. Each slice lives in `{plan_root}/{slice-name}/` and contains `plan.md` (master doc), `backend.md`, `frontend.md`, `shared.md`, `flows.md`, and `schema.mmd`. Check `{plan_root}/INDEX.md` for the catalog of all slices and their status.

3. **Read plan state**: Skim the INDEX for slice statuses — are there planned slices nobody has started? Draft slices that need review? Released slices with no implementation progress? Session plans that were started but abandoned? This is high-signal for what the smartest move is.

4. **Factor plans into your answer**: The smartest move might be "start implementing the auth slice that's been released for a week" (`/domain-scaffolder`), or "audit the three in-flight slices that have drifted" (`/domain-reviewer`), or "the backlog has 12 slices and no priorities — run `/audit-plans` before writing more code." Plans are context, not decoration.

If no overlay or plans exist, that's fine — not every project uses the planning system. Don't suggest adopting it unless the project's complexity genuinely warrants it.

## Immediate Beads Handoffs

Optional background repairs are an execution detail, not the default answer.
For anything more than a tiny single-file cleanup, route them through
`/divide-and-conquer` so Beads own the issue, claim, and status. Otherwise keep
the same discovery as an agentic route in the main recommendation.

Read [references/subagent-routing.md](references/subagent-routing.md) only when
the context-absorption phase finds an obvious side repair that should not block
the main recommendation.

## Output Format

## Required Verification and Closeout

`/smart` is allowed to recommend one move, but it is not allowed to hand back vibes. Before closing:

0. Confirm the Default Operating Procedure ran: a goal sequence was defined, minted as `no-ragrets` beads (`Outcome` / `Evidence` / `Failure avoided` per bead, `chain:smart` label, dependency order), and pursuit started — or name which step was intentionally collapsed (single bounded move) or blocked (no `.beads/`).
1. Name the concrete repo signals that drove the recommendation.
2. State whether the move is hardening-first or why hardening was skipped.
3. If the move depends on validation, name the exact repo-native command or explicit blocker instead of saying "test this later."
4. Always fill in `Loop goal`, `Success criteria`, and `Loop status`.
5. If a question blocks the next move, name the question-resolution route, the agentic sources tried or ruled out, and the resume condition.
6. If asking the human, justify why repo evidence, prior sessions, wiki, plans, tests, local commands, and bounded research could not answer it.
7. If an implementation completion claim is in play, fill in the `Completion gate` field with `pending`, `commit-blocked`, `reality-check-failed`, or `passed` based on actual evidence.
8. If durable smart-chain state is unavailable, say so explicitly rather than implying the chain was consulted.

When updating this skill itself, independently run:

```bash
python3 skill-issue/scripts/quick_validate.py path/to/smart
```

---

**The move:** [1-2 sentence headline of what to do — the first goal in the sequence]

**Goal sequence:** [Required by default. The ordered goals that encompass the move, one terse line each (first goal = the move, later goals = hardening/proof/follow-through). State the altitude: `one-shot`, `milestone`, or `program`. Collapse to a single line only when the smartest move is genuinely one bounded action.]

**Chain context:** [One terse sentence tying this move to the prior smart link, the latest modes-of-reasoning takeaway, and the material repo delta since the last chain entry. Omit only for the first link.]

**Repo signals:** [The concrete repo-integrity signals that mattered most: changed files, stale docs, weak tests, misleading comments, plan drift, or similar.]

**Integrity gap:** [The single most important trust or hardening gap found in the repo. Say `none material` if the integrity pass came back clean.]

**CRAP status:** [When relevant for supported languages/scopes: `unknown baseline`, `FINAL_SCORE >= 30`, or `FINAL_SCORE < 30`, with exact scope.]

**Hardening decision:** [State whether the move is hardening-first or why hardening was skipped despite the repo-integrity pass.]

**Loop goal:** [Required. The concrete outcome this move is steering toward.]

**Success criteria:** [Required. The concrete evidence that proves the move worked.]

**Loop status:** [Required. Use `one-shot 1/1`, `iteration N/M`, `resolving-question-agentically`, `waiting-on-human`, `waiting-on-research`, `blocked`, or `completed`.]

**Question being resolved:** [Required when uncertainty affects the next move. Omit when no blocking question exists.]

**Resolution route:** [Required when a question affects the move. Name the agentic skill, local evidence source, research route, direct question, or why no route is available.]

**Human ask justification:** [Required only when asking the human. Explain why repo evidence, prior sessions, wiki, plans, tests, local commands, and bounded research could not answer it.]

**Resume condition:** [Required. For waiting or blocked states, name the exact answer, artifact, command result, or evidence needed to continue. For `one-shot 1/1`, name what state would make another `/smart` pass useful.]

**Completion gate:** [Only when an implementation iteration claims completion. Report `pending`, `commit-blocked`, `reality-check-failed`, or `passed`.]

**Skill combo:** [Optional. A bounded 2-4 step sequence such as `cass -> describe -> reproduce` that carries out the move. Omit if one direct step is better.]

**Artifacts:** [Optional. Name the concrete handoff artifacts or decisions each combo step reads or writes.]

**Why this, why now:** [2-4 sentences on why this is the highest-leverage action given current state]

**First step:** [The literal first thing to do — a command to run, a file to open, a skill to invoke]

**Next `/smart` condition:** [Optional. The condition that makes another `/smart` pass useful instead of blindly continuing.]

**No-ragrets beads:** [Required by default. The `br` IDs minted for the goal sequence, each carrying an `Outcome` / `Evidence` / `Failure avoided` contract and `chain:smart` label, with the ready-frontier order. If `.beads/` is unavailable, say durable bead tracking is blocked and that the run stopped at the goal sequence.]

**Pursuit:** [Required by default. The execution posture taken: direct local work on the first ready bead, a `/divide-and-conquer` wave, or paused with a resume condition. Name what has actually started, not just what is planned.]

**Already in motion:** [If you routed Beads or `/divide-and-conquer` workers, list what and why. Omit this line if nothing was launched.]

## Recommendation Chain Artifact

After each `/smart` run, update the repo-local Beads chain issue using
[references/beads-recommendation-chain.md](references/beads-recommendation-chain.md).
Only render markdown when requested or required by a legacy handoff. Rendered
views must be generated from `br`, clearly marked as generated, and never edited
by hand.

Keep each Beads entry terse and easy to skim. Store these fields on the Beads
chain issue or its comment/update payload, not in a hand-authored markdown file:

```text
timestamp: 2026-04-10T09:37:00-04:00
repo_head: abc1234
compared_to: def5678
modes_report: /path/to/evaluations/{repo_slug}/modes/{run_id}/MODES_OF_REASONING_REPORT_AND_ANALYSIS_OF_PROJECT.md
modes_takeaway: [1 sentence]
delta_since_last_chain: [1 sentence or compact bullets]
repo_signals: [top repo-integrity signals that informed the move]
integrity_gap: [single biggest hardening or trust gap, or `none material`]
crap_status: [optional exact score state and scope, for example `packages/api FINAL_SCORE 42.10` or `unknown baseline`]
hardening_decision: [hardening-first, or the concrete reason it was skipped]
move: [headline]
skill_combo: [optional 2-4 step sequence; use `/divide-and-conquer` for substantial implementation]
why_now: [1 sentence]
first_step: [literal first step]
next_smart_condition: [optional condition that makes another `/smart` pass useful]
loop_id: [optional stable id when loop mode is active]
loop_goal: [required concrete outcome this move is steering toward]
success_criteria: [required evidence that proves the move worked]
loop_iteration: [optional current/maximum, for example 2/4]
loop_status: [required one-shot 1/1|iteration N/M|resolving-question-agentically|waiting-on-human|waiting-on-research|blocked|completed]
question_being_resolved: [optional unresolved question affecting the move]
resolution_route: [optional agentic skill, local evidence source, research route, direct question, or unavailable route]
human_ask_justification: [optional reason agentic routes could not answer the question]
resume_condition: [required exact answer, artifact, command result, evidence, or next-state condition needed to continue]
completion_gate: [optional pending|commit-blocked|reality-check-failed|passed]
reality_check_takeaway: [optional 1 sentence from the post-commit reassessment]
pause_or_stop_reason: [optional reason for pausing or stopping without completion]
```

When loop mode is active, reuse the same `loop_id` across continuing entries so later `/smart continue` calls can resume the same higher-level goal instead of inferring it from prose.

Read the most recent entry on the next invocation. Append new links; do not rewrite old ones unless they are factually wrong.

---

*If the user keeps invoking /smart iteratively, treat each call as "given everything so far including your last suggestion, the latest modes-of-reasoning output, and the diffs since the last chain link, what's the next smartest move?" Build on prior answers, don't repeat them.*

## Related

- [[no-ragrets]] — Step 2 success contract (`Outcome` / `Evidence` / `Failure avoided`) wrapped around each goal
- [[beads-workflow]] — Step 2 plan→Beads conversion that mints the goal sequence
- [[divide-and-conquer]] — Step 3 ready-frontier pursuit for substantial slices
- [[skill-issue]]
