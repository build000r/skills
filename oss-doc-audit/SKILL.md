---
name: oss-doc-audit
description: Audit a repository's public docs for drift against the active codebase, grade OSS readiness, and produce a ranked cleanup queue. Use when asked to "audit docs", "check OSS readiness", "find stale docs", "grade OSS readiness", "what docs are wrong", or "prepare this repo for open source".
---

# OSS Doc Audit

Audit public docs against live code and repo policy.

This is not a prose-polish skill. Factual correctness, active-stack alignment,
and functioning guardrails come first. Style cleanup is secondary.

## On Trigger

Start the first progress update with:

`Using oss-doc-audit ...`

If the repo is large, split the read-only audit into parallel concerns after the
baseline scan:

- public docs surface
- API/manifest/spec surface
- workflow, release, and licensing surface
- implementation proof surface for any disputed route or payload claims

Use `divide-and-conquer` when you need parallel agents.

Load [references/proof-checklist.md](references/proof-checklist.md) before the
first full audit pass.

If the first pass found more drift than expected, load
[references/drift-patterns.md](references/drift-patterns.md) before the second
pass.

## Modes

Repo-aware audits should use a local gitignored mode file when available.

1. List `modes/*.md` in this skill directory.
2. Match `cwd` against `cwd_match` path prefixes.
3. If multiple modes match, prefer the longest matching prefix.
4. If one best match remains, use it automatically.
5. If none match, infer the active codebase from repo files before scanning.

See [references/mode-template.md](references/mode-template.md).

## Workflow

### 1. Establish source of truth

Inspect the repo surfaces that define current reality:

- `AGENTS.md`
- `CLAUDE.md`
- root `README.md`
- primary manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, etc.)
- the active app entrypoint and router registration

Write down:

- active codebase path
- deprecated paths or stacks
- canonical validation commands
- current publish or licensing posture

If the repo has an explicit "active codebase" rule, treat that as binding unless
the code clearly contradicts it.

Prefer repo-native guidance over guesswork:

- if `AGENTS.md` names the active codebase, use that
- if `README.md` and `CLAUDE.md` disagree, treat that as a finding
- if an existing validator fails or crashes, treat the validator itself as part
  of the audit result

### 2. Map the public docs surface

Inventory the docs people will actually read first:

- root `README*`
- `CONTRIBUTING*`
- `docs/`
- `.github/` contributor docs and workflow docs
- package `README*` files
- API docs, manifests, OpenAPI specs, changelogs, release notes

Separate:

- active contributor docs
- historical or archived docs
- generated specs

Do not spend time grading archived material unless it is still linked from the
active surface.

### 3. Run existing validators before trusting them

If repo-local checks exist, run them first. Broken validators are findings.

Typical examples:

- docs hygiene scripts
- manifest or route parity checks
- OpenAPI parity checks
- package README validation
- docs CI workflows

Prefer repo-native commands over inventing new ones. If a validator points at a
deprecated stack, call that out explicitly.

### 4. Compare docs to code

Prioritize findings that would mislead an OSS reader:

- docs that describe routes that do not exist
- docs that present `501` stubs as shipped APIs
- stale stack instructions after a migration
- examples that call dead scripts or dead workflow files
- response payloads that no longer match the implementation
- licensing or package metadata mismatches
- leaked private infrastructure details, local paths, or internal-only values

Search for drift with targeted greps driven by the repo's own reality:

- deprecated path names
- old stack names
- removed commands
- missing workflow files
- mismatched endpoint paths

Do not stop at the docs. Open the implementation or router file that proves the
claim is wrong.

When a repo mixes active and deprecated stacks, explicitly test whether the
docs-validation toolchain still points at the deprecated tree.

Treat checked-in API specs such as `docs/api-reference*.yaml` as active public
docs when they are part of the contributor surface.

Use [references/drift-patterns.md](references/drift-patterns.md) when you need
to broaden the second pass beyond generic “stale docs” language.

### 5. Grade OSS readiness

Use the 100-point rubric in [references/rubric.md](references/rubric.md).

Start at 100 and subtract once per distinct issue cluster. Grade the repo as it
is today, not as it could be after cleanup.

If any fail gate in the rubric is present, state it clearly. A repo with dead
endpoint docs or broken doc validators is not "100%" ready.

Call out the difference between:

- repository readiness score
- audit workflow quality

Do not inflate the repository score just because the audit found the problems.

### 6. Produce a ranked cleanup queue

Use [references/report-template.md](references/report-template.md).

Rank by impact on OSS readers:

1. incorrect docs that change behavior expectations
2. broken validation or CI guardrails
3. stale contributor or release workflow docs
4. security, privacy, and infrastructure leakage
5. style or tone cleanup

Each queue item should name:

- the problem
- the affected file(s)
- the proof file(s)
- the expected fix
- the likely score recovery

### 7. Improvement loop

When the user wants iteration:

1. fix the highest-ranked queue items
2. rerun repo-local validators
3. rerun the audit
4. rerun the grade
5. patch this skill if the audit missed a class of issue

If the new run still misses obvious findings, improve this skill before doing
another broad cleanup pass.

When a validator changes from `crash` or `targets deprecated stack` to a clean
runtime failure, move the remaining issue from the guardrail bucket into
correctness/content drift.

Typical reasons to patch the skill after a run:

- it missed a whole drift cluster such as `501` stubs documented as shipped
- it trusted a broken validator without verifying its target stack
- it failed to compare docs payload examples against real response schemas
- it missed publish-surface contradictions across README, package manifest, and
  repo license

When the first pass finds repo-specific drift markers, add a reusable probe list
to a reference file instead of relying on memory. For common proof patterns, see
[references/proof-checklist.md](references/proof-checklist.md).

## Output Requirements

Always include:

- `Score: <n>/100`
- `Fail Gates:` present or none
- `Top Findings:` ordered by severity
- `Ranked Cleanup Queue:` ordered by score recovery and reader impact
- `Completed In This Loop:` when iterating on an existing queue
- `Validation Run:` commands executed and whether they passed
- `Next Loop:` what to fix first before rerunning

If no issues are found, say so plainly and still report what you checked.
