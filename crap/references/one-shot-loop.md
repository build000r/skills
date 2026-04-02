# One-Shot Remediation Loop

Use this mode when the user explicitly wants execution, not just analysis.

Examples:

- `take it under 30`
- `take it under 25`
- `/crap 25`
- `/crap --threshold 25`
- `fix the hotspots`
- `do it`
- `one-shot crap`
- `keep going until the score is down`

## Goal

Run a bounded improvement loop:

1. establish a trustworthy baseline
2. split the work by concern
3. implement the highest-return slices
4. hand stable slices to mutation testing when they drop below `30`
5. rerun coverage and CRAP
6. commit stable progress
7. repeat until the scoped `FINAL_SCORE` is below the agreed threshold or a
   real blocker stops progress

## Default Threshold

- Default target: `FINAL_SCORE < 30`
- Optional explicit input: `/crap 25`, `/crap --threshold 25`, or natural
  language like `get this under 25`
- If the user gives a different threshold, use that instead.
- Keep the threshold scoped. Do not compare a package-scoped score to a
  repo-wide threshold without saying so.

## One-Shot Loop

### 1. Baseline

- Resolve scope first: repo-wide, package-scoped, or path-scoped.
- Run `python3 scripts/inspect_test_stack.py {target}` if the baseline is
  unclear, the analyzer is all `N/A`, or the scope may not have tests yet.
- Bootstrap the smallest repo-native test path if needed.
- Bootstrap machine-readable coverage after the baseline test path exists.
- Run the analyzer with a concise inner-loop view:

```bash
python3 scripts/analyze_crap.py {target} --languages {languages} --top 20
```

- Capture a delta audit baseline snapshot immediately after the first analyzer
  run:

```bash
python3 scripts/delta_audit.py snapshot {target} --languages {languages} -o /tmp/crap-baseline.json
```

- Capture:
  - current `FINAL_SCORE`
  - top hotspot functions
  - whether the coverage run is green or only artifact-producing
  - whether the baseline is test-ready, coverage-ready, or still bootstrapping

### 2. Decide split strategy

- If prerequisite baseline work is still missing, keep that upstream and finish
  it before launching hotspot workers.
- If 2 or more hotspot clusters are independent, use `divide-and-conquer`.
- If the runtime cannot launch sub-agents, use the same decomposition as a
  single-agent concern-separated plan.
- Good split boundaries:
  - baseline bootstrap vs coverage bootstrap
  - domain service vs middleware vs startup/bootstrap
  - direct-coverage gap vs failing-test stabilization
  - fixture-harness work vs business-logic branch coverage

### 3. Implement test-first slices

For each slice:

1. Add or extend tests first.
2. Change production code only if the tests reveal a real gap.
3. Reuse existing test helpers before creating new harness layers.
4. Prefer small deterministic branch-coverage wins before broad rewrites.
5. When bootstrapping a missing harness, stop at the smallest viable baseline
   that makes CRAP measurement trustworthy.

### 4. Re-measure after every slice

After each slice or coherent batch:

```bash
make pytest
make pytest-cov-xml
python3 scripts/analyze_crap.py {target} --languages {languages} --top 20
```

If the scope uses a different canonical baseline, substitute the repo-native
equivalent. Keep the same order: baseline test path, coverage path, analyzer.

Record:

- previous `FINAL_SCORE`
- new `FINAL_SCORE`
- active threshold
- moved hotspots
- whether unrelated failing suites still exist

### 4.5 Mutation hardening hand-off

When a narrowed hotspot is below `30`, the baseline test path is green, and the
language is still within CRAP's supported v1 set (`rust`, `python`,
`typescript`):

- run the sibling `mutate` skill or the repo-native mutation command on that
  same narrowed scope
- use surviving mutants to drive stronger tests before adding more production
  code changes
- rerun coverage and CRAP after the mutation-driven test changes land

Do not present mutation results as a CRAP input. They are a separate signal
about test strength.

### 4.6 Delta integrity audit

After every re-measure (step 4), run the delta audit before committing:

```bash
python3 scripts/delta_audit.py audit /tmp/crap-baseline.json {target} --languages {languages}
```

Read the `DELTA_INTEGRITY` line:

- `clean`: proceed to commit.
- `warning`: review the flags, proceed if justified.
- `suspicious`: **stop the loop**. Show the flags to the user and do not commit
  until the suspicious changes are acknowledged or reverted.

Common flags and what they mean:

- **split-without-reduction**: A function was broken into pieces but the total
  complexity stayed the same or increased. The score dropped because individual
  functions are smaller, not because the code got simpler.
- **scope-escape**: Code disappeared from the analyzed target without a git
  deletion. It was likely moved to escape scoring.
- **hollow-coverage**: New test files contain zero assertions. They inflate
  line coverage without verifying behavior.
- **scope-narrowing**: The target path changed between the baseline snapshot
  and the current run. Score comparison across scopes is misleading.

After a clean commit, take a fresh snapshot for the next iteration:

```bash
python3 scripts/delta_audit.py snapshot {target} --languages {languages} -o /tmp/crap-baseline.json
```

### 5. Commit stable progress

Use the `commit` skill after each meaningful stable batch, not only at the very
end. Good commit points:

- coverage target bootstrap
- one hotspot slice
- one multi-file fixture + test slice

Do not mix unrelated dirty files into those commits.

### 6. Continue or stop

Continue while all are true:

- the score is still above threshold
- the last slice materially improved the score or removed a real hotspot
- the remaining work still looks incremental rather than architectural

Stop when any of these becomes true:

- scoped `FINAL_SCORE` is below threshold
- two consecutive iterations fail to produce a meaningful drop
- the remaining hotspot requires broad refactor rather than a bounded slice
- coverage cannot be trusted because the generating suite is too broken
- the remaining failures are unrelated and should become a separate slice

## Reporting Format

For each loop close-out, report:

- scope label
- threshold
- baseline score
- current score
- top moved hotspots
- commits made
- blocker, if any
- explicit next slice if the threshold is not met

## Practical Heuristics

- Favor small isolated functions with low direct coverage and deterministic
  dependencies.
- Fix the measurement before chasing inflated hotspots.
- If a failing suite already clusters around a hotspot, stabilizing that suite
  can be higher value than chasing the raw highest CRAP number.
- `FINAL_SCORE < 30` is a good mutation hand-off point; `FINAL_SCORE < 8` is a
  strong healthy end-state for stabilized hotspots.
- Treat `FINAL_SCORE` as “worst current hotspot,” not a repo average.
