---
name: ask-cascade
type: utility
description: Enforce hierarchical, dependency-aware question ordering for AskUserQuestion and other user-facing clarification steps. Use for gathering requirements, asking 2+ dependent questions, framing decision trees, or surfacing strategic branches before detail questions.
---

# Ask Cascade

## Default Marker

Start with a stable first progress message such as:

`Using \`ask-cascade\` to frame the next highest-impact decision before I ask follow-ups.`

## The Rule

Questions flow top-down: **highest-impact decisions first**, then details that depend on those answers. Never present questions where one answer could change, nullify, or reframe another.

When the top strategic fork is concrete enough to name, do not ask a naked abstract question first. Show the fork, recommend a starting branch, and let the user recalibrate before deeper questions.

## Before Every AskUserQuestion Call

Classify each question or branch you are considering:

1. **Strategic** — Changes scope, approach, or whether other questions even apply
2. **Tactical** — Implementation detail that only matters after a strategic choice is made
3. **Independent** — Answer doesn't affect any other question
4. **Branch preview candidate** — A strategic fork with 2-4 plausible branches you can name from the available context

Then apply these rules:

### Rule 1: Strategic Questions Go First, Alone

If you have a strategic question whose answer could change downstream questions, ask it **by itself** or with other truly independent questions. Wait for the answer before formulating tactical follow-ups.

**Bad:**
```text
Q1: "Should we add caching?" (strategic)
Q2: "Redis or Memcached?" (tactical — depends on Q1)
Q3: "What TTL?" (tactical — depends on Q1 AND Q2)
```

**Good:**
```text
Round 1: "Should we add caching?" (strategic)
[user answers yes]
Round 2: "Redis or Memcached?" (tactical, now relevant)
[user answers Redis]
Round 3: "What TTL?" (now has full context)
```

### Rule 2: Independent Questions Can Batch

Questions with no dependency between them should be batched for efficiency.

**Good batch:**
```text
Q1: "Which license: MIT or Apache?" (independent)
Q2: "Include CI/CD config?" (independent)
Q3: "Target Node version?" (independent)
```

All three are safe to ask together because no answer changes another.

### Rule 3: Test Each Batch

Before sending a batch, for each pair of questions ask:

`If the user answered Q1 differently, would I reword or remove Q2?`

- **Yes** → Split them. Ask Q1 first.
- **No** → Safe to batch.

### Rule 4: Re-evaluate After Each Answer

After receiving answers to a round of questions, reassess what you still need to ask. A strategic answer may:

- Eliminate questions entirely
- Spawn new questions you had not considered
- Change the framing of a follow-up

Do not ask stale questions from a pre-planned list.

### Rule 5: When The Fork Is Obvious, Show A Branch Preview

Use a branch preview when all of these are true:

- One strategic decision will change most downstream questions
- You can name 2-4 plausible branches from real context
- The user is likely to say "not that branch" unless you show the shape first

Format the preview like this:

1. State the root decision in plain language.
2. List numbered top-level options: `1`, `2`, `3`.
3. Mark one option as `recommended` and explain why in one sentence.
4. For the recommended option only, show subvariants as `1A`, `1B` when they materially change the next round.
5. Show a happy-path preview of at most 5 downstream nodes total.
6. End with one recalibration prompt: accept the recommendation, choose another number, or give a new starting point.

Guardrails:

- This is a recommendation, not a guessed user answer.
- Keep non-recommended branches brief. Do not print full trees for every option.
- If you cannot ground the options in the available context, ask the neutral strategic question instead.
- If the user already picked a branch, do not repackage it as a menu.
- If the branch involves legal, financial, security, or irreversible external action, call out the risk gate explicitly instead of burying it in the tree.
- Accept terse corrections like `2`, `1B`, or `none of these` as enough to re-anchor. Do not force the user to restate the whole problem.

## Compact Template

```text
Using `ask-cascade` to frame the next highest-impact fork.

Root decision: where this work should live.

1. Extend the existing module (recommended)
   Why: lowest migration cost and matches the current ownership boundary.
   1A. Keep the current data model
   1B. Add a new submodule under the same domain
   Happy path if we start here:
   - confirm module ownership
   - choose 1A or 1B
   - define the public entry point
   - decide tests and migration impact
2. Create a new sibling module
3. Extract a shared package

Reply with `1`, `2`, `3`, `1A`, `1B`, or give a better starting point.
```

## Examples

### Skill Creation With A Branch Preview

```text
Using `ask-cascade` to frame the first strategic fork.

Root decision: what form this reusable workflow should take.

1. Standalone skill (recommended)
   Why: the workflow is reusable, operator-invoked, and richer than a one-file note.
   1A. Manual trigger only
   1B. Manual trigger now, mode file later
   Happy path if we start here:
   - confirm this is a skill
   - choose 1A or 1B
   - define trigger phrases
   - decide bundled scripts or references
2. Hook
3. Project-local CLAUDE.md guidance only

Reply `1`, `2`, `3`, `1A`, `1B`, or give a new starting point.
```

### Feature Implementation Without A Branch Preview

```text
Round 1: "New feature, refactor, or bug fix?" (strategic)
[user: new feature]
Round 2: "Which module does this belong in?" (strategic)
[user: auth module]
Round 3: "OAuth or JWT?" + "Need refresh tokens?" (independent within the chosen module)
```

### Bad Pattern To Avoid

```text
Q1: "What language?"
Q2: "What test framework?"  ← depends on Q1
Q3: "What package manager?" ← depends on Q1
Q4: "Tab width?"            ← independent, safe to batch with Q1
```
