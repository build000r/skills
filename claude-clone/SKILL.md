---
name: claude-clone
description: >-
  Recreate a feature from a high-signal upstream (gh CLI, ripgrep, fzf, jj, lazygit,
  bat, delta, hyperfine, gron, etc.) by writing the smallest possible amount of new
  code. Performs deep archaeology on the upstream — finds the exact files, structs,
  flags, edge cases, and call graphs that matter — then stitches a minimal port into
  the target repo. Develops and validates the port inside the sibling `skillbox`
  dev container so the opinionated toolchain is already present. Use when the user
  says "clone this feature from gh", "I want X like ripgrep does it", "minimal
  port of Y", "rip this out of that repo and give me just the part I need",
  "recreate the upstream behavior in my repo", "what's the smallest code that gives me Z",
  or otherwise asks for a deliberately small reimplementation of an existing OSS
  capability.
---

# Claude Clone

Goal: produce the **smallest possible** new code that faithfully reproduces a
chosen capability from a high-signal upstream repo, by reading the upstream
deeply rather than guessing at the shape.

This is a meta-skill. The deep upstream archaeology is delegated to
`build-vs-clone` (prospect mode). The dev environment is delegated to the
sibling `skillbox` repo. This skill's job is the *stitching*: scoping the
clone, calling the right sub-skills, extracting the irreducible core, and
landing it in the target repo.

## On Trigger

Start the first progress update with:

`Using claude-clone ...`

Then, in one short paragraph, name:
1. The **upstream repo** (or candidate set) being cloned
2. The **specific capability** (a verb + object, not a vague area)
3. The **target repo** the port lands in
4. Whether the clone is `INLINE` (one file dropped in) or `MODULE` (a small
   subdirectory with its own boundary)

If any of those four is missing, ask once before proceeding. Do not ask about
anything else.

## Non-Goals

- Full forks, vendor-ins, or "let's just submodule it". Use `build-vs-clone`
  in `ADOPT` mode for those.
- Borrowing patterns without reading code. If the user wants conceptual
  inspiration only, route to `build-vs-clone` `BORROW`.
- Greenfield design. If no upstream is named or implied, route to
  `build-vs-clone` to find one first.
- Style-only translations (e.g., "rewrite this Go file in Python verbatim").
  This skill recreates *capabilities*, not files.

## Modes

### CLONE mode (default)

Use when the user has named both an upstream and a target. Five steps:

1. **Frame** — pin the four things from "On Trigger" in writing.
2. **Archaeology** — delegate to `build-vs-clone` prospect mode against the
   upstream. Ask it to map only the subgraph that implements the capability:
   entry points, core data structures, the 2–5 functions that do the real
   work, and the tests that pin the behavior.
3. **Reduce** — apply the extraction recipe in
   [references/extraction-recipe.md](references/extraction-recipe.md) to
   collapse the subgraph to its irreducible form.
4. **Port** — write the minimal new code in the target repo. Match the
   target's language and idioms, not the upstream's. Inline what you can,
   drop what the target already provides.
5. **Validate** — run the port inside the `skillbox` dev container (see
   [references/skillbox-devcontainer.md](references/skillbox-devcontainer.md))
   so the toolchain (compilers, linters, fuzzers, hyperfine, etc.) is
   already there. Land at least one behavioral test that pins a non-trivial
   case from the upstream's own tests.

### SCOUT mode

Use when the user has named a *capability* but no upstream ("I want fuzzy
matching like fzf does it, find me the right repo first"). Run
`build-vs-clone` ecosystem-fit mode to pick the upstream, then re-enter
CLONE mode at step 2.

### EXTRACT mode

Use when the user already has the upstream cloned locally and wants the
minimal extraction without re-discovery. Skip step 2's prospect call; go
straight to reading the named files and applying the extraction recipe.

## Hard Rules

- **Read before writing.** Do not write a single line of port code before
  you have named the exact upstream files and line ranges that justify it.
  If you cannot cite source, you are guessing.
- **Smallest viable port.** Every function, struct, flag, and dependency in
  the port must earn its place against a concrete behavior the user asked
  for. Cut everything else, even if "it might be useful later."
- **No transitive imports.** If the upstream pulls in three helper packages
  to do the job, prefer to inline the 20 lines you actually need over
  vendoring all three. Document the inlining at the top of the ported file.
- **Match the target, not the upstream.** Ported code obeys the target
  repo's language, formatter, error-handling style, and test framework.
  A faithful clone reads like the target wrote it themselves.
- **One test that proves it.** Land at least one behavioral test ported
  (not copied verbatim) from the upstream's own test suite. This is the
  contract that says "the clone is real."

## Delegation Contract

`claude-clone` does not duplicate work that `build-vs-clone` already does.

| Question | Owner |
|---|---|
| Is this worth cloning vs adopting vs building? | `build-vs-clone` |
| Which upstream is the right one? | `build-vs-clone` (SCOUT) |
| What does the upstream's relevant subgraph look like? | `build-vs-clone` (prospect) |
| What is the minimum code to recreate it? | `claude-clone` |
| Where does the code physically live in the target? | `claude-clone` |
| Does it pass a behavioral test? | `claude-clone` (in skillbox) |

If `build-vs-clone` returns `ADOPT` or `BORROW` for the underlying question,
stop and report that result instead of forcing a clone.

## Dev Container

All build/test/bench work for the port runs inside the sibling `skillbox`
repo's main workspace container. See
[references/skillbox-devcontainer.md](references/skillbox-devcontainer.md)
for the exact entry commands and the assumed package surface. Do not
install language toolchains on the host to support a clone — that is the
entire reason skillbox exists.

## Output Shape

When the clone is complete, report:

1. **Upstream + commit SHA** read during archaeology
2. **Files cited** (path + line range) that the port is derived from
3. **New files in the target** with line counts
4. **Behavioral test(s)** added and what upstream test they mirror
5. **Deliberately omitted** upstream features and why
6. **skillbox commands** the user can rerun to re-validate
