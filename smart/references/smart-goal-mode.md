# Smart Goal Mode

Use this mode when `/smart` is asked to write a serious goal instead of choosing
one immediate move. For a bare `smart goal` query, the chat output itself starts
with a compact, copy-pasteable `/goal ...` contract. Full trackers, MMDX stacks,
and Gantt views are secondary artifacts for explicit tracker/Gantt requests,
not the default chat shape.

## Trigger Shape

Activate this mode for prompts such as:

- `smart goal`
- "write a smart goal"
- "give me the one-shot goal"
- `ambitious goal tracker`
- `Gantt plan` or `ganntt plan`
- "start from where we are right now and fill in the blanks"
- "make a lofty goal with refinement and hardening rounds"

Classify the request before writing:

- `compact-goal`: bare `smart goal`, "write a goal", "one-shot this", or a
  request for a copy-pasteable goal. This is the default.
- `tracker`: ambitious goal tracker, milestone/program plan, or long-running
  loop request.
- `gantt`: explicit Gantt/`ganntt`, MMDX, timeline, or dated multi-view plan.

## Compact Goal Chat Output

For `compact-goal`, answer in the same terse style as a handoff prompt the user
can paste back into Codex. The first visible non-whitespace characters in the
chat response must be `/goal`; do not prepend "Use this as..." or any other
intro sentence.

```text
/goal $skill-one $skill-two process complete

One-shot goal: <one concrete finish line, including the target artifact,
repo/product/slice, and the most important build-vs-borrow or routing decision.>

Success criteria:
- <evidence-backed criterion>
- <evidence-backed criterion>
- <evidence-backed criterion>
- Detached fresh-eyes review is required before completion, and this goal
  authorizes at least one scoped reviewer worker for that gate, preferably
  routed through `/divide-and-conquer`: use an independent reviewer that did not
  implement the work, have it inspect the final diff/artifacts/validation
  evidence, and address or explicitly block on its findings before marking the
  goal complete.
```

Rules for this chat output:

- The answer starts with the `/goal` line itself. Do not add a heading, preamble,
  explanation, or wrapper fence before it.
- Add a "Shorter version" block only when the user asks for a tighter variant or
  the first goal is intentionally long; the shorter block must also start with
  `/goal`.
- Keep it copy-pasteable: no normal `/smart` field dump in chat, no MMDX link as
  the lead, no internal reasoning, no caveat pile.
- Start the block with `/goal` and include the sibling skill route when clear,
  such as `$domain-planner`, `$describe`, `$build-vs-clone`, `$divide-and-conquer`,
  or `$skill-issue`.
- Use `process complete` when the user wants the goal to drive the next agent
  until the handoff artifact is genuinely complete.
- Name the artifact or repo/slice directly. A future agent should know what to
  produce without reinterpreting the conversation.
- Include 5-10 success criteria by default. They should be observable proof,
  not aspirations.
- Capture build-vs-clone boundaries, out-of-scope boundaries, validation, and
  proof gates when they matter.
- Always include a detached fresh-eyes review success criterion for any
  implementation, plan, or handoff artifact: a separate reviewer worker that did
  not do the work must inspect the final artifacts and validation evidence before
  completion, and the goal must explicitly authorize at least one scoped reviewer
  worker for that gate, preferably routed through `/divide-and-conquer`, plus
  additional detached review rounds as needed.
- Do not ask a human question unless the agentic routes in the parent `/smart`
  contract cannot resolve it. Use recommended defaults inside the goal when
  reasonable.

For `tracker` or `gantt`, lead with the compact `/goal` block anyway, then add
the generated tracker path and short closeout details below it.

## Smart Goal Chain Logging

When the cwd is inside a git repo, log the exact compact goal block in `br`, not
as authoritative markdown:

1. Create or update the normal smart-chain issue with `--labels
   chain:smart,mode:goal`.
2. Include `smart_goal_mode` and `smart_goal_contract` in the issue notes, using
   the exact text shown in chat.
3. Store repo head, route, success criteria summary, fresh-eyes review
   requirement, tracker path, and resume condition in the issue fields using the
   mapping in [beads-recommendation-chain.md](beads-recommendation-chain.md).

If `.beads/` is unavailable, say that durable smart-goal chain logging is
unavailable. Do not invent a repo-root, overlay-local, harness-local, or markdown
fallback path.

`SMART_GOAL_CHAIN.md` is now only a rendered view. Generate it only when the user
explicitly asks for a markdown chain artifact or when a legacy handoff consumes
that file. The view must say it was generated from `br list --label
chain:smart --all --json` and must not be edited by hand.

## Required Inputs

1. Resolve today's date from the environment or `date +%F`. For `gantt`, the
   main chart starts on that date.
2. Run or emulate `/reality-check-for-project` first. Extract the current
   reality, vision checklist, gaps, proof gaps, bead coverage, blockers, and
   anything already working. For `compact-goal`, keep this proportional and use
   conversation/repo evidence when a full reality check would be heavier than
   the goal-writing request.
3. Query `/wiki` when project memory, operator preferences, or prior strategic
   guidance could materially steer the plan. Treat wiki output as directional
   guidance, not as implementation proof.
4. Apply `/build-vs-clone` thinking before every large workstream: improve,
   extend, extract, borrow, adopt, or build from scratch.
5. Route ambiguity before planning: use `/describe` when pass/fail criteria are
   unclear and `/domain-planner` when the goal spans a domain slice or multiple
   repos. Once the goal contract is sharp and implementation is substantial,
   hand off through `/divide-and-conquer` so it creates or consumes repo-local
   Beads before any worker wave launches.
6. Use `/mmdx` to create an MMDX stack only when the user explicitly asks for a
   Gantt/MMDX view or the plan genuinely has multiple views. The entry chart
   should be a Gantt; child charts should explain evidence, routing, hardening
   loops, proof gates, and dependencies.

## Goal Contract

Write this contract before or inside the tracker:

- `lofty_end_goal`: a concrete finish line, not a vibe. Example: "completely
  polished, well-tested, multi-round-refined user experience with relevant
  smart hardening between every implementation wave."
- `current_reality`: what is working, partial, unproven, stubbed, blocked, or
  uncovered by beads right now.
- `non_negotiable_quality_bars`: tests, e2e flows, performance, UX polish,
  accessibility, docs, operations, migration safety, and release proof as
  applicable.
- `out_of_scope`: tempting work that does not serve the goal.
- `proof_of_done`: command output, screenshots, test logs, reality-check result,
  closed beads, commits, deployed state, or other evidence that proves the goal
  is actually met.

## High-Altitude Goal Planning

When the user asks for a higher-level, loftier, or long-running goal, plan from
the end vision first. Do not let the nearest low-hanging fruit define the goal.
Use low-hanging fruit only as the first iteration when it measurably reduces a
blocker to the larger outcome.

Low-hanging fruit, hotspots, quick wins, and "start here" fixes are still valid
paths of work. The constraint is on the success criteria, not on the entry point:
the tracker should say why the first fix advances the bigger goal, then keep
iterating until the larger proof is met.

Before writing the tracker, classify the altitude:

- `one-shot`: one immediate recommendation with proof.
- `milestone`: one repo or product area moving toward a defined finish line.
- `program`: several related repos, surfaces, or skill workflows moving toward
  a shared quality bar.

For `milestone` and `program`, keep two success layers visible:

- Final success: the proof that the end vision is met.
- Iteration success: the proof that the current wave improved the system
  without pretending the larger goal is complete.

Example:

- `lofty_end_goal`: a well-maintained, performant codebase.
- `final_success_criteria`: relevant CRAP scores below the agreed threshold,
  mutation or metamorphic coverage where appropriate, reproducible performance
  baselines, passing repo-native test suites, no stale docs around changed
  paths, and a post-commit reality check that agrees the codebase is healthier.
- `iteration_path`: start with the highest-leverage hotspot or low-hanging
  fruit, then route through `/describe`, `/reproduce`, `/crap`, `/mutate`,
  `/testing-metamorphic`, `/profiling-software-performance`,
  `/extreme-software-optimization`, `/divide-and-conquer`, or
  `/vibing-with-ntm` as the evidence demands.

## Adjacent-Concern Sweep

Run this sweep before finalizing a high-altitude tracker:

- Neighboring code paths that call, render, import, or configure the target.
- Tests, fixtures, coverage, CRAP/mutation status, and missing reproducible
  checks around the target and adjacent paths.
- README/docs/comments/examples that could drift from the changed behavior.
- UX, accessibility, responsive behavior, copy, and workflow friction when a
  human-facing surface is involved.
- Data shape, migrations, rollout, deployment, auth, security, observability,
  and rollback risks when the change can affect runtime state.
- Skill, automation, or plan artifacts that future agents will inherit.

For each concern, decide whether it is:

- `in-scope`: must be handled in this goal.
- `guardrail`: must be checked before completion but may not require changes.
- `deferred`: intentionally out of scope with a reason.

## Granular Instruction View

Every substantial workstream in the tracker should have an instruction-level
handoff, not just a label. Include:

- `route`: direct work or sibling-skill combo.
- `artifact`: the file, Bead, plan, MMDX chart, test, or report produced.
- `validation`: exact command, screenshot/e2e proof, audit result, or blocker.
- `stop_condition`: the evidence that ends the wave or triggers the next one.

This is the bridge between a lofty end goal and executable agent behavior. It
lets later agents pursue the ambitious outcome without reinterpreting the
vision from scratch.

## Gantt Rules

Use dates, not vague phases. If the user has not supplied dates, choose
reasonable durations and say they are planning estimates.

- Section 1 is always `Now: Reality` and is filled from the reality check.
- Use `done` only for evidence-backed current wins.
- Use `active` for work already underway or the next immediate lane.
- Use `crit` for blockers, proof gaps, and hardening gates.
- Put a `milestone` after every major gate: goal contract, Beads
  baseline, hardening proof, user experience proof, final reality check.
- Every implementation wave needs a following hardening round. The default
  hardening bundle is `/describe -> /reproduce -> /crap or /mutate -> tests`.
- Every substantial UX wave needs at least two refinement loops: design pass,
  target-user workflow pass, and e2e/screenshot/accessibility proof when
  frontend work exists.
- The closing sequence is always validate, commit if authorized, then
  `/reality-check-for-project` from the new state.

## Ambition and Refinement Cadence

The tracker should raise the ceiling before it turns into tasks.

- Start with the reality check, then write the first goal contract.
- Run 2-3 plan-space ambition passes before implementation planning. The passes
  should ask what would make the outcome much more useful, polished, robust,
  differentiated, and humane for the target user.
- Add domain-specific depth where relevant: hard math, workflow theory,
  performance techniques, UX research, deployment operations, or market
  strategy. Do not add esoteric ideas unless they clearly serve the goal.
- If beads are available, convert the improved plan through
  `/divide-and-conquer` so future agents inherit the full context in the repo's
  `br` graph. If beads are unavailable, say durable bead tracking is blocked;
  use a clearly non-authoritative checklist only when the user still needs a
  temporary execution aid.
- Run 4-5 plan-space refinement passes before implementation when the goal is
  large enough to coordinate multiple waves. Stop earlier only when a pass finds
  no meaningful gap.

## MMDX Stack Shape

Start from `assets/templates/smart-goal-gantt-stack.mmdx` and replace all
generic labels with project-specific ones.

Minimum charts:

- `main`: Gantt from today to the lofty end goal.
- `goal-contract`: flowchart connecting current reality to the end goal.
- `reality-gap`: current evidence and missing proof from the reality check.
- `routing`: which sibling skills apply and why.
- `ambition-loop`: how the plan gets raised and refined before execution.
- `hardening-loop`: the repeated proof cycle between implementation waves.
- `proof-gate`: final evidence required before the loop can be called complete.

Optional child charts:

- `dependency-graph`: if there are beads, domain slices, or cross-repo
  dependencies.
- `ux-refinement`: if frontend experience quality is part of the goal.
- `build-vs-clone`: if major placement/reuse decisions are material.
- `wiki-guidance`: if wiki direction changed the path.

## Closeout

For `compact-goal`, the closeout is the copy-pasteable goal block. Keep the
normal `/smart` loop fields in the chain artifact rather than expanding them in
chat.

For `tracker` and `gantt`, return the compact goal block first, then the normal
`/smart` loop fields plus:

- `Goal tracker`: path to the generated `.mmdx` or markdown artifact.
- `Start date`: the concrete date used by the Gantt.
- `Reality baseline`: one sentence summarizing where the project is now.
- `Lofty end goal`: one sentence describing the finish line.
- `Hardening cadence`: the recurring proof loop inserted between waves.
- `Open assumptions`: assumptions that need agentic resolution or human input.

Do not call the goal complete until the final post-commit reality check agrees
that the higher-level goal is actually met.
