# Chart Choice Matrix

Pick the chart that makes the user's argument easiest to see while staying honest about the data.

| Narrative job | Best default | Persuasive move | Risk gate |
| --- | --- | --- | --- |
| One value beats one baseline | Bullet chart, indexed bar, or big-number plus mini bar | Make the delta label the focal point | Axis must show the baseline or state the focus range |
| Many categories have gaps | Sorted horizontal dumbbell or gap bar | Sort by gap descending and annotate the largest gap | Do not hide categories unless the selection rule is stated |
| Winner ranks above competitors | Ranked horizontal bars or lollipop | Put winner first, mute others, add rank label | Include all relevant competitors or disclose the shortlist |
| Trend is accelerating | Line or area chart | Annotate inflection and endpoint growth | Avoid cherry-picked start date; disclose the window |
| Recent period changed sharply | Slope chart or before/after bars | Show only the two decision-relevant periods | State both dates and avoid implying the missing middle is flat |
| Adoption or volume is compounding | Area chart | Fill the cumulative volume and label endpoint | Do not use area for non-additive values |
| Mix of volume and rate | Small multiples or aligned combo chart | Place volume and rate in adjacent panels with shared x-axis | Avoid dual axes unless clearly normalized and labeled |
| Parts of a whole changed | 100 percent stacked bars or mosaic | Use two time points and direct labels | Avoid pie charts for more than three segments |
| Distribution differs by group | Box, violin, or histogram small multiples | Annotate median shift or tail risk | Do not summarize skewed data with mean only |
| Multi-metric profile supports a vibe | Radar chart | Fill the favored profile and mute baseline | Only use comparable normalized axes; disclose that area perception exaggerates differences |
| Uncertainty affects trust | Dot-and-interval chart | Put the conclusion in the annotation, not by hiding intervals | Show intervals or sample sizes |
| Geographic concentration matters | Choropleth or proportional symbol map | Use a restrained palette and label top regions | Normalize by population or exposure when raw counts mislead |

## Chart Scoring

For each candidate, score 1-5:

- **Effect size visibility**: can the eye immediately see the claimed gap?
- **Audience familiarity**: will this audience understand it without training?
- **Scan speed**: can the point land in under five seconds?
- **Visual dominance**: can the key series dominate without hiding the rest?
- **Misread risk**: reverse score; high risk subtracts from the total.

Choose the highest total. If two charts tie, pick the simpler one.

## Radar Gate

Use radar charts only when all are true:

- 4-12 metrics.
- Same scale or normalized index.
- The goal is profile contrast, not exact value comparison.
- Axis labels are short.
- The caption or final answer names the perception risk.

If exact comparison matters, use sorted bars, dumbbells, or a table-plus-chart instead.
