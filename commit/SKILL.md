---
name: commit
type: utility
description: >
  Batch-commit working changes with clean, high-level messages. Use when:
  "commit", "commit my changes", "commit what you did", "save progress",
  "/commit", or at the end of a work session. Handles multi-repo dirty state,
  groups files into logical batches, and writes concise commit messages.
---

# Commit

Commit the working changes across repos touched during this session.
The working tree likely has changes from multiple sources — your work,
other agents, manual edits. Your job: identify what YOU changed, batch
it logically, and commit with clean messages.

## Process

1. Survey dirty state
2. Claim your files
3. Batch and commit

### Step 1: Survey dirty state

For each repo you worked in during this session, run:

```bash
git -C <repo> status --short
git -C <repo> diff --stat
```

If you worked in only one repo, just check that one.
If unsure which repos you touched, check the working directories from the session.

### Step 2: Claim your files

From the dirty files, pick only the files you actually created or modified.
**Add whole files** — never stage partial hunks. If you touched a file, commit
the whole file. If you didn't touch it, leave it alone.

When unsure whether a file is yours: skip it. Better to under-commit than to
commit someone else's in-progress work.

### Step 3: Batch and commit

Group your claimed files into **1–3 commits max** by logical unit.
A logical unit is a cohesive change — e.g., "new skill", "API endpoint + tests",
"config updates". One commit is fine. Three is the ceiling, not the target.

For each batch:

```bash
git -C <repo> add <file1> <file2> ...
git -C <repo> commit -m "$(cat <<'EOF'
<message>
EOF
)"
```

## Commit message rules

Always use conventional-commit format: `type(scope): description`

**Types:** `feat`, `fix`, `chore`, `refactor`, `test`, `docs`
**Scope:** the domain, module, or feature area (1-2 words)

**Good messages are short and describe the change at a high level.**

Do:
- `feat(commit): add batch-commit skill`
- `fix(email): handle HTML response from preview endpoint`
- `feat(telemetry): add frontend error reporting`
- `chore(sdk): bump version to 1.5.1`
- `fix(websocket): pg_notify reliability + cross-worker broadcast`

Don't:
- `feat(commit): add commit skill with SKILL.md containing frontmatter and instructions for batching changes across repos` (too long)
- `fix(reports): fix bug where timezone offset was incorrectly applied during DST transition causing dates to shift by one day in the Pacific timezone` (describing the issue, not the change)
- `refactor(utils): update line 42 to use .get() instead of bracket access` (implementation detail)
- `chore(auth): refactor, clean up, and improve error handling` (vague laundry list)

Format: **`type(scope): description` — imperative mood, no period, under 72 characters total.** One line only.

## Multi-repo

If you worked across multiple repos, commit each repo separately.
Same rules apply per repo. Don't try to create a unified commit across repos.

## After committing

Run `git status --short` in each repo to confirm clean state for your files.
Report what you committed: which repos, how many commits, and the messages.
Do NOT push unless explicitly asked.
