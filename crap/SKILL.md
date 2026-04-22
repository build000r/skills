---
name: crap
description: Compute CRAP-style hotspot scores across Rust, Python, TypeScript, and Swift, print a ranked risk report, end with a FINAL_SCORE line, and suggest hardening follow-ons. Use for "/crap", CRAP score, risk score, hotspot ranking, weak coverage, or taking a scoped score under a threshold.
license: MIT
---

# /crap

Score code-risk hotspots with a CRAP-style formula across Rust, Python,
TypeScript, and Swift.

This skill is for **analysis and planning**, not auto-fixing. It finds risky
functions, ranks them, and turns the output into candidate `/describe`
remediation units.

## Modes

- **Analysis mode**: baseline score, hotspot ranking, next-action suggestions.
- **One-shot remediation mode**: bootstrap coverage, split work, implement test-
  first slices, rerun CRAP, commit progress, and iterate until the scoped score
  is below threshold or a blocker stops the loop.

Enter one-shot remediation mode only when the user explicitly asks for
execution, for example:

- `do it`
- `take it under 30`
- `/crap 25`
- `/crap --threshold 25`
- `fix the hotspots`
- `keep going`

## Supported Languages

- `rust`
- `python`
- `typescript`
- `swift` (requires `pip install lizard` for function parsing; Swift coverage
  is read from Cobertura XML produced by `xcresultparser`)

If the user explicitly requests a language outside that set, stop and say so.
Do not fabricate scores, findings, or follow-on suggestions for unsupported
languages.

### Swift prerequisites

Swift analysis has two optional dependencies. If either is missing, the
analyzer degrades gracefully rather than crashing:

- **`lizard`** (Python library): parses Swift functions. Install with
  `pip install lizard`. If missing, Swift files are skipped with a one-time
  stderr warning; other languages still analyze.
- **`xcresultparser`** (Homebrew tool): converts Xcode `.xcresult` bundles to
  Cobertura XML. Install with `brew install xcresultparser`. See
  [references/coverage-targets.md](references/coverage-targets.md) for the
  `crap-swift-cobertura` Makefile recipe.

## Runtime Contract

Resolve and run `scripts/analyze_crap.py` relative to this `SKILL.md`.
Use [references/coverage-targets.md](references/coverage-targets.md) when the
repo needs coverage artifact targets. Use
[references/testing-bootstrap.md](references/testing-bootstrap.md) when the
repo lacks a trustworthy test or coverage baseline. Use
[references/one-shot-loop.md](references/one-shot-loop.md) for autonomous
reduction loops. Use `scripts/delta_audit.py` to validate that score
improvements are legitimate during remediation loops.

Examples:

```bash
python3 scripts/inspect_test_stack.py
python3 scripts/inspect_test_stack.py /path/to/repo
python3 scripts/inspect_test_stack.py /path/to/repo --json
python3 scripts/analyze_crap.py
python3 scripts/analyze_crap.py /path/to/repo
python3 scripts/analyze_crap.py /path/to/repo --languages rust,python
python3 scripts/analyze_crap.py /path/to/repo --languages swift
python3 scripts/analyze_crap.py /path/to/repo --languages python --top 20
python3 scripts/analyze_crap.py /path/to/repo --languages python --threshold 25 --top 20
python3 scripts/delta_audit.py snapshot /path/to/repo -o /tmp/crap-baseline.json
python3 scripts/delta_audit.py audit /tmp/crap-baseline.json /path/to/repo
python3 scripts/delta_audit.py audit /tmp/crap-baseline.json /path/to/repo --json
```

## Threshold Resolution

Treat the target threshold as explicit input when the user provides one.

Resolve it in this order:

1. `--threshold N` in the skill request or analyzer invocation
2. A bare numeric argument after `/crap`, for example `/crap 25`
3. Natural-language phrasing such as `take it under 25` or `get this below 20`
4. Default target: `FINAL_SCORE < 30`

Guardrails:

- Thresholds must be positive numbers.
- Keep the threshold scoped. A package-scoped run against `25` is not a
  repo-wide `25` claim.
- In one-shot remediation mode, restate the resolved threshold before starting
  the loop.

## Mutation-Testing Hand-Off

`crap` and `mutate` solve different problems.

- `crap` ranks change risk from complexity plus coverage.
- `mutate` checks whether the tests around a scoped hotspot are strong enough
  to kill realistic defects.
- Mutation testing does **not** directly change CRAP. Only coverage and
  complexity changes move the CRAP score.

Default hand-off rule:

1. Prioritize coverage bootstrap, characterization tests, and simplification
   while the scoped `FINAL_SCORE` is still `>= 30`.
2. Start mentioning or running the sibling `mutate` skill when the scoped
   `FINAL_SCORE` is below `30`, the baseline test path is green, coverage is
   numeric, the hotspot language is one that `/mutate` supports
   (`rust`, `python`, `typescript`, `swift`), and the hotspot scope is narrow
   enough to mutate economically.
3. Treat `FINAL_SCORE < 8` as a strong end-state target for stabilized
   hotspots, not as the prerequisite for mentioning `mutate`.
4. If the user explicitly wants mutation testing while the scoped score is
   still `>= 30`, keep the scope tight and say that the mutation signal may be
   noisy until the hotspot stabilizes.

## Analyzer Behavior

The bundled script must be the source of truth for score calculation and report
formatting.

1. Default target is the current working directory.
2. Default language mode is autodetect across supported files.
3. Coverage sources may come from `lcov.info`, `coverage.xml`, or
   `cobertura.xml`.
4. Missing coverage stays `N/A`. Never infer or invent coverage.
5. Sort numeric CRAP rows first, descending by score. Sort `N/A` rows after
   numeric rows.
6. The analysis block must end with exactly one machine-readable line:
   `FINAL_SCORE: <value>`
7. `FINAL_SCORE` is the maximum numeric CRAP value in the run. If there are no
   numeric CRAP values, emit `FINAL_SCORE: 0.00`.

## Prerequisite Bootstrap

If the scope does not have a trustworthy baseline test path yet, fix that
before doing hotspot remediation.

1. Run `python3 scripts/inspect_test_stack.py {target}` before improvising
   shell discovery when any of these are true:
   - the analyzer is all `N/A`
   - the repo has tests but no machine-readable coverage artifact
   - the repo does not appear to have tests at all
2. Interpret the inspector result strictly:
   - `ready`: reuse the existing baseline and coverage artifact
   - `add-coverage-target`: keep the fast path intact and add an additive
     coverage target
   - `bootstrap-tests`: add the smallest repo-native harness that makes CRAP
     measurement trustworthy
3. Prefer narrow characterization tests around the hottest scope instead of
   broad suite architecture when bootstrapping.
4. In mixed or monorepo scopes, narrow to the package or crate that owns the
   hotspot if root automation is too thin to provide a trustworthy baseline.
5. Do not claim a repo-wide numeric result after narrowing to one package.
6. Do not use `divide-and-conquer` for hotspot slices until the baseline test
   path and coverage lane are real. Treat bootstrap work as an upstream node.

## Coverage Bootstrap

When the analyzer returns `FINAL_SCORE: 0.00` because every finding is
`coverage N/A` / `CRAP N/A`, treat that as a coverage-artifact gap first.

1. Inspect repo automation before answering:
   - start with `python3 scripts/inspect_test_stack.py {target}`
   - then inspect `Makefile`, `package.json`, `pyproject.toml`, or `Cargo.toml`
     only as needed to implement the chosen bootstrap lane
2. If a machine-readable coverage target already exists, point to that exact
   target or script.
3. If coverage exists only as a terminal report, prefer adding an **additive**
   target instead of mutating the canonical fast path.
4. If the repo has a `Makefile` and the user wants a real numeric CRAP score,
   prefer creating Makefile targets instead of handing back a long one-off
   command.
5. Reuse the example names in
   [references/coverage-targets.md](references/coverage-targets.md):
   - `pytest-cov-xml`
   - `vitest-cov-lcov`
   - `cargo-cov-lcov`
   - optional aggregate `crap`
6. After adding or identifying the right target, run it if feasible, then
   rerun the analyzer.
7. If you only bootstrap coverage for a subset of the original target, label
   the rerun explicitly as **package-scoped** or **path-scoped** and name that
   path.
8. If the inspector reports `bootstrap-tests`, establish the smallest viable
   test lane first, then add the coverage target. Do not skip straight to
   coverage flags on an otherwise nonexistent test harness.

Guardrails:

- Keep fast-path developer targets like `make test` or `make pytest` intact.
- Prefer sibling targets with explicit artifact names over silently changing
  existing targets.
- If the repo has no `Makefile`, mirror the same behavior in package-manager
  scripts, but still prefer `Makefile` in repos that already use it.
- For mixed-language repos, create one target per tested ecosystem, then an
  optional aggregate `make crap` wrapper.
- If the user invoked `/crap` from repo root, do not silently redefine the
  result as repo-wide after narrowing to one package or one language. Either
  produce a true repo-wide rerun or state that the numeric result is partial.
- If the repo has no tests, do not stop at "coverage missing." Bootstrap the
  smallest repo-native harness needed for a trustworthy score.

## Scope Discipline

Treat scope as part of correctness.

1. If the analyzer runs against the user’s original target unchanged, call the
   result `repo-wide` or `target-wide`.
2. If you rerun against a narrower path such as `packages/python-server-quickstart`,
   call the result `package-scoped` or `path-scoped` and name the exact path.
3. If the user started at repo root and only one ecosystem has usable coverage,
   say that the repo-wide numeric score is still unknown.
4. Prefer adding per-language coverage targets plus an aggregate `make crap`
   wrapper when the user wants a true repo-wide score in a mixed-language repo.

## Delta Integrity Audit

In one-shot remediation mode, every iteration must pass a delta integrity check
before committing. This prevents agents from gaming the score through structural
tricks that lower the metric without improving actual code quality.

### When to run

Run the audit after every re-measure step in the one-shot loop (between step 4
and step 5 in [references/one-shot-loop.md](references/one-shot-loop.md)).

### How to run

1. At the start of the remediation loop, capture a baseline snapshot:

```bash
python3 scripts/delta_audit.py snapshot {target} --languages {languages} -o /tmp/crap-baseline.json
```

2. After each iteration's re-measure, audit the delta:

```bash
python3 scripts/delta_audit.py audit /tmp/crap-baseline.json {target} --languages {languages}
```

3. Read the `DELTA_INTEGRITY` line:
   - `clean`: proceed to commit.
   - `warning`: review the flags, proceed if justified.
   - `suspicious`: **stop the loop**. Show the flags to the user. Do not commit
     until the user acknowledges or the suspicious changes are reverted.

4. After a clean commit, take a fresh snapshot for the next iteration.

### What it detects

| Category | Signal | Verdict |
|---|---|---|
| `split-without-reduction` | Function disappeared, 2+ replacements in same file, sum(CC) >= original | suspicious |
| `scope-escape` | File disappeared without git deletion or rename into scope | suspicious |
| `hollow-coverage` | New test files with zero assertions | suspicious |
| `hollow-coverage` | Existing test file assertions dropped to zero | warning |
| `scope-narrowing` | Target path changed between snapshot and audit | suspicious |

### Guardrails

- Never commit with `DELTA_INTEGRITY: suspicious` unless the user explicitly
  acknowledges the flags.
- When a split is flagged, explain to the user whether the split genuinely
  reduced coupling or just distributed the same complexity.
- When scope escape is flagged, verify whether code was intentionally deleted
  or just moved out of the analyzed target.
- A clean delta audit does not guarantee the work is good — it guarantees the
  score movement is honest. Test quality still needs separate validation
  (mutation testing, code review).

## Output Flow

### Phase 1: Run the analyzer

Run the script and show its report.

### Phase 1.5: Bootstrap coverage targets when scores are all N/A

If the report is all `N/A` and the user asks how to get a real score, inspect
the current scope with `scripts/inspect_test_stack.py`, then add the missing
test and coverage prerequisites instead of only suggesting an ad hoc raw
command. Use [references/testing-bootstrap.md](references/testing-bootstrap.md)
for harness bootstrap and use
[references/coverage-targets.md](references/coverage-targets.md) for examples.

### Phase 1.6: Preserve scope in the close-out

If the rerun scope changed from the original target:

1. Say so before presenting the numeric score.
2. Name the narrowed path explicitly.
3. Do not call the resulting `FINAL_SCORE` repo-wide.

### Phase 2: Suggest next work only when numeric hotspots exist

If the analyzer produced one or more numeric CRAP findings, emit the suggested
follow-on block and ask exactly:

`Do we need to adjust any of these findings/next actions, or does this look good to launch?`

If there are no numeric findings, stop after the analysis output. Do not add
divide-and-conquer recommendations.

### Phase 3: Apply ask-cascade on the response

If the user answers `adjust` or otherwise asks for changes:

1. Ask exactly **one strategic question first** about what to adjust.
2. Do not ask detailed follow-ups until that answer is known.
3. Re-evaluate the follow-up questions after the user answers.

Good first question:

`What should we adjust first: scoring accuracy, hotspot grouping, follow-on /describe items, or the launch recommendation?`

This gate is mandatory. Do not blast the user with all possible follow-up
questions at once.

If the user answers `launch` or approves the next actions:

1. Keep the decomposition read-only until the next explicit execution request.
2. Recommend `divide-and-conquer` as the follow-on path when there are multiple
   hotspot groups.
3. Turn each hotspot group into its own `/describe` candidate plus one
   cross-language synthesis item.

### Phase 4: One-shot remediation mode

If the user explicitly asks for execution, use
[references/one-shot-loop.md](references/one-shot-loop.md) and run the bounded
loop directly.

Requirements:

1. Set a threshold first using the resolution order above. Default to
   `FINAL_SCORE < 30`.
2. Establish a trustworthy baseline before choosing slices.
   - run `scripts/inspect_test_stack.py` when the baseline is unclear
   - bootstrap tests before coverage when the scope lacks both
3. Use `divide-and-conquer` when hotspot groups are independent and the runtime
   supports it **after** measurement prerequisites are ready. Otherwise use the
   same concern split in a single-agent loop.
4. Implement tests first for each slice.
5. After each slice, rerun the canonical test path, the coverage target, and
   the analyzer.
6. When a slice drops below `30`, the baseline is green, and the hotspot
   language is one that `/mutate` supports (`rust`, `python`, `typescript`,
   `swift`), optionally run the sibling `mutate` skill on that narrowed
   scope before the next CRAP rerun.
7. Use `scripts/analyze_crap.py ... --top 20` for inner-loop reruns to keep
   output concise while preserving the true `FINAL_SCORE`.
8. After each re-measure, run `scripts/delta_audit.py audit` against the
   baseline snapshot. If `DELTA_INTEGRITY` is `suspicious`, stop the loop and
   show the flags to the user before committing.
9. Use the `commit` skill after each stable logical batch. Do not wait until
   the very end if the loop is making clean progress. After committing, take a
   fresh delta audit snapshot for the next iteration.
10. Continue iterating until:
    - the scoped score is below threshold, or
    - a real blocker or diminishing-return stop condition from
      [references/one-shot-loop.md](references/one-shot-loop.md) is hit.
11. Report the score delta after each loop step:
   - baseline score
   - current score
   - top moved hotspots
   - commits made
   - blocker or next slice

## Reporting Rules

- Show file path, symbol, CC, coverage, and CRAP for each finding.
- Use `N/A` for coverage and CRAP when no matching coverage data exists.
- Keep the final score line machine-readable and unique.
- Do not hide lower-scoring supported languages just because one language is
  worse.
- Do not include unsupported files in the ranking.
- When coverage artifacts are missing, explain the gap and prefer creating a
  repo-native target over returning only a one-off command.
- Treat the analyzer output as the formatting source of truth. Do not replace
  its `Suggested /describe follow-on` block or its final launch gate question
  with a handwritten alternative.
- If the scoped `FINAL_SCORE` is below `30` and the reported language is one
  that `/mutate` supports (`rust`, `python`, `typescript`, `swift`), mention
  the sibling `mutate` skill as a follow-on path. Make it explicit that
  mutation results are a test-quality signal, not a direct CRAP input.
- If you add a human summary, place it after the raw analyzer output and keep
  scope labels exact.
- If a threshold was explicitly provided or the user is in one-shot mode, state
  the resolved target alongside the score comparison.
- In one-shot remediation mode, keep inner-loop analyzer reruns concise with
  `--top`, but always report the true current `FINAL_SCORE`.

## Future Work

These are deferred follow-ups tracked here so they are not lost.

### Full Lizard backend swap (scope B)

Swift support currently routes only `.swift` files through
[Lizard](https://github.com/terryyin/lizard) while Rust, Python, and
TypeScript continue to use the hand-rolled analyzers in
`scripts/analyze_crap.py`. The hand-rolled Rust/TypeScript paths are
regex-based and known to miss edge cases that Lizard's token-state plugins
handle (arrow functions with template literals, Rust `?` error propagation,
etc.).

A follow-up slice should evaluate replacing all four per-language analyzers
with Lizard as a single backend:

- **Risk**: score drift on existing Rust/Python/TypeScript repos that already
  have CRAP baselines captured via `scripts/delta_audit.py`.
- **Required work**: additive version bump in `delta_audit.py` snapshot
  format so old baselines still load, plus a migration note for users with
  in-flight remediation loops. Decide whether to keep the Python `ast` path
  (structurally correct) or adopt Lizard's token-based Python plugin for
  consistency.
- **Benefit**: one parser path to maintain, richer per-function metrics
  (NLOC, nesting depth, token count, parameter count) available to
  `delta_audit.py` for stronger anti-gaming checks, and alignment with the
  Swift path.

Handle this as a standalone `/describe` packet with its own baseline
migration plan.

## Related

- [[skill-issue]]
