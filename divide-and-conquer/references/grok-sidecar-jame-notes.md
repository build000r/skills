# Sidecar review lessons for Jame

Use alongside [task selection](grok-sidecar-selection.md) when the selected route
permits Grok. An all-Codex instruction applies here too. These are reusable
review rules, not a current capability benchmark or a mandate to add a sidecar.

## Choose a bounded question

Read-only inventories and narrow lifecycle reviews can reduce the lead's search
space. Name the files or inline the relevant excerpt, request one falsifiable
finding, and require the guard or failing path plus an appropriate validation
command. Examples include panic-site enumeration, error-path cleanup, and a
single low-risk simplification. A named command with a concise result summary
is also suitable when its execution is already authorized.

Broad opportunity searches require repository context and judgment; use the
selected implementation/review lane. Repeated empty output or turn-budget
exhaustion is evidence to reroute, not a reason to keep raising the turn cap.
Require relevant output in the response; no separate result file is necessary.

## Preserve correctness and write ownership

- Keep DSP correctness, real-time allocation constraints, FFI/ABI safety,
  native/Wasm parity, and changes with cascading golden updates in the owning
  implementation lane with domain-appropriate independent review.
- Before running repository helpers, inspect their current side effects. A
  helper that stashes the entire tree or formats unrelated files is unsafe
  while another writer owns those changes. Never delegate broad stash,
  formatting, or staging operations across concurrent write scopes.
- Use disjoint named paths in the existing checkout where the workflow permits.
  Do not create a worktree merely because a sidecar is present. Commit execution
  follows the explicit scope and staging checks in task selection.
- Treat a proposed patch as a lead. Compile and run the relevant lint/test checks;
  a plausible simplification may violate local conventions or alter evaluation
  order, cleanup, or error precedence.
- Keep model-based tests independent from the implementation they check. Sharing
  the production decision helper with the test oracle can hide the same defect
  on both sides; test-only helper extraction is safer when behavior is unchanged.

## Verify audit claims

For a panic audit, ask for exact source locations and the bound, constructor
validation, or other guard behind each conclusion. For lifecycle work, check
resource cleanup on error paths, shutdown ordering, and preservation of the
original error. Protect audio callbacks and buffer recycling from incidental
refactors.

A negative audit narrows the search; it is not proof that no defect exists.
Spot-check important guards and compare with required tests or independent
review before accepting the conclusion. Historical results do not certify the
current source or model version.

## Recover prior evidence when needed

Exact trials, commits, and transcripts remain in their existing session history.
Use the canonical Cass frontdoor when a current decision needs that evidence:

```bash
sbp cass search "Jame sidecar panic-site audit" --limit 10
sbp cass search "Jame sidecar lifecycle cleanup" --limit 10
sbp cass search "Jame sidecar independent test oracle" --limit 10
```

Update this reference only with a reviewed reusable rule. Do not append verdict
logs, session narratives, commit lists, or invocation histories.
