---
name: mutate
description: >
  Run scoped mutation testing with the right language adapter, keep the
  baseline test path green, triage surviving mutants, and feed the results back
  into a CRAP/mutate hardening loop. Use when: "/mutate", "mutation test",
  "mutate this file", "surviving mutants", "weak tests", "harden these tests",
  "run mutmut", "run cargo-mutants", "run stryker", or after `/crap`
  identifies a hotspot below 30.
license: MIT
---

# /mutate

Use mutation testing to measure test strength on a narrow, already-stabilized
scope.

This skill is for **adapter selection, scoped execution, and survivor triage**.
It complements `crap`:

- `crap` ranks risk from complexity plus coverage.
- `mutate` finds assertions and scenarios your tests still miss.
- Mutation testing does **not** directly raise or lower CRAP. CRAP moves only
  when code complexity or coverage changes.

## Modes

- **Analysis mode**: choose adapter, scope, and run plan without executing.
- **Execution mode**: run a scoped mutation pass, triage survivors, improve
  tests, and rerun.

Enter execution mode only when the user explicitly asks to run it, for example:

- `/mutate`
- `run mutation testing`
- `mutate this file`
- `kill the surviving mutants`
- `harden these tests`

## Supported v1 Adapters

Use [references/adapter-matrix.md](references/adapter-matrix.md) to pick the
right adapter and command family.

- `rust`: `cargo-mutants`
- `python`: `mutmut`
- `javascript` / `typescript`: `StrykerJS`

If the target language or build stack has no credible adapter, stop and say so.
Do not invent generic mutation commands.

## Runtime Contract

Resolve and run `scripts/analyze_mutants.py` relative to this `SKILL.md`.
Use [references/state-model.md](references/state-model.md) for the normalized
ledger schema and [references/one-shot-loop.md](references/one-shot-loop.md)
for the execution loop.

Examples:

```bash
python3 scripts/analyze_mutants.py
python3 scripts/analyze_mutants.py /path/to/repo --top 20
python3 scripts/analyze_mutants.py /path/to/repo --write-ledger
python3 scripts/analyze_mutants.py /path/to/repo --adapters mutmut,stryker --top 20
```

## Hand-Off From `crap`

Use `crap` first when the repo is broad, noisy, or has weak coverage data.

1. Prioritize coverage bootstrap, characterization tests, and simplification
   while the scoped `FINAL_SCORE` is `>= 30`.
2. Start mentioning or running `mutate` when the target scope is below `30`,
   coverage is numeric, the baseline tests are green, and the scope is narrow
   enough to mutate cheaply.
3. Treat `FINAL_SCORE < 8` as a healthy end-state for stabilized hotspots, not
   as the prerequisite for running `mutate`.
4. If the user explicitly wants mutation testing while the scoped score is
   still `>= 30`, keep the scope tight and warn that the signal may be noisy
   until the hotspot stabilizes.

## Baseline Contract

Before any mutation run:

1. Identify the canonical test command for the chosen scope.
2. Run that baseline first. If it is red, stop and fix or narrow scope before
   mutating.
3. Confirm the workspace is clean enough to reason about generated artifacts
   and temporary edits.
4. Prefer disposable outputs over in-place mutation. If the adapter mutates the
   worktree in place, warn before continuing and verify cleanup afterward.
5. Keep scope explicit: file, module, or package. Do not silently mutate the
   whole repo unless it is already small and stable.

## Scope Discipline

- Name the exact target file, module, or package in every close-out.
- Prefer one hotspot file or one package per run.
- If the adapter supports file filters, use them.
- If the adapter does not support fine scope directly, narrow via config or
  test selection rather than mutating the whole repo silently.
- Do not compare a narrow mutation pass to repo-wide health claims.

## Output Flow

### Phase 1: Choose adapter and scope

- Detect language and build tool.
- Read [references/adapter-matrix.md](references/adapter-matrix.md).
- State which adapter you are using and why.
- If multiple adapters are possible, prefer the repo's existing one.
- Run `scripts/analyze_mutants.py` first when mutation artifacts already exist
  so you have a deterministic backlog before launching more test hardening.

### Phase 2: Establish baseline

- Run the canonical test path for the target scope.
- Stop if the baseline is red or flaky.
- If the adapter depends on coverage or test-mapping metadata, generate it with
  the repo-native path.

### Phase 3: Run mutation testing

- Use the narrowest practical target.
- Prefer config files already committed in the repo.
- Keep raw adapter output concise but preserve counts for:
  - killed mutants
  - surviving mutants
  - timeouts, no coverage, and equivalent-style noise when the adapter reports
    them
- When the repo wants durable tracking, rerun
  `scripts/analyze_mutants.py --write-ledger` after the mutation pass so the
  backlog is normalized into `.mutate/ledger.json`.

### Phase 4: Triage survivors

Bucket each survivor before writing production code:

1. missing assertion or missing example
2. incidentally covered code that lacks direct tests
3. equivalent or low-value mutant worth excluding
4. tooling noise or flaky timeout

Prefer stronger tests first. Change production code only when the survivor
exposes confusing structure or accidental complexity.

### Phase 5: Close the loop

- Rerun the baseline test path.
- Rerun the mutation pass for the same scope.
- If this work came from `crap`, rerun `crap` on the same scope after the test
  changes land.
- Report:
  - scope
  - adapter
  - baseline status
  - surviving mutants before and after
  - exclusions added
  - whether CRAP moved on rerun

## One-Shot Execution

If the user explicitly asks to run the loop, use
[references/one-shot-loop.md](references/one-shot-loop.md).

## Reporting Rules

- Treat `scripts/analyze_mutants.py` as the formatting source of truth for the
  normalized backlog report.
- State the adapter and exact command family used.
- Separate real survivors from equivalent or noise buckets.
- Do not claim a higher mutation score automatically means lower CRAP.
- If you exclude mutants, name the exact rule or config location and justify
  it.
- Prefer test additions over broad exclusion lists.
- When the run follows `crap`, frame the result as `crap -> mutate -> crap`,
  not as a replacement for CRAP analysis.
- Keep the final line machine-readable and unique: `FINAL_TODO: <value>`.
