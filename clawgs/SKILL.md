---
name: clawgs
description: Extract structured JSON from Claude Code and Codex JSONL session logs with a local Rust binary. Use when asked to parse agent transcripts, normalize .jsonl sessions, auto-discover current Claude/Codex logs by cwd, or generate machine-readable context snapshots for downstream tools.
license: MIT
---

# Clawgs

## Purpose

Use this skill to run a deterministic transcript extractor outside the thought loop.

## Prerequisites

- Rust toolchain with `cargo`
- This skill checked out locally

## Install

```bash
bash scripts/install.sh
```

## Verify

```bash
bash scripts/check.sh
```

## Core Command

```bash
target/release/clawgs extract --tool auto --cwd "$PWD"
```

## Useful Flags

- `--input <path>`: parse a specific JSONL file instead of discovery
- `--tool <claude|codex|auto>`: force or infer source format
- `--pretty`: pretty-print JSON output
- `--include-raw`: include raw parsed event excerpts for debugging
- `--max-actions`, `--max-task-chars`, `--max-detail-chars`: output size controls

## Output Contract

Schema version is `clawgs.v1`. Full field definitions and sample output are in [references/schema-v1.md](references/schema-v1.md).
