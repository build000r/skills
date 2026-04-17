# Verification Checklist

Use this after the UI/analytics patch lands.

## Build

- `make build`

## Unit Tests

- Run the repo-native unit target or a targeted suite that covers the analytics contract.

## UI Tests

- Run the signed-out/auth shell fixture slice.
- Run the onboarding/sign-up fixture slice.
- If the home/dashboard surface changed, run the current-plan or intake fixture slice too.

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
