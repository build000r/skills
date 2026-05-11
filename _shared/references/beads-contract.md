# Beads (`br`) Cross-Skill Contract

This file is the single source of truth for how skills in this repo
(`divide-and-conquer`, `domain-planner`, `domain-reviewer`,
`domain-scaffolder`, `smart`) integrate with
[beads_rust](https://github.com/Dicklesworthstone/beads_rust) — `br`, the
local-first, agent-first issue tracker.

When a skill needs to model "the work the swarm/loop is doing," the work lives
in `br` issues. Markdown artifacts (`WORKGRAPH.md`, `SMART_RECOMMENDATION_CHAIN.md`,
audit reports) become **rendered views** of `br` state, not the source of truth.

## Install + Bootstrap

```bash
# One-time install
curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/beads_rust/main/install.sh?$(date +%s)" | bash

# Per-repo, one-time
br init                                 # creates .beads/ at repo root
br agents --add --force                 # idempotent: drops/updates AGENTS.md instructions

# Verify
br --version && br where
```

The `.beads/` directory is committed to git. SQLite + JSONL coexist; commit
the JSONL (`.beads/issues.jsonl`) and the policy (`.beads/policy.yaml`).
Do not commit `.beads/*.db` (binary) or `.beads/.br_recovery/`.

Recommended `.gitignore` lines:

```
.beads/*.db
.beads/*.db-shm
.beads/*.db-wal
.beads/.br_recovery/
```

## Tier-1 Attribution (Required for Swarms)

Every agent invocation that mutates `br` state MUST stamp who did it. Skills
should set these env vars on entry and pass them through to spawned panes:

```bash
export BR_AGENT_NAME="<skill-name>"          # e.g. divide-and-conquer, domain-scaffolder
export BR_HARNESS="claude-code"              # or codex, ntm, etc.
export BR_MODEL="claude-opus-4-7"            # actual model handling the call
export BR_ACTOR="${USER:-agent}"             # for `--actor`
```

`divide-and-conquer` workers prepend these via the node prompt. `domain-*`
skills set them when entering each mode.

## Naming Convention

`br` derives the workspace prefix from the repo directory at `br init` time
(e.g. `htma`, `recipe-ios`). Issue IDs are `{prefix}-{slug}-{hash}`. The
examples below show `{prefix}` — your real prefix is whatever `br where`
prints under `prefix:`.

| Surface | Convention | Example |
|---|---|---|
| Slice (multi-node delivery) | `--type epic --slug {slice-name}` | `{prefix}-epic-key-insights-7f3a` |
| Execution node | `--slug exec-{NNN}-{kebab-title}` `--parent {epic-id}` | `{prefix}-exec-001-backend-api-9c2e` |
| Audit finding | `--type bug --parent {node-id}` `--labels finding:{kind}` | `{prefix}-finding-permissions-mismatch-1a4b` |
| Smart recommendation | `--type task --labels chain:smart` | `{prefix}-smart-2026-05-10-d8e1` |

Use `--labels` consistently:

- `concern:{slug}` — the node's concern (backend-api, frontend-widget, etc.)
- `repo:{slug}` — repo the node owns
- `wave:{n}` — which execution wave the node belongs to
- `risk:{none|human|external}` — risk gate
- `slice:{name}` — slice tag for cross-cutting queries

## Lifecycle Mapping

| Lifecycle event | Command |
|---|---|
| Plan node accepted | `br q --slug … --type task --parent {epic} --priority 1 --labels … --silent` |
| Add a dependency | `br dep add {child} {parent}` |
| Worker starts the node | `br update {id} --claim` (atomic: assignee + in_progress) |
| Worker reports `blocked` | `br update {id} -s blocked --notes "{reason}"` |
| Worker reports done | `br close {id} --reason "{summary}" --suggest-next --robot` |
| Wave complete (advance) | `br ready --json` (plain) or `br scheduler --robot` (ranked) |
| Slice retire | `br epic close-eligible --robot` |
| Final flush before commit | `br sync --flush-only` |

`br update --claim` is the canonical start signal because it is atomic — no
race between two panes claiming the same node. Skills MUST use it instead of
`br update -s in_progress`.

`br close --suggest-next` returns the newly unblocked frontier in the same
call; the orchestrator should consume that envelope and dispatch the next
wave without re-querying.

## Commit Policy

`.beads/issues.jsonl` is committed. Skills run `br sync --flush-only` before
the final integration commit so the JSONL reflects the SQLite state. The
JSONL is git-mergeable: concurrent panes in a swarm produce diff-friendly
appends, not conflicts, when each pane stamps its own actor and uses
distinct issue IDs.

Do NOT auto-commit `.beads/` updates inside node workers — only the final
integration/review wave commits. Workers run `br` mutations against the
shared `.beads/` directory but defer the commit to integration.

## Legacy Field Mapping (WORKGRAPH.md → br)

| Workgraph field | `br` flag/field |
|---|---|
| `id` | issue ID (auto from `--slug`) |
| `title` | positional title or `--title` |
| `concern` | `--labels concern:{slug}` |
| `repo` | `--labels repo:{slug}` |
| `depends_on` | `br dep add` after creation, or `--deps blocks:id1,blocks:id2` at create |
| `writes` (paths) | `--design "writes:\n  - …"` |
| `done_when` | `--acceptance-criteria` (multiline accepted) |
| `validate_cmds` | `--notes "validate:\n  - …"` |
| `risk_gate` | `--labels risk:{none\|human\|external}` |
| `status` (`todo`) | open (default) |
| `status` (`in_progress`) | `--claim` |
| `status` (`done`) | `br close` |
| `status` (`blocked`) | `br update -s blocked` |
| `status` (`skipped`) | `br close --reason "skipped: {why}"` |

## Required Verification (Skill Authors)

When a skill that declares `requires_beads: true` runs in a repo:

1. `br --version` succeeds (binary on PATH)
2. `br where` reports a `.beads/` directory; if not, run `br init` (and `br agents --add --force`)
3. `br doctor --robot` is clean (or report drift to the user)
4. The skill stamps `BR_AGENT_NAME`/`BR_HARNESS`/`BR_MODEL` before any mutating call
5. Commits include `.beads/issues.jsonl` and `.beads/policy.yaml` only — not `.db` files

`scripts/br_helpers.py` (in this `_shared/scripts/` bundle) wraps all of the
above. Skills should call it rather than re-implementing.

## Related

- Upstream: <https://github.com/Dicklesworthstone/beads_rust>
- Schema introspection: `br schema all --json` (treat as unstable per upstream warning)
- AGENTS.md template: `br agents --check` shows what the upstream installer would write
