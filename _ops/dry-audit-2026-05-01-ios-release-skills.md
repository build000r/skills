# DRY Audit - iOS Release And Surface Skills

Date: 2026-05-01

Target: reusable public and private iOS/release skill bundles.

Corpus floor: met. The combined skill corpus has 98 `SKILL.md` files.

## Summary

The recent private iOS beta push surfaced a high-leverage composition boundary:

- `ios-app-store` should own App Store/TestFlight release gates, Apple UI touchpoints, physical-device smoke, seed/cohort/entitlement proof, release-readiness wrappers, and MMDX release maps.
- `ios-surface-hardening` should stay focused on SwiftUI primitives, auth/onboarding/home consistency, analytics contracts, and fixture/screenshot validation, but it needs release-context awareness so visual changes do not invalidate App Store screenshots, privacy claims, or TestFlight gates.
- `mmdx` already owns MMDX mechanics; the repeated win is a release-Gantt pattern that every release skill can reference instead of rebuilding from project-local lore.
- the project-specific UI catalog remains private. Generalize the pattern as "preview/variant catalog" inside `ios-surface-hardening`, not as a public app-specific dependency.

## Candidates Table

| id | artifact | reuse | independence | shape | affordance | proposed_op | confidence |
|---|---|---:|---:|---:|---:|---|---|
| ios-release-001 | `ios-app-store` missing stable ack marker | 5 | 2 | 4 | 5 | compose | high |
| ios-release-002 | repeated release inventory shell work | 5 | 4 | 4 | 5 | extract | high |
| ios-release-003 | `ios-surface-hardening` blind to release context | 4 | 4 | 4 | 4 | compose | high |
| ios-release-004 | MMDX release Gantt pattern trapped in app-local ops docs | 5 | 5 | 5 | 5 | promote | high |
| ios-release-005 | project-specific preview catalog pattern | 3 | 5 | 5 | 3 | compose | medium |
| ios-release-006 | Apple UI human checkpoints | 5 | 5 | 4 | 5 | extract | high |

## Cluster Groups

### compose

`ios-release-001`: add a first progress marker to `ios-app-store` so transcript review can distinguish real skill invocation from path heuristics.

`ios-release-003`: make `ios-surface-hardening` read release artifacts when the touched UI is near TestFlight/App Store, then preserve release gates in closeout.

`ios-release-005`: keep project-specific UI catalogs separate, but compose the strongest generic idea into `ios-surface-hardening`: deterministic preview catalogs are for visual states, not flow tests.

### extract

`ios-release-002`: repeated manual inspection of signing, privacy, screenshots, Makefile targets, and generated artifacts should become an `ios-app-store` helper script.

`ios-release-006`: the human-touchpoint rule should be explicit: ask only for Apple UI/2FA/banking/submission/physical TestFlight work, keep working around those gates, and provide exact resume conditions.

### promote

`ios-release-004`: promote the linked release-Gantt MMDX pattern into the `mmdx` skill as a reference and example stack. Release skills can then point to the shared pattern instead of copying a one-off app chart.

## Applied In This Run

- Updated `ios-app-store/SKILL.md` with a first progress marker, human touchpoint policy, release-readiness checks, external beta gates, physical-device lane guidance, and MMDX release-map guidance.
- Added `ios-app-store/scripts/ios_release_audit.sh`.
- Updated `ios-surface-hardening/SKILL.md` with release-context reading, screenshot/catalog validation, and release-gate preservation.
- Added `ios-surface-hardening/references/deployment-context.md`.
- Updated `mmdx/SKILL.md` with release-Gantt MMDX routing.
- Added `mmdx/references/release-gantt-mmdx.md` and `mmdx/examples/release-gantt-stack.mmdx`.

## Apply Commands For Future Follow-Up

- Add a public generic `ios-preview-catalog` skill only if another app repeats the catalog pattern.
- Consider a public `ios-release-readiness` skill if `ios-app-store` grows beyond App Store/TestFlight and starts covering general device operations too heavily.

## Human Touchpoint Preference Captured

The operator preference is: minimize human checkpoints aggressively. Mandatory human steps should be represented as exact, small, resume-ready tasks in MMDX or a checklist, while the agent continues all command-first work that does not require Apple account UI, real-device possession, or irreversible release submission.
