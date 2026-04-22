---
name: spaps-feedback
description: Pull user-reported issues from the SPAPS issue reporting platform and route each one to the right sibling skill via a per-client overlay registry. Use when asked to "pull spaps feedback", "check user issues", "what's in the feedback inbox", "triage spaps issues", "find issues about X", or "which skill should handle this issue".
---

# SPAPS Feedback Triage

Fetch issues from the SPAPS `issue_reports` table and hand each one off to the sibling skill most likely to own it. Reads production data read-only, never writes.

## Default Marker

Start with a stable first progress update such as:

`Using spaps-feedback to resolve the client overlay, read issues, then match them to sibling skills.`

## Use This For

- Listing recent SPAPS-reported issues for a given app, user, or time window
- Matching an issue (or a batch) to the sibling skill that should handle it
- Previewing the fix workflow by handing off to the matched skill for user confirmation

## Do Not Use This For

- Writing replies to issues (that is a SPAPS API write path — not in scope here)
- Closing, assigning, or otherwise mutating issue state
- Building the issue-reporting frontend package or backend router (use `issue-reporting-setup` and the relevant application/backend repo)
- Generic SPAPS backend debugging (use `ssh-info` or `deploy`)

## Fetch Method

Issues are pulled by read-only SQL against the production SPAPS database via the same SSH + container pattern that `ssh-info` uses. No HTTP, no JWT, no SPAPS SDK — this is an operator lookup skill.

The fetch flow:

1. Resolve the client overlay for the current cwd
2. Read `spaps_feedback.db` from the overlay (host container, db user, db name) with defaults inherited from the overlay's `deploy` section if present
3. SSH to `deploy.droplet_ssh` and run `docker exec ... psql ... -c "SELECT ..."` through the bundled helper
4. Parse rows into JSON for the matcher

## Skill Routing Registry

Each client overlay declares a `spaps_feedback.skill_registry` — a list of candidate sibling skills with the tags and path globs that identify them. The registry is what makes this skill portable across clients: the base script does not know about any client-specific sibling skill ids or paths; it only reads the registry.

Registry entry shape (see `references/overlay-schema.md` for the full spec):

```yaml
spaps_feedback:
  db:
    droplet_ssh: ops@example-host                 # overrides deploy.droplet_ssh if set
    container: spaps-db                           # docker container running postgres
    user: spaps
    database: spaps
    table: issue_reports                          # default; override if renamed
  skill_registry:
    - id: client/portfolio-skill
      path: ~/repos/client/.agents/skills/portfolio-skill
      tags: [service-a, service-b, renewal, audit]
      match_fields: [note, component_label, page_url]
      applications: [client-frontend]            # optional: only match for these application ids
```

Matching is deterministic: score = count of registry `tags` that appear (case-insensitive, word-boundary) in the concatenation of the issue's `match_fields`. Ties break by registry order. Operators confirm matches before any handoff.

## Execution Policy

Run only what the user asked for.

1. Resolve the client overlay first. If no overlay matches the cwd, create one via `skill-issue` and re-resolve — do not guess a host, DB, or registry.
2. Respect requested scope: a single issue id, a window (`--since 24h`), or "top N pending".
3. Read-only: `SELECT` statements only. No `UPDATE`, `INSERT`, `DELETE`, or `ALTER`.
4. Before handing off to a sibling skill, show the user the top match (and 1-2 runners-up) and ask for confirmation. Never silently invoke another skill.

## Common Requests

### List Recent Issues

```bash
scripts/fetch_issues.py --since 7d --limit 20
```

Prints a JSON array of issues with `id`, `component_label`, `page_url`, `note` preview, and `created_at`.

### Match One Issue to a Skill

```bash
scripts/fetch_issues.py --id <issue-uuid> --json \
  | scripts/match_skills.py --json
```

Prints ranked skill candidates from the overlay registry.

### Triage Batch

```bash
scripts/fetch_issues.py --since 7d --json \
  | scripts/match_skills.py --top 3 --json
```

Review the top candidates with the user. Only hand off to a sibling skill after explicit confirmation.

## Safety

- Production-first caution: default to read-only inspection
- No destructive SQL — fetch script refuses non-`SELECT` statements
- No writes to SPAPS or to sibling skill repos
- No automatic handoff — always confirm the matched skill first
- No guesses when overlay or registry is missing

## Validation

Before shipping changes to this skill:

```bash
SKILLS_ROOT="$HOME/repos/opensource/skills"
python3 "$SKILLS_ROOT/skill-issue/scripts/quick_validate.py" "$SKILLS_ROOT/spaps-feedback"

# Scripts should print usage cleanly when run with no args
python3 "$SKILLS_ROOT/spaps-feedback/scripts/fetch_issues.py" 2>&1 | head -5
python3 "$SKILLS_ROOT/spaps-feedback/scripts/match_skills.py" 2>&1 | head -5
```

## See Also

- `ssh-info` — for the underlying SSH + container conventions
- `issue-reporting-setup` — for wiring SPAPS issue reporting into a frontend
- `skill-issue` overlay mode — for creating or repairing the client overlay that this skill depends on
- `references/overlay-schema.md` — the full `spaps_feedback` overlay config shape

## Related

- [[skill-issue]]
