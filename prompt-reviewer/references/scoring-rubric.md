# HUM-L Scoring Rubric

Score each axis by analyzing user prompts. Quote specific prompts as evidence.

## Axis Definitions

### 1. Clarity (0-3)
How well does the user articulate what they want?

| Score | Criteria |
|-------|----------|
| 3 | Goal explicit, deliverable named, validation steps included |
| 2 | Goal stated but missing validation or specifics |
| 1 | Vague request requiring clarification |
| 0 | No actionable request (e.g., just "ls", "continue") |

**Look for:** Named files/functions, success criteria, explicit outcomes
**Red flags:** "the thing", "fix it", bare commands, "continue"

### 2. Context & Inputs (0-3)
Does the user provide what's needed to start?

| Score | Criteria |
|-------|----------|
| 3 | Files, data, reproduction steps, and environment all provided |
| 2 | Some context given, missing key details |
| 1 | Minimal context, requires discovery |
| 0 | No context beyond workspace |

**Look for:** Pasted code, file paths, error messages, screenshots
**Red flags:** "Check X" with no details, environment-only starts

### 3. Autonomy & Scope Control (0-2)
Does the user scope by concern rather than location?

| Score | Criteria |
|-------|----------|
| 2 | Scopes by domain/concern, asks for approach, lets agent decide files |
| 1 | Partial boundaries, some micromanaging of location |
| 0 | No scope, or over-constrains with "only touch X" patterns |

**Look for:** "We're fixing the OAuth refresh", "What files need to change?", domain-scoped goals
**Red flags:** "Only modify src/X/", "Don't touch Y" — these micromanage; scope by concern instead

### 4. Constraint Handling (0-2)
Are safety/quality constraints stated?

| Score | Criteria |
|-------|----------|
| 2 | Safety rules, test requirements, or approval gates stated |
| 1 | Implied constraints via context (e.g., referencing AGENTS.md) |
| 0 | No constraints mentioned |

**Look for:** "Don't hit production", "Run tests first", "Ask before deploying"
**Red flags:** Direct production changes requested without safeguards

### 5. Iterative Checkpoints (0-2)
Does the user use phase-based checkpoints?

| Score | Criteria |
|-------|----------|
| 2 | Phase-based: "Create a plan", "What's your approach?", uses Plan Mode |
| 1 | Some structure via multi-step instructions |
| 0 | No checkpoints, or micromanaging step-by-step pauses |

**Look for:** "Create a plan first", "What's your approach?", mode-switching (explore → plan → implement)
**Red flags:** "Pause after step 1", "Show me before continuing" — these interrupt flow; use phases instead

### 6. Follow-up Efficiency (0-3)
Do follow-up messages maintain momentum?

| Score | Criteria |
|-------|----------|
| 3 | Follow-ups add new context or pivot direction meaningfully |
| 2 | Follow-ups provide feedback and minor adjustments |
| 1 | Follow-ups are vague or repeat previous requests |
| 0 | Filler messages: bare "continue", "ls", "ok" |

**Look for:** Specific feedback, new requirements, targeted questions
**Red flags:** "continue", single-word responses, re-asking same question

### 7. Collaboration Traits (0-3)
How does the user interact with the agent?

| Score | Criteria |
|-------|----------|
| 3 | Constructive feedback, acknowledgment, respectful redirects |
| 2 | Neutral interactions, mostly transactional |
| 1 | Frustration expressed but still working together |
| 0 | Hostile or dismissive responses |

**Look for:** "Good, but can you also...", "That's not quite right, try..."
**Red flags:** ALL CAPS, profanity at agent, ignoring agent questions

### 8. Adaptability & Learning (0-2)
Does the user adjust based on session progress?

| Score | Criteria |
|-------|----------|
| 2 | Explicitly adjusts scope/approach based on discoveries |
| 1 | Some flexibility shown when needed |
| 0 | Rigid adherence despite changing context |

**Look for:** "Let's pivot to...", "Based on that, change to...", "Forget X, do Y"
**Red flags:** Repeating failed approaches, ignoring agent suggestions

### 9. Outcome Alignment (0-3)
Does the session reach a clear conclusion?

| Score | Criteria |
|-------|----------|
| 3 | Explicit handoff: commit made, tests passing, deliverable confirmed |
| 2 | Task completed but no explicit confirmation |
| 1 | Partial completion, some items unresolved |
| 0 | Abandoned mid-task, no outcome |

**Look for:** "Looks good, commit it", "Tests pass", "That's what I needed"
**Red flags:** Session ends without resolution, last message is a question

## Composite Score Calculation

```
Composite = (Sum of axis scores) / (Sum of max scores)
         = (Clarity + Context + ... + Outcome) / 23
```

## Superlatives

When reviewing multiple sessions, identify:

- **Prompt MVP**: Best single prompt (high clarity + context)
- **Most Confusing**: Prompt requiring most clarification
- **Best Save**: Mid-session course correction that prevented waste
- **Prompt Facepalm**: Worst follow-up efficiency moment
- **Lowest Hanging Fruit**: Easiest improvement with highest impact
