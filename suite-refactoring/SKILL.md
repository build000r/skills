---
name: suite-refactoring
description: Move a test suite from an honest serial baseline toward safe parallelism, one scorer finding at a time. Use when a readiness scorer emits suite-readiness finding codes, when asked to "parallelize the tests", "shard the suite", "speed up CI", "split the test target", "make tests run on more than one machine", or when a suite must be made partitionable without weakening its assertions or losing its serial oracle.
---

# Suite refactoring

A slow suite that tells the truth is worth more than a fast one that does not.
Every change in this skill is therefore judged against a single question: does
the suite still fail for exactly the reasons it used to?

Parallelism is not the goal. It is a thing you are permitted to take once the
suite can prove it deserves it. Most of the work here is removing the reasons it
cannot.

## On trigger

Start the first progress update with:

`Using suite-refactoring ...`

Then read the finding codes. This skill is organized as **one recipe per finding
code**, and the code is the interface — you do not browse for advice, you open
the recipe whose heading is your code.

Load [references/recipes.md](references/recipes.md) and find the heading that
matches. Do not read the whole file first; read the recipe you were sent to.

The code list lives in the registry, not in this file. A third copy of the
mapping would be a third thing that drifts, and only two are machine-checked —
so do not add a code index here. To list the live codes:

```bash
python3 suite-refactoring/scripts/check_recipe_contract.py \
  --registry path/to/finding_registry.v1.json --json
```

## The loop

```bash
sbp test score --format json     # 1. get findings
                                 # 2. open the recipe matching one code
                                 # 3. apply it
sbp test score --format json     # 4. re-score, confirm that code closed
```

One recipe per pass. A batch that lands together cannot tell you which change
closed the finding, or which one introduced the flake.

When several findings are open, the order is not arbitrary — see **Applying more
than one** at the end of [references/recipes.md](references/recipes.md). Short
version: findings that deny your requested intent first, earlier ladder steps
before later ones, `optimization-only` last.

**A recipe is not applied until its Prove step passes.** If the evidence cannot
be produced in this environment, the finding stays open: say which Prove step
could not run and why. An unprovable recipe is an open finding with a note, not
a closed one with an excuse.

**Prerequisite.** This loop needs a readiness scorer that emits
`suite-readiness/v1` codes. If `sbp test score` is not available in the
installed CLI, you do not have a score — and *you cannot substitute your own
judgment for one*. Work the ladder from step 1, apply recipes only for problems
you can point at in the tree, and state plainly that no readiness claim is
backed by a score. Never report a readiness class you did not measure.

### Read the score correctly

The registry states its own authority, and it is narrower than it looks:

- **Named findings are authoritative; the numeric rollup is advisory.** The
  rollup never gates. A number an agent can optimize becomes the target, and
  optimizing it is not the same as fixing the suite.
- **Only a proven finding gates, and only for the intent it denies.** Check the
  finding's `blocks` and `denied_intents` against the intent you actually
  requested. A finding that denies `remote` does not block a `parallel` request.
  `optimization-only` findings deny nothing — they are real work, not gates.
- **Omission is unknown, and unknown neither passes nor gates.** A code that did
  not fire means nobody looked. It is not evidence of health.
- **Readiness scope is the v1 code subset, never the whole axis model.** Axes
  outside v1 are silent by construction. "Every v1 finding cleared" does not
  mean "the suite is ready"; it means the covered subset is clean. Say it that
  way.

## The ladder

Seven steps, in order. A recipe's `ladder step` says where it sits. Applying a
later step before an earlier one holds is how a working serial suite becomes a
flaky parallel one.

1. **Wrap, don't split.** Before changing anything, run the suite as it is and
   save a baseline receipt. This is the artifact the entire skill rests on, so
   record all four parts: the exact command, its exit code, the **list of test
   identifiers it selected**, and the pass/fail verdict. Identifiers are the
   part people skip and the part that matters — a count cannot tell you which
   tests disappeared. Steps 5 and 7 compare against this file; without it you
   cannot tell a refactor from a regression.
2. **Declare reality.** Write down what the suite actually runs today —
   entrypoints, packages, exclusions, service needs. Most findings at this step
   are discovered by writing the list, not by running anything.
3. **Isolate side effects.** Per-run namespaces, per-run endpoints, per-run
   directories, real teardown, and assertions that leaks fail. This is where
   most of the work is, and it is worth doing even if you never parallelize.
4. **Split only along existing semantic lanes.** Use a boundary the codebase
   already has — package, tag, phase. Inventing a taxonomy at this step produces
   a partition nobody can predict and everybody mis-selects.
5. **Prove coverage equivalence.** The union of the units must select the same
   tests as the serial oracle. Compare identifiers, not counts. Every deliberate
   exclusion must be named and visible where a reader will look.
6. **Prove parallel safety.** Randomize ordering, run concurrently, inject
   failures, and repeat enough times that a pass is not one lucky interleaving.
   One green concurrent run proves nothing.
7. **Retain the serial oracle permanently.** It stays invocable forever. The day
   the parallel path and the serial path disagree is the day you need it, and
   that is exactly the day it is missing if you deleted it after step 6.

## Safety stops

These are not preferences. If following a recipe seems to require one of these,
the recipe is not the problem — stop and report.

- **Never weaken an assertion to make a test pass in a new lane.** A test that
  asserts less is not the same test. If it cannot survive isolation without
  losing its meaning, it belongs in the lane it came from.
- **Never add a retry, a sleep, or a wider timeout to hide a flake.** These
  convert a deterministic failure into an intermittent one, which is strictly
  worse: it survives review and fails in the fleet. A flake that appears after
  a change is that change's evidence.
- **Never call a partial run proven.** A green run over a subset is a green run
  over a subset. If any unit's evidence is missing, the outcome is *incomplete*,
  which is a distinct result from *pass* and demands a different response.
- **On finding a product defect, stop.** If the suite starts failing because
  isolation exposed a real bug, record the exact failing case — the test, the
  command, the output — and stop. Do not fix the product under cover of a test
  refactor, and do not route around the failure. That defect is the most
  valuable thing the refactor produced.

## The anti-drift contract

The recipes and the registry must stay in bijection: every live code has exactly
one recipe, and every recipe answers a live code. Both directions fail
differently and both are checked.

```bash
python3 suite-refactoring/scripts/check_recipe_contract.py \
  --registry path/to/finding_registry.v1.json
```

Exit `0` holds, `1` is drift, `2` means the check could not run — which is never
the same as clean.

When the registry adds a code, this skill is incomplete until a recipe with that
heading exists. When a code is retired, its recipe goes with it. Pass the
registry path explicitly; the checker has no default and discovers nothing, so
it can never quietly validate the wrong file.

## Required verification

Run before reporting any change to this skill:

```bash
python3 skill-issue/scripts/quick_validate.py suite-refactoring
python3 suite-refactoring/tests/test_recipe_contract.py
python3 suite-refactoring/scripts/check_recipe_contract.py --registry path/to/finding_registry.v1.json
```

All three must pass. Do not mark work complete on a partial run — the same rule
this skill applies to the suites it refactors applies to the skill itself.

## What this skill does not do

- It does not implement or modify a scorer, a CLI, or a test runner. It consumes
  finding codes; it does not produce them.
- It does not decide that a suite is ready. It closes named findings; readiness
  is a claim about a scope, and the scope is narrower than the ten-axis model.
- It does not parallelize anything by itself. Steps 1 through 3 are frequently
  the entire job, and a suite that stops there is better than it was.
