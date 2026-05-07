# Repo Placement Mode Template

Copy this file to `modes/{portfolio-name}.md` and keep it gitignored.

---

# {Portfolio Name} Mode

## Detection

```
cwd_match: ~/repos
```

Use the broadest stable prefix that should activate this portfolio map.
If you need repo-specific overrides, create a second mode with a more specific
`cwd_match`; the most specific matching mode should win.

## Scan Roots

- `~/repos`

List the roots that matter when checking whether work belongs in an existing
repo or needs a new one.

## Trusted Upstream Skill Roots

Use this only for skill/workflow/tooling asks.

These are second-class priority inputs: local skill corpora you trust and want
checked before external OSS search, but which are not yet the canonical skills
home for the portfolio.

- `~/projects/some-skill-archive/skills`

List only roots that are worth treating as credible local prior art.

If you have a repo like `skillbox` that is both a platform and a source of
bundled skills, do not model it only as an upstream skill root. Also list it
under `Repo Ownership` or `Extraction Targets` so placement decisions can
distinguish the portable skill contract from runtime/distribution concerns.

## First-Class Dogfood Buckets

List portfolio repos that should be checked before recommending local builds or
external dependencies. These are not vague inspirations; they are owner buckets
that can receive work or provide the contract a consumer repo should use.

- `skillbox`
  - path: `~/repos/opensource/skillbox`
  - owns: runtime manager, focus/context generation, MCP/runtime wiring,
    devbox behavior, skill distribution mechanics
- `skillbox-config`
  - path: `~/repos/skillbox-config`
  - owns: client overlays, generated contexts, plans, workflows, evaluations,
    invocation artifacts, repo landscapes, per-client validation commands
- `swimmers`
  - path: `~/repos/opensource/swimmers`
  - owns: Rust binary crate, local server/TUI interaction surface,
    multi-agent/session visibility patterns, publishable CLI ergonomics
- `sweet-potato`
  - path: `~/repos/sweet-potato`
  - owns: SPAPS auth, sessions, API keys, application identity, billing,
    payments, entitlements, wallet identity, published clients, issue reporting
  - packages: `packages/python-server-quickstart`, `packages/python-client`,
    `packages/sdk`, `packages/spaps`, `packages/types`,
    `packages/issue-reporting-react`, `packages/wallet-utils`

## Repo Ownership

- `repo-name`
  - path: `~/repos/repo-name`
  - owns: auth, billing, admin tooling
  - does_not_own: marketing site, AI governance
  - prefer_for: API changes, schema changes, system-of-record logic
  - cross_repo_with: `other-repo` for UI or integration work
  - notes: any boundary nuance worth preserving

- `other-repo`
  - path: `~/repos/other-repo`
  - owns: website, copy, landing pages
  - does_not_own: auth backend, entitlements
  - prefer_for: presentation, content, frontend integration

## Shared Rules

- Prefer an existing repo when its bounded context already matches the request.
- Prefer a cross-repo slice when one repo owns the data model and another owns
  the surface area.
- Prefer a new repo only when no current repo has a clean ownership fit.
- Prefer the skills/tooling repo for reusable agent workflows or shared
  developer tooling.
- If a platform repo such as `skillbox` exists, prefer it for skill runtime,
  packaging/sync, client overlay behavior, or box/operator concerns rather than
  for the portable skill contract itself.

## Extraction Targets

Define the preferred "upward" destinations when something should be lifted out
for reuse:

- `shared-monorepo`
  - path: `~/repos/shared-monorepo`
  - use_for: domain-adjacent shared packages or concepts

- `skills-repo`
  - path: `~/repos/opensource/skills`
  - use_for: reusable agent workflows, operator playbooks, investigation logic

- `skill-platform`
  - path: `~/repos/skillbox`
  - use_for: skill runtime/distribution, default bundles, client overlays, box
    lifecycle, and operator tooling

- `helper-repo`
  - path: `~/repos/{helper-repo}`
  - use_for: tiny cross-project utilities that do not belong to a product repo

## Extraction Rules

- Prefer extracting upward to the nearest stable shared destination.
- Prefer `SKILL` when the reusable part is mostly workflow, not runtime code.
- Prefer `SHARED PACKAGE` inside an existing repo before creating a helper repo.
- Prefer a helper repo only when no current shared home is a clean fit.
- Prefer `NEW REPO` only when the extracted thing becomes a durable new domain.

## New Repo Threshold

Recommend `NEW REPO` only when at least one of these is true:

- the request introduces a genuinely new product/domain boundary
- adding it to any current repo would blur ownership permanently
- the work needs a different runtime/deploy model that would be awkward as a
  subdirectory

## Local Notes

Include anything private or organization-specific here instead of tracked
skill files:

- private skill roots
- trusted upstream skill corpora that are not yet integrated into the main
  skills repo
- adjacent platform repos that also bundle skills, such as `skillbox`
- internal naming conventions
- repo pairs that commonly ship together
- anti-goals such as "never put payments logic in the website repo"
- "extract up" defaults such as "prefer the shared auth/billing platform for
  auth/payment-adjacent shared concepts"
