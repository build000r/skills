---
name: build-vs-clone
description: >-
  Decide whether work should live in an existing repo, be extracted upward into
  a shared home, adopt existing open source, borrow patterns, or be built from
  scratch. Use for "where should this go", "should this be extracted", "should
  this become a skill/shared package/helper repo", "is there an open source
  repo for this", "am I recreating the wheel", "should we fork/build this",
  "audit this codebase for build-vs-buy violations", or when a plan should
  consider both ecosystem fit and the user's current repo portfolio.
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

This skill has four branches:

- ecosystem fit: browse/search is required
- local placement: inspect the local portfolio first, then browse only if the
  placement decision depends on external adopt/borrow/build options
- extraction review: inspect the current repo plus sibling repos to decide
  whether a capability should stay put or move to a more shared home
- audit: retroactive sweep of one or more repos to inventory build-vs-buy
  violations, redundancies, and reinvented wheels

For all asks, follow the tiered search order (Step 4): sweet-potato/skillbox
first, then loaded skills, then back-pocket projects, then trusted OSS authors,
then general ecosystem. Each tier is checked before widening to the next.

If a sibling `skillbox` repo exists, treat it as part of the default local
landscape for skill/tooling placement. It is not just another upstream skill
corpus: inspect it when the request touches skill packaging or sync, default
skill bundles, client overlays, box/runtime behavior, or operator tooling.

If the ask is only "where should this go?" and the decision can be made from
local repo evidence, local inspection is enough.

If the ask is "audit this for build-vs-buy", "what here is reinventing the
wheel", "what overlaps with X", or similar retroactive assessment, use audit
mode (Step 3b). Audit mode explores the target repo(s) broadly first, then
checks each component against the tiered search order. The user may name
specific tools they suspect overlap with — investigate those first.

## Modes

Repo-aware placement should use the skillbox client overlay when available.

1. Read `skillbox-config/clients/{client}/overlay.yaml` and its auto-generated
   `context.yaml` for the active client.
2. Match `cwd` against `cwd_match` path prefixes defined in the overlay.
3. If multiple modes match, prefer the most specific `cwd_match` (the longest
   normalized path prefix).
4. If one best match remains, use it automatically.
5. If none match, inspect local repos directly and state the uncertainty.
6. Keep personal or company repo maps in the client overlay, not in tracked files.

Modes may also define trusted upstream skill roots for non-canonical but highly
trusted local skill corpora. Use those roots before external OSS search when
the ask is about skills, reusable workflows, or agent tooling.

If a matching mode names `skillbox` or another adjacent skill platform repo,
preserve that distinction in the recommendation: canonical skill home versus
runtime/distribution home.

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
9. Follow the tiered search order (Tier 1→5) in Step 4. Do not skip to
   external OSS before checking sweet-potato/skillbox, loaded skills, and
   back-pocket projects.
10. Do not recommend a new repo just because the current repos are messy; only
   recommend `NEW REPO` when ownership would stay unclear after reasonable
   cleanup.
11. Do not recommend extraction just because two code paths look similar. Look
    for durable shared concepts, repeated maintenance pain, or repeated product
    use across repos.
12. Prefer extracting upward to the nearest existing shared boundary before
    inventing a brand-new repo.
13. When `skillbox` exists locally, inspect the relevant platform files before
    defaulting to `opensource/skills`: `README.md`,
    `workspace/default-skills.sources.yaml`,
    `workspace/default-skills.manifest`, relevant
    `workspace/clients/*/{skills.sources.yaml,skills.manifest,overlay.yaml}`,
    `skills/*/SKILL.md`, and sync/packaging/runtime scripts.

See [references/repo-diligence.md](references/repo-diligence.md) for the trust
rubric, red flags, and search prompts.

## Workflow

### 1. Frame the ask

Identify the real thing being requested before searching:

- ask type: `placement`, `ecosystem`, `extraction`, `audit`, or `both`
- problem category: library, app, agent, UI component, backend service, CLI,
  infrastructure template, algorithm, workflow
- target stack: language, framework, runtime, hosting model, database, browser
  or server constraints
- adoption constraints: license, security, self-hosting, SaaS avoidance,
  extensibility, performance, team familiarity
- desired outcome: existing repo, new repo, adopt directly, fork, reference
  implementation, extract upward, helper package, skill, just inspiration, or
  ranked audit of build-vs-buy violations

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
- if the problem smells like reusable workflow/tooling, check Tiers 1-3
  (sweet-potato/skillbox, loaded skills, back-pocket projects) before assuming
  the current skills repo is the only local prior art
- if a sibling `skillbox` repo exists and the ask touches skill runtime,
  installation, sync, packaging, client overlays, box behavior, or operator
  tooling, inspect it as a separate destination candidate
- shortlist 2-4 plausible destinations plus `NEW REPO` if none fit
- write down each candidate's ownership boundary:
  - what it owns
  - what it should not own
  - whether this request is core logic, integration, presentation, or reusable
    workflow

Prefer the mode's ownership map as the prior and repo-local files as
verification.

When both `opensource/skills` and `skillbox` are plausible, use this split:

- `opensource/skills`: canonical skill contracts, reusable authoring/review
  guidance, generic skill helper scripts, and portable workflow knowledge
- `skillbox`: durable runtime behavior, skill installation/sync, default skill
  bundle curation, client overlays, box lifecycle, and operator tooling
- `CROSS-REPO SLICE`: the skill contract belongs in `opensource/skills`, while
  runtime/distribution/integration behavior belongs in `skillbox`

Abstract example:

- a product repo owns a reporting or comms workflow
- a sibling platform repo exposes Flywheel-backed connectors, capability
  scoping, and runtime delivery
- recommendation: `CROSS-REPO SLICE`
- place domain-specific request handling, policy, and user-facing behavior in
  the product repo
- place Flywheel connector runtime, authz/scoping, sync, and operator plumbing
  in the platform repo
- extract only the generic integration seam upward; do not move the whole
  product workflow just because it depends on Flywheel

### 3. Scan for extraction opportunities when relevant

If the ask is "should this be extracted?" or the work smells more reusable than
its current home:

- identify the current home repo and the candidate higher-level homes from the
  client overlay
- inspect sibling repos for repeated or adjacent demand:
  - similar nouns, APIs, scripts, workflows, or docs
  - duplicated integration logic
  - repeated prompting/workflow steps that could become a skill
  - utility code that would become cleaner as a small helper package
- if `skillbox` is present, inspect `workspace/*.yaml`, `default-skills/`,
  `skills/`, and sync/runtime scripts before inventing a new helper repo; many
  cross-skill concerns are platform concerns instead
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

### 3b. Audit mode: retroactive build-vs-buy sweep

Trigger: the user asks to audit, review, or assess an existing codebase (one or
more repos) for build-vs-buy violations — things that were built without
considering whether an existing tool, library, sibling repo, or loaded skill
already handles the concern.

This is a whole-codebase pass, not a single-decision evaluation. The output is
a ranked inventory of discrepancies, not a single ADOPT/BORROW/BUILD verdict.

#### Phase 1: Inventory what was built

Explore the target repo(s) thoroughly. For each major component, module, or
subsystem, record:

- **name**: the component as it appears in code (e.g., "event journal + acking
  system", "skill packaging pipeline", "quality rubric loop")
- **what it does**: one-paragraph summary of the capability
- **where it lives**: file paths or directories
- **category**: memory/learning, orchestration, packaging, observability,
  config management, security, context assembly, or other

Do not skip small utilities. Things that look trivial often duplicate a
well-maintained upstream.

#### Phase 2: Identify overlap candidates

For each inventoried component, check whether the capability already exists in:

1. **Sibling repos** in the same portfolio (e.g., a procedural memory system
   sitting next to hand-rolled learning logic)
2. **Loaded skills** (`~/.claude/skills/`) that already expose the capability
3. **First-party tools** declared in the same runtime (artifacts, MCP servers,
   services) that the component doesn't use
4. **Well-known OSS** that solves the same problem with less maintenance burden

For each overlap found, estimate:

- **overlap %**: how much of the custom component's functionality the existing
  tool already covers (use 10% increments)
- **what's genuinely novel**: the part of the custom component that has no
  equivalent in the existing tool
- **what's redundant**: the part that directly duplicates existing capability

#### Phase 3: Classify and rank

Assign each finding to a severity tier:

- **Tier 1 — Direct duplication**: the custom code reimplements something that
  an existing tool in the same portfolio already does. The existing tool is
  already deployed or declared. High maintenance cost, high drift risk.
- **Tier 2 — Solved problem**: the custom code implements a well-known pattern
  that mature OSS or an existing package manager handles. Not a portfolio
  duplicate, but a reinvented wheel.
- **Tier 3 — Complementary but unwired**: two systems serve the same goal from
  different angles. Neither replaces the other, but they should talk to each
  other and currently don't. Learnings from one don't feed the other.
- **Tier 4 — Independently justified**: custom code that has no meaningful
  overlap. Note it for completeness but no action needed.

Within each tier, rank by estimated maintenance burden and drift risk.

#### Phase 4: Produce the audit report

Use this output format:

```markdown
## Build-vs-Buy Audit: <repo(s) assessed>

### Tier 1: Direct Duplication — Strongly Consider Replacement

**N. <Component Name>** (`<path>`)
- What it does: <summary>
- Overlaps with: <existing tool/system name>
- Overlap: ~NN%
- What's genuinely novel: <or "nothing — full overlap">
- What's redundant: <specific duplicated capabilities>
- Recommendation: <replace / consolidate / wire together>

### Tier 2: Solved Problem — Consider Adopting Existing

...same format...

### Tier 3: Complementary but Unwired — Wire Together

...same format, but "Recommendation" focuses on integration points...

### Tier 4: Independently Justified — No Action

| # | Component | Why it's justified |
|---|-----------|-------------------|
| N | <name>    | <one-line reason>  |

### Summary: Rank-Ordered Action Items

| # | Item | Overlaps With | Severity | Action |
|---|------|--------------|----------|--------|
| 1 | ...  | ...          | High     | ...    |
```

#### Audit rules

- Name specific things. "Seeing overlap" is not useful. "The event journal
  acking system in `pulse.py` reimplements cm's confidence decay" is useful.
- When the user names a specific tool they suspect overlap with (e.g., "cass
  would handle this"), investigate that tool first rather than doing a blind
  ecosystem scan.
- Inspect code, not just file names. Two things named similarly may serve
  different purposes; two things named differently may be identical.
- Static knowledge encoded in markdown (rubrics, checklists, phase templates)
  counts as "built" if it duplicates what a dynamic system (like a playbook or
  procedural memory tool) would maintain with feedback and decay.
- When the same *goal* is served by both a static file and a dynamic system,
  the recommendation is usually "bootstrap the static content into the dynamic
  system" rather than "delete the static file."
- Include the theme. After listing individual findings, state the overarching
  pattern (e.g., "a parallel procedural memory system was built in markdown
  that doesn't feed the actual procedural memory system").
- Do not pad Tier 4. If something is justified, a one-line row is enough.

### 4. Search in priority order

Search for prior art and candidates in this order. Stop widening when you have
enough evidence to decide. Each tier is checked before the next; do not skip to
external OSS before exhausting the local tiers.

#### Tier 1: Sweet Potato skillbox and first-class dependencies

The sweet-potato ecosystem is the innermost trusted ring. Check here first for
any ask — not just skill/tooling asks:

- `sweet-potato` — core auth/payments/identity service and its packages
- `skillbox` — skill runtime, packaging, sync, default bundles, client overlays,
  box lifecycle, operator tooling
- `skillbox-config` — client configurations, plans, overlay definitions

For skillbox, read: `README.md`, `workspace/default-skills.sources.yaml`,
`workspace/default-skills.manifest`, relevant
`workspace/clients/*/{skills.sources.yaml,skills.manifest,overlay.yaml}`,
`skills/*/SKILL.md`, and sync/packaging/runtime scripts.

If the capability already exists here, the answer is almost always `ADOPT` or
`EXISTING REPO` unless the user explicitly wants to diverge.

#### Tier 2: Loaded skills

Check `~/.claude/skills/` for skills already installed and active. These are
managed by JSM and represent the current working toolkit. Read `SKILL.md` and
`references/` for each relevant match.

If a loaded skill already covers the ask, the answer is `ADOPT` (use it) or
`BORROW` (take its patterns but build domain-specific). A loaded skill that
partially overlaps is a strong signal to extend rather than rebuild.

#### Tier 3: Back-pocket projects

Check `~/projects/*/` for unloaded projects, skill archives, and experimental
work. These are trusted local prior art that hasn't been promoted to the active
toolkit yet.

Read `SKILL.md`, `README.md`, or top-level docs to assess fit. If something
here is a strong match, recommend adopting/loading it before building from
scratch.

#### Tier 4: Trusted OSS authors

Before general GitHub/registry search, check repos from trusted authors whose
code quality and judgment are known:

- `https://github.com/steipete` — iOS/macOS tooling, developer experience
- `https://github.com/Dicklesworthstone` — AI agent workflows, planning
  systems, session search

Inspect their repos with the same code-reading rigor as any candidate (license,
manifest, core implementation, tests). Being trusted means they get checked
early, not that they get a pass on inspection.

#### Tier 5: General ecosystem search

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
- whether `sweet-potato`, `opensource/skills`, `skillbox`, or another existing
  repo is the nearest correct "upward" destination

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

Tier 1 (Sweet Potato / Skillbox)
- <repo>: fit summary, blockers, exact files inspected
- (or: "no relevant capability found in Tier 1")

Tier 2 (Loaded Skills)
- <skill>: fit summary, blockers, exact files inspected
- (or: "no relevant loaded skill")

Tier 3 (Back-Pocket Projects)
- <project>: fit summary, blockers, exact files inspected
- (or: "no relevant back-pocket project")

Tier 4 (Trusted OSS Authors)
- <owner/repo>: fit summary, trust summary, blockers, exact evidence inspected
- (or: "no relevant repo from trusted authors")

Tier 5 (General Ecosystem)
- <owner/repo>: fit summary, trust summary, blockers, exact evidence inspected
- (or: "skipped — decided at Tier N")

Local Placement Candidates
- <repo or new repo option>: ownership summary, fit summary, blockers

Extraction Candidates Reviewed
- <candidate target>: reuse summary, extraction fit, blockers, exact local evidence inspected

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
- For all asks, follow the Tier 1→5 search order before recommending BUILD.
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
- Prefer `skillbox` over `opensource/skills` when the reusable thing is mainly
  runtime behavior, provisioning, packaging/install/sync, default skill bundle
  curation, client overlay behavior, or durable box/operator tooling.
- Prefer `opensource/skills` over `skillbox` when the reusable thing is the
  portable skill contract itself: instructions, references, review workflows,
  or generic helper scripts for skill authors.
- Prefer a cross-repo slice when the canonical skill should live in
  `opensource/skills` but the behavior only becomes real through `skillbox`
  runtime or distribution integration.
