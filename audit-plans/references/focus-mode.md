# Focus Mode

Context-aware plan summary for the current working directory. Speak in user stories and rank the next work.

## Trigger

- `/audit-plans focus`
- natural language such as `what are we working on next here`, `what's next`, or `what's the plan here`

## Phase 1: Detect Context

### Determine the primary repo from `cwd`

Default rule:

```text
repo_name = basename(repo_root_or_nearest_meaningful_parent)
```

If the current directory is a generic folder such as `src`, `packages`, `services`, or `skills`, walk upward until the name looks like a repo root or ask the user.

Examples:

- `${REPOS_ROOT}/app-api` -> `app-api`
- `${REPOS_ROOT}/app-api/internal/jobs` -> `app-api`
- `${REPOS_ROOT}/workspace/services/billing-worker` -> `billing-worker`

### Determine related repos

Use `FOCUS_RELATED_REPOS` from the local mode when available.

Suggested format:

```bash
export FOCUS_RELATED_REPOS=$'app-api=app-web,ops-console\napp-web=app-api\nbilling-worker=app-api,app-web'
```

If no mapping exists, include only the detected repo plus any plans explicitly tagged `[multi-repo]`.

## Phase 2: Gather Plans

Launch two things in parallel when the catalog is large enough:

### 2a. Index scan

1. Read all configured indexes.
2. Match rows whose description tags mention the primary repo or a related repo.
3. Bucket matches into `DONE`, `IN_PROGRESS`, `FUTURE`, and `PLANNING`.

### 2b. Optional discovery pass

If the catalog often contains under-tagged plans, run a read-only discovery worker:

```text
Find plans that should likely be tagged with {repo_name} but currently are not.

1. Read the session index.
2. For plans lacking the repo tag, inspect the opening section.
3. Flag only plans with clear evidence:
   - file paths under the repo
   - repeated repo references
   - parent slice clearly tagged with the repo
Return plan name plus evidence.
```

## Phase 3: Build User Stories

For each non-done matching plan:

1. read the opening section of the plan
2. identify the actor, capability, and outcome
3. extract key deliverables and dependencies
4. preserve any explicit priority number

Story format:

```text
As a {actor}, I want {capability} so that {outcome}.
```

Prefer concrete actors from the plan itself. If the plan is vague, choose the least-speculative generic actor such as `user`, `operator`, or `admin`.

## Phase 4: Collect Discovery Results

If the discovery worker found clearly related untagged plans:

- add them to the ranked list when the context is strong enough
- otherwise show them in a short discovered footer with evidence

## Phase 5: Rank The Backlog

Rank all non-done stories into one list using these factors, in order:

1. already in progress
2. dependencies satisfied
3. deferred from recently completed parent work
4. explicit priority number
5. unblock value for other plans
6. scope and likely time-to-ship
7. domain or repo coherence with ongoing work

## Phase 6: Present The Result

Output one ranked table.

```text
## Focus: {repo_name}

Working in `{cwd}` | Related: {related_repos}

| # | Story | Plan | Why This Order |
|---|-------|------|----------------|
| 1 | As an operator, I want failed payment retries reconciled automatically so reporting stays accurate | payment-reconciliation | Already underway and nearly complete |
| 2 | As an admin, I want tenant role controls so access policies are enforceable | access-control | Unblocks downstream auth work |
| 3 | As a user, I want invoice exports grouped by tenant so finance handoff is simpler | tenant-export-followup | Small follow-on after completed billing foundation |
```

Rules:

- one table only
- every row needs a short reason for its position
- `IN_PROGRESS` rows stay at the top
- cap at roughly twenty rows unless the user asks for the full backlog

## Edge Cases

- if the current directory does not map cleanly to a repo, ask the user which repo to focus on
- if no plans match, say so and suggest full audit mode
- if related-repo mapping is missing, stay conservative and avoid guessing cross-repo relevance
