# Failure Matrix

Canonical failure scenarios for agent-facing CLIs and the behavior an agent should observe.

## Exit Code Convention

| Code | Meaning |
|------|---------|
| 0 | Success (including already-done mutations) |
| 1 | User error — bad input, missing flag, not found |
| 2 | Upstream error — dependency failure, timeout, rate limit |
| 3 | Internal error — unexpected state, report-worthy bug |

## Scenario Table

| Scenario | Expected Behavior | Exit |
|----------|-------------------|------|
| Missing required flag | Fail fast, name the flag: "`--title` is required" | 1 |
| Invalid value | Fail fast, show valid range or options | 1 |
| Resource not found | "not found: `<id>`", no stack trace | 1 |
| Ambiguous identifier | List matches, ask agent to narrow: "3 matches for `foo` — use full id" | 1 |
| Already-done mutation | Treat as success, return current state: "already closed" | 0 |
| Empty result set | "0 items" or "0 `<noun>`", never blank output | 0 |
| Permission denied | Name the permission needed and where to get it | 1 |
| Upstream dependency error | Translate into wrapper vocabulary, include upstream status if useful | 2 |
| Upstream timeout | Report timeout, suggest retry or `--timeout` flag if available | 2 |
| Rate limited | Report limit, include wait duration if the upstream provides it | 2 |
| Upstream returns unexpected shape | "unexpected response from `<dep>`", don't dump raw payload | 2 |
| Lock held by another process | "locked by pid `<N>`, retry in `<T>`s" — not a crash | 2 |
| Internal/unexpected error | Generic message + "report this" hint, no stack dump on stdout | 3 |

## Design Rules

- **Fail fast**: validate input before calling upstream. A typo should not cost a network round trip.
- **Translate errors**: the agent should never see raw dependency stderr or HTTP status codes as the primary message. Wrap them.
- **Stable codes**: exit codes are part of the contract. Don't change them without a version bump.
- **Actionable messages**: every error should tell the agent what to do next, not just what went wrong.
- **No stack traces on stdout**: if you need them for debugging, put them behind `--verbose` or write to stderr.
