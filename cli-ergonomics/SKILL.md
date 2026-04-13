---
name: cli-ergonomics
description: >-
  Build, modify, or review agent-facing CLIs for compact output, strong
  defaults, and clean shell UX. Use when a tool is mainly consumed through
  shell execution by Claude Code, Codex, Cursor, or similar agents.
---

# CLI Ergonomics

Build or review CLIs that agents can drive reliably from the shell.

## Upstream Lineage

This skill is informed by the upstream AXI project. It keeps the reusable
agent-first CLI design rules while leaving AXI's broader SDK, benchmark, and
runtime surface upstream.

Use `gh-axi` as a concrete example of this pattern: a small, opinionated wrapper
that makes GitHub workflows more compact and agent-legible without mirroring the
entire `gh` command tree.

## Use This For

- Designing a new CLI that agents will call repeatedly
- Wrapping an existing human CLI with a smaller, more agent-legible surface
- Reviewing a CLI for token waste, weak defaults, prompty behavior, or bad errors
- Tightening an existing tool's help, list views, detail views, and mutation semantics

## Do Not Use This For

- GUI-first products with no meaningful shell surface
- Generic API design that does not cross a CLI boundary
- One-off shell scripts that are not intended to become a stable interface

## Related Skills

- **`rust-cli-with-sqlite`** — For Rust CLIs that manage local state via SQLite + JSONL sync.
  Covers WAL/PRAGMA tuning, atomic writes, cross-process locking, sync strategy, and crash
  recovery. Use that skill for the implementation; use this one for the shell UX contract.

## Core Goal

Optimize for the real loop an agent experiences:

1. discover the tool
2. inspect the current state
3. take one action
4. understand what changed
5. decide the next command without unnecessary retries

Every extra field, follow-up call, interactive prompt, or ambiguous error makes that loop worse.

## Workflow

### 1. Frame the Interface

Before changing the CLI, write down:

- who is driving it: human, agent, or both
- whether the common path is read-heavy, mutation-heavy, or mixed
- what the "home view" should show with no args
- what the smallest useful list schema is
- what the likely follow-up command is after each main command

If the tool wraps another CLI, keep the wrapper opinionated. Do not expose the full upstream surface just because it exists.

#### Decision Trees

```
Wrapper or standalone?
├─ Wraps an existing CLI → Keep surface opinionated; expose ≤30% of upstream flags.
└─ New tool from scratch  → Design the verb set around the agent loop.

Primary consumer?
├─ Agent only  → Content-first home view, no interactive prompts, structured errors.
├─ Agent + human → Same rules, but consider --json / --human flags.
└─ Human only  → This skill is not for you.

Manages local state (DB, config, cache)?
├─ Yes → Expose recovery commands; detect stale state on startup.
│        See references/stateful-cli.md
└─ No  → Stateless; each invocation is self-contained.

Output format already chosen by the repo?
├─ Yes → Use it. Do not force format churn.
└─ No  → Compact structured text. TOON if the ecosystem uses it, plain otherwise.
```

### 2. Review the Current Shell UX

Run the tool like an agent would:

```bash
tool
tool --help
tool list
tool view 123
tool mutate 123
tool mutate 123 --bad-flag
```

Check for these failure modes:

- no-arg invocation shows help instead of live state
- list output includes too many fields by default
- detail output omits the main content entirely or dumps too much of it
- long bodies/diffs/logs have no truncation strategy
- empty results are ambiguous
- mutations are not idempotent
- bad input leaks raw dependency stderr
- the CLI prompts interactively instead of failing fast with a fixable error
- suggestions or next steps are missing after list/mutation commands

### 3. Shape the Surface for Agents

Apply these defaults unless the repo has a strong reason not to:

- Content first: no args should show useful live state, not a manual
- Command first: `tool <command> ...args ...flags`
- Minimal default schemas: identifier + title/name + status is usually enough
- Truncation with escape hatch: show a preview plus `--full`
- Explicit counts: tell the agent whether it saw all items or only the first page
- Pre-computed summaries: include cheap aggregates that remove a second command
- Structured errors on stdout: actionable message, stable exit code, no stack noise
- No interactive prompts: everything required must be expressible with flags
- Contextual disclosure: after list/mutation commands, show a few relevant next steps

Prefer compact structured text formats. If the repo already uses TOON, keep using it. If it does not, do not force format churn just to mimic another project.

### 4. Handle Mutations Carefully

Mutations should be legible and boring:

- treat already-done state as success when the intent is satisfied
- return a compact confirmation payload, not prose-heavy celebration
- include enough state for the next decision
- translate wrapped-tool failures into your CLI's vocabulary

Bad:

- "interactive editor opened"
- "are you sure? [y/N]"
- raw API exception or upstream CLI traceback

Good:

- "already closed"
- "merge: ok"
- "`--title` is required"

### 5. Decide Whether Hooks Belong

Ambient context is powerful, but only when it fits the host runtime.

- If the runtime already manages session context, avoid self-installing competing hooks by default
- If hooks are appropriate, make them idempotent and easy to disable
- Treat hook output as extremely scarce context budget

This matters in `skillbox`-style environments: the box already generates shared agent context, so a CLI should not silently add a second competing session-prelude unless that is explicitly desired.

### 6. Verify the Contract

Use a command-first check before shipping:

```bash
tool
tool list
tool list --limit 5
tool view 123
tool view 123 --full
tool mutate 123
tool mutate 123
tool bad-command
```

You want to prove:

- home view is useful
- lists are compact
- truncated content has a clear escape hatch
- repeated mutations become no-ops or stable confirmations
- invalid input returns a fixable error

## Exact Prompts

### THE EXACT PROMPT — Design a New CLI Surface

```
Design an agent-facing CLI surface for [tool].
1. Who drives it (agent, human, both)?
2. What does the home view show with no args?
3. What is the minimal list schema (id + name + status)?
4. What are the mutation verbs and their idempotency contracts?
5. What does the agent see on success, empty state, and error?
Output: filled references/surface-template.md
```

### THE EXACT PROMPT — Audit an Existing CLI

```
Audit [tool] for agent ergonomics:
1. Run: tool, tool --help, tool list, tool view <id>, tool mutate <id>, tool bad-input
2. Check each item in references/review-checklist.md
3. Score each failure against references/failure-matrix.md
4. Report: what fails, what wastes tokens, what's missing
Output: ranked list of fixes with expected impact
```

### THE EXACT PROMPT — Tighten a Mutation

```
Review [tool mutate] for agent safety:
1. Is it idempotent (already-done = success)?
2. Does success output include state for the next decision?
3. Does it fail fast on bad input before calling upstream?
4. Are interactive prompts suppressed?
5. Is the error vocabulary consistent with the rest of the CLI?
Output: before/after for each fix
```

### THE EXACT PROMPT — Design Error Catalog

```
Design the error catalog for [tool]:
1. List every user-facing error path
2. Assign stable exit codes per references/failure-matrix.md
3. Write actionable messages (what failed, what to do next)
4. Ensure no raw dependency stderr leaks to stdout
Output: error table with code, message template, and suggested fix
```

## Review Checklist

Read [references/review-checklist.md](references/review-checklist.md) when doing a full audit or PR review.

## Anti-Patterns

- **Help-as-home**: no-arg invocation dumps a manual instead of live state
- **Kitchen-sink wrapper**: exposing the full upstream surface instead of an opinionated subset
- **Chatty mutations**: "Successfully created! 🎉" instead of "created: id=123"
- **Interactive fallback**: prompting for missing flags instead of failing with the flag name
- **Naked errors**: leaking upstream stack traces or raw stderr to stdout
- **Schema bloat**: default list output with 15+ columns when 3-5 would suffice
- **Silent empty**: returning nothing on zero results instead of "0 items"
- **Hook pollution**: self-installing ambient hooks without checking the host runtime
- **Format churn**: forcing a new output format when the repo already has one

## Done When

- `tool` (no args) shows live state, not help
- `tool list` output fits in ~20 lines for typical data
- `tool view <id>` shows main content with truncation + `--full` escape hatch
- `tool mutate <id>` twice in a row produces stable output (idempotent or clear confirmation)
- `tool bad-input` returns non-zero with an actionable message naming what to fix
- No interactive prompts anywhere in the surface
- Error messages use the tool's vocabulary, not upstream dependency names
- Exit codes follow the convention in [references/failure-matrix.md](references/failure-matrix.md)

## Output Guidance

In closeout, report:

- what shell interaction got simpler
- which defaults changed
- what the agent now sees on success, empty state, and error
- what verification commands you ran

## Reference Index

| Need | Read |
|------|------|
| Full review checklist | [review-checklist.md](references/review-checklist.md) |
| Failure scenarios + exit codes | [failure-matrix.md](references/failure-matrix.md) |
| Stateful CLI design (recovery, locks, state detection) | [stateful-cli.md](references/stateful-cli.md) |
| Fillable surface design template | [surface-template.md](references/surface-template.md) |
| Rust + SQLite + JSONL implementation | `rust-cli-with-sqlite` skill (external) |
