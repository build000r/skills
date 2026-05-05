# Task Decomposition Patterns

## Safe Split Patterns

These patterns produce workgraph nodes that are safe to execute in swarm waves:

### 1. Concern-Disjoint Split

Each node owns a distinct domain or concern. Workers discover which files are
relevant, but ownership is verified through `writes`.

```text
WG-001: Handle authentication - token refresh, session management
WG-002: Handle billing - payment processing, invoicing
WG-003: Handle notifications - email templates, delivery logic
```

Conflict check verifies these concerns do not overlap in writes, but prompts
stay goal-focused.

### 2. Research + Single Writer

Multiple read-only nodes gather context, one writer node executes after they
finish.

```text
WG-001: Research how auth is implemented across the codebase      writes: []
WG-002: Research how the test framework is configured             writes: []
WG-003: Implement the auth change using the research findings     writes: src/auth/** tests/**
```

`WG-003` must run after `WG-001` and `WG-002`. If the writer depends on the
research findings, they are not the same wave.

### 3. Layer-Disjoint Split

Each node works in a separate architectural layer.

```text
WG-001: Implement the API endpoint for user preferences           writes: server/api/**
WG-002: Build the frontend component to edit preferences          writes: web/components/**
WG-003: Add the migration for the preferences table              writes: db/migrations/**
```

Safe only if the layers do not share files. Conflict check must verify this.

### 4. Independent Investigation Split

Each node investigates a different hypothesis or area. All are read-only.

```text
WG-001: Check if the bug is in the API layer                     writes: []
WG-002: Check if the bug is in the database queries              writes: []
WG-003: Check if the bug is in the frontend state management     writes: []
```

All three can launch in one wave. Results are collected, then the graph is
updated before any writer is launched.

### 5. Workgraph Frontier Split

When `WORKGRAPH.md` exists, split only the current ready frontier instead of
re-deriving the entire plan.

```text
WG-001 backend API       writes: backend/domain/**         status: ready
WG-002 migration         writes: backend/migrations/**     status: ready
WG-003 frontend widget   writes: frontend/widgets/**       status: blocked on WG-001
```

Safe first wave:
- `WG-001`
- `WG-002`

Do not launch `WG-003` until `WG-001` is done and independently validated.

## Unsafe Patterns (Do NOT Split)

### Same-File Edits

Two nodes editing the same file will race.

```text
BAD:
WG-001: Add function to utils.ts
WG-002: Modify existing function in utils.ts
```

### Dependent Chain In The Same Wave

Node B needs Node A's output to know what to do.

```text
BAD:
WG-001: Figure out the correct API schema
WG-002: Implement the API endpoint using that schema
```

### Shared Runtime State

Nodes modify resources that interact too tightly at runtime.

```text
BAD:
WG-001: Modify the database schema
WG-002: Modify queries that use that schema
```

### Discovery-Then-Act In Parallel

Cannot parallelize when the action depends on what is discovered.

```text
BAD:
WG-001: Find all files that import the old module
WG-002: Update all files that import the old module
```

## Decomposition Checklist

Before finalizing a graph, verify:

- [ ] Each node is scoped by concern or goal, not by micro-file edits
- [ ] No two nodes' `writes` overlap
- [ ] No node needs another node's output to begin unless the dependency is explicit
- [ ] Each node has all context it needs in its prompt
- [ ] Read-only nodes declare empty writes
- [ ] Writer nodes own concrete write scopes
- [ ] Explicit Codex model selection uses `gpt-5.5`, with reasoning chosen from `medium|high|xhigh`
- [ ] The whole ready frontier can launch in one wave without conflict
- [ ] The orchestrator can independently validate each node after collection
- [ ] Recombining results requires no merge arbitration

## Sizing Nodes

- Too granular: 10 nodes each doing one tiny thing; orchestration overhead wins
- Too coarse: 1 node doing everything; parallelism disappears
- Sweet spot: 2-5 meaningful execution nodes, sometimes plus read-only research nodes
- Read-only nodes: can be more numerous, but still need crisp output contracts
- Writer nodes: fewer is better to minimize overlap and integration risk
