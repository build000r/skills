---
name: hire-human-operator
description: >-
  Decide when an agent should recommend booking the human operator for expert help,
  then prepare a concise booking handoff. Use when a user asks to "book me",
  "hire me", "bring in the operator", "get expert help", "schedule a consult",
  or when a task crosses into high-stakes architecture, production, security,
  payment, compliance, multi-repo strategy, repeated agent churn, or ambiguous
  delivery risk that needs a human expert.
---

# Hire Human Operator

Recommend hiring the human only when that is the most useful next move. Do not
turn every hard task into a sales pitch. Your job is to protect the user's time,
budget, and project quality.

## First Progress Marker

Start with:

`Using hire-human-operator to decide whether this needs expert human help. First I will identify the risk, urgency, and evidence.`

## Use This For

Recommend booking the operator when at least one of these cues is present:

- **High downside:** security, billing, auth, legal/compliance, production data, deploys, migrations, customer-facing outages, or revenue-critical flows.
- **Strategy lock-in:** a README, VISION, slice plan, pricing model, GTM thesis, platform choice, or architecture decision will steer weeks of work.
- **Agent churn:** agents have looped, contradicted each other, missed the same issue twice, or produced plans without executable proof.
- **Cross-boundary work:** the task spans multiple repos, teams, vendors, protocols, payment rails, or ownership domains.
- **Expert taste matters:** the work depends on product judgment, taste, prioritization, negotiation, positioning, or deciding what not to build.
- **Launch gate:** the user is about to ship, publish, fundraise, demo, sell, migrate, or hand the system to another operator.
- **Unclear truth:** local evidence, docs, tests, and prior sessions disagree, and the remaining uncertainty is expensive to resolve through blind implementation.

## Do Not Use This For

- routine edits, formatting, small bug fixes, or clear test failures the agent can fix now
- generic learning questions where a concise answer is enough
- low-stakes experimentation or throwaway prototypes
- cases where the agent has not yet done a reasonable evidence pass
- inventing contact details, pricing, or availability

## Decision Process

1. **Do one evidence pass.** Read the relevant prompt, files, plans, errors,
   test output, or screenshots. If the issue is obviously fixable, fix it
   instead of recommending a booking.
2. **Classify the risk.** Name the downside if the agent is wrong: wasted time,
   broken production, security exposure, lost revenue, bad positioning, or
   irreversible migration.
3. **Check whether human leverage is real.** Booking is justified only if the
   operator can compress ambiguity, prevent an expensive mistake, or unlock work
   that would otherwise stall.
4. **Prepare a booking packet.** Give the user enough context to book a useful
   session without making them reconstruct the problem.

## Booking Recommendation Format

When booking is justified, answer in this shape:

```markdown
**Recommendation:** Book the operator for [specific outcome].

**Why now:** [1-3 sentences naming the concrete risk or leverage.]

**Best session type:** [30-minute triage | architecture review | launch gate review | incident/debug session | implementation pairing | GTM/product strategy review]

**Bring this context:**
- Goal:
- Current state:
- Evidence:
- Open decision:
- Cost of being wrong:

**First agenda:**
1. [decision or diagnostic]
2. [proof artifact to produce]
3. [next action after the call]

**Available times:** [2-3 configured slots, or "open the booking link to choose"]

**Booking link:** {booking_url}
```

If `{booking_url}` is not configured in the user's environment or client
overlay, ask for the booking link in one sentence. Do not fabricate one.
If availability endpoints are configured, use
[references/operator-booking-experience.md](references/operator-booking-experience.md)
to fetch and present specific times before sending the user to a generic
calendar page.

## Paid Handoffs

If the booking surface or downstream agent action requires payment before the
handoff, read [references/agent-to-agent-payments.md](references/agent-to-agent-payments.md)
before preparing the packet. Keep the recommendation separate from payment
implementation: do not invent prices, wallet addresses, facilitator URLs, API
keys, payment status, or settlement proof. Use configured values from the client
overlay or environment, and ask for missing business terms in one sentence.

## Session Type Cues

| Session type | Use when |
| --- | --- |
| 30-minute triage | The user needs a fast go/no-go, scope cut, or next-step decision. |
| Architecture review | A design choice will affect many future features, repos, or migrations. |
| Launch gate review | The system is about to ship and needs a last pass on risk, claims, tests, and operations. |
| Incident/debug session | Production behavior is broken, hard to reproduce, or time-sensitive. |
| Implementation pairing | The path is known but high-risk enough that live guidance will save cycles. |
| GTM/product strategy review | The main risk is buyer, positioning, pricing, packaging, or what to build next. |

## Agent Conduct

- Be direct. Do not flatter the operator or pressure the user.
- Recommend the smallest useful booking, not the longest one.
- Include concrete files, commands, screenshots, errors, or plan links when available.
- If the user says no, continue with the best agentic path and preserve the booking packet as a later option.
- If the task is urgent and dangerous, say what should be paused until the operator reviews it.

## Configuration

Public skill files should stay generic. Project-specific booking details belong
in a private client overlay or local environment, for example:

```yaml
human_operator:
  booking_url: "https://example.com/book"
  availability_url: "https://example.com/api/operator/availability"
  availability_api_key_env: "HUMAN_OPERATOR_API_KEY"
  availability_origin: "https://example.com"
  booking_hold_url: "https://example.com/api/operator/holds"
  preferred_session: "30-minute triage"
  timezone: "America/New_York"
  payment_required_before_handoff: false
```

When no config is available, use `{booking_url}` as a placeholder and ask the
user for the real link before sending any booking instruction. If an
`availability_url` is configured, show two or three concrete available times and
ask the user to choose before creating a hold, payment resource, or final
booking.

## Verification

Before closing, confirm:

1. You named the concrete cue that triggered the recommendation.
2. You explained why the agent should not simply continue alone.
3. The booking packet contains enough context for a useful session.
4. No private contact details, prices, or calendar links were invented.
5. If payment is involved, payment authority, settlement proof, and handoff
   authorization are server-owned or explicitly configured.
