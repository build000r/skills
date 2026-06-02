# Anti-Patterns

The mistakes that recur in AI-generated and rushed human-authored tables. Each has a concrete fix.

## Column selection

### Dumping every field as a column

Symptom: table has 14 columns, user sees 4 at a time without scrolling.
Fix: score columns (SKILL.md §2). Default-hide everything below rank 2. Keep hidden columns in the visibility menu, do not delete.

### Opaque ID as the first column

Symptom: first column is `a7f3-9c1e-...` because it is `row.id`.
Fix: first column is the strongest human-recognizable identifier (name, label, subject). IDs stack as secondary metadata under the primary label using the muted uppercase-tracked pattern.

### Separate column for data that belongs with another

Symptom: `Status` column and `StatusUpdatedAt` column side by side.
Fix: stack the timestamp under the status pill as secondary metadata. One concept per column.

### Missing a decision

Symptom: every design choice feels arbitrary because no one wrote down what the table is for.
Fix: write the one-line decision intent before touching columns. If it cannot be stated, do not build the table yet.

## Filtering

### Filter state hidden in a menu

Symptom: user applies three filters, later cannot remember what is active.
Fix: render active filters as dismissible chips above the table. Recognition over recall.

### Global search matching every field

Symptom: typing "2024" matches rows via created-at timestamps the user never intended to match.
Fix: build the haystack from identifier-strength fields only. Add explicit date-range filters if date matching is wanted.

### No filtered-empty state

Symptom: filters produce zero rows and the user sees the same empty state as "no data ever". They cannot tell the difference.
Fix: filtered-empty shows "No rows match these filters" + "Clear filters". Global empty shows a primary create action.

### Undebounced search

Symptom: typing "acme corp" fires eight renders and six network requests.
Fix: debounce 250 ms. Cancel in-flight server requests on new input.

## Sorting

### Default sort on an opaque ID or insertion order

Symptom: table loads sorted by primary key; the first row is whatever happened to insert first.
Fix: default sort is tied to the decision. "What is stuck" sorts by age desc. "Biggest exposure" sorts by amount desc.

### Sort indicator only on hover

Symptom: mobile users cannot see which column is active.
Fix: arrow is always visible; idle state uses `ArrowUpDown`, active uses `ArrowUp`/`ArrowDown`.

## States

### Spinner over skeleton on initial load

Symptom: layout jumps when data arrives because nothing reserved the space.
Fix: skeleton rows matching column widths. The header also has skeleton text so column widths lock immediately.

### Blanking the table on refresh

Symptom: polling empties the table for 200 ms every refresh, rows "flash".
Fix: keep prior data visible; show a thin progress bar at the top. Only blank on an actual error.

### No over-limit signal

Symptom: server caps at 1,000 rows; user sees 1,000 rows and assumes that is all.
Fix: show "Showing N of M — narrow your filters" when the server signals truncation.

## Responsiveness

### Horizontal scroll as the default mobile strategy

Symptom: on phone, the table scrolls sideways and users lose their row.
Fix: below `md`, collapse to a card list. The card mirrors the rank-1 and rank-2 columns; rank-3 goes behind a "details" expander.

### Same density across devices

Symptom: comfortable density on a laptop, comfortable density on a 13" external where 30 rows are needed.
Fix: persist density per-table in localStorage and expose the toggle in the toolbar.

## Styling

### Hex colors in the table

Symptom: `className="text-[#6b7280]"` sprinkled through cells.
Fix: consume `text-muted-foreground` from the brand tokens. If a needed role is missing, extend the brand-token contract; do not patch locally.

### Custom header treatment per table

Symptom: three tables in the same app have three different header styles.
Fix: use the house uppercase + 0.16em tracking on every sortable header. This is a portfolio-wide contract.

### Monetary columns left-aligned

Symptom: `$1,234.56` and `$12.34` do not line up on the decimal.
Fix: right-align, `tabular-nums`, fixed decimals per column.

## Accessibility

### Sort state not announced

Symptom: screen reader users cannot tell which column is sorted.
Fix: `aria-sort="ascending" | "descending" | "none"` on the header cell.

### Row-level action at 12×12 px

Symptom: a three-dot menu is technically clickable but Fitts says no.
Fix: either make the whole row clickable (with a clear primary navigation) or give the action button ≥ 32×32 px.

### No keyboard route to filters

Symptom: tab order skips the filter toolbar because the search input is absolutely positioned.
Fix: toolbar comes first in DOM order. `/` focuses search, `Esc` clears.
