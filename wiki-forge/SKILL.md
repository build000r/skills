---
name: wiki-forge
description: Identify the highest-lever concept in a wiki vault, stress-test it adversarially via multi-model duel, and file the synthesis back. Use for "wiki forge", "wiki synthesize", "deepen the wiki", "stress test the wiki", "find the highest lever", "forge a concept", "adversarial wiki synthesis", or when the wiki needs to confront its own assumptions.
---

# Wiki Forge

Identify the single highest-lever concept in a wiki vault, run an adversarial multi-model duel on it, and file the synthesis back as upgraded wiki content. The wiki uses itself to improve itself.

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
- **NTM** (`ntm` CLI for spawning agent swarms)
- At least 2 different agent CLIs: `cc` (Claude Code) + `cod` (Codex) or `gemini`
- Target vault must have a `CLAUDE.md` schema and 10+ concept pages in `_concepts/`

## Pre-Flight

1. Read the vault's `CLAUDE.md` to load conventions
2. Read `index.md` for the concept catalog
3. Verify NTM: `ntm deps -v` — need 2+ agent types
4. If fewer than 2 agent types are available, abort — forging requires adversarial cross-model pressure

## Phase 1: Identify the Highest Lever

Read ALL concept pages in `_concepts/`. For each concept, assess:

| Signal | What It Reveals |
|--------|----------------|
| **Cross-link density** | How many other concepts reference this one? High = hub concept. |
| **Tier** | Axioms and principles are structurally higher-leverage than mechanisms and instances. |
| **Tension markers** | Human notes flagging gaps, unresolved questions, or needed re-alignment. |
| **Dependency chain** | If this concept is wrong, how many other concepts break? |
| **Bidirectional load** | Does this concept determine both the "why" (thesis) and the "how" (execution)? |

The highest lever is NOT the most well-articulated concept — it's the one where:
- Getting it right makes everything else work
- Getting it wrong breaks the most other concepts
- It has the most unresolved tension or open questions
- It sits at the intersection of multiple conceptual clusters

Present the identification with reasoning before proceeding. The user should confirm or redirect.

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

Send the study prompt to all agents:

> Read the entire {vault_path} directory carefully. Start with CLAUDE.md to understand the wiki architecture. Then read log.md for history. Then read ALL files in _concepts/ — every single one. Understand the FULL body of strategic thinking. Pay special attention to {concept_name}.md and its related concepts. Take your time and be thorough.

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

Read ALL output files completely. You need the full text for cross-scoring.

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

### The Synthesis

The highest-value output: a combined program that neither model produced alone. Look for:
- Complementary layers (one model's insight + another model's mechanism)
- Post-reveal adoptions (ideas one model stole from the other)
- Merged framings (one model's language improving the other's concept)

### Scoring Asymmetry

If one model scored much higher than the other, note it. The harsher scorer is usually more evidence-grounded. The generous scorer may be inflating via politeness bias.

## Phase 8: File Back to Wiki

This is what makes wiki-forge different from a standalone duel. The synthesis findings get filed BACK into the wiki:

1. **Update the target concept page** — add new vocabulary, frameworks, or distinctions the duel produced. Use the wiki's deduplication rules: each new shared argument gets ONE canonical home.

2. **Create new concept pages** if the duel produced genuinely new concepts (e.g., "discovery authority vs. maintenance authority" may deserve its own page if it's referenced by 3+ other concepts).

3. **Update related concept pages** that are affected by the findings. Cross-link to the new material.

4. **Append to log.md** — record the forge operation, which concept was targeted, what was updated.

5. **Move wizard artifacts** to `{vault_path}/` so they're part of the vault but not concept pages. They're evidence, not synthesis.

Present the proposed wiki updates to the user before applying. The duel produces recommendations; the human decides what enters the wiki.

## Output

After forging, report:
- Which concept was identified as highest-lever, and why
- The /smart questions from both sides
- Consensus winners from the duel (with scores)
- What was killed and why
- The combined program (the synthesis)
- What wiki pages were updated or created
- Score asymmetry and what it reveals about model biases

## Anti-Patterns

| Problem | Fix |
|---------|-----|
| Wiki has < 10 concepts | Not enough material to forge. Build the wiki first via ingest. |
| User disagrees with lever identification | Let them redirect. The identification is a proposal, not a command. |
| Both agents generate identical ideas | Strong independent convergence. Note it. Re-run with --focus on a different angle. |
| Reveal produces no concessions | Agents were too polite. Nudge: "The other model scored your #1 idea at 280. Defend it or concede." |
| Synthesis doesn't produce anything the wiki didn't already know | The concept was already well-articulated. Pick a different lever. |

## Relationship to Other Skills

- **wiki**: wiki-forge reads from and writes back to the wiki. wiki owns the schema; wiki-forge owns the adversarial deepening process.
- **dueling-idea-wizards**: wiki-forge adapts the duel methodology for concept analysis rather than project improvement. The prompts, scoring, and reveal follow the same structure.
- **smart**: the /smart questions from both sides frame the duel. wiki-forge uses the same "single most accretive question" principle but applied adversarially.
- **power-map**: power-map challenges customer assumptions for specific products. wiki-forge challenges the wiki's own conceptual assumptions at the highest level.
