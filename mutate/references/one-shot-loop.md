# One-Shot Mutation Loop

Use this when the user explicitly wants execution, not just adapter selection.

Examples:

- `/mutate`
- `run mutation testing on this file`
- `kill the survivors`
- `harden this hotspot`

## Goal

Run a bounded loop on one narrowed scope:

1. establish a trustworthy baseline
2. run a narrow mutation pass
3. normalize the results into the ledger
4. triage survivors
5. add stronger tests or small refactors
6. rerun the same mutation scope
7. if this came from `crap`, rerun `crap` on the same scope
8. stop when the remaining survivors are either justified exclusions or a
   separate design slice

## Loop

### 1. Baseline

- Resolve scope first: file, module, or package.
- Pick the adapter from
  [adapter-matrix.md](adapter-matrix.md).
- Run the canonical baseline test command for that scope.
- Stop if the baseline is red or flaky.

### 2. First mutation pass

- Use the narrowest adapter filter the tool supports.
- Keep the command repo-native where possible.
- Capture:
  - killed mutants
  - surviving mutants
  - no coverage, timeout, or incompetent/equivalent-style buckets

### 2.5 Normalize the backlog

After the first mutation pass:

- run `python3 scripts/analyze_mutants.py {target} --write-ledger --top 20`
- treat `.mutate/ledger.json` as the durable backlog snapshot for the current
  scope
- preserve any existing `review_status` and `note` fields instead of wiping them

### 3. Survivor triage

For each survivor, classify it before editing code:

- missing assertion
- missing scenario or input boundary
- indirect coverage without direct tests
- equivalent or acceptable exclusion
- tooling noise or timeout

Prefer test improvements first. Exclude only when the mutant is low-value and
the exclusion can be stated precisely.

### 4. Patch and rerun

After each coherent batch:

- rerun the baseline test path
- rerun the same mutation command
- rerun `python3 scripts/analyze_mutants.py {target} --write-ledger --top 20`
- if this work came from `crap`, rerun `crap` on the same scope

Record:

- previous survivors
- current survivors
- exclusions added
- whether CRAP moved on rerun

### 5. Continue or stop

Continue while all are true:

- real survivors remain
- the remaining work still looks like bounded test hardening
- runtime is still acceptable for the current scope

Stop when any is true:

- no high-value survivors remain
- two consecutive reruns leave only equivalent or noise buckets
- the next step is a broader design refactor rather than test hardening
- the baseline becomes too flaky to trust

## Reporting Format

For each close-out, report:

- scope
- adapter
- baseline status
- survivors before and after
- exclusions added
- CRAP delta, if rerun
- next slice or blocker
