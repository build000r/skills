---
name: prompt-reviewer
description: Review and score your AI prompting quality. Analyzes Claude Code and Codex conversation history to evaluate clarity, context, collaboration, and outcomes on a 23-point scale. Tracks scores over time for week-over-week progress. Use when asked to "review my prompts", "score my prompts", "benchmark myself", "rate my prompting", "analyze my conversations", "prompt quality check", "show my trend", "prompt progress", "backfill my history", "backfill next", "list weeks", or "/prompt-reviewer". Also triggers on "how am I doing as a prompter?" or "what can I improve?" or "show my prompt history" or "what weeks haven't I reviewed?".
---

# Prompt Reviewer

Evaluate user prompting quality across AI coding tools. Supports Claude Code, Codex, AMP, OpenCode, and any other tool.

## Workflow Overview

**Review flow** (default):
1. Gather parameters (time range, provider, scope)
2. Extract sessions (script for Claude/Codex, manual for others)
3. Score prompts (9 axes, 23 points)
4. Output quick summary (default) → offer full scorecard
5. Save scores to history (with provider/model metadata)
6. Show trend if history exists

**Trend-only flow** (when user asks for "trend", "progress", "history"):
1. Run show_trend.py and display results (optionally filter by provider)
2. Skip review steps

**Backfill flow** (when user asks to "backfill", "backfill next", "list weeks", "catch up"):
1. Run `list_weeks.py` to see available weeks and backfill status
2. If user said "backfill next [provider]" → immediately run the full review for that provider's next unreviewed week (no need to ask)
3. If user just said "list weeks" → show the table and stop
4. After review, ask about purging, then offer to continue with next week

## Step 1: Gather Parameters

Ask the user with AskUserQuestion:

**Provider** (determines extraction method)
- Claude Code (auto-extract from ~/.claude sessions)
- Codex (auto-extract from ~/.codex sessions)
- OpenCode (auto-extract from ~/.local/state/opencode — single batch, no timestamps)
- AMP (manual — score current/pasted conversation)
- Other (manual)

**Time range** (default: today, for auto-extract providers only)
- Today (recommended)
- Past week
- Past month
- All time

**Source** (when provider is auto-extractable)
- All three (Claude Code + Codex + OpenCode)
- Both Claude Code and Codex (recommended)
- Claude Code only
- Codex only
- OpenCode only

**Model** (optional, for trend metadata)
- Ask what model they were using, or infer from context
- Examples: opus, sonnet, gpt-4o, o3, gemini-2.5-pro

**Scope** (Claude Code only)
- Current project only
- All projects

## Step 2: Extract Sessions

**For Claude Code / Codex / OpenCode** (auto-extract):

```bash
python3 {skill_dir}/scripts/extract_sessions.py \
  --source {claude|codex|opencode|both|all} \
  --since {date} \
  --project {project_path_if_filtered} \
  --limit 20
```

Source options: `both` = claude + codex, `all` = claude + codex + opencode

**OpenCode limitation:** OpenCode stores prompts without timestamps or session boundaries.
All prompts are returned as a single batch using the file's mtime for date filtering.
Backfill-by-week is not meaningful for OpenCode.

**For AMP / Other** (manual):

No extraction script needed. Instead:
1. Ask the user to paste conversation excerpts, share a session file, or point to a log
2. If the user says "review this session" or "review my last conversation", score the prompts visible in the current conversation context
3. Score whatever user prompts are available — the rubric works the same regardless of source

## Step 3: Score Prompts

Read `references/scoring-rubric.md` for detailed criteria.

Score each session on 9 axes:

| Axis | Max | What to look for |
|------|-----|------------------|
| Clarity | 3 | Named files, explicit goals, validation steps |
| Context & Inputs | 3 | Pasted errors, file paths, reproduction steps |
| Autonomy & Scope | 2 | "Only touch X", "Don't modify Y", stop conditions |
| Constraint Handling | 2 | "Run tests first", "Ask before deploying" |
| Iterative Checkpoints | 2 | "Pause after X", "Show me before continuing" |
| Follow-up Efficiency | 3 | New context vs bare "continue" or "yes" |
| Collaboration Traits | 3 | Constructive feedback, respectful redirects |
| Adaptability | 2 | Pivots based on discoveries |
| Outcome Alignment | 3 | Clear conclusion, explicit handoff |

**Composite = sum(scores) / 23**

## Step 4: Output

**Quick summary first** → then offer full scorecard.

### Quick Summary Template (default)

```
## Prompt Review - Quick Score

**Composite: X.XX / 1.00**
Sessions: N | Prompts: M

### Top 3 Improvements

1. **[Axis]** (X/max): [Coaching tip]
   > Example: "[quoted prompt]"
   > Try instead: "[improved version]"

2. ...

3. ...

### What's Working Well
- **[Axis]** (X/max): [Positive observation]
```

### Full Scorecard Template (on request)

```
## Prompt Review - Full Scorecard

**Composite: X.XX / 1.00**
Sessions: N | Prompts: M | Source: Claude/Codex/Both

### Axis Breakdown

| Axis | Score | Evidence |
|------|-------|----------|
| Clarity | X/3 | "[quoted prompt]" |
| Context & Inputs | X/3 | "[quoted prompt]" |
| Autonomy & Scope | X/2 | "[quoted prompt]" |
| Constraint Handling | X/2 | "[quoted prompt]" |
| Iterative Checkpoints | X/2 | "[quoted prompt]" |
| Follow-up Efficiency | X/3 | "[quoted prompt]" |
| Collaboration Traits | X/3 | "[quoted prompt]" |
| Adaptability | X/2 | "[quoted prompt]" |
| Outcome Alignment | X/3 | "[quoted prompt]" |

### Superlatives

- **Prompt MVP**: "[best prompt]" - [why it worked]
- **Best Save**: "[course correction]" - [what it prevented]
- **Facepalm**: "[worst follow-up]" - [what to do instead]
- **Lowest Hanging Fruit**: [easiest fix with biggest impact]

### Coaching Plan

1. **[Priority improvement]**
   > Before: "[current pattern]"
   > After: "[improved pattern]"

2. ...
```

## Step 5: Save Scores to History

After outputting the review, persist scores AND qualitative insights:

```bash
python3 {skill_dir}/scripts/save_review.py \
  --composite {composite} --sessions {N} --prompts {M} \
  --clarity {score} --context {score} --autonomy {score} \
  --constraints {score} --checkpoints {score} --followup {score} \
  --collaboration {score} --adaptability {score} --outcome {score} \
  --source {source} --provider {provider} [--model {model}] [--project {path}] \
  [--week YYYY-WNN] \
  --improvements '[{"axis":"...","score":X.X,"tip":"...","example":"..."},...]' \
  --strengths '[{"axis":"...","score":X.X,"observation":"..."},...]'
```

**Improvements** (Top 3): Each entry has `axis`, `score`, `tip` (coaching advice), `example` (quoted prompt).

**Strengths** (What's Working Well): Each entry has `axis`, `score`, `observation`.

**--week** (for backfills): Override the week recorded. Without this, saves use today's week.

Always run this after scoring. Scores accumulate in `~/.claude/prompt-review-history.jsonl`.

Provider values: `claude`, `codex`, `amp`, `opencode`, `other`

## Step 6: Show Trend

After saving, if history has 2+ reviews, show the trend:

```bash
python3 {skill_dir}/scripts/show_trend.py --weeks 8
```

Filter to a single provider:

```bash
python3 {skill_dir}/scripts/show_trend.py --weeks 8 --provider codex
```

CSV export (for spreadsheet charting):

```bash
python3 {skill_dir}/scripts/show_trend.py --csv --weeks 12
```

### Trend Output Template

```
## Prompt Score Trend (2025-W01 to 2025-W04)

**Composite:** 0.78 (+0.09) ▃▄▅▆

| Week | Composite | Sessions | Prompts | Trend |
|------|-----------|----------|---------|-------|
| 2025-W01 | 0.69 | 8 | 42 |   -- |
| 2025-W02 | 0.72 | 6 | 35 | +0.03 |
| 2025-W03 | 0.74 | 10 | 51 | +0.02 |
| 2025-W04 | 0.78 | 7 | 38 | +0.04 |

### Per-Axis Trends

| Axis | Max | Current | Trend | Spark |
|------|-----|---------|-------|-------|
| Clarity | 3 | 2.5 | +0.3 | ▄▅▅▆ |
| Context | 3 | 2.0 | +0.2 | ▃▃▄▅ |
| ... | ... | ... | ... | ... |

### Movers

- **Most improved:** Clarity (+0.3/3)
- **Needs attention:** Constraints (-0.2/2)

### By Provider

| Provider | Reviews | Avg Score | Spark |
|----------|---------|-----------|-------|
| claude   | 12      | 0.76      | ▅▅▆▆ |
| codex    | 5       | 0.68      | ▄▅▅   |
| amp      | 3       | 0.72      | ▅▅▆   |
```

The "By Provider" section appears automatically when history contains multiple providers.

## Backfill Workflow

To build trend history from past sessions, use the backfill flow.

### Quick Backfill (recommended)

When user says **"backfill next codex"** or **"backfill next claude"**:

1. Run `list_weeks.py` to find the next unreviewed week for that provider
2. Immediately run extract_sessions.py for that week
3. Score all prompts, output review, save with `--week` override
4. Ask about purging
5. Offer: "Continue with next week?"

No questions needed — just do the next week.

### Manual Backfill

If user wants to see status first or pick a specific week:

#### Step 1: List Available Weeks

```bash
python3 {skill_dir}/scripts/list_weeks.py
```

Or get the full backfill prompt directly:

```bash
python3 {skill_dir}/scripts/list_weeks.py --provider codex --prompt
```

Output shows all weeks with session data, which providers have data, and which have been reviewed:

```
## Session Weeks Available

| Week | Claude | Codex | OpenCode | Reviewed |
|------|--------|-------|----------|----------|
| 2025-W36 | — | 10 | — | — |
| 2025-W37 | — | 173 | — | — |
| 2025-W38 | — | 131 | — | codex |
| 2026-W05 | 656 | 3 | — | claude, codex |

### Next to Backfill

- **codex**: 2025-W36 (10 sessions)

### Backfill Command

python3 ~/.claude/skills/prompt-reviewer/scripts/extract_sessions.py \
  --source codex \
  --since 2025-09-01 \
  --until 2025-09-07 \
  --limit 100
```

### Step 2: Review the Week

Run the suggested extract command, then score ALL prompts (not a sample). Use the standard review flow:

1. Extract sessions for the week
2. Score every user prompt on all 9 axes
3. Output the review with week label (e.g., "2025-W36 Backfill")
4. Save scores with `save_review.py`

### Step 3: Repeat

Run `list_weeks.py` again to see updated status and get the next week to review.

### Backfill Prompt Template

For handing off a single week to another agent:

```
You are doing a prompt quality backfill review for week {WEEK} ({PROVIDER} sessions).

## Step 1: Extract sessions

Run:
python3 ~/.claude/skills/prompt-reviewer/scripts/extract_sessions.py \
  --source {provider} \
  --since {start_date} \
  --until {end_date} \
  --limit 100

## Step 2: Score all user prompts

Read ~/.claude/skills/prompt-reviewer/references/scoring-rubric.md.

Score EVERY user prompt (not a sample) on all 9 axes. Compute averages.
Composite = sum(axis averages) / 23

## Step 3: Output the review

## Prompt Review - {WEEK} ({PROVIDER} Backfill)

**Composite: X.XX / 1.00**
Sessions: N | Prompts: M | Provider: {provider}

### Top 3 Improvements
1. **[Axis]** (X.X/max): [Coaching tip]
   > Example: "[quoted prompt]"
2. ...
3. ...

### What's Working Well
- **[Axis]** (X.X/max): [Positive observation]

## Step 4: Save scores (include qualitative insights!)

python3 ~/.claude/skills/prompt-reviewer/scripts/save_review.py \
  --composite {composite} --sessions {N} --prompts {M} \
  --clarity {avg} --context {avg} --autonomy {avg} \
  --constraints {avg} --checkpoints {avg} --followup {avg} \
  --collaboration {avg} --adaptability {avg} --outcome {avg} \
  --source {provider} --provider {provider} --week {WEEK} \
  --improvements '[{"axis":"...","score":X.X,"tip":"...","example":"..."},...]' \
  --strengths '[{"axis":"...","score":X.X,"observation":"..."},...]'

IMPORTANT: Use --week {WEEK} to record the original week, not today's date.

## Step 5: Ask about purging old sessions (optional)

After saving, ask the user if they want to delete the reviewed session files to free disk space.

First preview (always use --dry-run first):
```bash
python3 {skill_dir}/scripts/purge_sessions.py \
  --provider {provider} --week {WEEK} --dry-run
```

If user confirms, run without --dry-run:
```bash
python3 {skill_dir}/scripts/purge_sessions.py \
  --provider {provider} --week {WEEK}
```

NEVER delete without asking first.
```

## Scoring Examples

### Clarity

**3/3** - Goal + file + validation:
> "Open `src/auth/login.ts`, confirm the OAuth callback matches the README spec, and stop before making changes."

**1/3** - Vague request:
> "make the transition look better"

**0/3** - No actionable request:
> "continue"

**Coaching**: Instead of "make it better", try "fade the transition over 0.5s with ease-out, and show me before applying"

### Context & Inputs

**3/3** - Error + file + steps:
> "Getting `TypeError: undefined is not a function` at line 42 of `utils.ts` when I run `npm test`. Here's the failing test output: [pasted]"

**1/3** - Missing details:
> "there's a bug in the auth flow"

**Coaching**: Paste the error message, specify which file, include reproduction steps

### Follow-up Efficiency

**3/3** - Adds new context:
> "Good, but the animation is too fast. Slow it to 300ms and add a subtle bounce at the end."

**0/3** - Filler:
> "yes"

**Coaching**: Instead of bare "yes", try "yes, and also check that it works on mobile"

## Scoring Philosophy

**Be constructive, not punitive.** The goal is improvement.

- Quote specific prompts as evidence
- Highlight what's working, not just problems
- Make coaching actionable ("Instead of X, try Y")
- Acknowledge context (quick questions don't need full briefs)
