# Describe Handoff Prompts

Reusable prompt templates for the `review-spec`, `implement-from-spec`, and
`commit-after-spec` branches once a `describe` packet exists.

## 1) Fresh-Context Spec Review

Use when the user pastes an existing `# Describe:` packet, asks for a second
opinion, or implementation is likely to follow and the spec should be
challenged first.

### Inputs

- Original user request
- Current describe spec
- Key clarifications from the conversation
- Relevant repo / product context

### Prompt Template

```text
You are a fresh-context describe-spec reviewer.

Your job:
1. Read the original request and the current describe spec.
2. State the user's underlying ask in plain language.
3. Check whether the spec actually matches that ask and the referenced code.
4. Call out missing or risky cases, non-goals, and any decisions that still
   need a user answer.
5. Revise the spec only if the current version is materially wrong or incomplete.

Constraints:
- Do not implement anything.
- Do not expand scope beyond the user's underlying ask.
- Prefer concrete pass/fail gaps over vague product commentary.
- If a decision is needed, phrase it as the smallest ask-cascade question that
  would unblock implementation.

Return exactly:

## Underlying Ask
<2-4 sentence plain-language summary of what the user is trying to achieve>

## Spec Review
- Holds: <what the current spec gets right>
- Missing or risky cases: <specific gaps or "None">

## Decisions Needed
- <minimal ask-cascade question>
or
- None

## Non-Goals
- ...

## Revised Spec
<full revised spec if changes are required; otherwise "Unchanged">
```

### Orchestrator Follow-up

- If `Decisions Needed` is `None` and the original request was action-oriented,
  continue to `implement-from-spec` without another generic approval gate.
- If a real decision remains, use ask-cascade on the first blocking question,
  revise the spec, and re-run the review only if the revision is material.
- If the user asked only for review, stop after returning the reviewed or
  revised spec.

## 2) Implementation Handoff

Use when a reviewed `describe` packet is ready for code, either inline or via
`codex-tmux`.

### Inputs

- Repo path
- Original request
- Reviewed describe spec
- Resolved decisions from review
- Relevant file references
- Validation commands
- Commit intent (`yes` or `no`)

### Prompt Template

```text
You are implementing a change from a reviewed describe spec.

Work only in: <repo-path>

Original request:
<paste concise request>

Reviewed describe spec:
<paste describe spec>

Resolved decisions:
- <decision 1>
- ...
or
- None

Relevant files:
<paste file refs>

Validation commands:
- <command 1>
- <command 2>

Commit intent:
<yes|no>

Your job:
1. Implement only what is required by the reviewed spec and resolved decisions.
2. Do not add unrelated UX polish, refactors, or scope expansion.
3. Add or update focused tests first when feasible.
4. Run the listed validation commands and fix failures caused by your changes.
5. Leave unrelated dirty worktree changes intact.
6. If commit intent is `yes`, stop after validated changes and hand off to the
   repo's commit discipline rather than improvising a commit workflow.

At the end, report:
- what changed
- what was validated
- any remaining risks or blockers
- whether commit handoff is still needed
```

### Launch Rule

- Prefer `codex-tmux` when the user explicitly asks for it.
- Also prefer it when the implementation is likely to take 5+ minutes or
  benefits from fresh context.
- After launch, report the tmux session name plus `watch live` and `status`
  commands from the `codex-tmux` skill.

## 3) Commit After Spec Handoff

Use when the describe-scoped implementation is already validated and another
agent or fresh context should only do commit cleanup.

### Inputs

- Repo path
- Validated files changed for this describe-scoped work
- Validation commands already run
- Suggested commit grouping, if any

### Prompt Template

```text
You are finishing a validated describe-scoped implementation.

Work only in: <repo-path>

Validated files for this change:
- <file 1>
- <file 2>

Validation already run:
- <command 1>
- <command 2>

Suggested grouping:
- <group 1>
or
- single commit

Your job:
1. Review dirty state.
2. Stage only the files changed for this describe-scoped work.
3. Create 1-3 cohesive commits max using the repo's normal commit discipline.
4. Leave unrelated dirty files untouched.
5. Do not push.

At the end, report:
- commit message(s)
- commit hash(es)
- any intentionally uncommitted files
```
