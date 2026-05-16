# Calibration Prompts

Use these prompts to discover explanation preference without forcing the user
through a long questionnaire.

Use `ask-cascade` for ordering: each round should depend on the answer before
it unless the questions are genuinely independent. Use `mmdx` only when the
answers form a map worth preserving, such as multiple interacting style axes or
a preference tree the user will revisit.

## Round 1: Root Style Fork

Ask this first unless the user already provided a clear style example.

```text
Root decision: what should an explanation optimize for first?

1. Crux first (recommended)
   Why: it gives the core mechanism or decision before examples and caveats.
   Happy path:
   - one-sentence crux
   - minimal mental model
   - concrete example
   - common misunderstanding
   - practical implication
2. Example first
3. Map first
4. Failure first

Reply with 1, 2, 3, 4, or give a better starting point.
```

## Round 2: Completion Axis

Ask after Round 1:

```text
What makes the explanation feel complete?

1. Mechanism: I understand what causes what.
2. Boundary: I understand where it applies and where it breaks.
3. Operation: I understand what to do next.
4. Judgment: I understand how to evaluate whether it is good or risky.
```

## Round 3: Example Type

Ask after the completion axis:

```text
Which example type helps most?

1. Tiny toy example.
2. Real example from the current task.
3. Analogy to a familiar domain.
4. Counterexample that shows what this is not.
```

## Round 4: Compression

Ask only if length preference is not obvious:

```text
Default length?

1. 5 lines.
2. 2 short paragraphs.
3. Bulleted mini-brief.
4. Full walkthrough.
```

## Round 5: Checkpoint Cadence

Ask only when the user will act on the explanation:

```text
When should I pause for your input?

1. Only when the next action depends on private preference.
2. Before committing to a plan.
3. Before deep detail.
4. Rarely; explain first, then let me correct.
```

## Optional MMDX Map Check

Ask only after the preference card exists:

```text
Would a small MMDX map help preserve this, or is the preference card enough?

1. Preference card only.
2. Add a private MMDX map of the style axes.
3. Add a private MMDX decision tree for when to ask vs explain first.
```

Default to option 1 unless the user asks for a visual map or the preference has
multiple branches that will be hard to remember as prose.

## Diagnostic Mini-Examples

Use these if the user is choosing abstractly.

### Crux First

```text
A cache is shortcut memory. The hard part is deciding when the shortcut is
still true. Most cache bugs are stale-truth bugs, not storage bugs.
```

### Example First

```text
If you check a weather app every minute, you can instead remember the last
answer for five minutes. That remembered answer is the cache.
```

### Map First

```text
There are three pieces: the caller, the cache, and the source of truth. The
caller asks the cache first. The cache either answers or asks the source.
```

### Failure First

```text
Caching goes wrong when the saved answer outlives the truth. You think you are
making the system faster, but you are serving old information.
```
