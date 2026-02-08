---
name: divide-and-conquer
description: >
  Decompose complex tasks into independent, parallel sub-agents with no overlapping
  concerns, race conditions, or inter-agent dependencies. Use BEFORE spawning Task
  agents when the work involves multiple files, domains, or concerns that could be
  parallelized. Triggers on: planning multi-agent work, "split this into agents",
  "parallelize this", "divide and conquer", or when about to launch 2+ Task agents
  for a complex task. Also use when a task feels too large for a single agent but
  the right decomposition isn't obvious.
license: MIT
---

# Divide and Conquer

Decompose a task into sub-agents that run fully in parallel with zero conflicts.

## Agent Types

Know what each type can and cannot do:

| Type | Can Read | Can Write | Can Bash | Sees Conversation | Best For |
|------|----------|-----------|----------|-------------------|----------|
| **Explore** | Yes | **No** | No | No | Research, codebase exploration — inherently safe |
| **general-purpose** | Yes | Yes | Yes | **Yes** | Implementation, complex multi-step work |
| **Bash** | No | No | Yes | No | Running commands, builds, tests, git operations |
| **Plan** | Yes | **No** | No | No | Designing implementation approaches |

Key implications:
- **Explore agents are physically read-only** — they cannot Edit, Write, or NotebookEdit. Use them for research without worrying about file conflicts.
- **general-purpose agents see full conversation history** — prompts can reference earlier context concisely instead of repeating everything.
- **Bash agents only have Bash** — they can't use Read/Edit/Glob/Grep tools. They run shell commands only.

## Process

### 1. Analyze the Task

Read the conversation to understand:
- What the user wants accomplished
- What files/areas of the codebase are involved
- What the dependencies between subtasks are

### 2. Identify Split Boundaries

Find natural seams where work can be divided. Good boundaries:
- **Domain boundaries**: Frontend vs backend vs database vs tests
- **Concern boundaries**: Research vs implementation, different features
- **Goal boundaries**: Different outcomes that don't interact

Scope agents by **concern**, not by file list. "Handle authentication changes" is better than "Modify src/auth.ts". The agent discovers which files are relevant; you verify no overlap in the conflict check.

### 3. Verify Independence

For each proposed agent pair, confirm:
- No two agents write to the same file
- No agent needs another agent's output to start
- No shared mutable state between agents
- Each agent's instructions are self-contained (or uses general-purpose type which sees conversation)

If any check fails, merge those agents or restructure the split.

See `references/decomposition-patterns.md` for safe/unsafe patterns and the full checklist.

### 4. Output the Plan

Present the decomposition as a numbered list of agents. For each agent specify:

```
## Agent [N]: [Short Label]

**Type**: Explore | general-purpose | Bash
**Model**: haiku (simple research) | sonnet (default) | opus (complex reasoning)
**Background**: true if non-blocking, false if results needed before next step
**Concern**: [Domain/goal this agent owns — scope by concern, not file list]
**Task**: [Goal-focused instructions. For general-purpose, can reference conversation context concisely.]
**Writes**: [Expected files — verified for no overlap, but agent discovers actual files needed. "None" for Explore/Bash types.]
```

Then add a **Conflict Check** section:

```
## Conflict Check
- Write overlap: None | [list conflicts]
- Data dependencies: None | [list dependencies]
- Type safety: [Confirm write-agents are general-purpose, research-agents are Explore]
- Verdict: Ready to launch | Needs restructuring
```

### 5. Launch

All parallel agents MUST be launched in a single message with multiple Task tool calls.
Agents that depend on prior results must be launched sequentially in a follow-up message.

### 6. After Agents Return

Once all agents complete:
1. Read each agent's output
2. Verify the work is consistent across agents
3. Run any integration checks (tests, type-checking, linting)
4. Report the combined result to the user

## Rules

- **2-5 agents** is the sweet spot. More than 5 signals over-decomposition.
- **Scope by concern, not files**. "Handle auth changes" > "Modify src/auth.ts". Agent discovers files; you verify no overlap.
- **Never split same-concern work** across agents. One domain = one owner.
- **Use Explore for research agents** — physically cannot write, so file conflicts are impossible.
- **Use general-purpose for write agents** — they see conversation history, so prompts can be concise.
- **Use haiku model for simple research** — faster and cheaper. Reserve sonnet/opus for complex work.
- **Use `run_in_background: true`** for agents whose results aren't needed before the next step.
- **Prefer fewer write-agents**. Read-only Explore agents are cheap to parallelize.
- **When in doubt, don't split**. A single well-prompted agent beats a bad decomposition.
- **Sequential is fine** when there are real dependencies. Don't force parallelism.
