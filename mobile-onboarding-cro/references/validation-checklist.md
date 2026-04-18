# Validation Checklist

Use this before shipping flow changes or closing an onboarding CRO audit.

## Flow Quality

- Is the first ask the strongest real branch key?
- Does every step have a defensible reason to exist right now?
- Is there visible progress when the setup takes more than three interactions?
- Does the user see evidence that answers changed the path or output?
- Is there a proof-of-fit screen before a paywall in quiz-heavy flows?
- Is delayed value explained honestly when the result does not appear
  immediately?

## Trust And Permissions

- Is each sensitive ask paired with a plain-language reason?
- Does the flow clearly separate optional from required information?
- Are permission asks contextualized and deferrable when possible?
- Does the flow avoid front-loading durable identity without a good reason?
- Are sensitive answers bucketed or omitted from analytics?

## Instrumentation

- Are `onboarding_id`, `flow_version`, and `step_id` stable?
- Can the operator see step views, advances, backtracks, and abandonment?
- Are identity capture, personalization completion, activation, and paywall
  events separate?
- Are branch keys attached to downstream onboarding events?
- Is duplicate exposure or duplicate event firing prevented?

## Experiment Readiness

- Is there one clear hypothesis per experiment?
- Is `experiment_exposed` logged at the first eligible exposure point?
- Can every variant still produce analyzable branch and step events?
- Are you avoiding stacked experiments you cannot interpret?

## SwiftUI / iOS Proof

- Do key steps have explicit analytics names or IDs?
- Do important screens and controls have stable accessibility identifiers?
- Is the analytics wrapper the single source of truth for event names?
- Is there a repeatable verification path: unit tests, UI fixtures, or local
  log validation?
