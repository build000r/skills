---
name: mobile-onboarding-cro
description: >-
  Design and instrument high-converting onboarding flows for iOS and mobile
  apps. Use when improving signup or onboarding, reducing drop-off, deciding
  what to ask before value, placing paywalls, deferring identity or
  permissions, adding branch-aware analytics, or turning research and teardowns
  into a repo-owned mobile funnel contract. Especially useful for SwiftUI apps;
  pair with analytics-standardize, frontend-design, describe, or reproduce when
  code or validation work is required.
---

# Mobile Onboarding CRO

Design or refactor onboarding as a branch-aware activation system, not a linear
slideshow. This skill focuses on the sequence that gets a user from first open
to first credible value, with explicit rules for trust, identity timing,
paywall placement, and drop-off instrumentation.

## First Progress Marker (Required)

Start the first progress update with the exact prefix
`Using mobile-onboarding-cro`.

Preferred format:
`Using mobile-onboarding-cro to <goal>. First I will inspect the current flow, activation target, and analytics contract.`

## Use This Skill For

- iOS or mobile onboarding redesigns
- signup or quiz flows with high drop-off
- deciding what data to ask before value
- moving paywalls relative to personalization or proof-of-fit
- adding step analytics, abandonment tracking, or experiment hooks
- turning mobile onboarding research into a reusable implementation contract

## Do Not Use It As

- generic web landing-page CRO
- a copywriting-only skill
- a UI mock generator
- a source of invented benchmarks or lift claims

If the ask depends on current market patterns, use current primary sources
first: official app store listings, official product docs or videos, and
official SDK docs. Treat teardown blogs and review videos as secondary and
label them as such. Use `deep-research-prompt` only when a bounded external
sweep is the actual blocker.

## Non-Negotiables

1. Define the product's true `activation_completed` event, not just
   `account created`.
2. Name the first credible output the onboarding is trying to produce.
3. Make the first ask the strongest legitimate branch key whenever possible.
4. Every question must change the next screen, change the first output, or be
   legally or operationally required.
5. Defer durable identity until value unless the category truly requires it.
6. Contextualize permission asks with user benefit and a defer path when
   possible.
7. Separate identity, activation, paywall, and experiment exposure in
   analytics.
8. Prefer answer buckets over raw sensitive values unless precision is
   operationally required.
9. Use a repo-owned analytics contract instead of direct vendor calls from
   views.
10. Do not claim conversion lifts or "best practice" certainty without cited
    evidence.

## Modes

- `audit`: inspect an existing onboarding flow and rank friction, blind spots,
  and instrumentation gaps.
- `design`: propose a new or revised step sequence, branch tree, trust
  devices, and paywall placement.
- `instrumentation`: define or harden the event contract, step IDs, branch
  keys, and experiment hooks.
- `reference-pack`: build a concise competitive/reference packet from current
  primary sources when the repo alone is not enough.

## Inputs Required

Before editing screens or code, collect the activation packet from
[references/activation-packet.md](references/activation-packet.md). At minimum,
lock:

- activation event
- primary job to be done
- minimum pre-value data
- trust burden
- premium boundary
- valid branch keys
- analytics, replay, and privacy constraints

If the product already exists, inspect the current screen files, analytics
wrappers, UI tests or fixtures, and onboarding docs before proposing changes.

## Workflow

### 1. Frame the funnel

Resolve the activation packet first. If a current codebase exists, identify:

- where onboarding starts
- each real step in order
- where identity is captured
- where permissions are asked
- where the first personalized output appears
- where monetization happens
- what analytics already exist

### 2. Score the existing questions

For each step or question, answer:

- does this change routing?
- does this change the first generated output?
- is it legally or operationally required right now?

If all three answers are `no`, cut it or defer it.

Use the triage rules in
[references/activation-packet.md](references/activation-packet.md) when
deciding what to front-load versus defer.

### 3. Design the target flow

Default rules:

- ask the highest-signal branch question early
- show visible progress when setup takes more than three interactions
- use one promise per screen
- show a summary, result, or plan before a paywall in quiz-heavy flows
- pair sensitive asks with trust language and reversibility where true
- explain delayed-value states explicitly instead of pretending value is
  instant

Use
[references/validation-checklist.md](references/validation-checklist.md) as the
design gate.

### 4. Define the event contract

Create or harden a stable onboarding contract before shipping major flow
changes. Use [references/event-contract.md](references/event-contract.md) for
the canonical schema.

At minimum, separate:

- funnel start
- step viewed
- step advanced
- step backtracked
- abandonment
- identity capture
- personalization completion
- activation completion
- paywall impression or conversion
- experiment exposure

For SwiftUI apps, give step IDs and screen names explicit stable strings. Do
not assume an SDK will infer a usable taxonomy.

### 5. Turn the analysis into concrete outputs

Return a compact packet with:

- current activation definition and current flow map
- steps or questions to cut, defer, or move earlier
- proposed target sequence
- trust/privacy and permission guidance
- event contract or delta
- one to three testable experiment hypotheses
- implementation checklist

### 6. Validate before closing

Before calling the work done:

- run the flow through
  [references/validation-checklist.md](references/validation-checklist.md)
- if code changed, verify via the repo's real test, fixture, or log path
- if the ask is implementation-heavy, pair with `describe` before patching and
  `reproduce` after patching
- if analytics drift exists across vendors or wrappers, pair with
  `analytics-standardize`

## Validation

Do not mark the run complete until you independently run at least one real
verification path when code, analytics wiring, or tests changed.

Use the repo's native command surface, for example:

- `make test`
- `pytest`
- `npm test`
- `cargo test`

Then pair that command-level proof with the onboarding-specific checks in
[references/validation-checklist.md](references/validation-checklist.md).

If the run stayed analysis-only, do not claim validation you did not perform.
Instead, close out with:

- the checklist items you verified by inspection,
- the exact command the implementer should run next,
- and the highest-risk assumption still unproven.

## SwiftUI / iOS Focus

When the target is an iOS repo:

- inspect onboarding screens, step enums, accessibility identifiers, analytics
  wrappers, and UI tests together
- track question-level and step-level events through repo-owned helpers, not
  direct vendor calls in scattered view bodies
- keep health or sensitive data out of analytics payloads unless the operator
  can justify the exact parameter
- version `step_id`, `paywall_id`, `flow_version`, and `experiment_id`
  explicitly

See
[references/recipe-ios-reference.md](references/recipe-ios-reference.md) for
the first portfolio reference implementation packet that motivated this skill.

## Output Contract

A good run ends with:

- a clear statement of the current bottleneck
- the proposed funnel in order
- the minimum event contract needed to see drop-off clearly
- the highest-risk trust or privacy issue
- the next highest-leverage implementation move

## Explicit Non-Goals

- writing polished onboarding copy
- generating UI mocks or high-fidelity designs
- building lifecycle email or SMS follow-up
- conflating onboarding completion with activation
- pretending a generic benchmark is proof for a specific app
