---
name: commit
type: utility
description: Commit working changes with clean, logical batches, including from a fresh repo context where no prior ownership is established. Use for "commit", "checkpoint", "commit everything", "commit my changes", "save progress", "/commit", "initial cleanup commit", or when a dirty tree needs batching, .gitignore decisions, and OSS/privacy-aware staging.
---

# Commit

Commit the working changes in the repo or repos touched during this run.
Treat `checkpoint` / `save progress` asks and dirty-tree cleanup commits as direct triggers for this workflow.

Default behavior matters:

- If the user says `commit what you did`, `commit my changes`, or otherwise narrows scope to the agent's own edits, use **claimed-changes mode**.
- If the repo is dirty, the context is fresh, no owned-file set is obvious, or the user just says `commit`, `save progress`, or `commit everything`, use **repo-steward mode**.
- In repo-steward mode, do **not** no-op just because session ownership is unclear. Treat the job as: classify the whole dirty tree, ignore local-only artifacts, scrub privacy risks, batch the intentional changes, and commit them.

Start with a stable acknowledgement in commentary:

```text
Using commit: surveying dirty state, deciding commit scope, and batching intentional changes.
```

## Process

1. Survey dirty state
2. Choose commit mode
3. Classify every dirty path
4. Update ignore files and scrub privacy risks
5. Batch and commit
6. Verify no unexplained leftovers

## Step 1: Survey dirty state

For each repo you worked in during this session, run:

```bash
git -C <repo> status --short --branch
git -C <repo> diff --stat
git -C <repo> ls-files --others --exclude-standard
```

If you worked in only one repo, inspect just that repo.
If the current directory is inside `opensource/`, remember the top-level `opensource/`
folder may not itself be a git repo; commit the actual nested repo you changed.

If `git -C <repo> rev-parse --verify HEAD` fails, treat it as a repo with no commits yet.
The batching rules still apply.

## Step 2: Choose commit mode

### Claimed-changes mode

Use this only when the scope is clearly limited to your own edits.

- Claim whole files, not hunks.
- If a file was touched by you and also by others, read it carefully before claiming it.
- If ownership is unclear, skip the file unless the user explicitly asked for the whole repo.

### Repo-steward mode

Use this when the user did not narrow scope and the repo is dirty.

- Own the classification pass for **all** tracked and untracked changes in the repo.
- Do not ask the user to decide file-by-file unless there is a real risk boundary.
- The goal is either:
  - a clean repo after the commit sequence, or
  - a short explicit list of leftovers with a concrete reason such as `merge conflict`,
    `contains credentials`, `needs legal review`, or `intentionally left uncommitted`.

## Step 3: Classify every dirty path

Every dirty or untracked path must end up in one of these buckets:

- **Commit now**: intentional source, docs, tests, config, migrations, fixtures, or other real project files
- **Ignore locally**: machine-specific, secret, generated, cache, log, export, or review artifact
- **Leave out for a specific reason**: risky, conflicting, unrelated, or not safe to publish yet

In repo-steward mode, do this classification for the whole dirty tree before committing.

### Strong commit-now signals

- Source files, tests, docs, schemas, migrations, lockfiles, CI config, reusable scripts
- Example env templates such as `.env.example` or `.env.sample`
- Small representative fixtures that are clearly intended for the repo
- Existing tracked files with intentional edits

### Strong ignore-locally signals

- Secrets or local env files: `.env`, `.env.*`, `*.local`, `*.secret`, credential dumps
- Editor and OS noise: `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`
- Dependency caches and virtual environments: `node_modules/`, `.venv/`, `venv/`, `__pycache__/`
- Test/build outputs: `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.next/`, `coverage/`, `.coverage*`, `dist/`, `build/`, packaged `.skill` files
- Logs, temp reports, downloaded artifacts, browser dumps, screenshots, local review notes, DB exports

### Leave-out reasons that justify stopping or excluding

- Mixed unrelated product work that would make the commit misleading
- Files containing credentials, legal/privacy risk, or internal business data
- Large binaries or vendored content with unclear licensing
- Ongoing conflict resolution or half-applied refactors

## Step 4: Update ignore files and scrub privacy risks

If untracked local-only artifacts are present and the repo does not already ignore them,
update `.gitignore` or the repo-appropriate ignore file **before** staging the rest.

Rules:

- Add generic ignore rules, not workstation-specific paths.
- Do not ignore files that are already intentionally tracked by the repo.
- Prefer the smallest durable pattern that solves the current noise.
- In open-source or potentially public repos, treat privacy hygiene as part of the commit, not optional cleanup.

Before staging candidate files, inspect them for obvious privacy or release problems:

```bash
git -C <repo> diff --stat -- <candidate-files...>
rg -n '/Users/|/home/|/srv/|AKIA|AIza|sk-|ghp_|xoxb-|-----BEGIN|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}|https?://[^ ]*(internal|staging|prod|private)|([0-9]{1,3}\\.){3}[0-9]{1,3}' <candidate-files...>
```

When the scan hits:

- scrub secrets, workstation paths, internal hosts, personal identifiers, and private business names before committing
- convert environment-specific values to placeholders, docs, or examples when appropriate
- if the file should never be public, do not stage it; ignore it or leave it out with an explicit reason

When the active repo is the local `opensource/skills` collection, a nested repo inside that
collection, or another open-source repo inside the local `opensource/` workspace, switch into
**safe-for-oss mode**.

### Safe-for-oss mode

- Treat privacy and release hygiene as mandatory.
- Do not claim generated artifacts unless the user explicitly asked for them.
- Prefer committing source, tests, docs, references, templates, and intentional config changes.
- If adding `.gitignore` rules, keep them generic and publishable.
- If a new file includes internal names, customer data, proprietary URLs, or machine-local paths, scrub or exclude it.

## Step 5: Batch and commit

Group staged files by **logical unit**, not by extension and not by directory alone.
Use as few commits as preserve meaning. Usually `1-4` commits is right. Do not create a pile of micro-commits.

Good batch shapes:

- feature code + tests
- docs + references for the same feature
- repo hygiene such as `.gitignore`, formatting, or generated-noise cleanup
- one independent subsystem per commit when the dirty tree clearly spans multiple unrelated changes

For each batch:

```bash
git -C <repo> add <file1> <file2> ...
git -C <repo> commit -m "$(cat <<'EOF'
<message>
EOF
)"
```

If `.gitignore` changes are purely supportive for other work, include them with the relevant batch.
If the ignore cleanup is large and stands on its own, a separate `chore(...)` commit is acceptable.

## Commit message rules

Always use conventional-commit format: `type(scope): description`

**Types:**

| Type       | When to use                          |
| ---------- | ------------------------------------ |
| `feat`     | New feature for users                |
| `fix`      | Bug fix                              |
| `refactor` | Code change, no feature or fix       |
| `perf`     | Performance improvement              |
| `test`     | Adding or updating tests             |
| `docs`     | Documentation only                   |
| `style`    | Formatting, whitespace, no logic     |
| `chore`    | Maintenance, deps, tooling           |
| `ci`       | CI/CD pipeline changes               |
| `build`    | Build system or dependency changes   |

Quick decision: new user-visible behavior → `feat`. Broken behavior fixed → `fix`. Faster → `perf`. Cleaner code, same behavior → `refactor`. Only tests → `test`. Only docs → `docs`. Everything else → `chore`, `ci`, or `build`.

**Scope:** the domain, module, or feature area (1-2 words).

### Subject line

- Imperative mood: "add" not "added"
- Lowercase first word, no period at end
- Max 50 characters for the subject
- Full `type(scope): subject` line under 72 characters

### Body (optional, use when non-obvious)

- Blank line after subject
- Wrap at 72 characters
- Explain WHAT changed and WHY, not HOW (the diff shows how)
- Use bullet points for multiple changes

### Footer (optional)

- Issue references: `Fixes #123`, `Closes #456`, `Refs #789`
- Breaking changes: add `!` after type (`feat(api)!: ...`) and include `BREAKING CHANGE:` footer
- Co-authors: `Co-authored-by: Name <email>`

### Good examples

- `feat(commit): batch dirty repo into safe commits`
- `chore(repo): ignore local build artifacts`
- `fix(auth): scrub private host references`
- `docs(skill): clarify repo-steward commit mode`

See `references/commit-examples.md` for full examples with bodies and footers.

### Anti-patterns

- `fix bug` / `update code` / `misc changes` — too vague, no scope
- `Fixed the login issue` — past tense, should be imperative
- `WIP` / `temp` / `asdf` — never commit placeholder messages
- `PR feedback` / `code review changes` — describe the actual change
- A subject that lists five unrelated areas at once

## Multi-repo

If you worked across multiple repos, commit each repo separately.
Do not try to create one synthetic commit across repos.

Use the same mode decision per repo:

- claimed-changes mode for explicitly scoped repos
- repo-steward mode for dirty repos the user asked you to cleanly commit

## Step 6: Required Verification (Post-Commit)

Run these checks after each repo's commit sequence. This verification is required before handback.

### Verify no unexplained leftovers

Run concrete post-commit checks:

```bash
git -C <repo> log -1 --stat --oneline
git -C <repo> status --short
git -C <repo> diff --stat
```

In safe-for-oss mode, also verify that no obvious generated or private material slipped in:

```bash
git -C <repo> show --name-only --format=oneline HEAD
git -C <repo> show HEAD -- . ':(exclude).mutate' ':(exclude)mutants.out'
```

Closeout contract:

- If the repo is clean, say so.
- If files remain dirty, list them and why they were left out.
- In repo-steward mode, unexplained leftovers are a failure. Either commit them, ignore them, or explicitly call out the risk that blocked them.
- Report which repos were committed, how many commits were created, and the commit messages.
- Do **not** push unless explicitly asked.
