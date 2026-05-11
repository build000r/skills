---
name: oss-doc-audit
description: Audit a repository's public docs for drift against the active codebase, grade OSS readiness, and produce a ranked cleanup queue. Use when asked to "audit docs", "check OSS readiness", "find stale docs", "grade OSS readiness", "what docs are wrong", or "prepare this repo for open source".
---

# OSS Doc Audit

Audit public docs against live code and repo policy.

This is not a prose-polish skill. Factual correctness, active-stack alignment,
and functioning guardrails come first. Style cleanup is secondary — for
prose-level slop (emdashes, "Here's why", forced enthusiasm), hand off to the
`de-slopify` skill after factual drift is resolved. The two skills
compose: this one decides whether a doc should exist and be accurate;
`de-slopify` decides whether the surviving prose sounds human.

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

Repo-aware audits resolve an overlay section before scanning. Load the
resolved context into the environment:

```bash
SKILL_DIR="$HOME/.claude/skills/oss-doc-audit"
[[ -d "$SKILL_DIR" ]] || SKILL_DIR="$HOME/.codex/skills/oss-doc-audit"
eval "$("$SKILL_DIR/scripts/select_mode.py" "$PWD" --format shell)"
```

`scripts/select_mode.py` reads `client.context.oss_doc_audit` from the matching
`skillbox-config/clients/{client}/overlay.yaml`. No local mode files are part
of the supported contract.

If you need to create a missing client overlay before proceeding:

```bash
python3 ~/.claude/skills/skill-issue/scripts/manage_overlays.py create --client-id {CLIENT_ID} --cwd "$PWD" --json
```

Once resolved, prefer the loaded `MODE_*` variables
(`MODE_ACTIVE_CODEBASE_PATH`, `MODE_DEPRECATED_PATHS`, `MODE_BASELINE_COMMANDS`,
`MODE_DRIFT_MARKERS`, ...) over guessing. See
[references/mode-template.md](references/mode-template.md) for the overlay key
reference.

If a matching overlay exists but lacks `client.context.oss_doc_audit`,
`scripts/select_mode.py` fails with a section-missing error. In that case:

1. extend the overlay if this repo needs repeatable audits, or
2. continue with explicit repo-native inference for a one-off audit

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

### 5b. Choose an output mode

Three output modes are supported. Pick based on the user's ask and the
doc-tree size:

- **Rubric mode** (default) — single 100-point score + ranked cleanup queue.
  Use when the repo has <40 docs or the ask is "grade OSS readiness".
- **Per-file scorecard mode** — score every doc on five axes. Use when the
  repo has 40+ docs and the user needs file-by-file fate decisions (keep,
  rewrite, delete). See [references/report-template.md](references/report-template.md)
  for the scorecard format.
- **Tier fate mode** — classify every doc into Tier 1–7 (delete/rewrite →
  keep). Use as a companion to scorecard mode when stakeholders need a
  defensible "what goes, what stays" list before bulk deletion.

The modes compose: run scorecard to generate per-file scores, then bucket into
tiers, then produce one rubric score for the repo overall.

#### Per-file scorecard axes

Each axis is scored 1 (worst) to 5 (best). Low scores on multiple axes are
stronger evidence for deletion than a single low score.

| Axis | Meaning | 1 = | 5 = |
|---|---|---|---|
| **H**elpfulness | Does it answer a real question a reader will have? | Answers nothing real | Answers a frequent high-value question |
| **A**ccuracy | Does it match the current codebase and stack? | Fabricated or targets dead stack | Verified against live code |
| **B**revity | Is it the right length for its value? | Bloated or padded | Tight, no filler |
| **R**edundancy | Is it the only copy? (5 = not redundant) | Third copy of the same content | Unique source of truth |
| **N**ecessity | Would anyone miss it if deleted? | No reader needs this | Blocks onboarding or decisions |

#### Tier fate taxonomy

| Tier | Label | Meaning | Default action |
|---|---|---|---|
| 1 | Harmful / fictional | Actively misleads: fabricated claims, dead-stack refs, wrong APIs | Delete or rewrite from scratch |
| 2 | Heavy slop | AI-generated filler with low signal, generic tutorials | Delete |
| 3 | Deprecated but referenced | Old content still linked from live surface | Delete + sweep links |
| 4 | Near-empty stubs | Placeholder or redirect-only pages | Delete |
| 5 | Redundant copies | Duplicate of a canonical source | Delete, keep canonical |
| 6 | Needs trimming | Useful core, padded with slop | Trim + hand to `de-slopify` |
| 7 | Keep | Accurate, necessary, non-redundant | Leave alone |

Fabricated compliance claims, invented benchmarks, and fictional pricing are
Tier 1 — not Tier 6. They mislead readers regardless of how they are written.
See [references/drift-patterns.md](references/drift-patterns.md) for the
fabrication smell catalog.

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

### 6b. Post-deletion link sweep

After executing any deletion from the cleanup queue, every remaining doc that
referenced the deleted files becomes a potential broken link. Before declaring
the cleanup done, sweep for dangling references.

1. For each deleted file, grep the remaining doc tree and any manifests/indexes
   for its basename and path:

   ```bash
   # For a deleted file like docs/guides/compliance-legal.md
   rg -l 'compliance-legal' docs/ README.md SECURITY.md *.md
   rg -l 'compliance-legal' docs/manifest.json deploy/reverse-proxy/static/
   ```

2. Check these common reference surfaces even if nothing obvious matches:
   - root `README.md` and `CLAUDE.md` doc indexes
   - `docs/manifest.json`, `docs/index.md`, or equivalent TOC files
   - "Related Guides" / "See also" sections in surviving docs
   - `llms.txt`, `sitemap.xml`, reverse-proxy static indexes
   - package `README.md` files with cross-links
   - security audit trackers and OSS readiness inventories

3. Edit each broken link. Remove the list item rather than leaving a dead
   anchor. Do not "archive" the deleted file by leaving a tombstone.

4. Leave audit trackers (`OSS_HYGIENE_INVENTORY.md`, audit reports) alone —
   they reference historical state, not live links.

This step is non-optional when deleting more than a handful of files.
Stakeholders will find broken links before they find the cleanup PR.

### 6c. Volume report for stakeholder comms

When the cleanup involves bulk deletion (10+ files), produce a one-paragraph
volume summary alongside the rubric score. Stakeholders track lines-removed
more intuitively than rubric deltas.

Format:

```
Deleted N files (~M lines) across K categories. Largest categories:
- <category>: <n> files (worst offender: <file>)
- <category>: <n> files (worst offender: <file>)
Edited E files to fix broken index links. Repo now has F docs, all of which
are either verified useful or tracked in audit files.
```

Example from a real run:

```
Deleted 48 files (~16,100 lines) across 8 categories. Largest categories:
- Supabase/Node.js-era content: 13 files (docker/README.md)
- Fabricated compliance claims: 4 files (compliance-legal.md)
- docs-ai/ duplicates of canonical: 7 files
Edited 11 files to fix broken index links. Repo now has 119 docs.
```

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

## Verification / Closeout

Before returning, report the exact repo-native docs, build, test, or link checks
you ran, plus any blocked checks and why they could not run. For edits to this
skill itself, run:

```bash
python3 skill-issue/scripts/quick_validate.py oss-doc-audit
python3 -m pytest oss-doc-audit/tests/test_select_mode.py
```

Do not call an audit complete until the public-doc findings are tied back to
live code evidence and the validation commands or blockers are explicit.

## Related

- [[skill-issue]]
