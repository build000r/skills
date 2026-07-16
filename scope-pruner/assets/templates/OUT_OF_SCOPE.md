# Out of Scope

Deliberate scope decisions for this project. Agents and contributors: read
this before adding any feature. Compare your proposed work's **user capability
and loop** against each entry's `Forbidden intent` and `Also covers` — not
against entry titles. Do not implement listed capabilities — or close
equivalents — without explicit operator approval. When in doubt, ask first.

**Reopening rule (never-auto-unpark):** a met `Revisit when` condition makes
an entry *eligible for operator re-review* — it never unparks anything by
itself, and re-scoring alone never changes a standing decision. Returns to
scope require an operator-approved entry in the Decision Log citing new
evidence. PROVISIONAL entries may be freely re-analyzed, but their standing
verdict still changes only via operator approval.

Vision reference: see `VISION.md` (or the vision section of the README).

## Parked (out of scope for now)

<!-- One entry per parked capability. Keep each entry under ~12 lines. -->

### {Feature name}  `scope-{stable-id}`

- **Status**: PARKED {YYYY-MM-DD} (score {NNN}, top loss: {dimension},
  vision as of {date/commit})
- **Forbidden intent**: {one sentence: the user capability / parallel loop
  that is out of scope}
- **Also covers**: {2–5 equivalent framings an agent might rebuild this as,
  each tied to a vision non-goal}
- **Allowed adjacency**: {nearby work that remains legitimate — keeps this
  entry from blocking real work}
- **Search hints**: {advisory terms/route prefixes/dependency names for
  patrol; hints surface candidates, they never decide equivalence}
- **Revisit when**: {an observable condition — "3+ paying users request it",
  "core-loop retention > X" — never "when we have time"}
- **Existing code**: {none | path(s), left in place | removed}

## Cut (removed or scheduled for removal)

### {Feature name}  `scope-{stable-id}`

- **Status**: CUT {YYYY-MM-DD}, approved by {operator} (score {NNN}, top
  loss: {dimension}, vision as of {date/commit})
- **Forbidden intent**: {one sentence}
- **Also covers**: {equivalent capability classes, each tied to a non-goal}
- **Why cut**: {largest loss contributor from the scope-pruner run}
- **Removal**: {commit/PR link, `attic/{feature}` branch, or deprecation plan
  when disposition risk is high}
- **Do not rebuild unless**: {condition, or "the vision changes"}

## Decision Log

<!-- Append-only. One line per scope decision, newest first. Includes patrol
     runs and operator-approved reopens. -->

- {YYYY-MM-DD}: {scope-id} → {PARK|CUT|REOPENED|promoted to non-goal #N},
  score {NNN} ({top-loss dim}), {one-line reason / new evidence}
- {YYYY-MM-DD}: patrol run, {N} candidate matches, {M} new surfaces triaged
