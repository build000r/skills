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

## Extraction Targets

Define the preferred "upward" destinations when something should be lifted out
for reuse:

- `shared-monorepo`
  - path: `~/repos/shared-monorepo`
  - use_for: domain-adjacent shared packages or concepts

- `skills-repo`
  - path: `~/repos/opensource/skills`
  - use_for: reusable agent workflows, operator playbooks, investigation logic

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
- internal naming conventions
- repo pairs that commonly ship together
- anti-goals such as "never put payments logic in the website repo"
- "extract up" defaults such as "prefer sweet-potato for auth/payment-adjacent
  shared concepts"
