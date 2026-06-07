# CLI Ergonomics Review Checklist

Use this when auditing or refining an agent-facing CLI.

## Home View

- Does `tool` show live state instead of generic help?
- Can an agent decide the next command from the no-arg output alone?
- Is the opening surface compact enough to fit comfortably in context?

## Lists

- Is the default schema minimal?
- Does the output include an explicit count or truncation hint?
- Are large text fields excluded unless explicitly requested?
- Does the empty state say "0 results" clearly?

## Detail Views

- Is the main content present by default?
- Are long fields truncated instead of omitted or dumped whole?
- Is there a clear `--full` or equivalent escape hatch?

## Mutations

- Are already-satisfied requests idempotent?
- Does success output show the state the agent needs next?
- Are interactive prompts fully suppressed?

## Errors

- Do validation failures fail fast before calling upstream dependencies?
- Are errors translated into the wrapper's vocabulary?
- Does stdout contain structured, actionable error text?
- Are exit codes stable and semantically meaningful?

## Next-Step Guidance

- After a list command, does the CLI suggest relevant detail/follow-up actions?
- After a mutation, does it suggest the next likely inspection step?
- Are suggestions omitted on self-contained detail views where they would be noise?

## Hooks And Ambient Context

- Does the tool install hooks only when the host runtime actually wants them?
- Are hooks easy to disable?
- Will hook output collide with an existing context system?

## Verification Commands

Minimum smoke path:

```bash
tool
tool --help
tool list
tool view 123
tool view 123 --full
tool mutate 123
tool mutate 123
tool bad-command
```
