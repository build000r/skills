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
Does the user set boundaries for agent work?

| Score | Criteria |
|-------|----------|
| 2 | Explicit scope: files in play, exclusions, stop conditions |
| 1 | Partial boundaries, some areas undefined |
| 0 | No scope, agent must guess limits |

**Look for:** "Only touch X", "Don't modify Y", "Stop after Z"
**Red flags:** Open-ended "fix everything", no files specified

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
Does the user request progress updates?

| Score | Criteria |
|-------|----------|
| 2 | Explicit checkpoints: "Pause after X", "Show me Y before continuing" |
| 1 | Implicit checkpoints via multi-step instructions |
| 0 | No checkpoints, run until done |

**Look for:** "Stop and show me", "Confirm before", "Let's discuss X first"
**Red flags:** Long tasks with no intermediate validation

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
