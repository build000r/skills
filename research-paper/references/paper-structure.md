# Default Paper Structure

Use this structure when no mode is active (generic web-research-only papers). Modes override this with their own section templates.

This file covers the canonical paper only. Companion X article defaults live in `references/companion-outputs.md`.

## Sections

1. **Title**: "{Topic}: {Subtitle with specific angle or finding}"
2. **Abstract**: 150-200 words. What problem, what this paper covers, key findings.
3. **Introduction**: Problem statement with data. Why current approaches fall short. What this paper offers.
4. **Core Analysis Sections** (3-5 sections):
   - Each covers one facet of the topic
   - Include data tables with real numbers from research
   - Use numbered headings (e.g. "3. Section Title", "3.1 Subsection")
   - Subsections go one level deep max
5. **Framework / Synthesis**: Propose a framework, taxonomy, or decision model:
   - Risk matrix, 2x2 grid, decision tree, or tiered classification
   - Based on evidence from prior sections, not speculation
6. **Implications**: Forward-looking:
   - What this means for operators / builders / researchers
   - Predictions grounded in the data
   - What signals to watch
7. **Conclusion**: Synthesis — how to think about this differently.
8. **References**: List sources with links (markdown format).

## Table Patterns

### MDX pipeline projects (buildooor)

Use `<ResearchTable>` — no raw HTML or Tailwind needed:

```mdx
<ResearchTable
  caption="Table 1. Description"
  columns={[
    { label: 'Column A' },
    { label: 'Column B', align: 'right', mono: true },
    { label: 'Column C', muted: true }
  ]}
  rows={[
    ['Row 1 A', 'Row 1 B', 'Row 1 C'],
    ['Row 2 A', 'Row 2 B', 'Row 2 C']
  ]}
  footnote="Source: citation"
/>
```

Column options: `align` ('left' | 'center' | 'right'), `mono` (boolean), `muted` (boolean). Table-level options: `compact` (boolean), `footnote` (string).

### Non-MDX projects

Use consistent Tailwind classes for all tables:

```
const thClass = "border border-gray-300 bg-gray-800 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-white";
const tdClass = "border border-gray-200 px-3 py-2 text-sm";
const trEven = "bg-gray-50";
```

Modes should override these with their brand colors.

## Highlight Boxes / Callouts

### MDX pipeline projects

Use `<ResearchCallout>`:

```mdx
<ResearchCallout>
Key finding or emphasis text here. Renders as black box with white italic text.
</ResearchCallout>
```

### Non-MDX projects

```html
<div class="rounded border-l-4 border-blue-500 bg-blue-50 p-4">
  <p class="text-sm font-semibold text-blue-800">Key Finding</p>
  <p class="mt-1 text-sm text-blue-900">Content...</p>
</div>
```
