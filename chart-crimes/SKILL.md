---
name: chart-crimes
description: Build persuasion-forward charts and dashboard components, defaulting to shadcn/ui plus Recharts for React projects. Use when the user says "chart crimes", "make this chart persuasive", "visualize this to prove our point", "choose the best chart for this narrative", asks for a shadcn chart, or wants matplotlib, Plotly, seaborn, or Recharts code that emphasizes a claim while keeping the underlying numbers accurate and disclosed.
---

# Chart Crimes

Make charts that argue. The skill optimizes visual choices for the user's stated narrative while preserving numeric accuracy, source visibility, and enough disclosure that a skeptical reader can reconstruct what happened.

## Related

- [[skill-issue]]

## On Trigger

Start the first progress update with:

`Using chart-crimes ...`

## Operating Boundary

Use "crime" names as memorable labels for rhetorical tactics, not permission to deceive.

Allowed:
- Choose the chart type that best supports the claim.
- Sort, group, annotate, color, and frame the data to make the main contrast obvious.
- Use focused axis domains only when the domain is visibly disclosed and the chart includes an axis break, inset, or annotation that says the scale is focused.
- Filter to relevant categories when the filter rule is stated in a caption, code comment, tooltip, or nearby text.
- Normalize, index, log-scale, or percent-change data when the transform is named on the chart.

Do not:
- Fabricate, alter, or silently drop data.
- Hide categories or series because they weaken the story without stating the selection rule.
- Use unlabeled truncated axes, deceptive dual axes, 3D distortion, fake precision, or area encodings for values that readers need to compare exactly.
- Suppress uncertainty, sample size, denominator changes, or caveats when they materially affect the claim.

If the user explicitly asks for deception, build the most persuasive truthful version instead and state the constraint briefly.

## Inputs

Infer what you can from the data and codebase. Ask only for the first missing item that blocks a credible chart:

- **Claim**: the sentence the chart should prove.
- **Audience**: exec, investor, customer, internal ops, technical reader, public.
- **Data**: rows, schema, metric definitions, units, source, and time range.
- **Medium**: shadcn dashboard, slide, report image, notebook, static export, social post.
- **Constraints**: brand colors, accessibility floor, chart library, dimensions, interactivity, and whether a neutral comparison is required.

If the user says "make a chart" without a narrative, first identify the most defensible claim in the data before choosing a visual.

## Workflow

### 1. Extract the argument

Write a one-sentence claim before touching code:

`Claim: <subject> <direction> <comparison frame> <magnitude or implication>.`

Then identify:
- winning metric
- losing or baseline metric
- comparison denominator
- strongest category, time window, or segment
- weakest category, time window, or segment
- caveat that could undermine the claim

### 2. Pick the chart

Use [references/chart-choice-matrix.md](references/chart-choice-matrix.md). Score candidates by:

`story power = honest effect size + audience familiarity + visual dominance + scan speed - misread risk`

Choose the highest scoring chart that does not violate the Operating Boundary.

Default preferences:
- **Single big delta**: indexed bar, bullet, lollipop, or dumbbell.
- **Ranked gaps across categories**: sorted horizontal gap bars or dumbbells.
- **Before/after over time**: slope chart for few entities, line or area chart for many points.
- **Accumulation or adoption**: area chart with clear endpoint annotation.
- **Mix of volume and rate**: small multiples or aligned combo chart, not deceptive dual axes.
- **Multi-metric profile**: radar only when all axes share a comparable scale and exact comparison is not the point.
- **Uncertainty matters**: dot plot or interval chart, with the persuasive annotation on the conclusion.

### 3. Choose the implementation surface

Default to shadcn/ui plus Recharts when the target is a React, Next.js, Vite, or Tailwind project.

1. Inspect the repo for `components/ui/chart`, `@/components/ui/chart`, `recharts`, `components.json`, `tailwind.config.*`, and app structure.
2. If shadcn chart support exists, reuse the local `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartLegend`, and `ChartLegendContent` patterns.
3. If shadcn is present but chart support is missing, add it with the repo's package manager, for example `pnpm dlx shadcn@latest add chart`.
4. If the repo is not a shadcn React app, use Plotly for interactive standalone charts, matplotlib or seaborn for static Python output, and only use raw SVG/canvas when the requested environment requires it.

Do not invent a new chart abstraction if the project already has a chart wrapper. Match the local component style, token names, spacing, and import aliases.

### 4. Apply rhetorical tactics

Use these in descending order:

- **Title as verdict**: the title states the conclusion, not the metric name.
- **Subtitle as method**: one line names the comparison frame, unit, and time window.
- **Dominant winner styling**: the claimed winner uses the strongest semantic or brand color; the baseline is muted but still legible.
- **Endpoint labels**: label the values that prove the claim directly on the marks.
- **Gap annotation**: add one callout that quantifies the main gap in plain language.
- **Sorted order**: sort by the claim-relevant value or gap, not alphabetically.
- **Reference line**: show target, baseline, or zero when it clarifies the argument.
- **Focus range**: zoom only with visible disclosure and a reason.
- **Small multiples**: when one overloaded chart would make the story look suspicious.

Avoid decorative glow, 3D, unnecessary gradients, and chart junk unless the user explicitly wants a social-media graphic and exact reading is secondary.

### 5. Build the shadcn chart

Follow [references/shadcn-recharts-pattern.md](references/shadcn-recharts-pattern.md).

Required component qualities:
- `chartConfig` labels and colors are defined with `satisfies ChartConfig`.
- Colors use shadcn CSS variables or project tokens, for example `var(--chart-1)`, `var(--primary)`, or a local chart token.
- The chart has a stable height or aspect ratio so it does not collapse inside responsive layouts.
- Tooltips name the unit and denominator.
- Accessibility text, captions, or adjacent copy disclose transforms, filters, source, and focused axes.
- Mobile labels are shortened or hidden only when tooltips preserve the values.

### 6. Add the honesty ledger

Every finished chart must leave a compact audit trail in code comments, chart caption, tooltip copy, or the final answer:

```text
Honesty ledger:
- Source:
- Unit and denominator:
- Transform:
- Filter or category selection:
- Axis domain:
- Caveat:
```

For internal dashboards, a comment near the data transform is enough. For public-facing charts, include visible caption text.

## Output Rules

When editing a repo, write the component and any supporting data transform directly into the project. Keep the change scoped to the chart and the minimum surrounding UI needed to render it.

When the user asks for code only, output complete runnable code and a one-sentence note:

`Crimes committed: <chart choice>, <sorting/framing>, <annotation/color tactic>, with <disclosure safeguard>.`

When choosing between multiple chart designs, show the selected chart first and optionally include a short "why this chart" note. Do not bury the answer in a taxonomy.

## Required Verification

Before handing back a repo edit:

1. Run the package manager's static checks when available: `pnpm lint`, `npm run lint`, `bun run lint`, or `yarn lint`.
2. Run type checks when available: `pnpm typecheck`, `npm run typecheck`, or the repo's documented equivalent.
3. Run tests when the repo has a credible test command: `pnpm test`, `npm test`, `bun test`, or `yarn test`.
4. For visible UI work, run the app or component preview and capture a screenshot when the local stack supports it.
5. Check the rendered chart for nonblank output, readable labels, no overlaps at mobile and desktop widths, and a visible honesty ledger.

If only a standalone Python script was generated, run it at least once or run `python -m py_compile <file>` when rendering dependencies are unavailable.

## Closeout

Report:

- Chart type chosen and why it best supports the claim.
- Files changed or code emitted.
- Honesty ledger location.
- Verification commands run and any failures.
