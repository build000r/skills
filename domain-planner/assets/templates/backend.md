# {slice_name} Backend Spec

> Business rules, permissions, and edge cases. See [schema.mmd](./schema.mmd) for entity relationships.
> Implementation details (file structure, framework patterns, migration format) are the scaffolder's job.

---

## Business Rules

### Rule 1: [Name]

**When:** [Trigger condition]
**Then:** [What happens]
**Edge cases:**
- [Edge case 1] → [Expected behavior]
- [Edge case 2] → [Expected behavior]

---

## Permissions & Access Control

### Who can do what

| Action | Owner | Other Users | Admin |
|--------|-------|-------------|-------|
| Create | Yes | No | Yes |
| Read | Yes | No | Yes |
| Update | Yes | No | Yes |
| Delete | Yes | No | Yes |

### Access Control Strategy

- [{slice_name}]: Owner-only (owner_id matches auth context)
- [Other table]: [Strategy]

---

## Algorithms / Complex Logic

### [Algorithm Name]

[Prose description — no code]

**Inputs:** [What data]
**Output:** [What result]
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

---

## Dependencies

- [Dependency 1] — [How this slice uses it]
- [Dependency 2] — [How this slice uses it]

---

## Edge Cases & Error Scenarios

| Scenario | Expected Behavior |
|----------|------------------|
| [Duplicate name for same owner] | [409 ALREADY_EXISTS] |
| [Referenced entity deleted] | [Cascade or orphan?] |
| [Concurrent edits] | [Last-write-wins or conflict?] |

---

## Production DB Transition (Only if Data-Impacting)

> Keep separate from API planning. Fill only when this slice changes existing production data.

### Transition Checklist

- [ ] Pre-change backup/snapshot is defined
- [ ] Raw SQL execution plan via `psql` is defined
- [ ] Script is safe to re-run (idempotent guards)
- [ ] Transaction/preview plan is defined (explicit `BEGIN`/`COMMIT` with verification queries before commit)
- [ ] Rollback SQL or restore path is defined
- [ ] Post-migration verification queries are defined

---

## Performance Envelope Implementation Rules

> Required when mode defines latency/throughput/backpressure targets.

### Runtime Constraints

- No blocking operations in request/stream hot paths.
- Bounded channels and bounded replay/output buffers.
- Overload behavior is explicit (reject/drop/backoff) and mapped to contract error codes.

### Observability Requirements

- Queue depth metrics
- Drop/rejection counters
- Latency metrics required by mode SLOs (for example p95/p99)

### Verification Scenarios

- [ ] Slow consumer under sustained output
- [ ] Queue saturation and overload handling
- [ ] Replay truncation behavior on reconnect

---

## Test Focus Areas

- [ ] [Business rule 1] — especially edge cases
- [ ] [Permission boundary] — cross-user access denied
- [ ] [Algorithm] — correctness with varied inputs
- [ ] All endpoints from shared.md contract

---

## Implementation Notes

**Use the domain-scaffolder skill with `surface=backend` to generate code from this spec.**
