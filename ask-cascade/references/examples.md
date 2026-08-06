# Examples

## Dependent Questions

Unknowns: whether caching should exist, backend, and TTL.

```text
Round 1: Should this path use a cache?
[human chooses yes]
Round 2: Which backend fits the confirmed constraints?
[human chooses Redis]
Round 3: What freshness/TTL policy matches the product requirement?
```

Backend and TTL never appear in round 1 because the first answer can remove or reframe them. Recompute after each answer.

## Coherent Independent Frontier

When prerequisites are settled, license, CI inclusion, and supported Node version may share one structured round if none changes the others in this project. Each question still carries a recommendation and consequence. If answering them requires unrelated mental frames, split into smaller coherent rounds.

## Branch Preview

```text
Root decision: where this capability should live.

1. Extend the existing module (recommended)
   Why: it preserves the current ownership boundary and avoids migration work.
   1A. Keep the current data model
   1B. Add a submodule under the same domain
   Likely next decisions: public entry point, tests, migration impact.
2. Create a sibling module
3. Extract a shared package

[Structured question: choose 1, 1A, 1B, 2, 3, or provide a different direction.]
```

Only the recommended branch receives subvariants, and the preview stops before speculative detail.

## Advisory Tool Versus Consent

A duel strongly recommends extracting a package. Use that result as the recommended option and explain the tradeoff. If package boundaries remain a human-owned scope choice, ask the human; the duel does not authorize extraction.

## Delegated Implementation Choice

The architecture is approved and local details are delegated. Choose a reversible helper name that matches repository convention, report it, and continue without a checkpoint.

## Ordinary Unblock Versus Deliberate Session

- During authorized implementation, resolve two dependent blockers and continue. No final shared-understanding question.
- During “grill me until the design is complete,” keep recomputing until the agreed frontier is empty, summarize decisions and residual assumptions, and require confirmation before implementation.

## Stale Branch Elimination

If the human declines caching, delete backend and TTL from the graph. Never continue because they appeared in the original question list.

## Pure Preference

```text
No objective recommendation: both treatments meet the stated constraints, so this is a visual taste decision. A is quieter; B creates stronger hierarchy.
```

Then present the grounded options through the visual picker and structured question tool.

## Failure Patterns

- Asking which package manager is used when a lockfile settles it.
- Letting an invoking agent answer product, priority, risk, or taste questions for the human.
- Batching cache existence, backend, and TTL in one round.
- Recommending an option without a rationale.
- Treating research, a prototype, or a duel as consent.
- Requiring a shared-understanding checkpoint after a routine clarification.
- Continuing through an eliminated branch or stopping because a numeric question limit was reached.
