# Recipe IOS Reference Packet

This skill was first extracted from the `recipe-ios` onboarding hardening work.
Use that repo as a proof case, not as a template to copy blindly.

## Concrete Reference Files

- `recipe-ios/recipe-ios/Views/Screens/SignInView.swift`
- `recipe-ios/recipe-ios/Views/Screens/SignUpView.swift`
- `recipe-ios/recipe-ios/Analytics/AppAnalytics.swift`
- `recipe-ios/docs/ANALYTICS_CONTRACT.md`

## What The Reference Implementation Proves

- A welcome shell can hand off into onboarding through an explicit,
  repo-owned analytics contract.
- Multi-step signup can expose stable step names instead of relying on inferred
  analytics taxonomy.
- SwiftUI flows can use visible segmented progress across onboarding sections.
- A decisive branch question can auto-advance when the answer is strong enough.
- Accessibility identifiers can make onboarding UI fixtures more reliable.

## Gaps To Avoid Copying Blindly

- `recipe-ios` does not yet prove paywall timing or paywall instrumentation.
- It does not yet show a production `experiment_exposed` loop.
- It currently tracks step views and advances, but not the full
  abandonment/backtrack contract from this skill.
- Health-adjacent onboarding still needs explicit privacy review before adding
  richer analytics sinks or replay links.

## How To Reuse The Packet

When extracting lessons into another mobile app:

1. Rebuild the activation packet for the new domain instead of copying the old
   questions.
2. Keep the analytics-wrapper pattern and stable step naming.
3. Reassess trust burden, premium boundary, and delayed-value handling from
   scratch.
