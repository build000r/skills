# Scope-Pruner Scoring Rubric

Objective: for each feature, estimate how much it advances the confirmed
vision per unit of ongoing cost, so that verdicts (CORE / SHARPEN / PARK /
CUT) are optimizable and comparable across runs instead of vibes.

Scale: every dimension is scored on a 0-1000 scale, with anchors at 0 / ~500 /
1000 defined per dimension below. Weighted sum → `alignment_score`.
`alignment_loss = 1000 - alignment_score`. Always report the top loss
contributor per feature in one sentence — that sentence is the finding.

## Anchor Snapping

A dimension score must be either (a) one of that dimension's defined anchor
values, or (b) an interpolation between two adjacent anchors that names the
two bracketing facts ("above 'reachable but optional' because X, below 'main
path for a minority' because Y"). Freehand precision ("683") is not allowed —
choosing a score means choosing an anchor definition, which is textual and
disputable.

## Evidence Tiers (scores are claims, claims need receipts)

- **T1 — observed behavior**: analytics, logs, revenue, crash reports, issues
  filed by real users.
- **T2 — artifacts**: pricing/landing copy, docs, code paths, routes, tests,
  git history. Bounded-search *absence* is citable T2 ("searched pricing,
  README, issues; feature is unmentioned").
- **T3 — inference**: the agent's own reasoning, uncited.

Citation rules (scoped to control token cost — cite verdict-drivers, not
everything):

- Each feature's largest-loss dimension, plus any dimension scored ≥750 or
  ≤250, needs a receipt: `path:line`, commit hash, issue/bead ID, route or
  test name, URL, or a quoted product-copy line (≤15 words).
- Directional caps: `journey_criticality` >400 requires a T1/T2 usage or
  primary-path artifact; `vision_fit` >750 requires the exact vision clause;
  `differentiation` >500 requires T2 positioning evidence (something actually
  sold or said); a non-goal contradiction cap requires **quoting the exact
  non-goal line**.
- **Unknown is not neutral.** Missing evidence is written `?`, never silently
  scored 500. A `?` on a capped dimension yields a conservative range; if the
  range crosses a verdict threshold, mark the row `PROVISIONAL/BOUNDARY` and
  take the lower verdict until evidence lifts it. A drafted (unconfirmed)
  vision caps `vision_fit` itself — a claim cannot be more certain than its
  yardstick.

Honest framing: receipts make dishonest scoring *effortful and auditable* —
they do not make the output verified. Required Verification includes a
spot-check: resolve 3 receipts (or all, in single-feature gate mode) before
handing back.

## Dimensions

### vision_fit (weight 0.32)

Does the confirmed vision *require* this feature?

- 0: contradicts a stated non-goal (quote it — this also triggers a hard gate)
- 250: unrelated to the vision; exists because it was easy or impressive
- 500: plausibly adjacent; the vision tolerates it but never mentions it
- 750: the vision implies it (a stated job needs it to be true)
- 1000: the vision is false without it

### depth_leverage (weight 0.27)

Depth vs breadth. Does this make the core loop deeper (faster, more reliable,
more delightful, more trustworthy) or the product wider (a new parallel thing
to do)?

- 0: pure breadth — a new surface with its own loop, users, and upkeep
- 300: mostly breadth with a thin bridge to the core loop
- 500: neutral plumbing both sides use
- 750: strengthens an existing core-loop step
- 1000: multiplies the core loop itself (quality, speed, retention of the
  main job)

### journey_criticality (weight 0.16)

Does the primary user (the one the vision names) hit this on the happy path?

- 0: no real user has ever reached it, or only the operator uses it
- 400: reachable but optional; a minority path
- 700: on the main path for a meaningful minority
- 1000: every successful session touches it

### maintenance_drag (weight 0.15, INVERTED — high drag lowers the score)

What does keeping this cost every future change?

Score the *drag*, then invert (`contribution = 1000 - drag`):

- drag 0: isolated, dependency-free, never breaks (low drag needs evidence of
  isolation, not just absence of observed problems)
- drag 400: occasional special-casing in shared code paths
- drag 700: shows up in most cross-cutting changes (schema, auth, deploys),
  own dependencies, own test surface
- drag 1000: routinely breaks builds/deploys, blocks upgrades, or forces
  every new feature to account for it

### differentiation (weight 0.10)

Would the target user pick this project because of this feature?

- 0: table stakes or invisible
- 500: nice-to-have they'd mention after the fact
- 1000: a named reason to choose/pay for this over alternatives

Differentiation only counts when pointed at the vision's user. "Would impress
a developer on Hacker News" scores 0 — see anti-gaming.

## disposition_risk (separate output — NOT part of alignment_score)

Removal/migration exposure: live users, paying customers, external API
consumers, data migrations, contracts. Reported per PARK/CUT candidate as
`low / medium / high` with the named consumer class or migration artifact.

Disposition risk shapes *how* to remove (deprecation cycle vs delete), never
*whether* the feature belongs. Folding it into alignment let entrenched,
misaligned features look aligned precisely because they are hard to remove —
that is the entrenchment bug this split fixes. Sunk implementation effort is
excluded entirely.

## Formula

```
alignment_score = 0.32*vision_fit
                + 0.27*depth_leverage
                + 0.16*journey_criticality
                + 0.15*(1000 - maintenance_drag)
                + 0.10*differentiation
```

Verdict thresholds:

- ≥ 700 → CORE
- 500–699 → SHARPEN
- 300–499 → PARK
- < 300 → CUT

## Hard Gates (cannot be averaged away)

Each `true` gate needs a receipt and appears in the output row:

- Contradicts a confirmed non-goal (quoted) → never above PARK.
- Adds a new parallel user loop → never above PARK without a confirmed vision
  change.
- No named primary-user path → never CORE.
- No concrete SHARPEN refit stated → PARK, not SHARPEN.
- Live consumers or revenue (`disposition_risk: high`) → any approved CUT
  requires a deprecation plan, never silent removal.

## REMOVE/ABSORB Depth Gate (CORE/SHARPEN candidates only)

Before finalizing a CORE or SHARPEN verdict:

- **REMOVE**: name the specific core-loop step, outcome, or metric that gets
  worse if this feature does not exist — with a receipt (call site, route,
  test, usage path, or a confirmed requirement + acceptance test for planned
  features). "It makes the loop more trustworthy" with no artifact is not an
  answer. No concrete answer → cap at PARK. Invisible-but-load-bearing
  infrastructure passes only with a proof tied to the core loop (a failure it
  prevents), not a vibe about robustness.
- **ABSORB**: if the useful part can fold into an existing core-loop step
  without a new surface, SHARPEN must name that exact refit ("fold X into
  step Y and remove the parallel surface"). PARK/CUT rows skip this gate —
  it exists to counter keep-everything bias, not to add lines everywhere.

## Boundary Rule

If the weighted composite lands within ±50 of a verdict threshold, state both
candidate verdicts and justify the chosen side in one sentence keyed to anchor
definitions.

## Overrides

Threshold overrides are `OVERRIDE-PROPOSED`, never silently final: they need a
receipt, may move at most one verdict band, and become standing only when the
operator ratifies them. Report total override pressure (count) per run.

## Loss Framing

For the run as a whole, report:

- `portfolio_loss`: mean alignment_loss across the inventory
- `breadth_ratio`: share of features with depth_leverage < 500 — the single
  best summary of "wide vs deep"
- top 3 loss contributors across the repo and which dimension drives each
- override pressure and PROVISIONAL count (high values = weak evidence base,
  fix that before trusting verdicts)

The next scope-pruner run on the same repo should try to reduce
`portfolio_loss` and `breadth_ratio`, primarily by executing approved
PARK/CUT verdicts and landing the active depth contract.

## Anti-Gaming Rules

- **WOW is a warning, not credit.** "Impressive", "magical", "demo-ready"
  language in commits/docs raises scrutiny on vision_fit; it never raises any
  dimension.
- **No sunk cost.** Effort already spent building a feature counts nowhere.
- **No self-dealing on journey_criticality.** Operator-only and agent-only
  usage does not count as the primary user's happy path unless the vision
  names the operator as the user.
- **SHARPEN is not a safe harbor.** No named refit → PARK (hard gate).
- **Do not average away contradictions.** Hard gates above.
- **Unknowns stay visible.** `?` → range + PROVISIONAL, never a quiet 500.
- **Receipts ≠ verification.** A resolvable receipt is not a supported claim;
  it is an auditable one. Never present receipt-bearing output as "verified".
- **Scoring posture matters.** Under an EXPLORE posture (see vision-sources),
  time-boxed experiments may be scored leniently but must carry an expiry;
  under MAINTAIN, new surfaces default to PARK unless they replace an
  existing one.
