# Private Eli-Me Skill Template

Use this as the starting point for the generated private `eli-me/SKILL.md`.
Replace bracketed placeholders with the user's calibrated preferences.

```markdown
---
name: eli-me
description: >-
  Apply the user's preferred explanation style. Use when the user says "eli-me",
  "/eli-me", "$eli-me", "explain this my way", "break this down to my
  preference", or corrects the agent's explanation style.
depends_on:
  - ask-cascade
---

# Eli Me

Use this skill to explain things in the user's preferred style. This skill is
private because it may contain personal communication preferences and examples.

## First Progress Marker

Start with the exact prefix:

`Using eli-me`

## Eli-Me Preference Card

Default explanation shape:
- Start with: [crux | example | map | failure]
- Then show: [mechanism | boundary | operation | judgment]
- Then prove: [source | toy example | real example | counterexample]
- Then ask: [checkpoint rule]

Definition preference:
- Preferred: [what makes a definition land]
- Avoid: [dictionary-only, analogy-only, overlong preface, etc.]

Examples:
- Use: [preferred example type]
- Avoid: [example type or framing to avoid]

Question cadence:
- Ask before explaining when: [condition]
- Explain first when: [condition]

Compression:
- Default: [length/shape]
- Expand when: [trigger]

## Explanation Recipe

Unless the preference card says otherwise:

1. State the crux in one sentence.
2. Give the minimum mental model.
3. Show one concrete example.
4. Name what people usually get wrong.
5. State the practical implication or next move.
6. Ask at most one check question, only when the next action depends on it.

## Updating The Preference

When the user corrects the explanation style:

1. Treat the correction as preference evidence.
2. Apply it immediately in the current answer.
3. If the correction should persist, patch this private skill after the answer
   or ask before writing if the target location is unclear.

## Required Closeout

For calibration or update runs, verify:

- The answer used the current preference card.
- Any new preference was added to the smallest relevant section.
- No public file received private preference content.
```
