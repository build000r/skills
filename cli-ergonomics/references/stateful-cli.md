# Stateful CLI Guidance

When a CLI manages local state (SQLite, config files, caches, lock files), agents need
additional guarantees beyond the core ergonomics contract.

## Recovery Commands

Expose at minimum:

- **export** — dump state to a human-readable format (JSON, JSONL, TOML, CSV)
- **import** — rebuild state from that export
- **check** / **doctor** — validate integrity and report problems

These give agents and humans an escape hatch when state corrupts or drifts.
Name them as subcommands of the tool itself so they're discoverable via `--help`.

## Startup State Detection

On startup, a stateful CLI should:

1. Detect obviously stale or corrupt state (version mismatch, failed integrity check)
2. Report the problem clearly instead of silently operating on bad data
3. Suggest the recovery command: "state corrupt — run `tool doctor` or `tool import`"

Do not auto-repair silently. The agent needs to know something was wrong so it can
adjust its plan.

## Concurrency

If multiple agents or processes might invoke the tool simultaneously:

- **Serialize writes** with a lock file (e.g., `fs4` in Rust, `flock` in shell)
- **Set a busy timeout** so callers get "locked, retry in Ns" instead of a crash
- **Allow concurrent reads** where the storage layer supports it (e.g., SQLite WAL mode)
- **Report lock holder** if possible — pid, age of lock, or at least the lock file path

An agent that hits a lock error should be able to decide whether to wait or bail
without guessing.

## Human Escape Hatch

State should always be inspectable and recoverable without the CLI itself:

- Store in a format humans can read (SQLite via `sqlite3`, JSON/JSONL via any editor)
- Document the state file location in `--help` or a `tool info` subcommand
- Never require the CLI to be functional in order to recover from CLI state corruption

## Version Markers

If the CLI syncs between two stores (DB + file, local + remote):

- Store a version marker (timestamp, monotonic counter, or content hash) in both stores
- Compare on startup to detect drift
- Refuse to overwrite newer data with older data

This prevents the silent data loss that comes from two-way sync without coordination.

## Rust + SQLite Implementation

For Rust CLIs using SQLite + JSONL sync specifically, see the **`rust-cli-with-sqlite`** skill,
which covers WAL/PRAGMA tuning, atomic JSONL writes, cross-process locking with `fs4`,
sync strategy patterns, and crash recovery in depth. That skill is the implementation
companion to the design principles here.
