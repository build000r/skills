---
name: shadcn-data-table
description: Design and implement data-intensive shadcn/ui tables that stay scannable at scale. Produces a column-priority plan, a filter/sort contract, density and state specs, and a TanStack Table v8 + shadcn implementation grounded in UX psychology (Hick, Fitts, F-pattern, recognition-over-recall) and Tufte-style data density. Use when asked to "design a data table", "build a shadcn table", "make this table easier to use", "pick columns for this table", "add filtering/sorting", "tame a table with too many columns", "make this table less overwhelming", or when a dense list/grid/report UI needs a real IA pass instead of dumping every field into columns.
license: MIT
---

# shadcn Data Table

Turn a dataset + a decision into a shadcn table that a real user can scan, filter, and act on without getting lost. Output is a column-priority plan plus a working TanStack Table v8 + shadcn implementation that consumes existing design tokens.

## On Trigger

Start the first progress update with:

`Using shadcn-data-table ...`

## What This Skill Owns

- Column selection, ordering, and default visibility for dense datasets.
- Filter contract (faceted vs text vs range) and sort contract (default, multi, indicators).
- Density modes (comfortable / compact / dense) and their content-collapse rules.
- Row-state coverage: empty, loading, error, partial/stale, over-limit.
- TanStack Table v8 wiring against shadcn `Table` primitives.
- URL-state persistence so a table view is shareable.

## What This Skill Does NOT Own

- Design tokens or brand system — consume from `unified-brand-system`.
- Charts and KPI cards — use `chart-crimes` for persuasive charts, `tufte-ui-review` for quantitative review.
- Detecting existing table variant drift across a codebase — that is `drift-detector`.
- Backend query/pagination APIs — note the contract the table needs, do not design the API here.

## Companion Skills

- `unified-brand-system` — defines the tokens this skill consumes (radius, spacing, muted/foreground, border).
- `tufte-ui-review` — run it on the finished table for a quantitative-clarity pass.
- `drift-detector` — run after adoption to catch table-variant drift across the repo.
- `chart-crimes` — sibling for the chart next to the table; same token contract.
- `describe` — spec pass/fail cases for table interactions before wiring.

## Inputs To Gather First

Ask only if missing; infer from context otherwise.

- **Dataset shape**: row type (TypeScript interface or sample JSON), field list with types.
- **Primary user role**: who reads this table (ops reviewer, controller, admin, end customer).
- **Decision this table enables in under 60 seconds**: e.g. "which reports are stuck", "which customers owe the most", "what changed today". If the user cannot state this, force the question — every downstream choice depends on it.
- **Row count tier**:
  - Small (≤ 50): no pagination or virtualization; render all.
  - Medium (50–2,000): client-side pagination + client-side filter/sort.
  - Large (2,000–50,000): client-side virtualization (`@tanstack/react-virtual`) + server-optional filter/sort.
  - Huge (> 50,000): server-driven filter/sort/pagination; client is a cursor.
- **Update cadence**: static snapshot, periodic refresh, live-stream.
- **Action surface**: read-only, row-click detail, inline action menu, bulk actions.

## Workflow

### 1. Decision intent

Write one line before touching columns:

`After viewing this table, the user should decide ___`

If the decision is vague, every later choice drifts. Pin it first.

### 2. Column priority (the core of the skill)

Score every candidate field on three axes (1–3 each):

- **Decision-relevance**: how directly the field informs the stated decision.
- **Identifier strength**: how well the field lets a user recognize the row (names > codes > opaque IDs > timestamps).
- **Scan frequency**: how often a user's eye needs to touch this field per session.

Sum per field. Then:

- **Rank 1 (top 2–3)**: identifier column + 1–2 decision-critical fields. Always visible. First column is the strongest identifier (optionally sticky-pinned on wide tables).
- **Rank 2 (next 3–5)**: decision-relevant context. Visible by default, but first to collapse into secondary metadata at compact density.
- **Rank 3 (everything else)**: hidden by default, available via column-visibility menu. Do not delete; persistence in the view spec matters for power users.

Hard caps: visible columns ≤ 7 at comfortable density; ≤ 5 at compact; ≤ 4 at dense. More than that and users stop reading headers — this is Hick's law, not an aesthetic preference.

### 3. Column form

Per visible column, pick:

- **Alignment**: left for text and IDs, right for numeric and monetary, center only for single-glyph status icons.
- **Type face**: monospace for IDs, codes, timestamps, and percentages; proportional for prose.
- **Case**: uppercase + wide tracking (`uppercase tracking-[0.16em] text-muted-foreground text-xs`) for secondary metadata under a primary label — this mirrors the in-house pattern in `references/in-house-pattern.tsx`.
- **Numeric formatting**: fixed decimals per column; thousands separators; align decimals (tabular-nums).
- **Date formatting**: one format per column; relative ("2h ago") only when the decision is recency-driven, absolute otherwise.
- **Null rendering**: a single muted glyph (`—`) not `null`, `N/A`, or blank.
- **Secondary metadata**: stacked under the primary cell using the muted uppercase-tracked pattern; never add a separate column for a field that belongs *with* another.

### 4. Filter contract

- **Low-cardinality enums (≤ 12 values)**: faceted filter (checkbox dropdown), show counts per facet, support "clear" and "select all". Multiple selected values = OR within the facet.
- **High-cardinality text**: debounced global search (250 ms) against a computed haystack of the most identifying fields. Mirror the `globalReportFilter` pattern in the reference.
- **Numeric or monetary**: range input with min/max; provide preset chips ("> 0", "this month", "overdue") when they map to the stated decision.
- **Dates**: presets first ("today", "last 7 days", "this quarter"), custom range second.
- **Active filters row**: show chips above the table for every active filter with individual ✕ and a "clear all". Never hide active filters inside a menu — recognition over recall.
- **Combination semantics**: AND across facets, OR within a facet. State this once in a help tooltip.
- **Empty result**: if filters produce zero rows, show "No rows match these filters" + a "clear filters" button, not the global empty state.

### 5. Sort contract

- **Default sort**: tied to the decision. For "what is stuck", sort by age descending. For "biggest risk", sort by monetary exposure descending. Never default to an opaque ID.
- **Sort UI**: sortable headers render as ghost buttons with `ArrowUpDown` (idle) → `ArrowUp` / `ArrowDown` (active). Indicator is visible without hover (mobile has no hover).
- **Multi-sort**: shift-click adds a secondary sort; show sort order (1, 2) in the header. Opt-in per column, not blanket.
- **Sticky header**: always sticky on tables > 15 visible rows.

### 6. Density and responsiveness

- **Comfortable**: default. 48–56px row height, generous padding, primary + secondary metadata stacked in identifier cell.
- **Compact**: 36–40px row height, secondary metadata hidden, muted column labels still visible.
- **Dense**: 28–32px row height, single-line cells, IDs shortened to last-6, tooltips on hover for full value.
- Persist density choice per-table in localStorage.
- Below `md`: collapse to a card list, not a horizontally scrolling table. Horizontal scroll is a last resort — readers lose their row.

### 7. State coverage (non-negotiable)

Every table ships with all of these wired, not just the happy path:

- **Empty**: no data ever loaded. Show cause + single primary action ("Create first report").
- **Filtered empty**: rows exist but filters hide them. Show "clear filters".
- **Loading (initial)**: skeleton rows matching column widths; include header skeleton too. Do not use spinner.
- **Loading (refresh with prior data)**: keep the old data visible, show a thin progress bar at the top. Never blank the table on refresh.
- **Error**: inline error row with retry. Preserve filters.
- **Partial/stale**: "Showing cached data from N minutes ago" + refresh action.
- **Over-limit**: if the server caps results, show "Showing N of M — narrow your filters".

### 8. URL state

Persist filters, sort, page, column visibility, and density to the URL. Use a small wrapper over `URLSearchParams` or `nuqs` if already present. Rationale: shareable views, back-button works, and reloads do not wipe an ops workflow.

### 9. Implementation contract

Stack:

- `@tanstack/react-table` v8 (verify version in target repo's `package.json`).
- shadcn primitives: `Table`, `Button`, `Input`, `DropdownMenu*`, `Select*`, `Badge`.
- Icons: `lucide-react` (`ArrowUpDown`, `ArrowUp`, `ArrowDown`, `Search`, `ChevronDown`, `ChevronLeft`, `ChevronRight`).
- Tokens consumed: `text-muted-foreground`, `border`, `bg-muted`, `text-foreground`. No hex colors.

File layout (component-local):

```
<feature>/
  <feature>-data-table.tsx     // orchestrator: useReactTable, toolbar, pagination
  <feature>-columns.tsx         // ColumnDef<Row>[] + header helpers
  <feature>-filters.tsx         // toolbar: global search + faceted filters + active chips
  <feature>-empty-states.tsx    // empty / filtered-empty / error
  use-<feature>-table.ts        // hook owning state + URL sync
```

Keep `columns` as data, not JSX-heavy logic. Cells that need interactivity import small presentational components from the feature folder.

### 10. Checks before shipping

- Column count is within the density cap for the default density.
- Decision intent line is present in a code comment above `columns`.
- Every state from §7 is reachable and visually distinct.
- Keyboard: tab reaches every interactive cell; `/` focuses global search; `Esc` clears it.
- Screen reader: header cells have `scope="col"`; sort state announced via `aria-sort`.
- Fitts: row-level actions are full-row click targets or a ≥ 32px action button, never 12px icons.
- Tabular numerics align on the decimal (`tabular-nums`).
- No hardcoded colors; nothing leaks through `unified-brand-system` tokens.

## UX Psychology References

- **Hick's law**: decision time grows with log(n). Cap visible columns and filter facets.
- **Fitts's law**: action hit area ∝ success. Full-row click > 32px button > icon-only.
- **F-pattern scanning**: strongest identifier in the leftmost column; secondary metadata stacked under, not to the right.
- **Recognition over recall**: active filters as chips above the table, not hidden in a menu.
- **Miller's 7±2**: even with column hiding available, do not default-show more than 7.
- **Banker's eye**: right-align monetary columns; align on the decimal; use tabular figures so digits line up vertically.
- **Progressive disclosure**: rank-3 columns live in a visibility menu, not deleted.

## Reference Material

- [`references/in-house-pattern.md`](references/in-house-pattern.md) — annotated extract of the house pattern from `ecom-reporting/src/components/reporting/report-list-data-table.tsx` with the sortable header helper, global filter pattern, faceted filter, and secondary-metadata styling.
- [`references/oss-prior-art.md`](references/oss-prior-art.md) — canonical external patterns worth borrowing: shadcn/ui `data-table` docs, `sadmann7/shadcn-table` advanced template, TanStack Table v8 examples, Linear/Airtable/Notion interaction patterns.
- [`references/anti-patterns.md`](references/anti-patterns.md) — the mistakes that recur in AI-generated tables: dumping every field, showing an ID as the first column, horizontal scroll as the default responsive strategy, spinners over skeletons, missing filtered-empty state, default sort on an opaque ID.
- [`references/ux-psychology.md`](references/ux-psychology.md) — deeper notes on the laws cited above with the specific table implications.

## Verification / Closeout Contract

For skill-contract edits, rerun:

```bash
python3 skill-issue/scripts/quick_validate.py shadcn-data-table
```

Before returning, confirm:

1. Decision intent line is pinned in code.
2. Column ranking was scored, not improvised.
3. Every state from §7 is wired.
4. Tokens are consumed, not redefined.
5. URL state persists the full view.
6. Keyboard + aria coverage matches §10.
