# Component Primitives Contract

Each primitive names exactly which tokens it may read. If it needs a value that isn't in its allowed set, the answer is either "use an allowed token" or "add a token," never "hardcode."

## Button

Allowed tokens: `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--destructive`, `--destructive-foreground`, `--border`, `--ring`, `--radius`, `--font-body`, `--text-sm`, `--text-base`.

Variants:

- `default`: background `--primary`, text `--primary-foreground`.
- `secondary`: background `--secondary`, text `--secondary-foreground`.
- `destructive`: background `--destructive`, text `--destructive-foreground`.
- `outline`: transparent background, border `--border`, text `--foreground`, hover background shift via `--muted`.
- `ghost`: transparent background, text `--foreground`, hover background `--muted`.
- `link`: transparent background, text `--primary`, underline on hover.

Focus state: 2px ring using `--ring` with `--background` offset.

Disabled state: opacity 0.5, no other color changes.

Sizes: `sm` (`--text-sm`, 36px tall), `md` (`--text-base`, 44px tall — boomer-legible default), `lg` (`--text-lg`, 52px tall).

## Input

Allowed tokens: `--background`, `--foreground`, `--muted-foreground` (placeholder), `--border`, `--input`, `--ring`, `--radius`, `--destructive`, `--font-body`, `--text-base`.

- Background `--background`, border `--input`, text `--foreground`, placeholder `--muted-foreground`.
- Focus: 2px ring `--ring`, border shifts to `--ring`.
- Error state: border `--destructive`, focus ring `--destructive`.
- Minimum height 44px for boomer-legibility.

## Card

Allowed tokens: `--card`, `--card-foreground`, `--border`, `--radius`, `--shadow-sm`, `--muted-foreground`.

- Background `--card`, text `--card-foreground`, border `--border`.
- Radius `calc(var(--radius) * 1.25)`.
- Shadow `--shadow-sm`. Larger elevations are not the card's responsibility — use a separate surface.

## Dialog / Popover

Allowed tokens: `--popover`, `--popover-foreground`, `--border`, `--radius`, `--shadow-lg`.

- Opens over an overlay using `--foreground` at 40% alpha. Express the overlay as a CSS variable (`--overlay`), do not hardcode.

## Badge / Chip

Allowed tokens: `--muted`, `--muted-foreground`, `--primary`, `--primary-foreground`, `--destructive`, `--destructive-foreground`, `--radius`.

Radius: `9999px` (pill). One of the few places pill radius is allowed even if the default radius is sharp.

## Navigation

Allowed tokens: `--foreground`, `--muted-foreground`, `--background`, `--muted`, `--ring`, `--font-body`, `--text-base`.

- Link default: `--muted-foreground`.
- Link hover: `--foreground`, background `--muted`.
- Link active: `--foreground`, background `--muted`, underline optional.
- Current-page indicator is a solid 2px border-bottom in `--primary`, not a color change.

## Table

Allowed tokens: `--background`, `--foreground`, `--muted`, `--muted-foreground`, `--border`, `--font-body`, `--text-sm`, `--text-base`, `--font-mono` (for numeric columns).

- Header background `--muted`, text `--muted-foreground`.
- Row border `--border`.
- Numeric columns use `--font-mono` OR `--font-body` with `font-variant-numeric: tabular-nums`.
- Hover row background `--muted` at ~40% alpha; express with a variable if used.

## Content Body (long-form markdown)

Allowed tokens: `--foreground`, `--muted-foreground`, `--primary`, `--border`, `--font-display`, `--font-body`, `--font-mono`, all text scale tokens.

- Headings use `--font-display` with tight leading.
- Body paragraphs use `--font-body` at `--text-base` with `--leading-relaxed`.
- Blockquotes have a 4px left border in `--primary` or `--border`.
- Inline code uses `--font-mono` at 0.9em of the parent.

## Forbidden in All Primitives

- No hex values.
- No rgb/rgba values except for derived overlays that reference a variable.
- No hardcoded radius.
- No hardcoded shadow — must reference a `--shadow-*` token.
- No hardcoded font size — must reference a `--text-*` token.
- No hardcoded color — must reference a semantic token.

## Extending the Contract

If a new component needs a token not in the base set, add the token. Name it semantically (`--ring-inverse`, not `--color-17`). Document which primitives may read it.
