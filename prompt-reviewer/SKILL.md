---
name: prompt-reviewer
description: Review and score your AI prompting quality. Analyzes Claude Code and Codex conversation history to evaluate clarity, context, collaboration, and outcomes on a 23-point scale. Use when asked to "review my prompts", "score my prompts", "benchmark myself", "rate my prompting", "analyze my conversations", "prompt quality check", or "/prompt-reviewer". Also triggers on "how am I doing as a prompter?" or "what can I improve?"
---

# Prompt Reviewer

Evaluate user prompting quality by analyzing Claude Code and Codex conversation history.

## Workflow Overview

1. Gather parameters (time range, source, scope)
2. Extract sessions (run script)
3. Score prompts (9 axes, 23 points)
4. Output quick summary (default)
5. Offer full scorecard (on request)

## Step 1: Gather Parameters

Ask the user with AskUserQuestion:

**Time range** (default: today)
- Today (recommended)
- Past week
- Past month
- All time

**Source**
- Both Claude Code and Codex (recommended)
- Claude Code only
- Codex only

**Scope** (Claude Code only)
- Current project only
- All projects

## Step 2: Extract Sessions

```bash
python3 {skill_dir}/scripts/extract_sessions.py \
  --source {claude|codex|both} \
  --since {date} \
  --project {project_path_if_filtered} \
  --limit 20
```

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
