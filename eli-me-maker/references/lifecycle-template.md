# Private Lifecycle Communication Template

Card schemas for a full-lifecycle `eli-me` profile: selling to, advertising
to, and emailing clients matching a target person or persona — in their
language, carrying the operator's brand voice the whole way through.

All cards below are private output. The public maker owns only these generic
schemas and the calibration method. Generate only the cards the operator's
current surface needs; every ungenerated card is a documented gap, not a
silent default. Uncalibrated rows must say so (`basis: provisional`), never
masquerade as learned truth.

## Ordering Contract

The Target & Evidence Authority card is a hard prerequisite: no voice,
lifecycle, or objection question may be asked before it exists, because it
decides who answers and with what standing. After it, build in value order:
objection ledger or lifecycle matrix first (whichever surface the operator
needs now), braid rules alongside, relationship cards when existing-client
copy starts.

## 1. Target & Evidence Authority Card

```markdown
## Target and evidence authority

Target type: self | named person | persona/segment | provisional hypothesis
Respondent: subject | authorized proxy | operator
Evidence basis: direct answers | bounded evidence pack | research synthesis | none yet
Evidence pack: [operator-named artifacts only: e.g. 6 proposals (3 won/3 lost),
  20 emails (replied vs ignored), 30 reviews — with date range]
Scope: offer / audience / region / lifecycle states the evidence represents
Known gaps: states or decisions the evidence does not cover
Confidence: confirmed | supported | provisional
```

Rules:

- The maker never roams the workspace for customer evidence. It accepts only
  operator-named files, a curated pack, or an explicit "no evidence yet".
- A persona is **evidence-informed, never evidence-answered**. Write "three
  supplied artifacts suggest X" or "operator predicts X" — never "the
  customer prefers X" unless the customer said it.
- Evidence artifacts are observations, not answers: reply rates are
  confounded by list, timing, and offer; won deals may share a strong seller;
  reviews are post-purchase language; silence labels nothing.

## 2. Brand Spine × Audience Braid

Two strands with per-decision ownership — not a 50/50 tone mixer.

```markdown
## Voice braid

Brand source: [canonical section below, or private references/brands/{brand}.md]

### Decision ownership
| Decision | Owner |
|---|---|
| Truth, claims, proof thresholds, ethics | Brand |
| Problem vocabulary, desired-progress words | Audience evidence |
| Next belief and CTA | Lifecycle state |
| Compression and format | Channel adapter |
| Conflict rule | Brand truth wins; unsupported audience inference is dropped |

### Keep ours
- [signature stance, cadence, claim style — behavioral, not adjectives]

### Speak theirs (lexicon)
| Our internal term | The word THEY use | Accuracy caveat |

### Never
- imitate slang, claim shared experience, infer private context,
  manufacture urgency or familiarity
```

Claims authority: "which sounds like us" duels calibrate voice only. What
may be *claimed* references an approved source (claim registry,
counsel-reviewed doc) or names an escalation route. Never minted by
calibration.

Brand extraction rule: the first profile carries the brand spine inline. At
the second persona or second brand scope, extract it to one canonical
private brand file (or a passive `eli-brand` skill with `depends_on` plus
explicit body routing) so brand evolution cannot silently fork the voice.

## 3. Lifecycle Intent Matrix (primary index)

State-primary, channel-secondary. States are semantic and re-enterable, not
a linear funnel. Six defaults; split a row only when evidence shows a
different next belief, risk, proof, or CTA ceiling.

```markdown
## Lifecycle intent matrix

| State | Current → next belief | Risk ref | Lead with | Proof | CTA ceiling | Never | Basis |
|---|---|---|---|---|---|---|---|
| Discover/orient | vague pain → recognized pattern | R-… | symptom in their words | concrete observation | inspect/learn | product dump | provisional |
| Evaluate | plausible → fits my case | R-… | mechanism + fit boundary | demo/comparison | scoped trial | hidden tradeoff | … |
| Decide | fits → worth committing | R-… | remaining risk resolved | right-sized proof | one commitment | pressure | … |
| Onboard/activate | bought → I can succeed | R-… | one first win | visible progress | complete one step | resell | … |
| Retain/expand | using → value compounds / adjacent need | R-… | verified outcome / observed need | account evidence | next habit / assess | vanity recap, feature dump | … |
| At-risk/win-back | left → relevance may have changed | R-… | changed value + permission | specific improvement | return or close loop | guilt | … |
| Advocate | succeeded → proud to vouch | R-… | their result, their numbers | verified success marker | one small declinable ask | ghost-written words, ask during open issue | … |
```

- "Next useful belief" is the row's job — never the terminal belief.
- `Risk ref` points at a ledger `R-*` id; the matrix selects risk, the
  ledger defines it. One authority, no drift.
- Pressure tolerance ("bounces past 2/month") is calibratable audience
  knowledge; send triggers and caps are campaign-system policy the copy
  agent cannot verify and must not claim to enforce.

State routing rule for agents: use an explicitly supplied state or trigger;
otherwise infer from observable relationship facts (never from channel),
name the inference and confidence in the brief, and when two states imply
different claims or CTA ceilings, pick the lower-commitment row or ask one
concrete state fork.

## 4. Channel Adapter

```markdown
| Surface | Preserve | Adapt |
|---|---|---|
| Pitch/proposal | state, risk, proof, fit boundary | depth, interaction |
| Ad + landing | state, problem, promise, truth | compression, hook, proof escalation — landing continues the ad's exact promise |
| Lifecycle email | state, relationship truth, next action | continuity, context |
```

## 5. Objection → Uncertainty → Proof Ledger

Objections are compressed statements of risk, not prompts for rebuttals.
Rank by impact × confidence, not frequency; keep the top 3–5.

```markdown
## Objection ledger

| Risk id | Verbatim objection (their words) | Underlying uncertainty | Status | Do not assume | Acknowledge | Answer / fit boundary | Approved proof or `missing` | Next step | Never | Basis |
|---|---|---|---|---|---|---|---|---|---|---|
| R-price | "too expensive for what it is" | cash timing, adoption, or weak value case | hypothesis | ignorance of ROI | name the tradeoff | clarify which cost; concede if value absent | calculation with their inputs | calculate or decline | unsupported "pays for itself" | … |
```

- One objection fans into several uncertainties; route to proof options or
  one diagnostic question, never a mechanical objection→proof pairing.
- Some rows correctly terminate in "not a fit" — disqualification builds
  the trust that closes the next deal.
- Pre-handle vs reply: a reply may name the objection; an ad must not plant
  a concern the audience did not have.
- Proof cells point at the harvest record (section 7) or say `missing` —
  never invent the case study, number, or guarantee.

## 6. Relationship Cards

### 6a. Account-Brief Join (existing-client copy)

Stable persona knowledge never contains live account facts. Each
existing-client task supplies an ephemeral account brief; the join happens
at draft time.

```markdown
### Account-context join
- Required before existing-client copy: purchased offer, stated outcome,
  verified progress, open issues, last meaningful contact — each marked
  known / unknown. Unknown fields stay unknown; never filled from persona
  inference.
- Precedence: account fact > persona default; their own words > segment
  vocabulary; current verified goal > original sales goal; brand truth
  bounds everything.
- Missing context lowers personalization and CTA pressure. Never imply
  usage, progress, disappointment, intent, or prior conversation the brief
  does not establish.
- Account briefs are not persisted into this profile.
```

### 6b. Sender Identity & Authority

Brand voice does not answer who is speaking. Table one row per sender role
the operator actually uses:

```markdown
| Sender role | May say "I…" about | May promise | Reply owner | Never imply |
|---|---|---|---|---|
| Founder | beliefs, decisions personally made | approved commitments only | named person | personal review not performed |
| Automated/product | observable product state | nothing discretionary | monitored route or explicit no-reply | human attention or emotion |
```

Drafting rule: declare the sender before drafting; if the desired claim or
intimacy exceeds the role's envelope, route to the authorized human instead
of writing around the limit.

### 6c. Reply Authority (inbound tripwire)

Copy that converts generates replies. Fail-closed table:

```markdown
| Inbound signal | Agent may | Must escalate | Never |
|---|---|---|---|
| Buying signal (pricing/call/timeline ask) | acknowledge + hold | immediately | continue the drip |
| Question a ledger/matrix row answers | draft reply citing the row | if basis < confirmed | improvise claims |
| Anger / complaint | acknowledge once, no defense | same day, with thread | cheerful on-card copy |
| Legal / compliance / data request | nothing | immediately | any substantive reply |
| Prose opt-out | confirm stop + halt sequence | log it | argue |
| Commercial terms (discount/refund/contract) | restate published terms | any deviation | imply yes |
| Unclassifiable | nothing | default route | guess |
```

Escalation packets are composed under the operator's own `eli-me`
explanation contract — the one place the explanation profile and the
lifecycle profile compose directly.

### 6d. Accountability, Bad News, and Graceful Exit

When the company caused harm, a material issue is open, or the customer
asked to leave: persuasion suspends.

```markdown
### Accountability mode
Order: verified impact in their terms → known vs unknown → own our part →
remedy or authorized action → next update time → clear exit/escalation path.
Suspend: urgency, upsell, referral asks, proof-as-defense, performed empathy,
save offers before the exit path is clear.
A clean exit is a valid success outcome.

### Bad-news rules (price increase, deprecation, incident)
- Change + number + effective date within the first two sentences.
- The real reason in one sentence, or none. Banned: "to serve you better",
  benefit-framing of a take-away.
- The reader's arithmetic: what THIS segment pays/loses, before and after.
- Apology register: own it once, remedy, prevention, stop.
- Every bad-news send pre-arms the anger and commercial-terms reply rows.
```

### 6e. Advocacy & Proof Harvest

The stage that manufactures the proof the ledger consumes.

```markdown
| Asset | Source | Consent scope | Fresh until | Ledger rows it serves |
```

Ask only after a verified success marker with no open issues; one specific,
small, declinable ask; agents may reduce the customer's effort (draft
questions, offer transcription) but never ghost-write words for the
customer to sign.

## 7. Pre-Draft Declaration (cold-agent contract)

Every copy task starts by filling this; a material unknown lowers
specificity or routes the gap — it is never invented:

```text
Brand / offer:
Target + evidence scope:
Sender role and actual mechanism:
Account facts supplied / missing (existing clients):
Lifecycle state + confidence:
Current → next belief:
Active risk id, if evidenced:
Approved proof ref or `missing`:
CTA ceiling:
Accountability trigger: yes/no
Channel:
```

## 8. Lifecycle Copy Closeout

Run before any artifact ships:

- Claim lineage holds: no contradiction and no unsupported escalation vs
  adjacent funnel stages (not verbatim sameness — the ad earns recognition,
  the landing expands mechanism, onboarding fulfills).
- Customer language fits the declared target and evidence scope; brand
  invariants remain detectable; banned words absent.
- Lifecycle state and next belief were declared; CTA within the state's
  ceiling; active risk used the canonical ledger row.
- Proof is real, approved, and proportionate — or the draft says `missing`.
- Personalization uses only supplied, authorized context; sender-truth
  holds (no borrowed intimacy or authority).
- Deterministic checks (exact banned phrases, required disclaimers, CTA
  count, subject length, unresolved placeholders) may be scripted; semantic
  checks (claim lineage, on-brand, faithful language) are agent/human
  judgment. A script is never presented as proof of a semantic property.

### Copy Score Contract

When judging a draft (closeout or cold-agent acceptance), score 0–1000 per
dimension and roll up with these weights; anchors: 0 = absent/harmful,
500 = passable with supervision, 800 = ships, 1000 = evidence-backed exemplar.

| Dimension | Weight | High score means |
|---|---:|---|
| Customer recognition | 30% | Problem, vocabulary, proof, and commitment level fit the declared target and evidence scope |
| Brand recognition | 25% | Promise, claims, ethics, and signature voice remain detectably ours |
| Lifecycle fit | 25% | Advances one declared next belief with a right-sized CTA for the state |
| Evidence honesty | 20% | No invented knowledge, proof, urgency, personalization, or certainty |

`copy_score = Σ(weight × dimension)`. Any dimension below 500 is a hard
fail regardless of the rollup. Report the lowest dimension as the loss to
reduce next; do not tune one dimension by sacrificing evidence honesty —
that dimension is never traded.

## 9. Sparse Update Rule

- Confirmed defaults carry no annotation. Provisional or contested rows
  carry one `basis` tag. Changed rules get one dated note only when the
  reason matters.
- An explicit correction from the subject or proxy patches the narrowest
  applicable row immediately (Mode D behavior).
- A behavioral metric (opens, clicks, wins, churn) only ever **proposes** a
  hypothesis — competing explanations stated, narrowest scope proposed,
  explicit operator review before any patch. No count threshold makes
  confounded signals into evidence; never auto-patch from metrics.
- Full evidence ledgers, revalidation windows, and superseded-rule history
  are v2, earned by observed profile churn.
