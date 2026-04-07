# Extraction Recipe

How to collapse an upstream subgraph into the smallest faithful port.

Apply these passes in order. Each pass deletes code; none add it.

## Pass 1 — Pin the behavior in one sentence

Write a single sentence that names the input, the output, and the property
the user actually cares about. If you cannot, the scope is still too vague
and the port will bloat to cover the ambiguity.

Example: "Given a list of strings and a query, return the strings ranked by
fzf's smith-waterman-style fuzzy score, ties broken by shorter match span."

Everything that does not serve that sentence is a candidate for deletion.

## Pass 2 — Walk the call graph from the public entry point

Start at the upstream's public function for the capability. Follow only the
edges that the pinned sentence requires. Do not follow:

- logging, telemetry, metrics
- config plumbing (hardcode the one config the user needs)
- plugin/extension hooks
- alternative algorithms hidden behind feature flags
- i18n / localization
- backwards-compat shims for old versions
- CLI argument parsing (the target has its own)

What remains is usually 3–8 functions. That is the irreducible core.

## Pass 3 — Inline transitive helpers

For each helper imported from another package in the upstream:

- If you use < 30 lines of it, inline those lines into the port and credit
  the upstream file at the top of the ported file.
- If you use > 30 lines and the helper has its own test surface, ask
  whether the helper itself is the real thing the user wants — they may
  have pointed at the wrong upstream.

Never reproduce a helper's full file just to use one function from it.

## Pass 4 — Strip the type system down

Most upstreams carry rich types for features the port does not need:

- generics that resolve to one concrete type → use the concrete type
- interfaces with one implementation → drop the interface
- option structs with 12 fields → take the 2 the user uses as positional
  args
- error enums with 9 variants → collapse to the 1–2 the caller actually
  branches on

Re-add abstraction only when a second caller exists.

## Pass 5 — Translate idioms, not syntax

When porting across languages, do not transliterate. Use the target
language's idiomatic equivalent for:

- iteration (range vs iterator vs comprehension)
- error handling (Result vs exceptions vs error returns)
- string handling (bytes vs runes vs grapheme clusters — pick what the
  pinned sentence requires)
- memory ownership (borrow vs clone vs arena)

A faithful clone reads native to the target. A literal translation always
reads foreign and accumulates bugs at the seams.

## Pass 6 — Port one test, then stop

Pick the upstream test that exercises the pinned sentence most directly.
Port it (translating idioms per Pass 5) and run it against the new code.
If it passes, the clone is real. If it fails, fix the clone — never edit
the test to match the bug.

Do not port the rest of the upstream's test suite. One pinned test is the
contract; more tests is scope creep.

## Anti-patterns

- "I'll port it faithfully and trim later" — you will not trim later.
- "Let me add a small wrapper for flexibility" — there is no second caller.
- "I'll keep this helper in case we need it" — delete it; git remembers.
- "I'll add a TODO for the edge case the upstream handles" — either the
  pinned sentence needs it or it does not.
