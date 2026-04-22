# OSS Prior Art

Borrow patterns, not dependencies. The house stack is TanStack Table v8 + shadcn primitives; anything heavier is out of scope unless explicitly chosen.

## shadcn/ui official `data-table` docs

- URL: `https://ui.shadcn.com/docs/components/data-table`
- What it gives you: the minimum-viable wiring of TanStack Table into shadcn `Table` primitives. Good starting point, intentionally thin.
- Borrow: component file layout, `flexRender` usage, pagination row slot.
- Do not borrow: its filter UI (too minimal), its empty state (non-existent), or its visibility menu styling (unopinionated — override with the house uppercase-tracked label style).

## `sadmann7/shadcn-table`

- URL: `https://github.com/sadmann7/shadcn-table`
- What it gives you: the best community reference for an advanced shadcn table — server-driven filtering, faceted filters with counts, debounced global search, URL state via `nuqs`, column visibility/order, row actions, column resizing.
- Borrow:
  - `DataTableToolbar` shape: left side = filters, right side = view/visibility controls.
  - `DataTableFacetedFilter` — the facet component with counts and search inside the dropdown.
  - URL-state hook pattern (even if you swap `nuqs` for plain `URLSearchParams`).
  - `DataTablePagination` layout with page-size select.
- Do not borrow wholesale: copy the patterns, not the package. Pinning this repo as a dependency adds churn; the author refactors aggressively.
- License: MIT — safe to mine.

## TanStack Table v8 examples

- URL: `https://tanstack.com/table/v8/docs/examples`
- Specific examples worth reading before implementing:
  - `filters-faceted` — facet values via `getFacetedUniqueValues`.
  - `row-selection` — if the table has bulk actions.
  - `virtualized-rows` — when row count exceeds ~2,000.
  - `column-pinning` — for wide tables that need a sticky identifier column.
  - `expanding` — for parent/child rows.
- Borrow the headless API usage. Do not borrow the example styling — it is intentionally minimal and token-free.

## Interaction patterns from production apps

Not dependencies — design references for how power users expect dense tables to behave.

- **Linear**: inline status editing via keyboard (`S` opens status picker), single-line density, monospace IDs, sidebar for filter state.
- **Airtable**: view-as-saved-state (filter + sort + column visibility is a named object), primary field as the leftmost identifier.
- **Notion databases**: filter-chips-above-table pattern with individual dismiss, sort-stack chips below filters.
- **GitHub issues list**: faceted filters in a single text bar with operator syntax (`is:open author:foo`). Too power-user for most internal tools, but the active-filter chip pattern below the bar is worth stealing.

## Heavier alternatives — when NOT to use them

- **AG Grid**: overkill for < 10,000 rows; licensing for enterprise features; styles fight Tailwind. Use only when the product *is* a grid (spreadsheet-like editing, pivot tables).
- **Material React Table / MUI DataGrid**: pulls in MUI, conflicts with shadcn theming. Avoid in shadcn projects.
- **Tremor**: good for dashboards, but its tables are thin wrappers. Prefer direct TanStack + shadcn.

## Rule for this skill

Default stack is TanStack Table v8 + shadcn. Justify any alternative in writing before adopting it. "More features out of the box" is not a justification — unused features are drag.
