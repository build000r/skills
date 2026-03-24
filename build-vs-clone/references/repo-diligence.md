# Repo Diligence

Use this checklist when deciding whether a repo is trusted enough to recommend.

## Minimum evidence per repo

Inspect all of these before recommending a repo:

1. `LICENSE`
2. Manifest/build file
3. One core implementation file
4. One test file or CI/workflow file
5. Recent maintenance evidence: latest release, latest meaningful commit, or
   issue/PR activity

If you cannot inspect these, do not present the repo as a trusted option.

## Strong trust signals

- Clear license with no ambiguity for the user's intended use
- Recent release or commit activity with concrete dates
- Real tests covering important behavior, not only snapshots or smoke stubs
- CI workflow present and apparently maintained
- Coherent code layout with clear entrypoints and boundaries
- Docs that match what the code actually does
- Maintainer or org with a credible track record in the area
- Stable issue tracker patterns: bugs get triaged, stale issues are limited,
  serious breakages are visible rather than hidden

## Weak or misleading signals

- High star count without recent activity
- Attractive README with little implementation depth
- Many commits that are only formatting, lockfile churn, or bot noise
- "Production ready" claims without tests or release hygiene
- Large install counts on an old package whose repo is effectively abandoned

## Red flags

- Missing or unclear license
- Core functionality hidden behind closed-source services
- Test directory exists but has little meaningful coverage
- CI is broken, absent, or obviously stale
- Repo is mostly generated boilerplate, examples, or thin wrappers
- Security issues or breaking bugs are open and unaddressed
- Major mismatch between requested stack and actual implementation
- Last real maintenance is old enough to matter for the ecosystem in question

## Search prompts

Start broad, then add constraints:

- `"<problem> github <language>"`
- `site:github.com <problem> <framework>`
- `site:npmjs.com <problem>`
- `site:pypi.org <problem>`
- `site:crates.io <problem>`
- `site:github.com "<problem>" "self hosted"`
- `site:github.com "<problem>" "LICENSE"`

Use broad search only for discovery. Final evidence must come from the repo,
registry, docs, or releases themselves.

## Decision shortcuts

Choose `ADOPT` when:

- one candidate already does most of the job
- integration cost is low enough
- trust signals are strong

Choose `BORROW` when:

- there is a good idea but not a good dependency
- the candidate is too large, too coupled, or too opinionated
- only one subsystem is worth reusing conceptually

Choose `BUILD` when:

- the ecosystem fit is weak
- licensing blocks the intended use
- maintenance risk is too high
- the user's requirements are genuinely unusual

## What to cite in the final answer

For each recommended repo, cite:

- repo URL
- exact files inspected
- current release or last activity date when relevant
- the specific reason it qualifies for `ADOPT`, `BORROW`, or `BUILD`
