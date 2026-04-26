---
name: drift-detector
description: Detect UI drift across a frontend codebase — ad-hoc color/spacing/typography values vs design tokens, duplicate component variants, Tailwind arbitrary values, className soup, orphan primitives — then produce a ranked consolidation plan. When variants are consolidated, the old code is moved to a numbered per-family archive (single-page index) so no archetype is lost. Use when the user asks about "UI drift", "inconsistent UI", "poorly modularized UI", "too many button variants", "clean up the design system", or "consolidate components across projects".
license: MIT
---

# Drift Detector

Find UI inconsistency across a frontend codebase, propose a consolidation plan, and never lose an archetype on the way to consistency.

## On Trigger

Start the first progress update with:

`Using drift-detector ...`

## Design

Two layers that stay in their lanes:

1. **Deterministic scanners** (scripts) — emit facts as JSON. No opinions, no prose, no LLM in the loop. Reproducible on the same SHA.
2. **LLM interpretation** — reads the JSON + source, clusters findings into *design families* (buttons, cards, dropdowns, spacing scale, color scale), proposes a canonical form per family, ranks families by `impact × frequency`.

The agent never guesses what is duplicated. Scanners surface candidate duplicates; the agent names the family and picks the canonical form.

## Companion Skills

- `unified-brand-system` — defines the *target* tokens this skill measures against. If no token source exists, run it first.
- `simplify` — executes the consolidation edits once a plan is accepted.
- `codebase-audit` (UX domain) — a11y-focused; complementary, not overlapping.

## Supported Stacks

The scanner ships with stack adapters. Stack is auto-detected per repo; a repo can have multiple stacks and the scanner runs each adapter.

| Stack | Detected by | Default scope | Categories |
|---|---|---|---|
| `tsx` | `package.json`, `tsconfig*.json`, `.tsx` files | first non-empty of `{src, app, components, pages}` | tailwind_arbitrary, raw_color_literals, off_scale_spacing, off_scale_typography, inline_styles, classname_soup, clone_clusters, orphan_primitives |
| `swift` | `*.xcodeproj`, `Package.swift`, `.swift` files | first non-empty of `{Sources, App, <repo>/<repo>}` | arbitrary_modifiers, raw_color_literals, off_scale_typography, modifier_soup, clone_clusters |

Swift categories map to SwiftUI idioms:
- `arbitrary_modifiers` — `.padding(12)`, `.frame(width: 237)`, `.font(.system(size: 14))`, `.offset(x: 2)`, `.spacing(8)`
- `raw_color_literals` — `Color(hex: "#...")`, `Color(red:green:blue:)`, `UIColor(red:...)`, bare `#hex`
- `off_scale_typography` — `.font(.system(size: N))`, `Font.system(size: N)`
- `modifier_soup` — 6+ chained modifiers on one View (proxy for inline-style overuse)
- `clone_clusters` — jscpd with swift tokenizer

Add a stack by writing a new adapter pair (`scan_<stack>`, `default_scope_<stack>`) inside `scan.sh`. Detection goes in `detect_stacks()`.

## Inputs

- Target repo path (required)
- `--stack auto|tsx|swift` (default `auto`)
- `--scope <subpath>` to override stack-default scope
- `--all` to bypass stack defaults and scan the whole repo (noisy; use only when you know why)
- `--tailwind-config <path>` to pin a tailwind config explicitly
- `--output <path>` to write a repo-relative or absolute scan artifact other than `.drift/scan.json`
- `--token-source <path>` to exclude a repo-relative token source from violation counts; repeat for multiple files. Swift files named like `*Colors.swift`, `*Typography.swift`, `*DesignTokens.swift`, or `*Theme.swift` are auto-detected.
- Optional repo-local `.driftignore` file. Each non-comment line is an `rg` glob excluded from scanner findings after normal stack scoping.

## Workflow

### 1. Scan (deterministic)

```bash
scripts/scan.sh <repo-path> [--stack auto|tsx|swift] [--scope <subpath>] [--all]
```

Writes `<repo>/.drift/scan.json` with `meta.stacks`, `findings.<stack>.<category>`, and `summary.<stack>.<category>`. Every finding has `file:line`, matched substrings, and the raw line value. The scanner does not cluster or categorize — that is the LLM's job.

The TSX adapter also suppresses three noisy false-positive classes before writing findings:
- repo-gitignored files (post-filtered even when `rg -g` globs are in play)
- repo-local `.driftignore` globs
- prompt-content hexes in `image_prompt` / `video_prompt` / `keyPrompt` fields and Tailwind `data-[...]` variants such as Radix state selectors

`scan.json` is a generated local artifact. It may include source-line snippets for scanner evidence, so do not commit it by default in public repos. Commit the human plan (`.drift/plan.md`) and keep `scan*.json` ignored unless the operator explicitly wants raw findings versioned. Clone-cluster findings strip full duplicate fragments and retain locations/counts only.

Stack-agnostic drift signals always present:
- raw color literals
- clone clusters (jscpd)
- off-scale typography

Stack-specific signals documented in the Supported Stacks table above.

### 2. Cluster into design families

The agent reads `scan.json` plus the top N offending files and groups findings into families:

- **Component duplication families**: `button`, `card`, `dropdown`, `modal`, `input`, `badge`, `avatar`, ... (or SwiftUI analogs: `PrimaryButton`, `CardView`, etc.)
- **Token violation families**: `color`, `spacing`, `typography`, `radius`, `shadow`, `z-index`
- **Structure families**: `inline-style-overuse` / `modifier-soup`, `classname-soup`, `orphan-primitive`

Before emitting the plan, identify the **token source file(s)** for the stack (e.g. `tailwind.config.*`, `Theme/*.swift`, `DesignTokens.swift`) and exclude them from violation counts — they are the canonical, not drift. Findings inside the token source are expected.

For each family, record:
- canonical candidate (file path + reason it's the best starting point)
- variant list with `file:line` and a short "what makes this one different" note
- impact score: `variants × call_sites × loc_churn`
- a restore hint: the archive path each variant will land in

### 3. Rank and emit the plan

Write `<repo>/.drift/plan.md`:

```markdown
# Drift Consolidation Plan — <repo> — <date>

## Top families by impact

| # | family | variants | call sites | impact | canonical |
|---|--------|---------:|-----------:|-------:|-----------|
| 1 | button | 7 | 142 | 994 | src/components/ui/Button.tsx |
| 2 | card   | 4 | 88  | 352 | src/components/ui/Card.tsx   |

## Per-family detail
### button (impact 994)
- canonical: src/components/ui/Button.tsx — reason: most call sites, closest to shadcn shape
- variants to merge:
  - src/pages/marketing/HeroCTA.tsx — "gradient bg + oversized pad"
  - src/pages/pricing/BuyButton.tsx — "accent color only"
- token deltas needed: one new `--accent-gradient`; all other variants fold into `variant` prop
```

### 4. Archive on consolidation

**Never delete a variant.** When the user (or a downstream `simplify` run) accepts a merge, call:

```bash
scripts/archive.sh <repo> <family> <source-file> --reason "<short description>"
```

This:
1. Copies the source file to `<repo>/archive/<family>/NN-<basename>` where `NN` is the next zero-padded number in the family
2. Appends an entry to `<repo>/.drift/archive.json` with `{family, number, from, reason, date, sha, canonical_at_time}`
3. Re-renders the archive index (see 5)
4. Removes the original file (caller handles call-site rewrites via `simplify`)

### 5. Single-page archive index

```bash
scripts/render_archive_index.sh <repo>
```

Rebuilds `<repo>/archive/INDEX.md` — one page, per-family sections, numbered, with the **current canonical** shown in each family heading:

```markdown
# Design Archive

> Numbered per family. The canonical component is listed in each family heading.
> To restore: `cp archive/<family>/NN-* src/... && git status` to review.

## button — canonical: `src/components/ui/Button.tsx`
| #  | archived from                      | reason                    | archived  |
|----|------------------------------------|---------------------------|-----------|
| 01 | src/pages/marketing/HeroCTA.tsx    | gradient bg, oversized    | 2026-04-17 |
| 02 | src/pages/pricing/BuyButton.tsx    | accent color only         | 2026-04-17 |
| 03 | src/components/legacy/GhostBtn.tsx | ghost variant pre-tokens  | 2026-04-17 |

## card — canonical: `src/components/ui/Card.tsx`
| #  | archived from          | reason              | archived   |
|----|------------------------|---------------------|------------|
| 01 | ...                    | ...                 | ...        |
```

The index is the safety net: if a user scans it and realizes archetype `button/03` was the one they actually wanted, they copy it back and rerun the plan.

## Non-Goals

- Does not auto-edit component code. Consolidation edits go through `simplify` or a human.
- Does not generate tokens. That's `unified-brand-system`.
- Does not do a11y review. That's `codebase-audit` UX domain.
- Does not cover non-frontend codebases.

## Determinism Contract

- Scripts produce byte-identical `scan.json` on the same SHA with the same flags. No LLM, no network, no timestamps *inside* findings (only at the top level).
- All LLM reasoning happens on top of scanner JSON + source reads. If the agent claims a family exists, it must point to at least one `file:line` from `scan.json`.
- Archive moves are never done by the LLM directly — always via `scripts/archive.sh` so numbering and sidecars stay consistent.

## Required Verification

Before handing the run back, independently run `scripts/check.sh <repo>` and confirm it exits zero. Do not mark the task complete if it fails — fix the reported inconsistency first (usually: rerun `scripts/scan.sh` or `scripts/render_archive_index.sh`).

```bash
scripts/check.sh <repo>
```

The script verifies:
- `.drift/scan.json` has `meta`, `findings`, `summary` keys
- `.drift/archive.json` has `families` and every `archived_path` resolves on disk
- `archive/INDEX.md` is not orphaned (exists only if `archive.json` exists)

Additional ad-hoc checks during iteration:

```bash
jq '.summary' <repo>/.drift/scan.json
```

When changing scanner behavior, run the regression harness as well:

```bash
scripts/test_scan.sh
```

## Troubleshooting

- **No tailwind arbitrary findings on a Tailwind repo**: confirm `scripts/scan.sh` detected `tailwind.config.*` (logs the path). Pass `--tailwind-config <path>` if needed.
- **jscpd flagging boilerplate imports as clones**: tune `scripts/jscpd.json` threshold, not the agent output.
- **Archive index out of sync**: rebuild via `render_archive_index.sh`; never hand-edit `INDEX.md`.
