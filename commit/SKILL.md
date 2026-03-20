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
3. Apply repo-specific safety rules
4. Batch and commit

### Step 1: Survey dirty state

For each repo you worked in during this session, run:

```bash
git -C <repo> status --short
git -C <repo> diff --stat
```

If you worked in only one repo, just check that one.
If unsure which repos you touched, check the working directories from the session.

Start the run with a stable acknowledgement in commentary:

```text
Using commit: surveying dirty repos and claiming my files first.
```

### Step 2: Claim your files

From the dirty files, pick only the files you actually created or modified.
**Add whole files** — never stage partial hunks. If you touched a file, commit
the whole file. If you didn't touch it, leave it alone.

When unsure whether a file is yours: skip it. Better to under-commit than to
commit someone else's in-progress work.

### Step 3: Apply repo-specific safety rules

When the active repo is the local `opensource/skills` collection, a nested repo inside that
collection, or another open-source repo inside the local `opensource/` workspace, switch into
**safe-for-oss mode**.

In safe-for-oss mode:

- Treat privacy and release hygiene as part of the commit contract, not optional cleanup.
- Do **not** claim generated artifacts unless the user explicitly asked for them:
  `.mutate/`, `mutants.out/`, `dist/`, `build/`, `.coverage*`, `coverage/`, temporary review files,
  cached logs, packaged `.skill` files, or other run outputs.
- Prefer committing only source files, tests, docs, references, and intentional config changes.
- Before staging, inspect the candidate paths for project-specific or private data:

```bash
git -C <repo> diff --stat -- <claimed-files...>
rg -n '/Users/|/srv/|@|AKIA|AIza|sk-|ghp_|xoxb-|https?://[^ ]*(internal|staging|prod|private)' <claimed-files...>
```

- If the scan finds likely secrets, personal identifiers, hardcoded workstation paths, or internal hostnames,
  stop and scrub those values before committing.
- If the repo contains unrelated dirty generated files, leave them unstaged and commit only the intentional source edits.
- In the local `opensource/` workspace, remember the top-level directory may not itself be a git repo;
  commit the actual nested repo you changed.

### Step 4: Batch and commit

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

Run concrete verification before closeout:

```bash
git -C <repo> diff --cached --stat
git -C <repo> status --short
```

For safe-for-oss mode, also verify that no generated artifact directories or obvious private strings slipped into the staged diff:

```bash
git -C <repo> diff --cached --name-only
git -C <repo> diff --cached -- . ':(exclude).mutate' ':(exclude)mutants.out'
```

Run `git status --short` in each repo to confirm clean state for your files.
Report what you committed: which repos, how many commits, and the messages.
Do NOT push unless explicitly asked.
