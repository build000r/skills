# CLI Surface Design Template

Fill this before coding a new agent-facing CLI or tightening an existing one.
Copy this file into your project and replace the placeholders.

---

## Identity

- **Tool name:**
- **Primary consumer:** agent / human / both
- **Wraps an existing CLI?** yes → which? / no

## Home View (no args)

- **What it shows:**
- **Compact enough for agent context?** yes / no
- **Agent can decide next command from this alone?** yes / no

## List Schema

| Column | Default | Notes |
|--------|---------|-------|
| id | yes | |
| name / title | yes | |
| status | yes | |
| | | |

- **Hidden-by-default columns:**
- **Max items before truncation:**
- **Empty state message:**

## Detail View

- **Main content shown by default:**
- **Truncated fields and preview length:**
- **Escape hatch flag:** `--full` / other

## Mutation Verbs

| Verb | Idempotent? | Success output | Already-done output |
|------|-------------|----------------|---------------------|
|      |             |                |                     |

## Error Catalog

| Scenario | Exit code | Message template |
|----------|-----------|------------------|
| Missing required flag | 1 | "`--<flag>` is required" |
| Resource not found | 1 | "not found: `<id>`" |
| Upstream failure | 2 | translated message |
|  |  |  |

## State (if applicable)

- **Manages local state?** yes / no
- **State location:**
- **Recovery commands:** export / import / doctor
- **Concurrency model:** lock file / single-process / n/a

## Hooks

- **Installs hooks?** yes / no
- **Idempotent?** yes / no
- **Disableable?** yes / no
- **Conflicts with host context system?** check

## Next-Step Suggestions

- **After list:**
- **After detail:**
- **After mutation:**
- **After error:**

## Output Format

- **Default format:** compact text / TOON / JSON / other
- **Alternate formats available:**

---

## Verification Smoke Path

After filling this template, confirm the contract with:

```bash
tool
tool list
tool list --limit 5
tool view <id>
tool view <id> --full
tool <mutate> <id>
tool <mutate> <id>      # idempotency check
tool bad-command
```
