# Example: Minimal Complete Skill

This is a complete, working skill that demonstrates core principles in ~50 lines.

## The Skill: `csv-analyzer`

```
csv-analyzer/
├── SKILL.md
└── scripts/
    └── summarize.py
```

### SKILL.md

```markdown
---
name: csv-analyzer
description: Analyze CSV files to extract statistics, find patterns, and generate summaries. Use when asked to "analyze CSV", "summarize data", "CSV statistics", or when working with .csv files that need exploration or reporting.
---

# CSV Analyzer

## Quick Start

For basic analysis, use pandas directly:

\`\`\`python
import pandas as pd
df = pd.read_csv('data.csv')
print(df.describe())
\`\`\`

## Detailed Summary

For comprehensive summaries, run the bundled script:

\`\`\`bash
scripts/summarize.py data.csv
\`\`\`

Output includes: row/column counts, data types, missing values, numeric statistics, and top categorical values.

## Common Tasks

- **Find duplicates**: `df[df.duplicated()]`
- **Missing value report**: `df.isnull().sum()`
- **Correlation matrix**: `df.corr()` (numeric columns only)
```

### scripts/summarize.py

```python
#!/usr/bin/env python3
"""Generate comprehensive CSV summary."""
import sys
import pandas as pd

def summarize(path):
    df = pd.read_csv(path)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"\nColumns: {', '.join(df.columns)}")
    print(f"\nData types:\n{df.dtypes}")
    print(f"\nMissing values:\n{df.isnull().sum()}")
    print(f"\nNumeric summary:\n{df.describe()}")

if __name__ == "__main__":
    summarize(sys.argv[1])
```

## Why This Works

1. **Trigger-rich description**: Includes action phrases ("analyze CSV") and file patterns (".csv files")
2. **Concise body**: ~30 lines of instructions, assumes the agent knows pandas
3. **Script for repetitive task**: `summarize.py` avoids rewriting the same analysis code
4. **No over-explanation**: Doesn't explain what CSV is or how pandas works
5. **Progressive disclosure**: Quick start for simple needs, script for detailed analysis
