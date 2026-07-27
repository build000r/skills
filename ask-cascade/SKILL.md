---
name: ask-cascade
type: utility
description: Order user-facing questions by dependency. Use when two or more clarifications may depend on one another, a high-impact fork should be resolved before details, a plan needs a decision-tree interview, or a visual choice should be previewed before asking.
---

# Ask Cascade

Ask Cascade is a dependency-aware scheduler for human-owned unknowns. It resolves everything the agent can resolve, asks the current decision frontier through the best available interface, and recomputes after every answer or round.

## Activation Marker

Emit this exact message once per activation:

`Using \`ask-cascade\` to frame the next highest-impact decision before I ask follow-ups.`

## Structured Questions

In Claude Code, every formal choose, confirm, or clarify step must use `AskUserQuestion`. Use one tool call for a coherent independent frontier round. In other runtimes, use the equivalent structured input tool. Use plain text only when no structured tool exists or the response genuinely requires unrestricted prose. Render real choices instead of prose menus when the runtime supports them.

## Decision Frontier

The decision frontier is the set of unresolved human-owned questions whose prerequisites are settled and whose answers cannot be obtained from context, code, documentation, tools, or other authorized sources.

Run this loop:

1. Inventory the unresolved unknowns.
2. Assign ownership and type to each unknown.
3. Resolve every non-human prerequisite through the cheapest capable source.
4. Build or update the dependency graph.
5. Identify the current decision frontier.
6. Ask one controlling question or the smallest coherent batch of independent questions.
7. Give grounded context, options, consequences, and a recommendation.
8. Ask through the runtime's structured question tool.
9. Recompute the graph and frontier from the answers.
10. Drop questions that became irrelevant, settled, or differently framed.
11. Complete according to the active completion contract.

Recompute from current evidence; never continue through a stale questionnaire. Respect natural steering such as `stop`, `wrap up`, `summarize what we have`, or `proceed with current assumptions`.

## Decision Rights

Classify every unknown before resolving it:

| Unknown | Owner and action |
|---|---|
| Discoverable fact or technical constraint | Agent: resolve through context, code, docs, tools, wiki, or targeted research. Ask only when trusted sources conflict or remain inconclusive. |
| Recorded authoritative decision | Agent: adopt when current, authoritative, and consistent. Surface when stale, disputed, ambiguous, or materially consequential. |
| Advisory judgment | Agent/tool: use analysis, prototypes, duels, or research to form a recommendation. Advisory output is not human consent. |
| Human-owned unknown | Human: ask about product intent, priority, private context, risk tolerance, scope, taste, public commitment, or retained authority. |
| Delegated agent-owned implementation choice | Agent: decide a low-risk, reversible detail within confirmed constraints and report it without a checkpoint. |

Research may settle facts and improve recommendations. It may not silently convert a human-owned decision into an agent-owned decision. When another agent or skill invokes Ask Cascade, that agent may investigate facts but must not answer the human side of the exchange.

## One Question or a Frontier Round

For every pair of proposed questions, test:

> Would a different answer to Q1 cause me to remove, reword, defer, or materially reinterpret Q2?

If yes, ask the highest-impact controlling question first and defer Q2. If no, the questions may share a round only when the user can answer them from the same mental context. Technical independence alone does not make a batch coherent.

There is no numeric question or round limit. Continue while the agreed scope has meaningful unresolved branches; treat redundant or low-value questions as a prompt defect, not a counting problem.

### Frontier Round Quality

Optimize for the least interruption that preserves human decision rights.

- **Dimensions and weights:** ownership correctness `O` (35%), dependency safety `D` (30%), mental-frame coherence `C` (20%), and grounded answerability `A` (15%).
- **Scale anchors:** for every dimension, `0` means violated, `500` means mixed or weakly grounded, and `1000` means fully satisfied.
- **Formula:** `round_score = 0.35O + 0.30D + 0.20C + 0.15A`.
- **Loss and threshold:** `loss = 1000 - round_score`. Any `O` or `D` below 1000 blocks the round; otherwise reduce the largest weighted loss before asking.
- **Anti-gaming:** shorter rounds, fewer questions, boilerplate rationales, and false precision earn no credit; only evidence-backed question quality counts.

## Shape Each Question

Every formal choice question contains:

1. The unresolved decision in plain language.
2. Only the context needed to answer it.
3. Grounded options when a useful option set exists.
4. A recommended option and one-sentence rationale when evidence supports one.
5. The material tradeoff or consequence.
6. An escape hatch for a different answer.

When evidence cannot prefer an option because the answer is taste, private context, or personal priority, say: `No objective recommendation: this is a preference/private-context decision. The meaningful tradeoff is ...`

A recommendation is advice, not a guessed answer or consent.

## Assumptions and Resolution

Before each round, internally name the assumption that acting without asking would encode. Surface it only when it materially affects the branch, explains why the question is needed, exposes conflicting sources, changes risk or scope, or lets the user redirect a costly resolution route.

Resolve non-human unknowns in this order:

1. Existing conversation and context.
2. Repository code and documentation.
3. Accumulated project knowledge or wiki.
4. A targeted prototype, adversarial analysis, or current external research.
5. Human.

For exact wiki, duel, escalation, prototype, and research routing, read [references/resolution-routing.md](references/resolution-routing.md) when a local answer is insufficient. A routed answer settles facts or informs a recommendation according to its authority; it never supplies human consent.

## Branch Previews

Use a branch preview when one root decision controls most downstream questions, two to four plausible branches are grounded in real context, and seeing their likely shape will help the user recalibrate.

1. State the root decision.
2. Show two to four top-level options.
3. Mark one recommended option and explain why.
4. Show subvariants only when they materially alter the next round.
5. Preview only enough downstream shape to explain the consequence.
6. End with one structured selection or recalibration question.

Keep non-recommended branches brief. Accept terse corrections as enough to re-anchor. Read [references/examples.md](references/examples.md) for dependent rounds, coherent batches, branch previews, and failure patterns.

## Visual Branches

When the unresolved question is visual and the real project can render alternatives, read [references/visual-picker.md](references/visual-picker.md). Show concrete grounded variants before asking for preference, and keep rendered labels identical to structured-question labels. Ask Cascade still owns decision ordering and cleanup after selection.

## Completion Contracts

### Unblock — default

Use during already-authorized work. Complete when the current blocker is resolved, stale dependent questions are discarded, and control can return to the calling workflow. Continue work without a ceremonial shared-understanding checkpoint.

### Deliberate

Use when the user or caller asks to grill, interview, stress-test, fully specify, visit every relevant branch, or reach shared understanding. Continue until the frontier is empty for the agreed scope. Summarize material decisions and residual assumptions, then obtain explicit shared-understanding confirmation before execution.

### Risk approval overlay

Under either contract, obtain explicit approval immediately before an irreversible, destructive, costly, public, legal, financial, security-sensitive, or privacy-sensitive side effect. Respect any stricter gate owned by the calling workflow.

## Invariants

Before returning control, verify:

1. No discoverable fact was unnecessarily asked of the user.
2. No round combined questions when one answer could change another.
3. Every human-owned choice had a grounded recommendation or an explicit reason none existed.
4. Advisory research was not treated as consent.
5. The frontier was recomputed after every answer or round.
6. No stale question survived a branch-changing answer.
7. The structured question tool was used where required.
8. The stable marker appeared exactly once.
9. Completion followed the correct contract.
10. Every risky side effect retained an explicit approval gate.
