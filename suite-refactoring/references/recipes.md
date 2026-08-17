# Suite-refactoring recipes

One recipe per `suite-readiness/v1` finding code. The code is the API: the
scorer emits a code, you open the recipe with the matching heading, you apply
it, you re-score.

Every recipe has the same five parts:

- **Detect** — what the scorer saw.
- **Invariant** — the property that must hold when you are done. This is copied
  from the registry, not invented here.
- **Do** — the change, in order.
- **Prove** — the evidence that closes the finding. A recipe is not applied
  until this passes.
- **Stop** — the specific way this recipe gets faked, and what to do instead.

`ladder step` places the recipe on the seven-step ladder in `SKILL.md`. Never
apply a recipe from a later step before the earlier steps hold: a parallel-safety
proof written before the serial baseline exists is proof of nothing.

The contract between this file and the live registry is machine-checked:

```bash
python3 suite-refactoring/scripts/check_recipe_contract.py --registry <registry.json>
```

---

## Selection completeness

### CROSS_MACHINE_PARTITION_MISSING

- recipe_id: `suite-refactor/cross-machine-partition`
- axis: `selection_completeness`
- blocks: `optimization-only`
- ladder step: 4

**Detect.** The big suite has no cross-machine partition vocabulary. In-process
sharding is not one: a thread pool inside a single command cannot be addressed
by a scheduler that owns two machines.

**Invariant.** The suite can be partitioned into disjoint subsets addressable
from the CLI.

**Do.**

1. Name the partition axis you already have — package, directory, tag, lane.
   Do not invent a new taxonomy; the axis must be one a reader can predict.
2. Expose it as an argument on the existing entrypoint (`--lane`, `--package`,
   a positional selector). One flag, not a new command.
3. Make the selector total: enumerate the partitions from the same source the
   aggregate run uses, so a new package appears in both or neither.
4. Emit the partition list as data (`--list-lanes`, JSON) so a scheduler can
   read it instead of hardcoding it.

**Prove.** The union of every listed partition, run separately, selects the same
test set as the aggregate run. Compare collected identifiers, not counts —
counts collide.

**Stop.** Do not hand-maintain the partition list beside the suite. A list that
can drift from the suite will drift, and the failure is silent: tests vanish
from every partition at once. If the source of truth cannot enumerate itself,
that is the finding to fix first, and it is a product change — record it and
stop.

### PACKAGE_LANES_UNENUMERATED

- recipe_id: `suite-refactor/enumerate-package-lanes`
- axis: `selection_completeness`
- blocks: `parallel`
- ladder step: 2

**Detect.** Test-bearing packages exist that no declared entrypoint runs, so the
unit union is not the suite.

**Invariant.** Every test-bearing package is reachable from a declared aggregate
entrypoint.

**Do.**

1. Enumerate test-bearing packages from the build/workspace manifest, not by
   reading directory names.
2. Diff that set against what the declared entrypoint actually runs.
3. For each package in the gap, either add it to the aggregate entrypoint, or
   record an explicit, named exclusion with a reason next to the entrypoint.
4. Make the diff a check that runs in the suite, so a new unreferenced package
   fails the gate rather than being quietly skipped.

**Prove.** The check from step 4 passes, and the exclusion list is visible in the
same file a reader consults to learn what the suite covers.

**Stop.** An undeclared exclusion is worse than a failing test: it reports green
for work never attempted. If a package cannot run today, exclude it *by name*
with the reason — never by leaving it out of the enumeration.

### SERVICE_REQUIREMENT_UNDERIVED

- recipe_id: `suite-refactor/derive-service-requirements`
- axis: `selection_completeness`
- blocks: `parallel`
- ladder step: 3

**Detect.** Service markers are maintained by hand, so the service-free lane
drifts silently: a test acquires a database and nobody moves its label.

**Invariant.** A test's service requirement is derived from what it requests,
not hand-labelled.

**Do.**

1. Find the seam where a test obtains a service — a fixture, a factory, a
   client constructor. There is usually exactly one per service.
2. Have that seam record the requirement when it is used, rather than asking the
   author to declare it.
3. Derive the lane assignment from the recorded requirement at collection time.
4. Keep the hand labels only as an assertion: if a declared label and the
   derived requirement disagree, fail.

**Prove.** Deliberately make a service-free test acquire a service. The suite
must fail on the mismatch, not reassign it silently.

**Stop.** Do not resolve a label/requirement disagreement by rewriting the
label. The disagreement is the signal. If the derived requirement is right, the
test moves lanes; if the seam is wrong, that is a product defect — record the
exact failing case and stop.

---

## Entrypoint clarity

### TARGET_MONOLITHIC

- recipe_id: `suite-refactor/split-monolithic-target`
- axis: `entrypoint_clarity`
- blocks: `optimization-only`
- ladder step: 4

**Detect.** The gate is an `&&` chain, so a phase cannot be placed or retried on
its own.

**Invariant.** The declared gate is separately invocable lanes, not one chain of
phases.

**Do.**

1. Read the chain and name each phase. If a phase has no name, it is not yet a
   lane — do not split it.
2. Give each phase its own invocable target with the same semantics it had
   inside the chain, including its exit code.
3. Keep the original aggregate target, now composed of the named lanes. It
   remains the serial oracle.
4. Only then may a scheduler place lanes independently.

**Prove.** The aggregate target still passes and still fails for the same
reasons. Run it before and after on the same tree; the pass/fail verdict and the
failing phase must agree.

**Stop.** Splitting an `&&` chain changes failure semantics by default: a chain
stops at the first failure, independent lanes do not. Decide deliberately
whether the aggregate short-circuits, state it, and never let the split turn one
failure into a partially-run suite that reports green.

---

## Workspace isolation

### PATH_FRAGILE

- recipe_id: `suite-refactor/repo-relative-paths`
- axis: `workspace_isolation`
- blocks: `remote`
- ladder step: 3

**Detect.** Parent-directory traversal or absolute paths threaded through
targets break the moment the tree moves.

**Invariant.** No target depends on an absolute path or a path that escapes the
repo root.

**Do.**

1. Resolve every path from a single anchor computed at runtime — the repo root
   located from the file that defines it, not from the caller's working
   directory.
2. Replace traversal that escapes the root with an explicit input: an argument
   or an environment variable the caller must set.
3. Route temp, output, and cache paths through one per-run directory beneath
   that anchor, or through the platform temp directory. Never a fixed path.
4. Make the anchor independent of invocation directory, so the suite behaves the
   same from the root and from a subdirectory.

**Prove.** Run the suite from a copy of the tree at a different path, and from a
subdirectory. Both must pass without editing anything.

**Stop.** Do not fix a fragile path by hardcoding the machine that works today.
An absolute path that is correct on one checkout is the same defect with a
narrower blast radius.

---

## Service isolation

### SERVICE_FREE_LANE_MISSING

- recipe_id: `suite-refactor/service-free-lane`
- axis: `service_isolation`
- blocks: `parallel`
- ladder step: 3

**Detect.** Every declared lane needs a database, cache, or container to start.

**Invariant.** At least one declared lane runs to completion with no external
service.

**Do.**

1. Identify tests that touch a service only incidentally — through a shared
   fixture they never assert against.
2. Move the service acquisition behind the seam from
   `SERVICE_REQUIREMENT_UNDERIVED`, so the requirement is derived rather than
   assumed for the whole lane.
3. Declare the service-free lane as a real entrypoint and run it with services
   unavailable, not merely unused.
4. Leave genuinely service-dependent tests where they are. The goal is one
   honest fast lane, not a maximal one.

**Prove.** Run the service-free lane in an environment where the service is
absent — not just stopped. It must pass, and it must fail loudly if a test
reaches for the service.

**Stop.** Never reach the invariant by mocking a service the test was actually
asserting against. That converts a real test into a test of the mock. If a test
cannot lose its service without losing its meaning, it belongs in the
service-dependent lane.

---

## Concurrency safety

### EXTERNAL_SCHEDULER_LOCK_SEAM_MISSING

- recipe_id: `suite-refactor/external-scheduler-seam`
- axis: `concurrency_safety`
- blocks: `parallel`
- ladder step: 4

**Detect.** The only entrypoint serializes itself, so an external scheduler
cannot own ordering.

**Invariant.** The suite exposes a way to run its work without taking its own
global lock.

**Do.**

1. Find the lock and name what it protects. It is usually a shared workspace, a
   fixed port, or a singleton service — all of which have their own recipes.
2. Fix what the lock protects first. A seam added while the shared resource
   still collides converts a safe serial run into a flaky parallel one.
3. Add an entrypoint that performs the work without acquiring the lock, and
   leave the locking entrypoint in place as the default.
4. Document which resources the caller is now responsible for isolating.

**Prove.** Two lock-free invocations, run concurrently against the same tree,
both pass — repeated enough times to be more than one lucky interleaving, with
the ordering randomized between runs.

**Stop.** Removing the lock before fixing the contention is the single most
damaging move in this file: it converts a correct slow suite into an incorrect
fast one, and the resulting flake will be blamed on the tests. If contention
cannot be removed, keep the lock and record the blocker.

### SERVICE_ENDPOINT_STATIC

- recipe_id: `suite-refactor/dynamic-service-endpoints`
- axis: `concurrency_safety`
- blocks: `parallel`
- ladder step: 3

**Detect.** A fixed port or fixed socket path makes two concurrent runs collide.

**Invariant.** Service endpoints are allocated per run and injected by
environment.

**Do.**

1. Allocate the endpoint at startup — an ephemeral port from the OS, or a socket
   inside the per-run directory. Never a constant.
2. Inject it into the test process by environment variable. The tests read the
   variable; they do not compute the endpoint.
3. Fail closed when the variable is absent, rather than falling back to the old
   constant. A fallback preserves the collision and hides it.
4. Tear the endpoint down with the run that allocated it.

**Prove.** Start two runs concurrently and assert they received different
endpoints, then assert both completed. Also assert the process fails cleanly
with the variable unset.

**Stop.** Do not "fix" a port collision with a retry, a sleep, or a wider
timeout. Those convert a deterministic collision into an intermittent one, which
is strictly worse: it survives review and fails in the fleet.

---

## Determinism

### SERVICE_IMAGES_UNPINNED

- recipe_id: `suite-refactor/pin-service-images`
- axis: `determinism`
- blocks: `caching`
- ladder step: 2

**Detect.** A floating tag means two runs of the same tree can test different
software.

**Invariant.** Every external service image is pinned by digest.

**Do.**

1. Resolve each floating tag to the digest currently in use, and record the
   digest beside the tag so a human can still read what it is.
2. Pin every image the suite starts, including ones pulled indirectly by
   compose or fixture code.
3. Make the pin the thing that runs — a tag left in any start path defeats every
   other pin.
4. Give the update a deliberate path: a documented command that re-resolves and
   rewrites the digests, so pinning does not mean freezing forever.

**Prove.** Two runs of the same tree, with the registry's floating tag having
moved in between, start byte-identical images. Where that cannot be staged,
assert that no start path references a tag.

**Stop.** Pinning is not a caching feature — it is what makes a cached result
mean anything. Do not skip it because the suite "passes anyway"; an unpinned
suite that passes has proven something about an unknown version.

---

## Observability

### RECEIPT_NOT_COMPOSABLE

- recipe_id: `suite-refactor/composable-receipts`
- axis: `observability`
- blocks: `parallel`
- ladder step: 5

**Detect.** Proof exists only whole-tree, so a fanned-out run cannot be
aggregated honestly.

**Invariant.** Proof of a run composes from per-unit evidence.

**Do.**

1. Have each unit emit a machine-readable receipt naming what it ran — test
   identifiers, not counts — plus its verdict and its exit code.
2. Write receipts to per-run paths so concurrent units cannot overwrite each
   other.
3. Write an aggregator that combines receipts into one verdict, and make it
   refuse to aggregate when a unit's receipt is missing.
4. Make "missing receipt" a distinct outcome from "unit failed". They demand
   different responses.

**Prove.** Delete one unit's receipt and confirm the aggregate reports
incomplete rather than green. This is the load-bearing test: an aggregator that
treats absence as success is the mechanism by which partial runs get called
proven.

**Stop.** Never aggregate by summing passes. A total that cannot name which
tests ran cannot distinguish a full green run from a green run that silently
skipped a third of the suite.

---

## Applying more than one

Fix in this order when several codes are open:

1. Codes whose `blocks` denies the intent you actually requested. A finding that
   denies `remote` does not gate a `parallel` request — check `denied_intents`
   in the registry rather than assuming severity implies gating.
2. Within that set, earlier ladder steps first. Steps 2 and 3 remove contention;
   step 4 splits; step 5 proves. Reordering produces flakes.
3. `optimization-only` codes last. They deny no intent and are real work, not
   gates.

Re-score after each recipe rather than after all of them. A batch of recipes
that lands together cannot tell you which one closed the finding — or which one
introduced the flake.
