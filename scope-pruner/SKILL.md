---
name: scope-pruner
description: >-
  Critically evaluate a planned or existing feature against the project's
  vision and decide whether to keep, sharpen, park, or cut it — favoring depth
  on the core loop over breadth of surface area. Use for "is this in scope",
  "does this fit the vision", "prune scope", "feature creep", "scope creep",
  "depth not breadth", "should we remove this", "audit features against the
  vision", "why does this feature exist", "agents keep adding WOW features",
  "keep this out of scope", maintaining an OUT_OF_SCOPE.md ledger, patrolling
  a repo for re-added parked/cut features, or gating proposed work items
  (beads/plans) before they enter the backlog. Read-only by default: it
  recommends and records; it does not delete code without explicit approval.
---

# Scope Pruner

Agents (and humans) reliably increase the **breadth** of a project — new
surfaces, WOW-factor features, speculative options — faster than they increase
its **depth**: the quality of the few things the project exists to do. This
skill is the counterweight. It evaluates features against the project's vision
and produces one verdict per feature:

- `CORE` — directly serves the vision's primary loop. Keep; invest depth here.
- `SHARPEN` — right idea, wrong shape. Keep, but refit it to serve the core
  loop instead of standing beside it.
- `PARK` — deliberately out of scope *for now*. Record it in the scope ledger
  with a reason and a revisit condition. Code may stay, but no further
  investment.
- `CUT` — actively hurts focus, drags maintenance, or contradicts the vision.
  Propose removal. Removal itself requires explicit operator approval.

A feature that merely "works" or "is impressive" earns no verdict credit.
The question is never "is this good?" — it is "does this make the core thing
deeper, or the whole thing wider?"

## On Trigger

Start the first progress update with:

`Using scope-pruner ...`

## Do Not Use This For

- Deciding *where* work should live or whether to adopt open source — that is
  `build-vs-clone`.
- Code quality, security, or UX auditing — that is `codebase-audit`.
- Generating expansion ideas — that is `make-indispensable` or `smart`. This
  skill is their adversary; run it *after* them, not instead of them.
- Prioritizing an existing backlog by value — that is a beads/triage concern.
  Scope-pruner decides membership (in/out), not ordering.

## Modes

| Request shape | Mode | Output |
|---------------|------|--------|
| "should we build/keep feature X" | **gate** (single feature) | one scored verdict + rationale |
| "audit this repo's features against the vision" | **audit** (sweep) | verdict table over the feature inventory + proposed ledger |
| "keep X out of scope", "stop agents re-adding X" | **ledger** | OUT_OF_SCOPE.md entry + guard block |
| "did anything parked/cut sneak back in" | **patrol** (advisory) | candidate-match table + due revisit conditions |
| "gate these proposed beads/plan items" | **intake** (batch gate) | verdict per proposed item, before work is filed |
| no vision statement exists | **vision-recovery** | drafted vision, confirmed by operator, then proceed |

## Step 0: Establish the Vision (Never Skip)

A verdict scored against a vision the operator has never seen is worthless.
Locate the vision using the source ladder in
[references/vision-sources.md](references/vision-sources.md). In order:

1. `VISION.md` / `MISSION.md` / a "Vision"/"Philosophy"/"Non-goals" section in
   `README.md`, `CLAUDE.md`, or `AGENTS.md`
2. Client overlay context when present (e.g. a `repo_landscape` block with
   `owns` / `does_not_own` / `prefer_for` entries for this repo)
3. Product docs: landing copy, App Store description, pricing page — what is
   *sold* is strong evidence of what is core
4. The issue graph: epic-level beads/issues and their stated goals
5. Git archaeology: what the first ~20 commits built is usually the core loop

If sources 1–2 are missing or stale, enter **vision-recovery**: draft a
candidate vision (template in `assets/templates/VISION.md`) from sources 3–5,
present it to the operator, and get confirmation **before scoring anything**.
State plainly which sources you used and where you extrapolated.

The vision statement you score against must fit in a few lines and name:
the one user, the one job, the core loop, 3+ explicit non-goals, and a
**scope posture** — EXPLORE (pre-PMF: a few time-boxed experiments allowed),
CONVERGE (experiments get absorbed or retired), or MAINTAIN (new surfaces
default to out unless they replace one). Posture is reconsidered only at
milestones (first users, paid launch, pivot), and it modulates strictness so
young repos aren't strangled and mature repos don't sprawl. Scoring against a
vision the operator has not confirmed makes every verdict `PROVISIONAL`.

## Step 1: Inventory Features (audit mode)

Build the feature list from the artifact, not from memory:

- entry points: routes, CLI subcommands, screens/pages, exported APIs, cron
  jobs, background workers
- the README/docs feature list (what is *claimed*)
- recent additions: `git log --oneline --since="3 months ago"` scanned for
  feature-shaped commits — recent breadth is where creep concentrates
- anything the docs brag about ("also supports…", "bonus", "additionally")

Deduplicate to user-meaningful features (10–40 items for most repos), not
files. Log anything you deliberately excluded from the inventory.

## Step 2: Score Each Feature

Score with the rubric in
[references/scoring-rubric.md](references/scoring-rubric.md). Summary:

Five dimensions, each 0–1000, weighted into `alignment_score`:

| Dimension | Weight | Question |
|-----------|--------|----------|
| vision_fit | 0.32 | Does the confirmed vision *require* this? |
| depth_leverage | 0.27 | Does it make the core loop deeper, or the product wider? |
| journey_criticality | 0.16 | Does the primary user hit this on the happy path? |
| maintenance_drag | 0.15 (inverted) | What does keeping it cost every future change? |
| differentiation | 0.10 | Would the target user choose this project because of it? |

Removal exposure is deliberately **not** in the formula: report it separately
as `disposition_risk` (low/medium/high, with the named consumer class). It
shapes *how* to remove something, never *whether* it belongs — otherwise
entrenched misaligned features score as aligned.

Scoring discipline (full rules in the rubric):

- **Anchor snapping** — scores are anchor values, or interpolations naming
  the two bracketing facts. No freehand "683".
- **Evidence tiers with receipts** — verdict-driving scores (largest-loss
  dimension, anything ≥750 or ≤250) carry a checkable receipt (`path:line`,
  commit, issue ID, quoted copy). Unknowns are `?` → conservative range +
  `PROVISIONAL`, never a quiet 500. Receipts make claims auditable, not
  verified.
- **REMOVE/ABSORB gate** (CORE/SHARPEN candidates only) — name the core-loop
  step that degrades without the feature (with a receipt) or cap at PARK;
  SHARPEN must name the exact absorption refit.

`alignment_loss = 1000 - alignment_score`. For every feature, name the single
largest loss contributor — that sentence is the rationale, the score is only
its shadow.

## Step 3: Verdict

| alignment_score | Default verdict |
|-----------------|-----------------|
| ≥ 700 | CORE |
| 500–699 | SHARPEN |
| 300–499 | PARK |
| < 300 | CUT |

Hard gates that no average can outvote (receipts required, gate named in the
row): contradicting a quoted non-goal or adding a new parallel user loop →
never above PARK; no named primary-user path → never CORE; no concrete refit
→ PARK, not SHARPEN; live users/revenue → CUT only with a deprecation plan.

Composites within ±50 of a threshold must argue both candidate verdicts in
one sentence keyed to anchor definitions. Threshold overrides are
`OVERRIDE-PROPOSED` (receipt required, one band max) and become standing only
when the operator ratifies them.

## Step 4: Outputs

Always produce, in this order:

1. **Verdict table** — feature, score, verdict, evidence receipt for the
   verdict-driver, one-sentence largest-loss rationale, disposition risk,
   any hard gate or `OVERRIDE-PROPOSED`. Sorted worst-first. Include
   `portfolio_loss`, `breadth_ratio`, override pressure, PROVISIONAL count.
2. **Proposed scope ledger** — a draft `OUT_OF_SCOPE.md` (template in
   `assets/templates/OUT_OF_SCOPE.md`). Every PARK/CUT entry records a
   stable scope ID, the **forbidden intent** (capability, not name), 2–5
   "also covers" equivalents tied to non-goals, **allowed adjacency** so the
   entry doesn't block legitimate work, advisory search hints, and an
   observable revisit condition.
3. **Guard block** — a self-contained ≤10-line block for ONE always-loaded
   file (`AGENTS.md` or `CLAUDE.md`, not both) listing the highest-re-add-risk
   entries by forbidden *intent* with their scope IDs, a one-line "compare
   intent, not names; full ledger in `OUT_OF_SCOPE.md`" instruction, and a
   `generated from OUT_OF_SCOPE.md {date}` marker so drift is detectable.
   Pointer-only guards fail — agents load the file but don't follow
   references out of it; the intents must be in context.
4. **Depth contract** — the prune's reinvestment, made concrete: the single
   core-loop step that receives the freed effort, the next depth deliverable,
   and how improvement will be shown (tie it to the vision's depth
   scoreboard when one exists). One active depth contract per repo; the next
   scope run checks whether it landed. A prune with no reinvestment is just
   deletion, not focus.
5. **Consolidation proposal** (audit/patrol modes, when applicable) — if ≥3
   ledger entries cluster around one capability class, propose promoting a
   new ratified non-goal to `VISION.md`; superseded entries collapse to
   one-line citations of it. This is what keeps the ledger *shrinking* as
   prevention strengthens.

## Patrol Mode (advisory re-add detection)

Given an existing `OUT_OF_SCOPE.md`: take the window since the **last patrol
date recorded in the decision log** (first patrol: since the newest decision).
Scan `git log --oneline --since=<cursor>` and the entry-point inventory delta
(new routes, commands, screens, exported APIs) against each entry's search
hints and "also covers" intents. Output a table of **candidate matches** —
never "violations"; hints surface candidates, they don't decide equivalence —
plus any new surfaces with no matching entry, and revisit conditions now met
(which makes entries *eligible for operator re-review*, nothing more). Patrol
writes nothing except, on approval, a one-line decision-log entry recording
the patrol date. It also flags guard-block drift (marker date ≠ ledger date).

## Scope-at-Birth (cheapest prune is the unfiled one)

Cutting a planned work item costs nothing; cutting shipped code costs
approvals, deprecations, and operator anxiety. So push the gate upstream:

- **Intake mode**: when expansion pipelines (ideation skills, planners, swarm
  orchestrators) produce proposed features, run a batch gate over the
  proposals *before* work items are filed. Verdicts attach to the proposals;
  born-PARK items go straight to the ledger draft, never the ready queue.
- **`deepens:` field**: feature-shaped work items should name the core-loop
  step they deepen. Un-fillable → born PARK. A glib value is still a written,
  greppable claim that audit mode scores later.
- **Swarm scope authority**: in multi-agent work, implementing a new
  user-facing capability is an *authority*, not initiative — workers execute
  the assigned outcome with the smallest user-visible surface delta; adjacent
  ideas come back as quarantined proposals for the gate, not as bonus code.

## Reopening a Standing Decision

Scope decisions ratchet. A met revisit condition, a re-run, or a higher
re-score never un-parks anything by itself — standing verdicts change only
via an operator-approved, append-only decision-log entry citing new evidence
(quote the old score/basis when proposing one). PROVISIONAL entries are easy
to re-*review*, but their standing still changes only via the operator.

## Risk Gate (Mandatory)

- The default run is **read-only**: present the verdict table and drafts, then
  stop. Do not write to the repo until the operator approves.
- Writing `OUT_OF_SCOPE.md`, `VISION.md`, and the guard paragraph after
  approval is low-risk.
- **Deleting or disabling code (CUT execution) always requires explicit,
  per-feature operator approval** — never batch-approve cuts, and never treat
  ledger approval as cut approval. Features with live users, revenue, or
  external API consumers (`disposition_risk: high`) additionally need a
  deprecation plan, not a silent removal.
- **Offer the attic**: execute approved cuts as a move to a tagged
  `attic/<feature>` branch with a one-cherry-pick resurrection path noted in
  the ledger. Reversible-feeling cuts get approved; "delete forever" gets
  deferred forever.
- If the operator confirmed the vision in this session, say so; if you are
  running against an unconfirmed drafted vision, label every verdict
  `PROVISIONAL`.

## Required Verification

Before handing back:

1. Confirm the vision source used is quoted (or the drafted vision was shown)
   in the output, including the scope posture in effect.
2. Confirm every PARK/CUT row has a forbidden intent, allowed adjacency, and
   an observable revisit condition in the draft ledger.
2b. Spot-check receipts: resolve 3 of your own citations (all of them in
   single-feature gate mode) — open the file line, the commit, the copy —
   before handing back. State the result.
3. If any repo writes were approved and made, show `git diff --stat` and
   confirm no source code was touched unless a specific CUT was approved.
4. Confirm the depth dividend section exists and names concrete reinvestment
   targets.
5. If an approved CUT removed code, run the repo's own gate — `make test`,
   `npm test`, `cargo test`, or the project's documented equivalent — and
   report the output before declaring the cut complete.

## Related Skills

- `build-vs-clone` — where should surviving work live; adopt vs build
- `make-indispensable` / `smart` — expansion ideation; scope-pruner is the
  counterweight that runs after them
- `codebase-audit` — quality of what remains in scope
