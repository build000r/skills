# In-House Pattern — `ecom-reporting`

Source: `~/repos/ecom-reporting/src/components/reporting/report-list-data-table.tsx`

This is the house pattern. New tables should match its shape unless a concrete constraint forces deviation.

## What to copy verbatim

### SortableHeader helper

```tsx
function SortableHeader<TData, TValue>({
  column,
  title,
}: {
  column: Column<TData, TValue>;
  title: string;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="-ml-3 h-8 px-3 text-xs uppercase tracking-[0.16em] text-muted-foreground hover:text-foreground"
      onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
    >
      {title}
      <ArrowUpDown className="size-3.5" />
    </Button>
  );
}
```

Why:

- `-ml-3` reclaims the button's internal padding so the label aligns with non-sortable header text.
- `h-8` locks header row height across sortable and non-sortable columns.
- Uppercase + 0.16em tracking is the house label style; reuse it, do not invent a new header treatment.
- Icon is always visible (not hover-only). Swap for directional arrow when `getIsSorted()` returns `"asc"` or `"desc"` in the production version.

### Global filter

```tsx
const globalFilter: FilterFn<Row> = (row, _columnId, value) => {
  const needle = String(value ?? "").trim().toLowerCase();
  if (!needle) return true;
  const haystack = [
    row.original.primary_name,
    row.original.primary_id,
    row.original.status,
    row.original.kind ?? "pending",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
};
```

Why:

- Build the haystack from identifier-strength fields, not every field. Search-matching against low-signal fields creates false positives.
- Default `?? "pending"` or an explicit sentinel for nullable enums so filtering does not drop them.
- Debounce the input in the toolbar (250 ms). The filter function stays pure.

### Secondary metadata stacking

```tsx
cell: ({ row }) => (
  <div>
    <div className="font-medium">{row.original.primary_name}</div>
    <div className="mt-1 font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
      {row.original.primary_id}
    </div>
  </div>
);
```

Why:

- Primary label is what the eye reads first. Identifier code is auxiliary but recoverable.
- Two-line cell keeps the table one column narrower and reinforces F-pattern scanning.
- The muted uppercase-tracked pattern (`font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground`) is the house treatment for secondary metadata. Reuse it in every table in the portfolio.

### Faceted enum filter

```tsx
filterFn: (row, columnId, value) => {
  return value === "all" || row.getValue(columnId) === value;
};
```

Pair with a `Select` in the toolbar where `"all"` is the default value; the column reads `value === "all"` as "no filter".

## What not to copy

- Do not copy column-specific logic verbatim — re-score columns for the new decision.
- Do not copy the default sort — it is domain-specific.
- Do not copy the pagination size (varies by row count tier).

## Files actually inspected

- `src/components/reporting/report-list-data-table.tsx` (lines 1–200 confirmed)
- `src/components/reporting/report-list.tsx` (wrapper)
- `package.json` — confirmed `@tanstack/react-table` v8
