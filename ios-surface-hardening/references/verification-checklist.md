# Verification Checklist

Use this after the UI/analytics patch lands.

## Build

- Read the repo's command notes (`AGENTS.md`, `CLAUDE.md`, `README.md`) and
  Makefile.
- Use the repo-native simulator build lane. Common examples: `make build`,
  `make ios-build`, or `make ios-sim-build`.
- If no Makefile lane exists, use the repo's documented raw `xcodebuild`
  command.

## Unit Tests

- Run the repo-native unit target or a targeted suite that covers the analytics contract.

## UI Tests

- Run the repo-native signed-out/auth shell fixture slice.
- Run the repo-native onboarding/sign-up fixture slice.
- If the home/dashboard surface changed, run the current-plan or intake fixture
  slice too.
- Use fixture UI or screenshot lanes such as `make test-ui-fixtures`,
  `make acceptance-local`, `make ios-ui-test`, `make screenshots`, or
  `make ios-screenshots` when those are the repo-owned proof paths.

## Visual Integrity Checks

- Sign-in, sign-up, and home screens use the same card/chip/button language.
- Test-facing accessibility identifiers still exist.
- Placeholder/debug-only visual experiments were removed or isolated to debug-only surfaces.
- The first meaningful action on each screen is visually obvious.

## Analytics Integrity Checks

- Feature code only calls the repo-owned analytics wrappers.
- Event names and parameter names are stable and documented.
- No PII is emitted.
- The default sink records events exactly once per meaningful action.
