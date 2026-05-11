# OSS Doc Audit Report Templates

Three templates. Pick the one(s) that match the output mode chosen in Step 5b
of `SKILL.md`. For large bulk-cleanup runs, emit all three: scorecard feeds
tier report feeds rubric.

## Rubric template (default, single repo score)

```markdown
Score: <n>/100

Fail Gates
- <gate> | none

Top Findings
- High: <problem>. Docs: <file>. Proof: <file>.
- High: <problem>. Docs: <file>. Proof: <file>.
- Medium: <problem>. Docs: <file>. Proof: <file>.

Ranked Cleanup Queue
1. <fix title>
   - Files: <docs>, <proof>
   - Why now: <reader impact>
   - Expected score recovery: +<n>
2. <fix title>
   - Files: <docs>, <proof>
   - Why now: <reader impact>
   - Expected score recovery: +<n>

Validation Run
- <command>: pass | fail
- <command>: pass | fail

Next Loop
- Fix items 1-2, rerun validators, rerun grade.
```

## Per-file scorecard template

Scores are 1 (worst) to 5 (best) on Helpfulness, Accuracy, Brevity,
Redundancy (5 = not redundant), Necessity. Sort ascending by row-sum so the
worst files rise to the top.

```markdown
## Per-File Scorecard: <repo>

| File | Lines | Problem | H | A | B | R | N | Sum |
|---|---|---|---|---|---|---|---|---|
| docs/guides/compliance-legal.md | 732 | Fabricated SOC2/ISO/PCI certs | 1 | 1 | 1 | 5 | 1 | 9 |
| docs/guides/performance-scaling.md | 681 | Invented benchmarks | 1 | 1 | 1 | 5 | 1 | 9 |
| ... | | | | | | | | |

Scorecard summary
- Files scored: <n>
- Mean row-sum: <x.y>
- Files with sum ≤ 10 (delete candidates): <n>
- Files with sum ≥ 20 (keep candidates): <n>
```

## Tier fate template

```markdown
## Tier Fate Report: <repo>

### Tier 1 — Delete or rewrite (harmful/fictional)
| File | Lines | Problem |
|---|---|---|
| ... | ... | ... |

### Tier 2 — Heavy slop (AI filler)
...

### Tier 3 — Deprecated but referenced
...

### Tier 4 — Near-empty stubs
...

### Tier 5 — Redundant copies
...

### Tier 6 — Needs trimming (hand to de-slopify after)
...

### Tier 7 — Keep
(count only, no table)

## Volume Summary

Deleted <N> files (~<M> lines) across <K> categories. Largest categories:
- <category>: <n> files (worst offender: <file>)
- <category>: <n> files (worst offender: <file>)
Edited <E> files to fix broken index links. Repo now has <F> docs.
```
