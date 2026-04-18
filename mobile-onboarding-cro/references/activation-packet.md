# Activation Packet

Lock this packet before redesigning the flow or editing code.

## Required Inputs

- `activation_event`: The user action that proves the app delivered value.
- `first_output`: The first concrete thing the user should receive, see, or
  unlock because of onboarding.
- `job_to_be_done`: Learn, track, plan, pair, record, convert, or another
  single dominant job.
- `minimum_pre_value_data`: The smallest data set needed to produce the first
  credible output.
- `trust_burden`: Low-risk lifestyle, sensitive health, public social,
  finance, or hardware/device pairing.
- `premium_boundary`: What stays free, what is gated, and when that boundary
  appears.
- `branch_keys`: The small set of questions that legitimately change routing or
  the first output.
- `delayed_value_state`: Whether value is immediate or arrives later and needs
  expectation-setting.
- `analytics_constraints`: The current sink, privacy rules, replay policy, and
  experimentation surface area.

## Question Triage

Keep a question early only if it:

- changes the next screen,
- changes the first generated output,
- is required to fulfill the promise right now, or
- is legally or operationally required.

Defer by default when the question is mainly about:

- profile completion,
- attribution,
- demographics,
- notifications,
- contacts or social graph,
- avatar or display customization,
- preferences that do not affect the first output.

Cut the question if the downstream effect is unclear or unverifiable.

## Default Sequencing Heuristic

1. Promise the result.
2. Ask the strongest branch key.
3. Gather only the minimum personalization data needed for the first output.
4. Show proof-of-fit: plan, summary, result, or clear next-state explanation.
5. Ask for identity, permissions, or payment only where they make sense.

## Trust Burden Notes

- Sensitive health and finance flows need stronger explanation, privacy
  language, and answer bucketing.
- Public-social flows need explicit explanation before asking for contacts,
  sharing, or social defaults.
- Hardware or delayed-value flows need expectation-setting when the result will
  arrive later.
