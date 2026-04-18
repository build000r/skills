# Event Contract

Use a repo-owned analytics wrapper and keep onboarding events stable across
vendors. Do not call GA4, Firebase, PostHog, or other SDKs directly from views.

## Shared Parameters

Put these on onboarding events whenever they apply:

- `onboarding_id`: Stable funnel instance ID created at entry.
- `flow_version`: Version of the flow contract.
- `step_id`: Stable machine ID for the current step.
- `step_index`: Zero-based or one-based step order. Pick one and stay
  consistent.
- `screen_name`: Stable surface name.
- `branch_key`: The current route bucket or answer path.
- `app_version`
- `platform`

Optional:

- `experiment_id`
- `variant_id`
- `paywall_id`
- `replay_id`

Keep sensitive values bucketed. Avoid raw health data, free text, or personal
identifiers when a coarse category is enough.

## Canonical Events

### `onboarding_started`

- Purpose: Mark the first moment the user enters the funnel.
- Required parameters: `onboarding_id`, `flow_version`, `entry_point`,
  `screen_name`.
- Do not fire when: the user merely views a marketing shell without entering
  setup.

### `onboarding_step_viewed`

- Purpose: Make per-step drop-off measurable.
- Required parameters: `onboarding_id`, `flow_version`, `step_id`,
  `step_index`, `screen_name`.
- Optional parameters: `branch_key`, `experiment_id`, `variant_id`.
- Do not fire when: decorative subcomponents render inside the same step.

### `onboarding_advanced`

- Purpose: Measure successful progression between meaningful steps.
- Required parameters: `onboarding_id`, `flow_version`, `from_step_id`,
  `to_step_id`, `to_step_index`.
- Optional parameters: `branch_key`, `advance_method`.
- Do not fire when: a picker changes locally but the user has not advanced.

### `onboarding_backtracked`

- Purpose: Capture where users retreat or reopen prior decisions.
- Required parameters: `onboarding_id`, `flow_version`, `from_step_id`,
  `to_step_id`.
- Optional parameters: `branch_key`, `reason`.
- Do not fire when: the app restores state on relaunch without an intentional
  back action.

### `onboarding_abandoned`

- Purpose: Record that a user dropped before activation.
- Required parameters: `onboarding_id`, `flow_version`, `last_step_id`,
  `last_step_index`, `abandon_reason`.
- Optional parameters: `branch_key`, `time_in_funnel_seconds`.
- Do not fire when: the user later resumes the same active session and no
  abandonment threshold was crossed.

### `identity_captured`

- Purpose: Separate durable account creation or login from the rest of funnel
  progress.
- Required parameters: `onboarding_id`, `identity_method`.
- Optional parameters: `flow_version`, `step_id`.
- Do not fire when: the user types into fields without successfully creating or
  linking identity.

### `personalization_completed`

- Purpose: Mark completion of the minimum inputs needed to generate a tailored
  result.
- Required parameters: `onboarding_id`, `flow_version`, `personalization_type`.
- Optional parameters: `branch_key`, `summary_variant`.
- Do not fire when: required upstream inputs are still missing.

### `activation_completed`

- Purpose: Mark the first true value moment.
- Required parameters: `onboarding_id`, `activation_type`.
- Optional parameters: `flow_version`, `branch_key`, `time_to_activation_seconds`.
- Do not fire when: the user only lands on a home screen without completing the
  value action.

### `paywall_viewed`

- Purpose: Separate monetization pressure from the rest of onboarding.
- Required parameters: `onboarding_id`, `paywall_id`, `placement`,
  `offer_context`, `trial_offer_type`.
- Optional parameters: `branch_key`, `experiment_id`, `variant_id`.
- Do not fire when: the user opens a general settings subscription screen after
  onboarding.

### `paywall_converted`

- Purpose: Connect a specific onboarding paywall to revenue conversion.
- Required parameters: `onboarding_id`, `paywall_id`, `product_id`, `price`,
  `currency`, `trial_offer_type`.
- Optional parameters: `billing_period`, `discount_percent`.
- Do not fire when: the purchase is pending, restored, canceled, or duplicated
  by receipt reconciliation.

### `experiment_exposed`

- Purpose: Anchor causal analysis to the first moment a user could experience a
  treatment.
- Required parameters: `experiment_id`, `variant_id`, `exposure_point`,
  `onboarding_id`, `flow_version`.
- Optional parameters: `branch_key`, `allocation_version`.
- Do not fire when: the treatment was not actually eligible or visible yet.

## SwiftUI Notes

- Define step IDs in code, not by inferred view names.
- Keep analytics names and accessibility identifiers aligned where practical.
- Emit one meaningful event per user action, not per state mutation.
