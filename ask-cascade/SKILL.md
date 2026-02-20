---
name: ask-cascade
type: utility
description: |
  Enforce hierarchical, dependency-aware question ordering when using AskUserQuestion.
  High-level decisions first, detail questions only after strategic choices are settled.

  **Proactive triggers** - activate when:
  - About to call AskUserQuestion with 2+ questions
  - Gathering requirements, preferences, or implementation decisions from the user
  - Planning work that requires multiple user inputs
  - Using EnterPlanMode or AskUserQuestion during any skill/workflow

  **Explicit triggers** - "ask cascade", "question order", "ask strategy"
---

# Ask Cascade

## The Rule

Questions flow top-down: **highest-impact decisions first**, then details that depend on those answers. Never present questions where one answer could change, nullify, or reframe another.

## Before Every AskUserQuestion Call

Classify each question you're about to ask:

1. **Strategic** — Changes scope, approach, or whether other questions even apply
2. **Tactical** — Implementation detail that only matters after a strategic choice is made
3. **Independent** — Answer doesn't affect any other question

Then apply these rules:

### Rule 1: Strategic Questions Go First, Alone

If you have a strategic question whose answer could change downstream questions, ask it **by itself** (or with other independent questions). Wait for the answer before formulating tactical follow-ups.

**Bad:**
```
Q1: "Should we add caching?" (strategic)
Q2: "Redis or Memcached?" (tactical — depends on Q1)
Q3: "What TTL?" (tactical — depends on Q1 AND Q2)
```

**Good:**
```
Round 1: "Should we add caching?" (strategic)
[user answers yes]
Round 2: "Redis or Memcached?" (tactical, now relevant)
[user answers Redis]
Round 3: "What TTL?" (now has full context)
```

### Rule 2: Independent Questions Can Batch

Questions with no dependency between them should be batched for efficiency.

**Good batch:**
```
Q1: "Which license: MIT or Apache?" (independent)
Q2: "Include CI/CD config?" (independent)
Q3: "Target Node version?" (independent)
```

All three are safe to ask together — no answer changes another question.

### Rule 3: Test Each Batch

Before sending a batch, for each pair of questions ask: *"If the user answered Q1 differently, would I reword or remove Q2?"*

- **Yes** → Split them. Ask Q1 first.
- **No** → Safe to batch.

### Rule 4: Re-evaluate After Each Answer

After receiving answers to a round of questions, reassess what you still need to ask. A strategic answer may:

- Eliminate questions entirely (user chose a path that makes them irrelevant)
- Spawn new questions you hadn't considered
- Change the framing of a follow-up

Don't ask stale questions from a pre-planned list.

## Examples

### Skill creation
```
Round 1: "What does this skill do?" (strategic — defines everything)
[user answers]
Round 2 (batch): "Hook, skill, or CLAUDE.md?" + "Always-on or manual trigger?" (independent of each other, both depend on Round 1)
[user answers]
Round 3: Detail questions specific to the chosen form
```

### Feature implementation
```
Round 1: "New feature, refactor, or bug fix?" (strategic)
[user: new feature]
Round 2: "Which module does this belong in?" (strategic — affects file structure)
[user: auth module]
Round 3 (batch): "OAuth or JWT?" + "Need refresh tokens?" (independent, both scoped to auth)
```

### Bad pattern to avoid
```
Q1: "What language?"
Q2: "What test framework?"  ← depends on Q1!
Q3: "What package manager?" ← depends on Q1!
Q4: "Tab width?"            ← independent, safe to batch with Q1
```
