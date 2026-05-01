# Deployment Context For iOS Surface Hardening

Use this reference when a SwiftUI hardening pass is happening close to TestFlight, App Store review, or a customer beta. The goal is to avoid polishing the surface while losing the operational proof needed to ship it.

## Evidence To Read

- `README.md`, `AGENTS.md`, `CLAUDE.md`
- product vision or style guide docs
- App Store metadata, submission checklist, privacy policy, and support pages
- TestFlight or beta runbooks
- current `Makefile` or documented `xcodebuild` lanes
- fixture UI tests, screenshot capture tests, and physical-device smoke notes
- analytics contract docs and implementation

## Release-Coupled Checks

Before editing:

- identify whether the changed screens appear in App Store screenshots
- identify whether auth, onboarding, paywall, entitlement, privacy prompts, or health data copy changes
- identify which local fixture tests prove the flow
- identify which physical-device or TestFlight smoke remains human-only

After editing:

- run the repo's fixture acceptance gate before any live/backend smoke
- regenerate screenshot decks only when the visuals changed
- keep screenshot attachment names stable so App Store docs do not drift
- update privacy/data-collection docs if the UI now collects or exposes a new class of data
- update release-readiness checks when a repeated manual verification can be scripted

## Human Touchpoint Policy

Ask the operator only for steps the agent cannot do safely: Apple 2FA, agreements, banking/tax, App Store Connect fields, subscription setup, public link enablement, final submission, and physical TestFlight install/smoke. For everything else, create or use a command, fixture, runbook, or chart.

When a human step is mandatory, hand back:

- exact Apple screen or device action
- build number or account state involved
- what proof to capture
- what command or artifact lets the agent resume

## Preview Catalog Pattern

For apps with many SwiftUI states, prefer a DEBUG-only variant catalog or deterministic preview fixtures:

- state snapshots should render the production view with different fixture state
- layout experiments should live under DEBUG-only drafts and promote the winner back into production
- every notable variant should have an Xcode `#Preview` when possible
- screenshot capture should launch deterministic scenarios and fail before capture on alerts, fixture errors, loading states, or missing expected UI

Do not treat catalog scenarios as flow tests. Use UI acceptance tests for flows.
