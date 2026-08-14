---
name: wiki-forge
description: Identify the highest-lever concept in a wiki vault, stress-test it adversarially via multi-model duel, optionally validate the final synthesis against current external reality with GPT-5 Pro + Deep Research, and file it back. Use for "wiki forge", "wiki synthesize", "deepen the wiki", "stress test the wiki", "find the highest lever", "forge a concept", "adversarial wiki synthesis", or when the wiki needs to confront its own assumptions.
---

# Wiki Forge

Identify the single highest-lever concept in a wiki vault, run an adversarial multi-model duel on it, and file the synthesis back as upgraded wiki content. The wiki uses itself to improve itself.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using wiki-forge`.

Preferred format: `Using wiki-forge to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

## When to Use

- The wiki has 10+ concept pages and you suspect one concept grounds all the others
- You want the wiki to confront its own contradictions, gaps, or untested assumptions
- You want to deepen one concept with adversarial cross-model pressure
- The user asks to "synthesize", "deepen", "forge", or "stress-test" the wiki

## When NOT to Use

- Simple wiki questions → use `/wiki query`
- Adding new sources → use `/wiki ingest`
- Health checks → use `/wiki lint`
- Generating project improvement ideas → use `/dueling-idea-wizards`

## Dependencies

- **wiki** skill (reads concept pages, files findings back)
- **escalate** skill for the final external-reality gate when the concept
  depends on live outside facts
- **deep-research-prompt** skill when `escalate` routes the final pass there
- **NTM** (`ntm` CLI for spawning agent swarms)
- At least 2 different agent CLIs: `cc` (Claude Code), `cod` (Codex),
  `gemini`, or Grok CLI as a sidecar through Swimmers/direct headless Grok
- Target vault must have a `CLAUDE.md` schema and 10+ concept pages in `_concepts/`
- **A local checkout of the target vault.** Forging writes back into the vault
  (concept pages, exclusion ledger, `_sources/notes/`, wizard artifacts), so it
  cannot run from a checkout-less machine. The `sbp wiki` central front door
  (contract `wiki-central-sbp-v1` in the wiki skill) is read-only — use it only
  for preliminary reads such as checking a vault's concept count or freshness
  (`sbp wiki status --json`, `sbp wiki search`) before deciding where to run
  the forge; the duel and file-back require the checkout.

## Pre-Flight

1. Read the vault's `CLAUDE.md` to load conventions
2. Read `index.md` for the concept catalog
3. If `_ops/focus-sweeps/` exists, read the single active sweep note if present. Treat it as a hint about the current operator lens, not proof.
4. Verify NTM: `ntm deps -v` — need 2+ agent types
5. If fewer than 2 agent types are available, abort — forging requires
   adversarial cross-model pressure. Grok counts as a distinct type when
   `command -v grok` succeeds and you can launch it through Swimmers
   `spawn_tool: "grok"` or direct headless Grok.

## Phase 1: Identify the Highest Lever

Read ALL concept pages in `_concepts/`. For each concept, assess:

| Signal | What It Reveals |
|--------|----------------|
| **Cross-link density** | How many other concepts reference this one? High = hub concept. |
| **Tier** | Axioms and principles are structurally higher-leverage than mechanisms and instances. |
| **Tension markers** | Human notes flagging gaps, unresolved questions, or needed re-alignment. |
| **Dependency chain** | If this concept is wrong, how many other concepts break? |
| **Bidirectional load** | Does this concept determine both the "why" (thesis) and the "how" (execution)? |

If the vault schema includes `importance` and `focus` metadata, treat them as operator hints:
- `importance` = durable structural leverage
- `focus` = temporary working set

Do not trust either field blindly. Use them as priors to inspect, confirm, or challenge from the actual concept bodies.

If the vault schema includes `focus-sweep` notes, treat the single active sweep as an operator hint about the current working-set lens:
- `focus_set` = what the operator is actively trying to reason through right now
- `considered` = adjacent concepts already reopened against that lens

Do not treat a sweep as evidence that a concept is actually high leverage. It is a recency/context signal only.

The highest lever is NOT the most well-articulated concept — it's the one where:
- Getting it right makes everything else work
- Getting it wrong breaks the most other concepts
- It has the most unresolved tension or open questions
- It sits at the intersection of multiple conceptual clusters

Present the identification with reasoning before proceeding. The user should confirm or redirect.

If the vault is small or the concept set is tightly bounded, it is acceptable to identify:
- 1 highest-lever concept
- 1-3 `focus: now` concepts
- 1-3 additional high-importance but not-currently-focused concepts

## Phase 2: /smart Both Sides

Formulate the two most accretive questions about the identified concept:

**Side A — The Amplifier:** What is the single thing that would make this concept 10x more durable, transferable, or scalable? Not more products, not more marketing — what makes the core mechanism compound faster?

**Side B — The Stress Test:** If this concept is wrong — if it has a scaling ceiling, produces false confidence, or becomes obsolete — what's the failure mode? What assumption would be most dangerous to get wrong?

Present both questions to the user. These frame the duel.

## Phase 3: Spawn and Study

```bash
ntm spawn {PROJECT} --cc=1 --cod=1 --no-user --stagger-mode=smart
ntm --robot-wait={PROJECT} --condition=idle --timeout=120s
```

If Grok is part of the forge, do not pass `--grok` to NTM. Launch one Grok CLI
sidecar in the vault cwd through Swimmers `spawn_tool: "grok"` or a direct
headless prompt-file run. Track it by Swimmers session id/process output and
the expected `WIZARD_*_GROK.md` artifacts; NTM idleness does not prove Grok
completion.

Send the study prompt to all agents:

> Read the entire {vault_path} directory carefully. Start with CLAUDE.md to understand the wiki architecture. Then read log.md for history. Then read ALL files in _concepts/ — every single one. Understand the FULL body of strategic thinking. Pay special attention to {concept_name}.md and its related concepts. Take your time and be thorough.

If `_ops/focus-sweeps/` contains an active sweep, read that too so you understand the current operator lens before deciding whether to reinforce it or challenge it.

Wait for study to complete:
```bash
ntm --robot-wait={PROJECT} --condition=idle --timeout=300s
```

## Phase 4: Independent Ideation

Send the ideation prompt to all agents. The prompt must include:
1. The concept identification and why it's the highest lever
2. Both /smart questions (amplifier + stress test)
3. Instructions to generate 15 ideas covering BOTH directions
4. Instructions to winnow to top 5 with full rationale
5. Instructions to write to `WIZARD_IDEAS_{TYPE}.md`

Poll for output files:
```bash
ls {vault_path}/WIZARD_IDEAS_*.md
```

Read ALL output files completely, including `WIZARD_IDEAS_GROK.md` when a Grok
sidecar participates. You need the full text for cross-scoring.

## Phase 5: Cross-Scoring

Show each agent the OTHER agent's ideas. Use `--cc` and `--cod` flags to target by type.

Each agent scores the opponent's ideas 0-1000 on:
- Depth and genuine insight
- Novelty vs. what the wiki already articulates
- Practical utility across the portfolio
- Evidence survivability against specific wiki content
- Utility-to-complexity ratio

Output: `WIZARD_SCORES_{SCORER}_ON_{SCORED}.md`

Read ALL scoring files. Note the score matrix and any asymmetry.

## Phase 6: The Reveal

Show each agent how the OTHER agent scored THEIR ideas.

Ask for honest reactions:
- Where do you agree?
- Where are they wrong, and why?
- Did they make a point that changes your evaluation?

Output: `WIZARD_REACTIONS_{TYPE}.md`

The reveal is where genuine concessions happen. Don't skip it — the reaction files contain the most honest assessments.

## Phase 7: Synthesize

Kill the swarm: `echo "y" | ntm kill {PROJECT}`

Compile the final report to `{vault_path}/DUELING_WIZARDS_REPORT.md`:

### Score Matrix

For each idea: origin, self-rank, opponent's score, post-reveal status (consensus, contested, killed).

### Consensus Winners

Ideas scored 700+ by BOTH agents, or where post-reveal concessions aligned both models. These are the real findings.

### Killed Ideas

Ideas where the opponent scored below 400 AND the originator conceded post-reveal. Dead. Note why.

For each killed idea, append one row to `{vault_path}/_ops/exclusion-ledger.md`
(create the file with the header from `/wiki` if absent) so the duel's
anti-knowledge is durable, not buried in a moved wizard artifact:

```
| {concept}:{idea_slug} | {today} | forge_kill | {concession text, ≤120 chars} | {+90d} | active |
```

Skip the append when `{concept}:{idea_slug}` already has an `active` row to avoid duplicate entries across reruns.

### The Synthesis

The highest-value output: a combined program that neither model produced alone. Look for:
- Complementary layers (one model's insight + another model's mechanism)
- Post-reveal adoptions (ideas one model stole from the other)
- Merged framings (one model's language improving the other's concept)

### Scoring Asymmetry

If one model scored much higher than the other, note it. The harsher scorer is usually more evidence-grounded. The generous scorer may be inflating via politeness bias.

## Phase 7b: Final External Reality Pass

If the target concept makes claims about current market structure, regulation,
competitive motion, buyer behavior, or other live external facts, run the final
external-reality gate after the duel and before the wiki update.

Rules:

1. Invoke `escalate` with `caller: wiki-forge`, the concept, the two `/smart`
   questions, the top duel findings, and the exact premises that could be
   broken by current external evidence.
2. If `escalate` returns `route: deep-research-prompt`, run a bounded brief that
   stress-tests the duel synthesis against dated facts. Do not ask Pro to
   replace the duel.
3. If `escalate` returns `route: thesis-gtm`, use that route only when the
   forged concept is explicitly a GTM, market, distribution, positioning, or
   customer thesis.
4. If `escalate` returns `skip`, cite the skip reason. If it returns
   `too-broad`, narrow the premise before filing changes. If Oracle execution
   is unavailable for a selected route, mark the forge as externally-unverified.
5. Distill any routed result to
   `{vault_path}/_sources/notes/wiki-forge-<concept>-<date>.md`, including the
   Oracle session ID if any, verdict, confirming/disconfirming evidence, and
   affected concepts/articles.
6. Run `/wiki ingest` on that note before finalizing the concept updates so
   the concept layer can cite the note as a source.

## Phase 8: File Back to Wiki

This is what makes wiki-forge different from a standalone duel. The synthesis findings get filed BACK into the wiki:

1. **Update the target concept page** — add new vocabulary, frameworks, or distinctions the duel produced. Use the wiki's deduplication rules: each new shared argument gets ONE canonical home.

1a. **Update concept metadata when the duel justifies it.**
- Set or revise `importance` if the duel changes your view of which concepts are structurally load-bearing.
- Set `focus: now` on at most 1-3 concepts when the user explicitly wants a working set.
- Move previously active concepts to `focus: next` or clear `focus` when they are no longer current.
- Keep `importance` durable and `focus` temporary; never use `focus` as a synonym for importance.

1b. **Update focus coverage only when the user wants the working set to stay graph-visible.**
- If the vault uses `_ops/focus-sweeps/`, update the single active sweep or create a new one when the duel materially changes the active lens.
- Prefer one append-only sweep note per real pass instead of stamping per-note review metadata across many concept pages.
- If the duel supersedes the previous active lens, close the old sweep and make the new one `status: active`.
- Do not use `updated` / `updated_at` to mean "considered during this forge."

2. **Create new concept pages** if the duel produced genuinely new concepts (e.g., "discovery authority vs. maintenance authority" may deserve its own page if it's referenced by 3+ other concepts).

3. **Update related concept pages** that are affected by the findings. Cross-link to the new material.

4. **Scan relevant published `/research/*.md` articles** for drift against the forged concept layer.
   - Classify each candidate as `research discrepancy` or `research improvement opportunity`
   - Prepare a concise patch plan, but do not edit published articles yet

5. **Append to log.md** — record the forge operation, which concept was targeted, what was updated, and any article drift discovered.

6. **Move wizard artifacts** to `{vault_path}/` so they're part of the vault but not concept pages. They're evidence, not synthesis.

Present the proposed wiki updates to the user before applying. The duel produces recommendations; the human decides what enters the wiki. This is especially strict for published root-level `/research/*.md` articles: concept updates may be auto-filed, but article edits require explicit human confirmation in the current turn.

## Output

After forging, report:
- Which concept was identified as highest-lever, and why
- The /smart questions from both sides
- Consensus winners from the duel (with scores)
- What was killed and why
- The combined program (the synthesis)
- Which final `escalate` route was selected, what it changed, and the
  `_sources/notes/` path + Oracle session ID if any
- What wiki pages were updated or created
- Whether the active `focus-sweep` was updated, replaced, or intentionally left alone
- Which published articles now appear stale or improvable, and why
- Score asymmetry and what it reveals about model biases

## Anti-Patterns

| Problem | Fix |
|---------|-----|
| Wiki has < 10 concepts | Not enough material to forge. Build the wiki first via ingest. |
| User disagrees with lever identification | Let them redirect. The identification is a proposal, not a command. |
| Both agents generate identical ideas | Strong independent convergence. Note it. Re-run with --focus on a different angle. |
| Reveal produces no concessions | Agents were too polite. Nudge: "The other model scored your #1 idea at 280. Defend it or concede." |
| Synthesis doesn't produce anything the wiki didn't already know | The concept was already well-articulated. Pick a different lever. |
| Stopping at the duel when the concept is externally gated | Run the final `escalate` route and file any resulting note to `_sources/notes/` before calling the forge complete. |

## Relationship to Other Skills

- **wiki**: wiki-forge reads from and writes back to the wiki. wiki owns the schema; wiki-forge owns the adversarial deepening process.
- **dueling-idea-wizards**: wiki-forge adapts the duel methodology for concept analysis rather than project improvement. The prompts, scoring, and reveal follow the same structure.
- **smart**: the /smart questions from both sides frame the duel. wiki-forge uses the same "single most accretive question" principle but applied adversarially.
- **power-map**: power-map challenges customer assumptions for specific products. wiki-forge challenges the wiki's own conceptual assumptions at the highest level.

## Verification / Closeout Contract

Before returning, confirm all of the following:

1. The highest-lever concept was identified with explicit reasoning and the
   user had a chance to redirect before the duel proceeded.
2. Duel artifacts were produced, read, and synthesized into a final report.
3. If the concept was externally gated, the final `escalate` route either ran
   and was filed to `_sources/notes/`, returned `skip` / `too-broad`, or was
   explicitly marked externally-unverified.
4. Wiki updates are explicit: concept pages, new concepts, log updates,
   focus-sweep changes, and article-drift findings.
5. `/wiki ingest` status is reported for any note filed from the run.

## Related

- [[skill-issue]]
