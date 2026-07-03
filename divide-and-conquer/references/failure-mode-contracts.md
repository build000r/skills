# Swarm Failure Mode Contracts

Use these contracts when a divide-and-conquer run is at risk of stalling,
declaring success too early, or accepting visual work from worker self-report.

## Blocked-Node Handling

A node is truly blocked only when no model-solvable proof, preparation, or
scope-tightening work remains. A human decision, unavailable external system,
credential gate, production approval, or missing artifact is a gate, not a
reason to park the whole wave.

When a worker reports a gate, the root orchestrator must first carve the
model-solvable child:

- Create or tighten a prep/proof node that can run now: reproducer, fixture,
  read-only audit, failing test, screenshot capture, rollback plan, risk memo,
  exact human question, external-system probe, mocked integration path, or
  decision brief with options and consequences.
- Give that child exact `writes` or read-only scope, validation, model route,
  expected assignee, and stop rules. Make the gated node depend on the child if
  the proof is required before work can continue.
- Keep unrelated ready nodes moving. Do not block the epic or cancel the wave
  while the prep child or other frontier work remains executable.
- If the prep child proves that a real external/human gate remains, block only
  the smallest affected node with the exact decision or external state needed.

Workers may propose this graph change in `Workgraph Notes`; the root owns the
actual `br create`/`br dep add`/`br update` mutation.

## Closeout Discipline

Final integration is root-owned work in the same run, not backlog for a future
session. After execution nodes are complete or truly externally blocked, the
root must execute the closeout lane before reporting:

- Reconcile every child against `br show`, result artifacts, and independent
  validation. Repair attribution before close when needed.
- Run integration, validation, Beads flush, close-eligible checks, final review,
  and commit acceptance in the active invocation run.
- If integration reveals a model-solvable defect, create or run the rework node
  immediately and then repeat closeout. Do not leave "final integration" or
  "closeout" as an open or blocked Bead for a later agent.
- If closeout cannot finish because of a real external gate, block the smallest
  exact node with the gate and record the proof that all model-solvable prep has
  already been completed.

`DAC_FINAL_RESULT.md` is the closeout evidence attachment. Its absence means the
root has not completed final integration.

## Visual-Parity Lane

Design, UI, screenshot, and visual-parity nodes are not accepted from worker
self-score. Acceptance requires independent fresh-context review.

For each design-related node or final visual review:

- Ask an independent reviewer the ORIGINAL user question and acceptance
  criteria, not a softened "review this diff" prompt. Include relevant
  screenshots, URLs, diffs, and validation output, but do not seed the reviewer
  with the implementer's self-score.
- Require severity-classified findings: `blocker`, `material`, `minor`, or
  `nit`. A material shortfall is any mismatch that would make the original ask
  unfulfilled: missing required behavior, visual parity failure, broken
  responsive state, incoherent layout/overlap, unusable interaction, or design
  system violation with user-visible impact.
- Stop only after two consecutive independent fresh-context reviews report no
  blocker or material shortfall. Minor/nit findings may be accepted only when
  they do not undermine the original ask and are recorded.
- If any blocker or material shortfall appears, patch or create a rework node,
  rerun validation/screenshots, and restart the consecutive-review count at
  zero.

Use the normal design route for this lane: Claude Fable high when available,
with Codex `gpt-5.5` xhigh as the recorded fallback.
