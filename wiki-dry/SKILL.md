---
name: wiki-dry
description: Apply non-deterministic DRY refactoring to non-code artifacts — wiki concept pages and skill bundles. Identify candidates to inline, extract, compose, unify, split, or promote so the corpus stays modular without restating the same idea in five places. Use for "wiki dry", "/wiki-dry", "dry the wiki", "dry my skills", "which skills should be sub-skills", "merge these concepts", "split this concept", "find duplicate concepts", "concept refactor", "skill consolidation", "abstract these up", or when a wiki vault or skill collection feels redundant, sprawling, or sub-optimally organized.
---

# Wiki Dry

DRY for prose. Apply functional-programming refactoring moves (inline, extract, compose, unify, split, promote) to a corpus of wiki concept pages or skill bundles. Code DRY is provable; concept DRY is LLM-judge territory — so this skill audits with an explicit rubric and, for contested calls, runs an adversarial duel before mutating anything.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using wiki-dry`.

Preferred format: `Using wiki-dry to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

## When to Use

- A wiki vault has 15+ concept pages and you suspect redundancy, sprawl, or fragmentation
- A skill collection has 30+ skills and you suspect overlap, missing parents, or hidden sub-skills
- The user asks to "dry", "consolidate", "abstract up", "find duplicate concepts", "decide what should be its own page", or "decide which skills should fold into others"
- The corpus has grown organically and a structural pass is overdue

## When NOT to Use

- Health checks (orphans, contradictions, staleness) → use `/wiki lint`
- Deepening one concept adversarially → use `/wiki-forge`
- Answering a question against the wiki → use `/wiki query`
- Creating a new skill from scratch → use `/skill-issue`
- Code-level deduplication → use `/simplify-and-refactor-code-isomorphically`

## Dependencies

- **wiki** skill for vault traversal, concept-page reads, and writes when `--target wiki`
- **skill-issue** for skill packaging, validation, and the SKILLS_COVERAGE.yaml lifecycle when `--target skills`
- **dueling-idea-wizards** for contested merge-vs-split calls (Phase 4)
- Read access to either a registered wiki vault (via `~/repos/skillbox-config/wikis.yaml`) or the skills root (`~/.claude/skills/`)
- On a checkout-less machine the vault is reachable **read-only** via the `sbp wiki` front door (contract `wiki-central-sbp-v1` in the wiki skill) — enough for `--mode audit`, never enough for `--mode apply`

## Modes and Targets

```
/wiki-dry --target {wiki|skills} --mode {audit|apply} [--top N] [--operation OP] [--id ID]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--target` | required | `wiki` (concept pages in a vault) or `skills` (SKILL.md bundles) |
| `--mode` | `audit` | `audit` ranks candidates and writes a report; `apply` executes one refactor |
| `--top` | `10` | How many candidates to surface in audit mode |
| `--operation` | — | Restrict audit/apply to one of: inline, extract, compose, unify, split, promote |
| `--id` | — | Required in `apply` mode; the candidate id from a prior audit report |
| `--vault` | — | Forwarded to `/wiki` when `--target wiki` |

Audit is read-only. Apply mutates and requires an audit id plus user confirmation.

## The Six Refactor Operations

Each operation is the prose analog of a code refactoring move. The audit pass tags every candidate with one operation.

| Operation | Code analog | Concept signal | Wiki example | Skill example |
|-----------|-------------|----------------|--------------|---------------|
| **inline** | inline function | 1 backlink, no independent reuse, body is a paragraph or two | Concept page only referenced from one other concept → fold it in | Skill only invoked from one other skill's body → make it a section there |
| **extract** | extract function | N pages restate the same sub-idea with no canonical home | 3+ concepts repeat the same framework → promote it to its own concept | 3+ skills repeat the same preflight → bundle as a shared reference |
| **compose** | function call | Logic duplicated when it could be a reference | Concept restates another concept's claim → replace with `[[wikilink]]` | Skill restates another skill's contract → replace with `Use /other-skill for X` |
| **unify** | rename / dedupe | Two artifacts are the same idea under different names | `operator-velocity.md` and `founder-throughput.md` cover the same mechanism | Two skills with overlapping descriptions and trigger phrases |
| **split** | extract function (from one) | One artifact does two jobs; readers skip half to find the part they want | Concept page mixing thesis with execution playbook | Skill bundling audit + apply for two unrelated domains |
| **promote** | hoist to module | Sub-concept turns out to be generally useful beyond its parent | Section inside one concept gets referenced by 3+ unrelated concepts → its own page | Helper inside one skill gets invoked from 3+ skills → top-level skill |

Sub-skill question maps to **compose** (keep separate, make the dependency explicit) or **inline** (absorb if there is no real reuse).

## Decision-Route Composition Pattern

A high-leverage **compose** case appears when several artifacts repeat the same decision gate rather than the same body text. Common skill examples:

- "Should this escalate to Oracle, Deep Research, browser mode, or a local-only path?"
- "Which downstream skill should run next?"
- "Does this caller force a route even though the shared policy usually decides?"

In this pattern, centralize the decision contract, not the whole workflow.

The canonical artifact owns:

- Input packet schema: caller, goal, trigger, evidence, forced-route hints, and stop conditions
- Route table and priority rules
- Anti-loop guards and "do not escalate" cases
- Structured result: route, reason, command/next action, confidence, and resume instruction

The caller keeps:

- Topic selection
- Domain evidence gathering
- Local grading and acceptance criteria
- Artifact filing
- Post-route continuation
- Target-specific constraints and vocabulary

Bad compose: "all GTM research now lives in escalate." Good compose: "`thesis-gtm` asks `escalate` for the external-reality route, then `thesis-gtm` resumes its wiki/VISION.md flow."

Use this when duplication is a "whether/how/where next" decision. Do not use it when the duplicated material is the domain workflow itself.

## Decision Rubric

Every candidate is scored on four signals before assignment to an operation. The audit report shows the per-signal scores so the human can override.

1. **Reuse** — referenced from 2+ distinct places (backlinks for wiki, `Use /X` mentions or `depends_on:` for skills). Low reuse pushes toward **inline**.
2. **Independent evolution** — does it change for different reasons than its neighbors? (Single Responsibility.) High independence pushes toward **split** or **promote**.
3. **Distinct shape** — does it have its own claims, sources, examples, contract surface? Strong shape pushes toward **keep separate**; weak shape pushes toward **unify** or **inline**.
4. **Lookup affordance** — would a reader/agent search for this on its own? Strong affordance pushes toward **promote** or **keep separate**; weak pushes toward **inline**.

Disagreement among the four signals is the trigger for the Phase 4 duel.

### Composition Boundary Checks

For every **compose** candidate, answer these before recommending extraction or caller rewrites:

1. Is the duplicated material a decision gate, transport/mechanics, or a domain workflow?
2. Can the canonical artifact return a decision/result while callers keep their own continuation?
3. Does the proposed contract include anti-loop rules so skills do not call each other recursively?
4. Will a caller-aware route table become a stale registry, or is it small and policy-relevant?
5. Does centralization remove repeated judgment without hiding the local context that makes the judgment correct?

If the answer points to "shared routing, local continuation," recommend **compose** with a caller packet/result contract. If the answer points to "shared whole workflow," consider **extract** or **promote** instead. If the canonical artifact would need to understand every caller's domain-specific artifacts, it is probably over-centralized.

## Pre-Flight

1. Resolve the target:
   - `--target wiki`: resolve the vault via `/wiki` registry rules (`~/repos/skillbox-config/wikis.yaml`); read its `CLAUDE.md` and `index.md`
   - `--target skills`: read `~/.claude/skills/SKILLS_COVERAGE.yaml` and list every `SKILL.md` under the skills root
2. Build the artifact graph:
   - Wiki: parse frontmatter and `[[wikilinks]]` to compute backlinks per concept
   - Skills: parse frontmatter `name`, `description`, `depends_on:`; grep skill bodies for `/<other-skill>` mentions and `Use \`<other-skill>\`` references to compute a use-graph
3. If the corpus is below the floor (wiki <15 concepts, skills <30 bundles), tell the user and stop. There is not enough material for structural refactoring.

## Phase 1: Score Every Artifact

For each artifact, compute the four rubric signals. Output a table:

```
| id | reuse | independence | shape | affordance | proposed_op | confidence |
```

`confidence` is high when 3+ signals agree on the operation, medium when 2 agree, low when signals split.

## Phase 2: Cluster

Group artifacts by proposed operation. For **unify** and **extract**, also group by semantic neighbor: which other artifacts is this candidate paired with? The output of this phase is a list of refactor groups, not individual candidates.

Example (wiki):
- `unify`: {operator-velocity, founder-throughput} — same mechanism, different vocabulary
- `extract`: {three-pillars-thesis, gtm-stack, product-stack} all restate "thin-slice rollout" — extract to its own concept
- `inline`: {micro-distribution-loop} — 1 backlink, fits in parent

Example (skills):
- `compose`: wiki-duel → already composes wiki + dueling-idea-wizards (good model); audit other duel-using skills for the same pattern
- `compose`: thesis-gtm/power-map/domain-planner → use escalate for external-reality routing; callers keep topic selection, grading, filing, and follow-through
- `unify`: {codebase-audit, codebase-archaeology} share trigger phrases — confirm or split contracts
- `inline`: {session-to-tweet} — only 1 invocation pattern, could be a sub-mode of `commit`

## Phase 3: Filter by Confidence

- **High confidence** candidates → eligible for direct apply
- **Medium confidence** → present to user for confirmation, no duel needed
- **Low confidence** (signals split) → routed to Phase 4

## Phase 4: Adversarial Duel for Contested Calls

For each low-confidence candidate, invoke `/dueling-idea-wizards` with a focused prompt:

> Two artifacts in {target}: {A} and {B}. One model argues they should {merge|split|stay separate|compose}. The other argues the opposite. Each defends with: which of the four DRY signals supports their position, what breaks under the opposite choice, and one concrete example from the corpus.

The duel produces a recommendation with consensus level. Record it in the audit
report. If Grok CLI is available, let `/dueling-idea-wizards` include it through
its normal Grok sidecar lane; wiki-dry should not define a separate Grok
transport.

For wiki targets where the contested artifacts make claims about external reality (markets, regulation, live competitive structure), consider a `wiki-forge`-style external-reality pass after the duel — but this is optional and only when the merge/split decision is gated by external facts, not internal corpus structure.

## Phase 5: Audit Report

Write the report to:
- `--target wiki`: `{vault_path}/_ops/dry-audit-{date}.md`
- `--target skills`: `~/.claude/skills/_ops/dry-audit-{date}.md` (create `_ops/` if missing)

Report contents:
1. **Summary** — totals per operation, top 3 highest-leverage moves
2. **Candidates table** — full rubric scores, proposed operations, confidence
3. **Cluster groups** — refactor groups, not individuals
4. **Duel results** — for any candidates routed to Phase 4
5. **Apply commands** — exact `/wiki-dry --mode apply --id <ID>` invocations for each accepted candidate

The audit never mutates the corpus. The user reviews the report and decides which applies to run.

## Phase 6: Apply (separate invocation)

`apply` mode requires `--id <candidate-id>` from a prior audit report. It executes exactly one refactor operation, with a dry-run diff first.

Per-operation apply contract:

- **inline** — copy body of A into B at the wikilink site; delete A; rewrite all other backlinks to B; for skills, fold A's instructions into a new section of B and remove A from `SKILLS_COVERAGE.yaml` (status: `excluded`, reason: `inlined into B`)
- **extract** — create new artifact C with the shared sub-idea; rewrite N parents to reference C; for skills, scaffold C via `init_skill.py` and update `depends_on:` in parents
- **compose** — replace duplicated body in A with a reference to B (`See [[B]]` or `Use /B for X`); leave A's surrounding contract intact. For decision-route composition, define the caller packet/result contract in B, update A to send the relevant packet fields, and explicitly state how A resumes after B returns.
- **unify** — pick canonical name (the one with more inbound references wins; tie-broken by clarity), redirect the loser, rewrite backlinks; for skills, mark loser `excluded` in `SKILLS_COVERAGE.yaml` with `reason: unified into <canonical>`
- **split** — create new artifact A2 from the second job; rewrite A to point at A2 for that concern; for skills, run `init_skill.py` for A2 and trim A's frontmatter description
- **promote** — extract the section into its own artifact at the top level; rewrite the parent to reference it; for skills, run `init_skill.py` for the new top-level skill and add `depends_on:` from the original parent

Mandatory checks before any write:
1. **Wiki**: run autoblog awareness from `/wiki` — surface any `published_to` / `publication_gate` impact before writing
2. **Skills**: run `quick_validate.py` on every skill the apply touches; never auto-`package_skill.py`
3. **Diff preview**: show the user the exact set of file creations, deletions, edits before applying
4. **Confirmation**: explicit user yes per apply (no batch yes for `apply`)

## Output

Audit mode reports:
- Path to the audit report
- Top 3 highest-leverage moves with one-line rationale each
- Any duels run, with consensus levels
- Suggested next `apply` invocation

Apply mode reports:
- Operation executed and id
- Files created, deleted, edited
- Backlink rewrites performed
- For wiki: any concepts whose `sources:` frontmatter or backlinks changed
- For skills: SKILLS_COVERAGE.yaml updates and any `depends_on:` rewrites

## Anti-Patterns

| Problem | Fix |
|---------|-----|
| Audit produces 50 candidates and the user freezes | Default `--top 10`. Surface highest-leverage only. |
| Two artifacts look identical to the LLM but the human knows they have different audiences | Capture the override and add a `keep_separate_reason:` line to both — future audits skip the pair. |
| Apply runs on a stale audit (corpus moved) | Audit reports include corpus hashes; apply refuses if hashes differ. |
| Promote churn — promoting then immediately re-inlining when reuse doesn't materialize | Promotion candidates require ≥3 actual reference sites already, not "could be referenced." |
| User wants to merge but the merger destroys the loser's distinct examples | The unify apply preserves the loser's examples by appending them to the canonical artifact's "Examples" section, not silently dropping. |
| Wiki autoblog publishes a half-edited concept mid-apply | Apply runs autoblog awareness from `/wiki` first; aborts on any non-gated publication risk. |
| DRY turns a router into a mega-skill | Centralize policy, route selection, packet schema, and result shape only. Leave domain workflows, artifacts, and post-route work in the callers. |

## Relationship to Other Skills

- **wiki**: vault traversal, autoblog awareness, write contracts. wiki-dry is to `/wiki lint` what `simplify-and-refactor-code-isomorphically` is to a linter — lint flags symptoms, dry restructures.
- **wiki-forge**: forge deepens one concept adversarially; wiki-dry restructures across many. Forge changes content; dry changes shape.
- **wiki-duel**: external-target adversarial brainstorm; not invoked here. The Phase 4 duel uses `/dueling-idea-wizards` directly.
- **skill-issue**: owns skill creation, packaging, and the coverage ledger. wiki-dry calls into it for `init_skill.py`, `quick_validate.py`, and `SKILLS_COVERAGE.yaml` updates rather than reimplementing them.
- **dueling-idea-wizards**: invoked in Phase 4 for contested merge-vs-split decisions.
- **simplify-and-refactor-code-isomorphically**: the code-side analog. Same philosophy applied to a different artifact type.

## Verification / Closeout Contract

Before returning, confirm:

1. The target was resolved and the corpus floor was met (≥15 concepts or ≥30 skills), or the run was halted with that explanation.
2. Audit reports were written to the documented `_ops/` path with all required sections.
3. For `apply` runs: a dry-run diff was shown, the user explicitly confirmed, and post-apply validation (`quick_validate.py` for skills; backlink integrity for wiki) passed.
4. For wiki applies: autoblog awareness ran and any publish/unpublish risks were surfaced before writing.
5. No artifact was deleted without preserving its distinct examples or sources somewhere in the canonical destination.
