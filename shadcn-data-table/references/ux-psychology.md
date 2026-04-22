# UX Psychology for Dense Tables

The laws and biases that actually change table design. Each entry: the principle, the table-specific implication, and a concrete rule this skill enforces.

## Hick's Law

Decision time scales with log₂(n + 1) for n equiprobable choices.

Implication: every additional visible column or filter facet adds log-scale cognitive cost, not linear.

Rules:

- Cap default-visible columns: 7 / 5 / 4 at comfortable / compact / dense.
- Cap facet values shown in a filter dropdown at 12 before requiring internal search.
- Page sizes: 10 / 25 / 50 / 100 — not a free-text number.

## Fitts's Law

Time to hit a target ∝ log₂(distance / size).

Implication: small action icons and row-level buttons are expensive to hit, especially on touch.

Rules:

- Primary row action: make the entire row a click target when navigation is the primary action.
- Icon-only buttons: minimum 32×32 px hit area even if the icon itself is 16 px.
- Pagination controls: at least 32 px on each axis; never 20 px arrows.

## F-Pattern Scanning

Users scan left-aligned text in an F shape: horizontal across the top, shorter horizontal mid-page, vertical down the left edge.

Implication: the leftmost column gets the most attention. Identifier strength is rewarded here.

Rules:

- First column is the strongest human-recognizable identifier. Not an ID.
- Secondary metadata stacks beneath the primary label, not to the right as a separate column.
- For wide tables, sticky-pin the identifier column so horizontal scroll does not break the anchor.

## Recognition Over Recall

Users are better at recognizing things they can see than recalling things that are hidden.

Implication: active state buried in menus forces recall; exposed state supports recognition.

Rules:

- Active filters render as dismissible chips above the table.
- Active sort visible in the header without hover.
- Column visibility menu shows which columns are currently hidden, not just the full list.
- Density mode indicator visible in toolbar.

## Miller's 7 ± 2

Working memory holds ~7 chunks.

Implication: even if the screen can fit 12 columns, users cannot hold 12 column meanings in memory while scanning.

Rules:

- Default-visible column cap of 7 at comfortable density.
- Chunk related data into a single cell with primary + secondary when it reduces column count without information loss.

## Serial Position Effect

First and last items in a list are remembered better than middle items.

Implication: column order matters beyond aesthetics.

Rules:

- Rank 1 columns go first (identifier) and last (primary action column if any).
- Rank 2 columns fill the middle.
- Do not sort columns alphabetically unless the domain genuinely has no priority (rare).

## Goal-Gradient Effect

Motivation increases as users approach a goal.

Implication: if the table's purpose is completing work (reviewing, approving, resolving), showing progress toward zero-remaining accelerates the user.

Rules:

- When the table enables a work queue, show a remaining-count badge prominently.
- Default sort to bring the "next thing to act on" to the top.

## Peak-End Rule

People judge an experience by its peak moment and its ending.

Implication: the filtered-empty state and the action-completed state are disproportionately memorable.

Rules:

- Filtered-empty state is designed, not default. "No rows match these filters" + clear action.
- After a row action, show a brief confirmation, then update in place — do not reload the entire table.

## Banker's Eye (convention, not a law, but enforced)

Accountants align monetary values on the decimal.

Implication: left-aligned money looks wrong even when correct.

Rules:

- Right-align monetary and numeric columns.
- `tabular-nums` so digit widths match.
- Fixed decimal places per column; do not vary per row.
- Thousands separators always for values ≥ 1,000.

## Progressive Disclosure

Show what is needed now; reveal more on request.

Implication: rank-3 columns should not be visible but must be reachable.

Rules:

- Column-visibility menu keeps all rank-3 columns accessible.
- Row-detail drawer or expand row shows fields that do not belong in any column (notes, full audit trail, JSON dumps).
- Never delete fields from the type just because they are rank-3.

## Error-Cost Asymmetry

The cost of a missed row (user acts on stale data) usually exceeds the cost of a slower refresh.

Implication: staleness must be visible; do not silently cache.

Rules:

- Show "cached N minutes ago" when serving from cache.
- Refresh keeps prior data visible but marks the table as loading.
- Over-limit cap shows "Showing N of M — narrow your filters" so users know they are not seeing everything.
