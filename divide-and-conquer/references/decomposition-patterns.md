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

When the slice's `br` epic exists, split only the current ready frontier
(`br_helpers.py ready --label slice:{slug}`) instead of re-deriving the
entire plan.

```text
WG-001 backend API       writes: backend/domain/**         status: ready
WG-002 migration         writes: backend/migrations/**     status: ready
WG-003 frontend widget   writes: frontend/widgets/**       status: blocked on WG-001
```

Safe first wave:
- `WG-001`
- `WG-002`

Do not launch `WG-003` until `WG-001` is done and independently validated.

### 6. Subgoal Controller Split

For massive runs, split first by subgoal when each group can advance its own
ready frontier. A subgoal is represented by a controller issue plus
`slice:{root}`, `subgoal:{slug}`, and `subgoal-role:*` labels. The controller
owns the group-level write boundary, child-orchestrator assignment, run
directory, isolation mode, and status artifact.

Good subgoal boundaries:

```text
SUBGOAL auth       writes: backend/auth/**             leaves: auth tests, token flow
SUBGOAL billing    writes: backend/billing/**          leaves: invoice tests, qbo adapter
SUBGOAL docs       writes: docs/**                     leaves: README, migration guide
```

Safe when:
- every active subgoal has disjoint controller-level `writes`
- shared files are named in `shared_files:` and remain root-owned
- `br ready --label slice:{root} --label subgoal:{slug}` is proven to return
  only that subgoal's leaves, or helper-side AND filtering is used
- each child can validate its leaves without waiting on a sibling's output

The root can run several subgoal controllers at once in meta-lead multiplexing
mode, then escalate one controller to an NTM child orchestrator when its own
frontier is large enough to justify another lead.

### 7. Repo-Disjoint Workspace Split

When a root outcome spans multiple repositories, one subgoal per repo is often
the safest first split.

```text
SUBGOAL backend-api       repo: api        writes: api/**
SUBGOAL frontend-app      repo: web        writes: web/**
SUBGOAL mobile-client     repo: ios        writes: ios/**
```

Cross-repo integration, release validation, and shared public docs stay
root-owned unless they have their own explicit subgoal and write scope.

### 8. Read-Only Subgoal Fanout

Several subgoals can be read-only when the root needs broad discovery before
writer nodes are safe.

```text
SUBGOAL auth-inventory       writes: []
SUBGOAL billing-inventory    writes: []
SUBGOAL ui-inventory         writes: []
ROOT writer                  blocked on all inventories
```

Results feed back into Beads as tightened leaf nodes or controller updates. Do
not launch writer subgoals until the discovery outputs are reconciled.

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

### Shared Migration Or Generated Files Across Subgoals

Two subgoals that both need a shared migration, generated client, lockfile,
manifest, or central config are not independently launchable unless the shared
file is root-owned and sequenced.

```text
BAD:
SUBGOAL auth       writes: backend/auth/** backend/migrations/**
SUBGOAL billing    writes: backend/billing/** backend/migrations/**
```

Make the migration a root-owned leaf or a separate sequential subgoal.

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
- [ ] For subgoal mode, no two active controllers' `writes` overlap
- [ ] Subgoal leaves keep both `slice:{root}` and `subgoal:{slug}` labels
- [ ] Multi-label `br ready` behavior is proven to be AND semantics, or a
      helper applies AND filtering before dispatch
- [ ] No node needs another node's output to begin unless the dependency is explicit
- [ ] Each node has all context it needs in Beads fields/comments, and
      `br_helpers.py hydrate-node <id>` can expose it before dispatch
- [ ] Read-only nodes declare empty writes
- [ ] Writer nodes own concrete write scopes
- [ ] Cwd/workflow routing, skill-tag extraction, cleaned-request drafting, and
      broad read-only evidence bucketing are routed through the `voice-to-text`
      Grok dispatcher when that runtime is available
- [ ] Design-related nodes are routed to Claude Opus, including UI/UX,
      visual design, design-system, CSS/token, screenshot, and visual parity work
- [ ] Non-design execution nodes are routed to Codex `gpt-5.5`, with reasoning
      chosen from `medium|high|xhigh`
- [ ] Every node has an expected `BR_AGENT_NAME`, and the lead will verify
      `br show` reports `status=in_progress` plus that assignee before edits
      begin
- [ ] The whole ready frontier can launch in one wave without conflict
- [ ] In subgoal mode, the root accepts controller completion only after an
      independent convergence gate, not child self-report
- [ ] The orchestrator can independently validate each node after collection
- [ ] Recombining results requires no merge arbitration

## Sizing Nodes

- Too granular: 10 nodes each doing one tiny thing; orchestration overhead wins
- Too coarse: 1 node doing everything; parallelism disappears
- Sweet spot: 2-5 meaningful execution nodes, sometimes plus read-only research nodes
- Read-only nodes: can be more numerous, but still need crisp output contracts
- Writer nodes: fewer is better to minimize overlap and integration risk
- Subgoals: use them only when each controller is large enough to justify its
  own frontier. For small graphs, a normal wide frontier is cheaper and safer.
