# State Model

`scripts/analyze_mutants.py` normalizes tool-native mutation artifacts into one
repo-owned backlog and can write that snapshot to `.mutate/ledger.json`.

## Canonical Statuses

Active todo statuses:

- `survived`
- `no_coverage`
- `no_tests`
- `timeout`
- `suspicious`
- `not_checked`
- `compile_error`
- `segfault`
- `type_check`
- `deferred`

Adapter nuance:

- `cargo-mutants` `Unviable` artifacts normalize to `ignored` because they are
  invalid/generated mutants rather than surviving test gaps.

Closed statuses:

- `killed`
- `skipped`
- `ignored`
- `equivalent`
- `resolved`

## Ledger Fields

Top-level shape:

```json
{
  "version": 1,
  "generated_at": "2026-03-16T00:00:00+00:00",
  "repo_root": "/abs/path/to/repo",
  "summary": {
    "total": 12,
    "todo": 5,
    "status_counts": {
      "survived": 3,
      "timeout": 1,
      "killed": 8
    }
  },
  "sources": ["mutants/src/foo.py.meta"],
  "mutants": []
}
```

Per-mutant fields:

- `key`: stable normalized identifier
- `adapter`: `cargo-mutants`, `mutmut`, or `stryker`
- `status`: tool-native status mapped into the canonical set
- `effective_status`: `status` after applying any review override
- `todo`: whether this mutant is still backlog work
- `path`: repo-relative source file when known
- `symbol`: function or method when known
- `line`: source line when known
- `raw_id`: tool-native mutant identifier when available
- `detail`: free-text detail from the adapter
- `source`: repo-relative artifact file that produced the record
- `review_status`: optional manual override
- `note`: optional manual note
- `first_seen`: preserved across reruns
- `last_seen`: updated on each ledger write

## Manual Review Overrides

The analyzer preserves these optional manual fields from an existing ledger when
the `key` is stable across reruns:

- `review_status`
- `note`
- `first_seen`

Recommended `review_status` values:

- `equivalent`
- `ignored`
- `resolved`
- `deferred`

`equivalent`, `ignored`, and `resolved` close the backlog item. `deferred`
keeps it active but makes the intent explicit.
