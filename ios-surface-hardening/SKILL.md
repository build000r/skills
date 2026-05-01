---
name: ios-surface-hardening
description: Harden SwiftUI iOS surfaces by extracting a shared visual language from the strongest existing screen, reusing it across auth/onboarding/home flows, and pairing the UI pass with a repo-owned analytics contract plus fixture-backed validation. Use when an iOS app has one polished surface and weaker sign-in, onboarding, settings, or companion screens; when someone asks to "make onboarding look like the main app", "standardize the design system", "harden SwiftUI auth flow", or "add one analytics contract for iOS".
---

# iOS Surface Hardening

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using ios-surface-hardening`.

Preferred format: `Using ios-surface-hardening to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

## Goal

Take the best-looking, most trustworthy existing iOS surface in the repo and turn it into the source of truth for weaker screens without redesigning the whole product from scratch.

The hardening batch should usually produce all of these:

- shared SwiftUI surface primitives
- consistent auth/onboarding/home styling
- a repo-owned analytics contract for the touched funnel
- validation that proves the first-run flow still works
- release-context notes when the touched surface is on the path to TestFlight or App Store submission

## Workflow

### 1. Read The Local Truth First

Before editing anything, inspect:

- `README.md`
- any product vision or style guide docs
- any release, TestFlight, App Store, or beta runbooks
- `AGENTS.md` / `CLAUDE.md` command notes
- the strongest existing screen in code
- the weaker screen(s) that need to inherit that language
- current UI tests for auth/onboarding/home
- current Makefile or `xcodebuild` lanes for simulator, fixture, and physical-device smoke

Do not invent a new design language if the app already has one.

If the hardening work is release-coupled, also read [references/deployment-context.md](references/deployment-context.md) before editing.

### 2. Identify The Visual Source Of Truth

Find the screen that already feels the most intentional.

Usually this is the dashboard, home, or detail surface with:

- the best card/chip treatment
- the clearest spacing rhythm
- the strongest color usage
- the least placeholder/debug clutter

Extract from that screen first. Do not duplicate its helper methods into more files.

### 3. Promote Shared Primitives

Prefer a small shared kit over one-off rewrites:

- background treatment
- card container
- hero panel
- primary button
- chip / pill CTA
- form field styling
- key-value row or summary row

Keep the names boring and reusable. This is hardening, not branding theater.

### 4. Rebuild The Weak Screens On Top

Apply the shared kit to the weakest user-facing flows first:

- sign in
- sign up / onboarding
- settings or companion shell

Preserve accessibility identifiers and test-facing copy unless there is a concrete reason to change them and corresponding tests are updated.

### 5. Add One Analytics Contract

Do not call vendor SDKs from SwiftUI views.

Create one repo-owned analytics layer with:

- canonical event names
- canonical parameter names
- typed wrapper functions for the actual funnel actions
- one default local sink such as logger output
- one doc mapping the contract and explicitly listing deferred sinks

Track business steps, not noise:

- screen viewed
- onboarding started
- onboarding step viewed / advanced
- sign in submitted / succeeded / failed
- sign up submitted / succeeded / failed
- high-value dashboard CTAs

Never include email, name, or other PII in analytics params.

### 6. Validate In This Order

1. Build the app.
2. Run the unit tests that cover the analytics contract.
3. Run the auth/onboarding/home fixture UI slices.
4. Run any deterministic screenshot or preview-catalog capture that covers the changed surfaces.
5. Only then consider broader acceptance runs.

If the repo already has targeted make targets or xcodebuild invocations, use those instead of inventing new ones.

Use [references/verification-checklist.md](references/verification-checklist.md) as the closeout checklist.

### 7. Preserve Release Gates

When the app is already moving toward TestFlight/App Store, do not let a visual hardening pass erase release evidence:

- keep explicit device lanes separate (`device-local`, `device-fixtures`, `device-prod`/`device-beta`) instead of hiding runtime choice behind overrides
- keep fixture proofs distinct from TestFlight physical-device smoke
- preserve App Store screenshot identifiers and dimensions when changing screenshot surfaces
- update any release-readiness wrapper if the surface changes privacy data, metadata claims, entitlements, or supported device families
- leave Apple UI touchpoints as short operator tasks with exact resume conditions, and keep working around them

## Output Contract

When you use this skill, the closeout should usually include:

- which screen was treated as the visual source of truth
- which shared primitives were extracted
- which screens were rebuilt on top of them
- where the analytics contract lives
- which tests/build commands proved the patch
- which release/TestFlight gates were affected, if any
- any residual trust gaps you did not fix
