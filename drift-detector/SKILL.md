---
name: drift-detector
description: Detect UI drift across a frontend codebase — ad-hoc color/spacing/typography values vs design tokens, duplicate component variants, Tailwind arbitrary values, className soup, orphan primitives — then rank useful consolidations in the existing review or issue tracker. Preserve meaningful component behavior and use Git history for superseded source. Use when the user asks about "UI drift", "inconsistent UI", "poorly modularized UI", "too many button variants", "clean up the design system", or "consolidate components across projects".
license: MIT
---

# Drift Detector

Find UI inconsistency across a frontend codebase, rank consolidations, and preserve meaningful behavior while removing redundant variants.

## On Trigger

Start the first progress update with:

`Using drift-detector ...`

## Design

Two layers that stay in their lanes:

1. **Deterministic scanners** (scripts) — emit facts as JSON. No opinions, no prose, no LLM in the loop. Reproducible on the same SHA.
2. **LLM interpretation** — reads the JSON + source, clusters findings into *design families* (buttons, cards, dropdowns, spacing scale, color scale), proposes a canonical form per family, ranks families by `impact × frequency`.

The agent never guesses what is duplicated. Scanners surface candidate duplicates; the agent names the family and picks the canonical form.

## Companion Skills

- `ui` — provides the design-quality bar for Tailwind markup, components, typography, surfaces, tables, and responsive behavior.
- `simplify-and-refactor-code-isomorphically` — executes consolidation edits once a plan is accepted.
- `codebase-audit` (UX domain) — a11y-focused; complementary, not overlapping.

## Supported Stacks

The scanner ships with stack adapters. Stack is auto-detected per repo; a repo can have multiple stacks and the scanner runs each adapter.

| Stack | Detected by | Default scope | Categories |
|---|---|---|---|
| `tsx` / web | `package.json`, `tsconfig*.json`, Vite/Next/Astro/Svelte/Vue config, `index.html`, or frontend source extensions | all source roots from `{src, app, components, pages, public}`, nested package/app roots, and top-level `index.html` | tailwind_arbitrary, raw_color_literals, off_scale_spacing, off_scale_typography, inline_styles, classname_soup, component_motifs, ui_guideline_violations, clone_clusters, orphan_primitives, unused_canonical |
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
- `--stack auto|tsx|swift` (default `auto`; `tsx` is the generic web frontend adapter, not React-only)
- `--scope <subpath>` to override stack-default scope
- `--all` to bypass stack defaults and scan the whole repo (noisy; use only when you know why)
- `--tailwind-config <path>` to pin a tailwind config explicitly
- `--output <path>` to write a repo-relative or absolute scan artifact other than `.drift/scan.json`
- `--token-source <path>` to exclude a repo-relative token source from violation counts; repeat for multiple files. Swift files named like `*Colors.swift`, `*Typography.swift`, `*DesignTokens.swift`, or `*Theme.swift` are auto-detected.
- `--canonical-root <path>` to declare a repo-relative folder or file whose named exports are canonical UI primitives for the `unused_canonical` scanner. Repeatable. When omitted, defaults only to `src/components/ui`, `components/ui`, and `app/components/ui`. Feature-local primitive roots must be passed explicitly or via overlay; the scanner intentionally does not auto-promote every `**/components/<area>/index.tsx` barrel because feature barrels are often not primitive owners.
- Skillbox client overlays may declare canonical roots under `frontend.design_system.canonical_roots: [...]`; the calling agent passes these to `scan.sh` via `--canonical-root` (the script itself stays overlay-agnostic).
- Optional repo-local `.driftignore` file. Each non-comment line is an `rg` glob excluded from scanner findings after normal stack scoping.

## Workflow

### 1. Scan (deterministic)

```bash
scripts/scan.sh <repo-path> [--stack auto|tsx|swift] [--scope <subpath>] [--all]
```

Writes `<repo>/.drift/scan.json` with `meta.stacks`, `meta.tsx_scope`, `meta.tsx_canonical_roots`, `findings.<stack>.<category>`, and `summary.<stack>.<category>`. Every line-based finding has `file:line`, matched substrings, and the raw line value. The scanner emits candidate facts; the LLM verifies and clusters them into design families.

Before interpreting results, confirm `meta.tsx_scope` contains every expected frontend root. The generic web adapter now looks beyond React/Next layouts: it includes Vue/Svelte/Astro/plain HTML files, nested `package.json` / Vite app roots, `packages/*/src`, `apps/*/src`, and top-level `index.html` when present. If a repo keeps UI somewhere unusual (`frontend`, `website`, `examples/foo`, generated source checked in under a custom name), rerun with `--scope` or `--all`. Do not produce a consolidation plan from a scan that omitted known frontend code.

The TSX/web adapter also suppresses noisy false-positive classes before writing findings:
- repo-gitignored files (post-filtered even when `rg -g` globs are in play)
- repo-local `.driftignore` globs
- prompt-content hexes in `image_prompt` / `video_prompt` / `keyPrompt` fields and Tailwind `data-[...]` variants such as Radix state selectors
- common generated or preserved-output folders: `node_modules`, `dist`, `dist-ssr`, `build`, `coverage`, `.next`, `.nuxt`, `storybook-static`, `.drift`, and the drift archive folder `archive`

`scan.json` is generated evidence and may contain source-line snippets. Keep `<repo>/.drift/scan.json` when an existing downstream gate consumes that path; do not commit raw findings by default. For an ad-hoc review with no later consumer, use `--output` in owned temporary scratch and remove it after consuming the findings. Put decisions in the existing Bead or review, not a new `.drift/plan.md` by default. Clone-cluster findings strip full duplicate fragments and retain locations/counts only.

Stack-agnostic drift signals always present:
- raw color literals
- clone clusters (jscpd)
- off-scale typography

Stack-specific signals documented in the Supported Stacks table above.

#### `component_motifs` (TSX)

Surfaces semantic UI-family candidates even when token-level clone detection misses them. Families currently emitted:

- `button`
- `card`
- `form-control`
- `dropdown`
- `table`
- `tabs`
- `pagination`
- `badge`
- `modal`
- `filter-bar`
- `widget`

Each record includes `{file, line, family, matches, value}`. This scanner handles JSX/TSX, JS/TS, Vue, Svelte, Astro, and plain HTML where regex can see markup or class attributes. Treat these as candidate evidence, not a final verdict; read the top files before recommending a canonical form.

#### `ui_guideline_violations` (TSX)

Surfaces direct `/ui` guideline candidates that regex can prove without layout inference:

- `inline_text_size` — `text-*` / `leading-*` on inline elements
- `redundant_display` — default display utility on matching native elements
- `deprecated_tailwind` — deprecated utilities such as `min-h-screen`, `bg-gradient-*`, `flex-shrink-*`, `flex-grow-*`, `leading-tight/snug/relaxed`, or `theme(...)`
- `small_default_text_review` — unprefixed `text-xs` / `text-sm` requiring review against mobile body-text rules
- `heading_font_bold` — headings using `font-bold`
- `solid_divider_color` — solid gray/slate/zinc/neutral divider colors instead of opacity-based dividers
- `table_heading_uppercase` — uppercase table headers
- `table_vertical_divider` — vertical table dividers / `divide-x`
- `button_text_base` — app buttons using `text-base`
- `margin_layout_candidate` — margin utilities that may need parent `gap-*`

These findings are intentionally conservative about absence-style rules. They work across `className=` and plain `class=` attributes where possible. They do not prove missing `text-balance`, missing focus rings, missing table responsive wrappers, or "only one primary button"; those require source review.

#### `unused_canonical` (TSX)

Surfaces *canonical-bypass* drift — files that render motifs already covered by a canonical primitive but do not reference that primitive. Discovers canonical roots in this order:

1. `--canonical-root` flags (overlay-fed, when present)
2. Default convention folders: `src/components/ui`, `components/ui`, `app/components/ui`

For each canonical root the scanner extracts named exports (top-level `export function|const|class` plus `export { ... }` re-exports), classifies each export into a UI family, and compares those families against `component_motifs`. Then it finds files in scope that:

- match a semantic component motif family
- live outside every canonical root
- reference none of that canonical root's exports for the same family

Each match emits one finding: `{file, family, canonical_root, canonical_file, missing_exports[], motif_signals[]}`. The LLM then verifies imports/call sites, names the family, and proposes consolidation.

This is the signal that catches "agent rebuilt the rules table in a different file" — token-level dup (jscpd) misses it because the rebuilt UI uses different prop names while serving the same intent.

### 2. Cluster into design families

The agent reads `scan.json` plus the top N offending files and groups findings into families:

- **Component duplication families**: `button`, `card`, `dropdown`, `modal`, `input`, `badge`, `avatar`, `table`, `filter-bar`, `sort-header`, `tabs`, `pagination`, `accordion`, `drawer`, `data-grid`, ... (or SwiftUI analogs: `PrimaryButton`, `CardView`, etc.)
- **Token violation families**: `color`, `spacing`, `typography`, `radius`, `shadow`, `z-index`
- **Structure families**: `inline-style-overuse` / `modifier-soup`, `classname-soup`, `orphan-primitive`
- **Guideline families**: direct `/ui` rule drift from `ui_guideline_violations`

Before emitting the plan:

1. Confirm `meta.tsx_scope` covers all frontend roots. Rerun if it does not.
2. Confirm `meta.tsx_canonical_roots` contains every design-system primitive root. Rerun with `--canonical-root` for feature-local primitives.
3. Identify the **token source file(s)** for the stack (e.g. `tailwind.config.*`, `Theme/*.swift`, `DesignTokens.swift`) and exclude them from violation counts — they are the canonical, not drift. Findings inside the token source are expected.
4. Cross-check `component_motifs`, `unused_canonical`, `clone_clusters`, and `ui_guideline_violations`; do not rely on any single category as complete.

For each family, record:
- canonical candidate (file path + reason it's the best starting point)
- variant list with `file:line` and a short "what makes this one different" note
- impact score: `variants × call_sites × loc_churn`
- source custody: the existing commit and path for superseded tracked variants; identify any unique uncommitted behavior that still needs a decision

### 3. Rank and record decisions

Use the existing Bead, review, or response for the ranked families and their decisions. A compact table and the details needed to assess each consolidation are enough. Create a standalone plan only when requested or required by an existing consumer, using that consumer's established location.

```markdown
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

### 4. Consolidate and retire superseded source

For an authorized consolidation, preserve useful differences in the canonical component, update its callers, and verify the relevant behavior and visual states. Then remove the superseded variant. Git history retains committed source; record the existing commit/path when recovery context matters. Do not create numbered copies, archive sidecars, or index pages as a routine consequence of consolidation.

Git history does not preserve unique uncommitted changes. Keep those in place until their useful behavior is integrated or explicitly rejected. An unresolved design decision is not permission to delete its only implementation.

### 5. Optional archive compatibility

Use a separate archive only for an explicit request or a concrete unresolved need for a separate retained copy. Name its consumer and retention condition first; do not duplicate source already adequately retained in Git or its existing working location. The existing helper remains available for that deliberate choice:

```bash
scripts/archive.sh <repo> <family> <source-file> --reason "<short description>"
```

It moves the source to `<repo>/archive/<family>/NN-<basename>`, records metadata in `.drift/archive.json`, and renders `archive/INDEX.md`. The original path is removed, so caller rewrites and behavior verification still belong to the consolidation. Existing retained archives keep their current schema and validation.

If an existing archive index needs regeneration:

```bash
scripts/render_archive_index.sh <repo>
```

The index describes only that retained archive. It is not a completion requirement for ordinary consolidation.

## Non-Goals

- Does not auto-edit component code. Consolidation edits go through `simplify-and-refactor-code-isomorphically` or a human.
- Does not invent a target brand system. It measures against existing repo tokens, canonical roots, and `/ui` guidance; if those are missing, call that out before consolidation.
- Does not do a11y review. That's `codebase-audit` UX domain.
- Does not cover non-frontend codebases.

## Determinism Contract

- Scripts produce byte-identical `scan.json` on the same SHA with the same flags. No LLM, no network, no timestamps *inside* findings (only at the top level).
- All LLM reasoning happens on top of scanner JSON + source reads. If the agent claims a family exists, it must point to at least one `file:line` from `scan.json`.
- When an optional archive is justified, use `scripts/archive.sh` so its existing numbering and sidecars remain consistent.

## Required Verification

Before handing the run back, run `scripts/check.sh <repo>` for artifacts retained at its standard paths and resolve any reported inconsistency. It validates existing artifacts and creates nothing; it does not require a plan, archive, or index to exist. If the scan used a temporary `--output`, inspect that JSON's required keys and findings directly before removing it. Verify relevant source/tests and visual behavior separately; artifact structure alone does not prove a successful consolidation.

```bash
scripts/check.sh <repo>
```

For artifacts that exist, the script verifies:
- `.drift/scan.json` has `meta.stacks`, `findings`, and `summary` keys
- `.drift/archive.json` has `families` and its archived and canonical paths resolve on disk
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
- **Expected frontend root missing from `meta.tsx_scope`**: rerun with `--scope "<root1> <root2>"` or `--all`, then add a `.driftignore` for generated/noisy local folders. If the layout is common across repos, add a regression fixture to `scripts/test_scan.sh` before changing the scope heuristic.
- **jscpd flagging boilerplate imports as clones**: tune `scripts/jscpd.json` threshold, not the agent output.
- **Archive index out of sync**: rebuild via `render_archive_index.sh`; never hand-edit `INDEX.md`.
