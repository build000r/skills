# shadcn Recharts Pattern

Use this as the default implementation pattern for React projects that have shadcn/ui.

## Detection

Check for:

```bash
rg -n "components/ui/chart|ChartContainer|ChartConfig|recharts" .
rg -n "components.json|tailwind.config|@/components" .
```

If `components/ui/chart` is missing but shadcn is installed, add the chart component with the repo's package manager:

```bash
pnpm dlx shadcn@latest add chart
```

Use `npm`, `yarn`, or `bun` if that is the package manager in the repo.

## Component Shape

```tsx
"use client"

import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"

import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

const chartConfig = {
  winner: {
    label: "The story metric",
    color: "var(--chart-1)",
  },
  baseline: {
    label: "Baseline",
    color: "var(--muted-foreground)",
  },
} satisfies ChartConfig

const data = [
  { segment: "A", winner: 82, baseline: 41 },
  { segment: "B", winner: 75, baseline: 38 },
]

export function PersuasiveGapChart() {
  return (
    <ChartContainer config={chartConfig} className="h-[320px] w-full">
      <BarChart accessibilityLayer data={data} layout="vertical" margin={{ left: 8, right: 40 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" hide />
        <YAxis dataKey="segment" type="category" tickLine={false} axisLine={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="winner" fill="var(--color-winner)" radius={4}>
          <LabelList dataKey="winner" position="right" className="fill-foreground" />
        </Bar>
        <Bar dataKey="baseline" fill="var(--color-baseline)" radius={4} />
      </BarChart>
    </ChartContainer>
  )
}
```

## Rhetorical Defaults

- Put the strongest narrative color on the winning series.
- Use direct labels on the marks that carry the claim.
- Use `ChartTooltipContent` to show exact values, units, and denominators.
- Keep gridlines faint; never remove all scale context when exact comparison matters.
- Use `layout="vertical"` for long category names and ranked comparisons.
- Use `className="h-[280px] sm:h-[360px] w-full"`, `min-h-*`, or an aspect class so the SVG always has a real height.
- For current shadcn chart components on Recharts v3, prefer `var(--chart-1)` style token references. If an existing repo still uses HSL triplet variables, follow the local pattern consistently.

## Common Fixes

- Blank chart: parent height is missing. Add a fixed or responsive height class to `ChartContainer`.
- Labels overlap on mobile: hide nonessential axis ticks below `sm` and keep values in the tooltip.
- Colors do not render: use `var(--color-key)` inside chart marks where `key` exists in `chartConfig`.
- TypeScript complains about `ChartConfig`: import it from the local `components/ui/chart` file and use `satisfies ChartConfig`.
