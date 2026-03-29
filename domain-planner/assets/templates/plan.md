# {slice_name} Plan

> Strategic coordination document for the {slice_name} domain slice.

---

## Business Value

<!-- One paragraph: What problem does this solve? Why now? -->

---

## User Stories

<!-- Parseable by Kanban UI. Use checkbox format. -->

- [ ] **{Role} can {action}** - {Benefit/outcome}
- [ ] **{Role} can {action}** - {Benefit/outcome}
- [ ] **{Role} can {action}** - {Benefit/outcome}

---

## Key Decisions

### Decision 1: [Topic]

**Options considered:**
- A) [Option A] - [Pros] / [Cons]
- B) [Option B] - [Pros] / [Cons]

**Decision:** [A or B]

**Rationale:** [Why this choice]

---

## Architecture Overview

```
                    ┌───────────────┐
                    │  {frontend}   │
                    │  (frontend)   │
                    └───────┬───────┘
                            │ API calls
                            ▼
                    ┌───────────────┐
                    │  {backend}    │
                    │  (backend)    │
                    └───────────────┘
```

<!-- Add domain-specific diagram -->

---

## Performance Envelope & Acceptance

> Required when the active mode defines performance targets.

| Target | SLO | Load Assumption | How Tested |
|--------|-----|-----------------|------------|
| [Keystroke echo / request latency] | [p95/p99 + unit] | [users/sessions/traffic shape] | [test or benchmark name] |
| [Dispatch/processing latency] | [p95/p99 + unit] | [load assumption] | [test/benchmark] |
| [Throughput/concurrency] | [target] | [assumption] | [test/benchmark] |
| [Memory/buffer bounds] | [bound] | [assumption] | [assertion/metric] |

**Hard Constraints:**
- [ ] No blocking operations on hot paths.
- [ ] Explicit backpressure and bounded queues/buffers.
- [ ] Push-first live updates (polling only degraded fallback).

---

## Delivery Strategy (Default: Big-Bang)

- [ ] **Big-bang target state** — implement the final contract directly; no dual endpoints or legacy compatibility layer unless explicitly requested.
- [ ] **No transition overhead by default** — avoid deprecation windows/parallel run paths unless user asks for them.

### Production DB Transition (Only if Data-Impacting)

> Fill this section only when existing production data must be changed.

- [ ] Backup/snapshot plan documented
- [ ] Raw `psql` migration plan documented (agent-run, not ORM magic)
- [ ] Preview/transaction safety plan documented (wrap in transaction, inspect affected row counts before commit)
- [ ] Idempotency guards documented
- [ ] Rollback plan documented and tested

---

## Out of Scope

- [ ] [Feature 1] - Deferred because: [reason]
- [ ] [Feature 2] - Deferred because: [reason]

---

## Open Questions

- [ ] [Question 1]
- [ ] [Question 2]

---

## Related Files

- [schema.mmd](./schema.mmd) - Entity relationships (SOURCE OF TRUTH)
- [flows.md](./flows.md) - User journeys and state transitions
- [shared.md](./shared.md) - API contract
- [backend.md](./backend.md) - Backend spec
- [frontend.md](./frontend.md) - Frontend spec
- [WORKGRAPH.md](./WORKGRAPH.md) - Post-sign-off execution handoff (created after plan acceptance)
