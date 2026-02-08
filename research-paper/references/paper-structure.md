# Default Paper Structure

Use this structure when no mode is active (generic web-research-only papers). Modes override this with their own section templates.

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
   - What this means for practitioners / builders / researchers
   - Predictions grounded in the data
   - What signals to watch
7. **Conclusion**: Synthesis — how to think about this differently.
8. **References**: List sources with links (markdown format).

## Table Patterns

Use consistent Tailwind classes for all tables:

```
const thClass = "border border-gray-300 bg-gray-800 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-white";
const tdClass = "border border-gray-200 px-3 py-2 text-sm";
const trEven = "bg-gray-50";
```

Modes should override these with their brand colors.

## Highlight Boxes

For key findings or callouts:

```html
<div class="rounded border-l-4 border-blue-500 bg-blue-50 p-4">
  <p class="text-sm font-semibold text-blue-800">Key Finding</p>
  <p class="mt-1 text-sm text-blue-900">Content...</p>
</div>
```
