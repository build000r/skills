# Local mode: <repo-name> (gitignored)

cwd_match: ~/repos/<repo-name>

## Active Codebase

- path: `<active codebase path>`
- deprecated_paths:
  - `<deprecated path>`

## Public Docs Surface

- `README.md`
- `CONTRIBUTING.md`
- `docs/`
- `.github/`

## Baseline Commands

- `<repo-native doc validator>`
- `<manifest or route parity command>`
- `<package docs validator>`

## High-Risk Drift Markers

- deprecated route roots
- old stack names
- removed workflow files
- wrong deploy file names
- license mismatches

## Notes

- Record any repo-specific truths the audit should prefer over generic guesses.
