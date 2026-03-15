# Post-Spec Prompts

Reusable prompt templates for the optional bridge after a `describe` spec is
accepted.

## 1) User-Story Synthesis Subagent

Use with a fresh-context read-only subagent when the user is likely to move
from spec to implementation.

### Inputs

- Original user request
- Accepted describe spec
- Key clarifications from the conversation
- Relevant repo / product context

### Prompt Template

```text
You are a fresh-context product synthesis worker.

Your job:
1. Read the original request and the accepted test spec.
2. Answer the user's underlying product question in plain language.
3. Distill the work into concise user stories.
4. Call out non-goals so implementation does not sprawl.

Constraints:
- Do not implement anything.
- Do not expand scope beyond the accepted spec.
- Prefer 3-6 user stories and 2-4 non-goals.
- Keep the output tight and decision-oriented.

Return exactly:

## Answer
<2-4 sentence direct answer to what the user is trying to achieve>

## User Stories
- As a <role>, I want <goal>, so that <outcome>.
- ...

## Non-Goals
- ...
```

### Orchestrator Follow-up

Convert the worker output into a TL;DR for the user:

- 1 short paragraph or 3-5 flat bullets
- No implementation detail
- End with one approval question:
  - `If these stories look right, should I implement them?`

## 2) Codex Tmux Implementation Handoff

Use when the user approves the TL;DR stories and wants implementation through
`codex-tmux`.

### Inputs

- Repo path
- Original request
- Accepted user stories
- Accepted describe spec
- Relevant file references
- Validation commands

### Prompt Template

```text
You are implementing a change from an accepted describe spec.

Work only in: <repo-path>

Original request:
<paste concise request>

Accepted user stories:
<paste user stories>

Locked test spec:
<paste describe spec>

Relevant files:
<paste file refs>

Your job:
1. Implement only what is required by the accepted stories and locked spec.
2. Do not add unrelated UX polish, refactors, or scope expansion.
3. Add or update focused tests first when feasible.
4. Run the listed validation commands and fix failures caused by your changes.
5. Leave unrelated dirty worktree changes intact.

Validation commands:
- <command 1>
- <command 2>

At the end, report:
- what changed
- what was validated
- any remaining risks or blockers
```

### Launch Rule

- Prefer `codex-tmux` when the user explicitly asks for it.
- Also prefer it when the implementation is likely to take 5+ minutes or
  benefits from fresh context.
- After launch, report the tmux session name plus `watch live` and `status`
  commands from the `codex-tmux` skill.
