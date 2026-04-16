---
name: wiki-duel
description: Run /dueling-idea-wizards on a project or topic after first grounding the agents in the wiki. Thin wrapper that calls /wiki query to build a shared prior, then launches /dueling-idea-wizards with that prior baked into the study phase. Use for "wiki duel", "grounded duel", "duel with wiki context", "duel but check the wiki first", or when an adversarial brainstorm should start from accumulated wiki knowledge rather than a cold read of the repo.
---

# Wiki Duel

Ground the agents in the wiki first, then run a standard adversarial duel. Nothing more.

The wiki already contains synthesized concept pages, cross-references, and prior research about the project or topic. A cold `/dueling-idea-wizards` run skips all of that and makes both agents rediscover it from source. Wiki-duel removes that waste: both agents start from the same informed baseline, so the duel argues from the frontier instead of from first principles.

## When to Use

- You are about to run `/dueling-idea-wizards` on a project or topic that the wiki already covers.
- You want the duel to start from the wiki's accumulated synthesis, not a cold repo read.
- The user says "duel but ground in the wiki first", "wiki duel", or otherwise asks to chain the two skills.

## When NOT to Use

- No wiki coverage of the topic yet → run `/dueling-idea-wizards` directly, or `/wiki ingest` first.
- The goal is to deepen a concept inside the wiki itself → use `/wiki-forge`.
- The goal is just to answer a question from the wiki → use `/wiki query`.
- Simple ideation on an obvious project → plain `/dueling-idea-wizards` is enough.

## Contract

### Step 1 — Ground in the Wiki

Invoke the wiki skill in query mode against the duel topic:

> /wiki query {topic or project name} — what does the wiki already say about this? Surface the relevant concept pages, frameworks, cross-links, open tensions, and any focus-sweep lens currently active. Return a tight grounding brief suitable for seeding an adversarial duel.

Capture the brief. Do not edit the wiki during this step — this is a read-only grounding pass. If `/wiki query` produces a novel synthesis that would normally be filed back, note it but defer the write until after the duel so the grounding stays honest.

If the wiki has no coverage, stop and tell the user. Either ingest first or run a plain duel. Do not fabricate grounding.

### Step 2 — Launch the Duel with the Brief

Invoke `/dueling-idea-wizards`, passing the grounding brief as study context. Two acceptable shapes:

1. **Prepend the brief to the Phase 3 study prompt** so every agent reads the wiki synthesis before reading the repo. Keep the standard study prompt intact after the brief.
2. **Pass the brief via `--focus`** when the user wants the duel biased toward a specific angle the wiki already raised.

Prefer shape 1 by default. Use shape 2 only when the user has asked to focus the duel.

Then let `/dueling-idea-wizards` run its standard phases without modification. Do not override its scoring, reveal, or synthesis logic — wiki-duel's job ends once the grounding is injected.

## Output

Report:
- Which concept pages and sources the wiki grounding pulled from.
- How the brief was injected (prepended to study vs. `--focus`).
- The `/dueling-idea-wizards` report path it produced.
- Any wiki updates deferred from Step 1 that the user may want to file back now.

## Relationship to Other Skills

- **wiki**: provides the grounding brief via `/wiki query`. Wiki-duel does not write to the wiki.
- **dueling-idea-wizards**: does all the actual adversarial work. Wiki-duel only feeds its study phase.
- **wiki-forge**: the inverse shape — forge picks a concept inside the wiki and files findings back; wiki-duel points the duel outward at a project and leaves the wiki untouched.
