# Lifecycle Calibration Prompts

Calibration flights for full-lifecycle communication profiles (sell /
advertise / lifecycle email). Same discipline as the explanation ladder in
[calibration-prompts.md](calibration-prompts.md): concrete A/B/C choices,
dependency-ordered by ask-cascade, stop at enough signal. The examples here
are synthetic and public; a private run replaces their facts and vocabulary
with material from the operator's authorized evidence pack.

## Flight Rules

- **Evidence first, then flights.** Real evidence establishes facts,
  vocabulary, objections, and candidate rules; controlled A/B/C rewrites
  then isolate one decision each; the respondent confirms, rejects, or
  scopes the inferred rule. Synthetic examples are the bootstrap when no
  evidence exists, and the control when real artifacts vary on too many
  dimensions.
- **One variable per trio.** Hold offer, facts, and length roughly constant.
- **No projection phrasing.** For persona scope never ask "which would
  bring YOU back if you were them". Ask: which version best matches the
  supplied evidence; what observed phrase supports that choice; which makes
  the smallest unsupported assumption.
- **Record the reason, not the letter.** Encode why the winner won as an
  executable rule with a `basis` tag; accept hybrids and "none".
- **Stop** when remaining uncertainty would not change an artifact.

## Round 0: Profile Scope And Authority

Ask before any style or lifecycle question:

```text
Scope decision: what should this profile cover?

1. Explanation preference only (existing ladder)
2. Full lifecycle communication (sell / advertise / lifecycle email)
3. Both

And who answers for the target?

1. The subject themselves
2. A named proxy who knows them
3. Nobody can sit for this (customer persona) — I will name a small
   authorized evidence pack (won/lost proposals, replied vs ignored emails,
   reviews, tickets) or declare "no evidence yet" for a provisional profile.
```

Fill the Target & Evidence Authority card from the answers before
continuing. For option 3, everything downstream is evidence-informed and
tagged accordingly.

## Root Flight 1: Brand/Customer Balance

Same truthful claim, three balances:

```text
1. Brand-dominant: "Accurate receivables. Clear decisions. No surprises."
2. Customer-dominant: "Stop spending Friday night figuring out who still
   owes you."
3. Braided: "Know exactly which invoices need attention — without giving
   up Friday night."

Which feels both credible and personally legible for the target — 1, 2, 3,
or a hybrid? Which exact phrase creates or breaks that feeling?
```

The answer routes follow-ups (rejection of 2 → informality, invented
context, or missing proof? winner 3 → where does the braid sit for
proposals vs ads?) and seeds the braid's decision-ownership rows.

## Root Flight 2: Recognition Frame

```text
1. Product-first: "We give independent operators a single receivables
   workspace."
2. Problem-first: "Most operators don't need more reports; they need to
   know which unpaid invoice deserves attention now."
3. Outcome-first: "You should be able to decide what to chase, what to
   wait on, and why, in minutes."

Which would keep the target listening? Which sentence feels generic or
assumptive?
```

## Root Flight 3: Trust Move / Proof Type

Same claim, three proof forms — quantitative result with conditions,
mechanism explanation, peer example with context. Ask which reduces
uncertainty fastest and which triggers skepticism. Seeds the matrix's
proof column and the ledger's proof options.

## Root Flight 4: Commitment Move / CTA

Three CTAs of increasing commitment for the same message. Ask which is easy
enough to take yet meaningful enough to advance. Seeds per-state CTA
ceilings; follow up on whether a permission-based CTA is global or limited
to high-friction and re-entry states.

## Per-State Flights

Run only for states the operator needs now. Two examples:

Onboarding:

```text
1. Resell: "You made the right choice — here are all twelve features."
2. Orient: "First, connect one account. You'll see your overdue invoices
   in about two minutes."
3. Reassure: "Setup can wait until tomorrow; here's what to have ready."
```

Win-back:

```text
1. Guilt/familiarity: "We miss you. Come back for 20% off."
2. Renewed value: "The cash-flow view now shows the exceptions that need
   a decision."
3. Permission: "Is this still useful, or should we close the loop?"
```

Ask which asks for the right next belief for that state and where
assertiveness becomes pressure. The permission answer sets the win-back
row's CTA and Never cells.

## Objection Flights

One flight per material objection. Vary the response frame, not the facts:

```text
"Too expensive":
1. Defend ROI: "It pays for itself if it saves two collection hours a week."
2. Bound fit: "If collections aren't already costing more than this, it
   may be too early."
3. Diagnose: "Is the concern total cost, cash timing, or whether the team
   will use it?"

Which response helps the target evaluate rather than feel handled? What
proof would make it credible? Which phrase loses trust?
```

Seed rows from the evidence pack (lost-deal notes, churn reasons, explicit
objections) before asking; silence is never treated as a labeled objection.

## Relationship Flights

Sender truth (same event, three senders):

```text
1. Founder: "I noticed you haven't connected the account yet."
2. Account manager: "Your setup shows one connection remaining. Reply here
   if the blocker is on our side."
3. System: "One connection remains before setup is complete."

Which sender can truthfully send each version? Which phrase implies human
attention that may not exist?
```

Personalization boundary (where relevance becomes presumption):

```text
1. Neutral: "If overdue invoices are slowing decisions…"
2. Context-aware: "You said collections are stealing a day each month…"
3. Implied intimacy: "We know how frustrating your Fridays have become…"
```

Accountability (service failure):

```text
1. Explanation-first: "A third-party provider caused an outage, but
   service is restored."
2. Empathy-but-vague: "We understand how frustrating this must have been."
3. Accountable-operational: "For 47 minutes you couldn't export. We failed
   to switch traffic when the provider degraded. Restored; validating
   delayed exports now; update by 3 p.m."
```

Bad news (price increase): band-aid-direct vs context-first vs
value-recap-first — the third is the trap most operators think they prefer
until they read it as the customer. Calibrate the lede rule and reason
policy from the choice.

Cancellation: save-first vs exit-first vs exit-plus-optional-repair. Ask
where retention effort becomes obstruction.

Advocacy ask: direct favor vs value-frame vs lowest-effort interview offer;
plus the public-voice axis — "here are three pull-quotes we might feature:
which would this persona be proud to attach their name to, which would
embarrass them?"

## Negative Flight

Show three deliberately *plausible* failures — one overclaims, one
overpersonalizes, one buries the point — and ask for the first phrase that
breaks trust. Negative selection produces crisper rules than
favorite-picking; encode each as a paired wrong-because/instead anchor.
