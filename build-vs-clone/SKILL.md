---
name: build-vs-clone
description: >-
  Decide whether work should live in an existing repo, be extracted upward into
  a shared home, adopt existing open source, borrow patterns, or be built from
  scratch. Use for "where should this go", "should this be extracted", "should
  this become a skill/shared package/helper repo", "is there an open source
  repo for this", "am I recreating the wheel", "should we fork/build this", or
  when a plan should consider both ecosystem fit and the user's current repo
  portfolio.
---

# Build Vs Clone

Find credible open-source options, verify them by reading code, then recommend
one of three paths:

- `ADOPT` - use an existing repo or library directly
- `BORROW` - reuse ideas, patterns, tests, or architecture, but do not depend
  on the repo as-is
- `BUILD` - implement from scratch because the ecosystem fit or trust bar is
  not good enough

When the user already has a portfolio of repos, answer a second question too:
where the work should live. Placement outcomes are:

- `EXISTING REPO` - one current repo clearly owns the bounded context
- `CROSS-REPO SLICE` - one repo owns the core logic and another owns the
  integration, UI, or surface area
- `NEW REPO` - no current repo is a clean ownership fit
- `SKILL / MODULE` - the work is reusable agent workflow or shared tooling,
  not product logic

When the user is asking whether something should be lifted out of its current
home, answer a third question: should this be extracted upward into a more
shared layer? Extraction outcomes are:

- `LEAVE IN PLACE` - keep it where it is because reuse pressure is weak
- `EXTRACT UP` - move to the nearest shared parent/bounded context
- `SHARED PACKAGE` - create a package/module inside an existing shared repo or
  monorepo
- `SKILL` - extract as reusable agent workflow/tooling
- `HELPER REPO` - create a small focused helper repo for cross-project reuse
- `NEW REPO` - create a new top-level repo because this is a durable new domain

## On Trigger

Start the first progress update with:

`Using build-vs-clone ...`

This skill has three branches:

- ecosystem fit: browse/search is required
- local placement: inspect the local portfolio first, then browse only if the
  placement decision depends on external adopt/borrow/build options
- extraction review: inspect the current repo plus sibling repos to decide
  whether a capability should stay put or move to a more shared home

For skill, workflow, or agent-tooling asks, add one more sweep before external
OSS search: inspect trusted upstream local skill directories as second-class
priority inputs. They are trusted and worth checking before GitHub/package
search, but they are not the canonical first-choice home unless the evidence
still says they should be.

If the ask is only "where should this go?" and the decision can be made from
local repo evidence, local inspection is enough.

## Modes

Repo-aware placement should use a local gitignored mode file when available.

1. List `modes/*.md` in this skill directory.
2. Match `cwd` against `cwd_match` path prefixes.
3. If multiple modes match, prefer the most specific `cwd_match` (the longest
   normalized path prefix).
4. If one best match remains, use it automatically.
5. If none match, inspect local repos directly and state the uncertainty.
6. Keep personal or company repo maps in `modes/`, not in tracked files.

Modes may also define trusted upstream skill roots for non-canonical but highly
trusted local skill corpora. Use those roots before external OSS search when
the ask is about skills, reusable workflows, or agent tooling.

See [references/mode-template.md](references/mode-template.md) for the
recommended structure.

For extraction review, also use
[references/extraction-heuristics.md](references/extraction-heuristics.md).

## Non-Negotiables

1. Do not recommend a repo from memory, stars, or README quality alone.
2. Inspect actual code for every serious candidate before recommending it.
3. Prefer primary sources: the repo itself, package registry pages, official
   docs, releases, and issue tracker.
4. For every recommended repo, inspect at least:
   - `LICENSE` or equivalent
   - primary manifest/build file (`package.json`, `pyproject.toml`,
     `Cargo.toml`, `go.mod`, etc.)
   - one core implementation file
   - one test file or CI/workflow file
5. Default to read-only inspection. Do not run arbitrary third-party code
   unless execution is separately justified.
6. When discussing freshness, use concrete dates from current sources.
7. If no candidate clears the trust and fit bar, say `BUILD` plainly instead of
   padding the answer with weak options.
8. If recommending placement in an existing repo, inspect local repo evidence
   first: `CLAUDE.md`, `.claude/`, manifests, and relevant top-level docs.
9. For skill/workflow/tooling asks, inspect configured trusted upstream local
   skill roots before widening to external OSS. If no mode is available, probe
   nearby workspace roots such as `../../projects/*/skills/*` only when they
   actually exist from the current working repo.
10. Do not recommend a new repo just because the current repos are messy; only
   recommend `NEW REPO` when ownership would stay unclear after reasonable
   cleanup.
11. Do not recommend extraction just because two code paths look similar. Look
    for durable shared concepts, repeated maintenance pain, or repeated product
    use across repos.
12. Prefer extracting upward to the nearest existing shared boundary before
    inventing a brand-new repo.

See [references/repo-diligence.md](references/repo-diligence.md) for the trust
rubric, red flags, and search prompts.

## Workflow

### 1. Frame the ask

Identify the real thing being requested before searching:

- ask type: `placement`, `ecosystem`, `extraction`, or `both`
- problem category: library, app, agent, UI component, backend service, CLI,
  infrastructure template, algorithm, workflow
- target stack: language, framework, runtime, hosting model, database, browser
  or server constraints
- adoption constraints: license, security, self-hosting, SaaS avoidance,
  extensibility, performance, team familiarity
- desired outcome: existing repo, new repo, adopt directly, fork, reference
  implementation, extract upward, helper package, skill, or just inspiration

Infer constraints when obvious. Ask only the next blocking question if a
missing constraint would change the shortlist materially.

### 2. Inspect the local portfolio when placement matters

If the ask is "where should this go?" or the user has an existing repo
portfolio:

- load a local mode if one matches the current `cwd`
- if `~/.claude/context/manifest.yaml` exists, use it as a discovery index, not
  as final truth
- inspect candidate repos directly:
  - `CLAUDE.md`
  - `.claude/`
  - primary manifests
  - top-level docs that define scope
- if the problem smells like reusable workflow/tooling, inspect
  `opensource/skills` plus any configured trusted upstream skill roots before
  assuming the current skills repo is the only local prior art
- shortlist 2-4 plausible destinations plus `NEW REPO` if none fit
- write down each candidate's ownership boundary:
  - what it owns
  - what it should not own
  - whether this request is core logic, integration, presentation, or reusable
    workflow

Prefer the mode's ownership map as the prior and repo-local files as
verification.

### 3. Scan for extraction opportunities when relevant

If the ask is "should this be extracted?" or the work smells more reusable than
its current home:

- identify the current home repo and the candidate higher-level homes from the
  mode file
- inspect sibling repos for repeated or adjacent demand:
  - similar nouns, APIs, scripts, workflows, or docs
  - duplicated integration logic
  - repeated prompting/workflow steps that could become a skill
  - utility code that would become cleaner as a small helper package
- classify the thing being extracted:
  - domain concept
  - shared infrastructure
  - product-facing integration
  - agent workflow / operator playbook
  - tiny helper utility
- decide the smallest sensible extraction target:
  - leave in place
  - extract up into an existing monorepo/shared repo
  - shared package/module in an existing repo
  - skill
  - helper repo
  - new top-level repo

Prefer the nearest stable shared boundary. Do not jump straight to a new repo.

### 4. Check trusted upstreams first, then broaden fast

If the ask is about skills, reusable workflows, or agent tooling:

- inspect mode-configured trusted upstream skill roots before external OSS
  search
- treat them as second-class priority: trusted local prior art, not the
  default canonical destination
- if no mode provides roots, probe nearby workspace roots such as
  `../../projects/*/skills/*` only when they exist from the current working
  repo
- shortlist the strongest local upstream candidates by reading:
  - `SKILL.md`
  - relevant `references/`
  - bundled `scripts/` or `assets/` when they materially affect reuse
- decide whether each upstream candidate is something to:
  - adopt into the current portfolio
  - borrow from while keeping the canonical skill in `opensource/skills`
  - leave upstream because it is trusted but still too specialized or noisy

Use web search plus primary-source discovery on the likely repo host and
package ecosystem.

Good discovery surfaces:

- GitHub/GitLab/Codeberg repo search
- package registries such as npm, PyPI, crates.io, Go packages, Docker Hub
- official docs for well-known projects
- curated `awesome-*` lists only as discovery inputs, never as final evidence

Shortlist 3-5 candidates. Remove forks, wrappers, abandoned demos, and repos
that miss obvious hard constraints.

Skip this step when the ask is pure local placement and no external ecosystem
decision is needed.

### 5. Inspect the code, not just metadata

For each shortlisted candidate, verify fit by reading the repo.

If shell and `git` are available, prefer shallow clone or archive inspection:

```bash
tmp="$(mktemp -d)"
git clone --depth 1 https://github.com/<owner>/<repo> "$tmp/repo"
cd "$tmp/repo"
rg --files | rg '(^|/)(README|LICENSE|package.json|pyproject.toml|Cargo.toml|go.mod|src/|lib/|cmd/|tests?/|\.github/workflows/)'
```

Read enough to answer:

- Does the core architecture actually solve the user's problem?
- Is the implementation real, or mostly scaffolding/demo code?
- Is there meaningful test coverage or CI verification?
- Does the license permit the intended use?
- Is the codebase active, stable, and understandable enough to adopt?

Do not stop at the README. Open implementation and verification files.

### 6. Score fit, trust, placement, and extraction

Evaluate each serious candidate on these axes:

- `Placement`: whether this belongs in an existing repo, a cross-repo slice, a
  skill/module, or a new repo
- `Extraction`: whether the capability should stay local or move to a more
  shared layer
- `Fit`: how directly it satisfies the request, matches the target stack, and
  avoids heavy unwanted assumptions
- `Trust`: maintenance, code quality, tests, release hygiene, license clarity,
  docs, security posture, and issue quality

Keep stars as a weak signal only. A popular repo with weak code inspection
signals should not win.

For local repo candidates, score on:

- bounded-context match
- integration cost
- ownership clarity after the change
- blast radius if the repo absorbs the work

For extraction candidates, score on:

- repeat demand across repos or workflows
- conceptual stability
- API/contract clarity if extracted
- cost of premature abstraction
- whether the target shared home already exists
- whether `sweet-potato`, `opensource/skills`, or another existing repo is the
  nearest correct "upward" destination

### 7. Choose the path, destination, and extraction target

Use these decision rules:

- `ADOPT`
  - one repo covers most of the requirement already
  - trust signals are strong
  - license and integration cost are acceptable
- `BORROW`
  - repo contains useful ideas, architecture, tests, or narrow subsystems
  - direct adoption would add too much complexity, risk, or opinionated design
- `BUILD`
  - no repo matches the core requirements
  - or trust, licensing, maintenance, or integration risk is too high

Use these placement rules:

- `EXISTING REPO`
  - one current repo already owns the main nouns, users, and data model
- `CROSS-REPO SLICE`
  - one repo owns the system of record and another owns the user surface or
    integration point
- `NEW REPO`
  - the work introduces a new bounded context that would make ownership muddier
    in every current repo
- `SKILL / MODULE`
  - the work is reusable workflow/tooling that should not be buried in an
    app-specific repo

Use these extraction rules:

- `LEAVE IN PLACE`
  - reuse pressure is speculative
  - abstraction would mostly add indirection
- `EXTRACT UP`
  - the capability already wants to serve multiple sibling surfaces and there
    is an obvious higher-level owner
- `SHARED PACKAGE`
  - the capability is code, not just a pattern, and belongs inside an existing
    shared repo or monorepo
- `SKILL`
  - the reusable part is mostly agent workflow, operator knowledge, or
    repeatable investigation/deployment logic
- `HELPER REPO`
  - the capability is small, reusable, and cross-project, but does not belong
    to any current product/domain repo
- `NEW REPO`
  - the extraction creates a durable new product/domain boundary that should be
    independently owned

If recommending `BORROW`, be specific about what to borrow:

- architecture
- file layout
- APIs
- test cases
- parsing or sync logic
- UI interaction patterns

If recommending `NEW REPO`, explain why the current portfolio boundaries are a
real mismatch, not just an inconvenience.

### 8. Respond with evidence

Keep the answer concise but auditable. Include:

```markdown
Recommendation
- Decision: ADOPT | BORROW | BUILD
- Placement: EXISTING REPO | CROSS-REPO SLICE | NEW REPO | SKILL / MODULE
- Extraction: LEAVE IN PLACE | EXTRACT UP | SHARED PACKAGE | SKILL | HELPER REPO | NEW REPO
- Destination: <repo path> | <repo A> + <repo B> | <new repo rationale>
- Extraction Target: <current repo> | <shared repo/package> | <skill> | <helper repo>
- Best fit: <owner/repo> @ <tag/branch/commit or registry version>
- Why: <2-4 sentence rationale>

Local Candidates Reviewed
- <repo or new repo option>: ownership summary, fit summary, blockers, exact local evidence inspected

Trusted Upstream Candidates Reviewed
- <skill dir>: fit summary, trust summary, blockers, exact local evidence inspected

Extraction Candidates Reviewed
- <candidate target>: reuse summary, extraction fit, blockers, exact local evidence inspected

Candidates Reviewed
- <owner/repo>: fit summary, trust summary, blockers, exact evidence inspected
- <owner/repo>: fit summary, trust summary, blockers, exact evidence inspected

Evidence Inspected
- local: <CLAUDE.md>, <manifest>, <settings>, <docs>
- <repo>: <LICENSE>, <manifest>, <implementation file>, <test or CI file>

Suggested Path
- Adopt directly, fork, borrow specific ideas, or build from scratch
- Place the work in <repo> because <ownership reason>
- Extract to <target> because <reuse / boundary reason>
- If borrowing: list the exact subsystem or pattern to copy
- If building: explain why the ecosystem gap is real
```

Whenever possible, include exact repo links and the specific files that shaped
the recommendation.

## Practical Rules

- Prefer maintained libraries over giant template repos when the user only
  needs one subsystem.
- Prefer boring, proven code over flashy demos for production suggestions.
- Prefer official upstream repos over unofficial mirrors or tutorial code.
- Distinguish between "good inspiration" and "safe dependency."
- If the user already has a codebase, optimize for integration cost, not for
  abstract popularity.
- If all strong candidates are close but not right, recommend `BORROW` instead
  of forcing `ADOPT`.
- For skill/workflow/tooling asks, inspect trusted upstream local skill
  directories before treating external OSS as the next option.
- Prefer extending an existing repo over creating a new repo when the bounded
  context is already there.
- Prefer a skills/tooling repo for reusable agent workflows, not product repos.
- Prefer a public site repo for presentation and content, not the core domain
  engine behind it.
- If one repo is the system of record and another is a consumer, put core logic
  in the owner and only the integration surface in the consumer.
- Prefer extracting upward into an existing shared repo or monorepo before
  creating a helper repo.
- Prefer `SKILL` when the reusable thing is mostly instructions, investigation,
  deployment steps, or operator workflow rather than a stable runtime library.
- Prefer a small helper repo only when the utility is genuinely cross-project
  and does not fit a current domain owner.
