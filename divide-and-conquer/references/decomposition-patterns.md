# Task Decomposition Patterns

## Safe Split Patterns

These patterns produce agents that are guaranteed conflict-free:

### 1. File-Disjoint Split
Each agent owns a distinct set of files. No two agents touch the same file.

```
Agent A: Modify src/auth.ts, src/auth.test.ts
Agent B: Modify src/billing.ts, src/billing.test.ts
Agent C: Modify src/notifications.ts, src/notifications.test.ts
```

### 2. Explore + Single Writer
Multiple Explore agents (physically read-only) gather context, one general-purpose agent writes.

```
Agent A (Explore, haiku): Research how auth is implemented across the codebase
Agent B (Explore, haiku): Research how the test framework is configured
Agent C (general-purpose, sonnet): Implement the change (uses findings from A and B)
```

Note: Agent C must run AFTER A and B complete. Use this only when A/B are
research-only and C is the sole implementor. If C depends on A/B findings,
they cannot all be parallel — launch A+B together, then C after they return.
Since C is general-purpose, it sees the full conversation including A/B results.

### 3. Domain-Disjoint Split
Each agent works in a completely separate domain/layer.

```
Agent A: Backend API endpoint (server/)
Agent B: Frontend component (client/)
Agent C: Database migration (migrations/)
```

Caution: Only safe if domains don't share files (e.g., shared types file).

### 4. Independent Investigation Split
Each agent investigates a different hypothesis or area. All Explore type (cannot write).

```
Agent A (Explore, haiku): Check if the bug is in the API layer
Agent B (Explore, haiku): Check if the bug is in the database queries
Agent C (Explore, haiku): Check if the bug is in the frontend state management
```

All three launch in a single message. Results reviewed by orchestrator to determine root cause.

## Unsafe Patterns (Do NOT Split)

### Same-File Edits
Two agents editing the same file will cause race conditions.

```
BAD:
Agent A: Add function to utils.ts
Agent B: Modify existing function in utils.ts
```

### Dependent Chain
Agent B needs Agent A's output to know what to do.

```
BAD:
Agent A: Figure out the correct API schema
Agent B: Implement the API endpoint using that schema
```

### Shared State
Agents modify resources that interact at runtime.

```
BAD:
Agent A: Modify the database schema
Agent B: Modify queries that use that schema
```

### Discovery-Then-Act
Can't parallelize when the action depends on what's discovered.

```
BAD:
Agent A: Find all files that import the old module
Agent B: Update all files that import the old module
```

## Decomposition Checklist

Before finalizing a split, verify:

- [ ] No two agents write to the same file
- [ ] No agent needs another agent's output to begin work
- [ ] Each agent has all context it needs in its prompt (or is general-purpose and can reference conversation)
- [ ] File ownership boundaries are explicit and non-overlapping
- [ ] Research agents use Explore type (physically cannot write)
- [ ] Write agents use general-purpose type
- [ ] Command-only agents use Bash type
- [ ] Model is haiku for simple research, sonnet/opus for complex work
- [ ] All parallel agents are launched in a single message
- [ ] The orchestrator can review each agent's work independently
- [ ] Recombining results requires no conflict resolution

## Sizing Agents

- **Too granular**: 10 agents each doing one tiny thing = overhead > benefit
- **Too coarse**: 1 agent doing everything = no parallelism
- **Sweet spot**: 2-5 agents, each with a meaningful chunk of work
- **Research agents**: Can be more numerous since Explore type is read-only and haiku model is cheap
- **Implementation agents**: Fewer is better to minimize conflict risk
