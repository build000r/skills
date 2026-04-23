---
name: ask-cascade
type: utility
description: Enforce hierarchical, dependency-aware question ordering for AskUserQuestion and other user-facing clarification steps. Use for gathering requirements, asking 2+ dependent questions, framing decision trees, surfacing strategic branches before detail questions, or routing open-ended visual choices into a show-don't-tell picker flow before asking the user to choose.
---

# Ask Cascade

## Default Marker

Start with a stable first progress message such as:

`Using \`ask-cascade\` to frame the next highest-impact decision before I ask follow-ups.`

## Required Tool In Claude Code

**When this skill is active in Claude Code (the Anthropic CLI / `claude-code` runtime), you MUST use the `AskUserQuestion` tool for every user-facing question step.** This is a hard requirement, not advisory.

Applies to every moment you are formally:

- **Choosing** — asking the user to pick between 2+ options (including branch previews like `1`, `1A`, `2`).
- **Confirming** — asking the user to approve, reject, or modify a proposed action or plan.
- **Clarifying** — asking the user to resolve an ambiguity you cannot route to code / wiki / duel / deep-research.

Do NOT:

- Emit the question as a plain assistant message and wait for the next turn.
- Bullet-list options in prose and say "reply with 1/2/3" when `AskUserQuestion` can render them as real options.
- Batch a question into a longer narrative message hoping the user answers inline.

The only exceptions:

- A single, terse yes/no confirmation already scoped by the immediately preceding assistant sentence, where rendering a tool UI would be more friction than the question is worth.
- A free-form request where the user genuinely needs to type prose and no option set applies — even then, prefer `AskUserQuestion` with an "Other" escape hatch over a bare prose prompt.

### Other Runtimes

If this skill is invoked in a runtime that is not Claude Code:

- Use that runtime's equivalent structured question/input tool when one exists.
- If no such tool exists, ask the smallest plain-text question necessary, but still apply every cascade rule below.

## The Rule

Questions flow top-down: **highest-impact decisions first**, then details that depend on those answers. Never present questions where one answer could change, nullify, or reframe another.

When the top strategic fork is concrete enough to name, do not ask a naked abstract question first. Show the fork, recommend a starting branch, and let the user recalibrate before deeper questions.

## Picker Branches: Show, Don't Tell

When the unresolved decision is a visual direction, component treatment, layout, hierarchy, or "what looks best?" choice, prefer a picker journey over a prose-only question.

Use this route when:

- The task is in a real project with source files that can render the relevant surface.
- The user is asking for ideas, options, variants, recommendations, or visual taste.
- A screenshot, browser preview, or in-app comparison would answer the question better than text.

Do not use it when the user asked for one specific surface change, when the blocker is product logic/data rather than visual judgment, or when the project cannot reasonably be previewed.

Route the branch through a picker. If a dedicated picker skill or tool is available, use it. Otherwise configure the picker directly:

1. Read the current surface and identify the visual decision point.
2. Implement variants directly in the existing source files. For an existing screen, keep the current implementation as option 1 and label it with `(current)`.
3. Mark the comparison wrapper with `data-uidotsh-pick="Human readable label"`.
4. Mark each option with `data-uidotsh-option="Human readable option"`, using the `contents` class on picker wrappers/options so scaffolding does not affect layout.
5. Keep exactly one option visible and mark the rest `hidden`.
6. Inject the picker toolbar once in the shared app shell/root layout after variants are in place, using a framework-native script API when available or `<script src="https://ui.sh/ui-picker.js"></script>` before `</body>`.
7. Let the user inspect the options in-browser, then ask the selection question with labels that exactly match the picker option labels.
8. After selection, keep only the chosen variant and remove unpicked picker scaffolding unless the user wants another comparison round.

Ask-cascade still owns the ordering: show the highest-impact visual branch first, avoid batching dependent detail questions, and only ask for final preference after the user has something concrete to inspect.

## Surface Assumptions Before Asking

Before any user-facing question, run a two-step check:

1. **Name the silent assumption.** If you were about to act without asking, state what you were going to assume and why. "I was going to assume the export is paginated JSON returned from an API endpoint, because that matches the existing patterns in this repo."
2. **Decide who can answer it.** Not every ambiguity needs the human. Pick the cheapest source that can actually resolve it.

### Resolution routing (cheapest-first)

Route the blocker to the source that can answer it without interrupting the user:

| Source | Use when |
|---|---|
| **Read the code/docs** | The answer is in the repo, CLAUDE.md, or already-visible context. Just look. |
| **`/wiki query`** | The answer lives in the user's accumulated project knowledge (past decisions, product context, prior research). |
| **`/wiki-duel`** | Two plausible interpretations and the wiki holds enough prior context to ground an adversarial read between them. |
| **`/dueling-idea-wizards`** | Cold-context strategic fork (scope, approach, architecture) with no clear winner and no external-reality blocker — let the adversarial pass surface the tradeoffs. |
| **`/deep-research-prompt` (Oracle/Pro browser or external DR)** | The blocker is current external reality: market facts, library behavior under load, pricing, competitive positioning, API contracts that may have drifted. |
| **Ask the human** | Only preference, taste, priority, risk tolerance, or private context the above can't reach. |

Rules:

- Escalate only once. If a routed pass (wiki, duel, or research) returns a confident answer, adopt it and keep going — do not then re-ask the human as a ceremonial checkpoint.
- If the pass returns ambiguity, present its findings to the human as the question, not as a second round of "what do you want?"
- Surface the routing decision to the user in one line: "Blocker is [X]. Resolving via [source] before asking." This lets the user redirect if they'd rather just answer.
- If a risk gate applies (irreversible, external, legal, financial), always ask the human even when another source could answer — routing does not override risk gating.

### Example

```text
Silent assumption I was about to make: export means an API endpoint returning paginated JSON.
Source best equipped to confirm: /wiki query ("how do we expose user data today").

[runs wiki query]

Wiki says: past exports were always background jobs emitting S3 files, not API endpoints.
Revised assumption: background job with S3 output.
Now asking the human only the remaining preference question: retention window?
```

## Before Every User-Facing Question Tool Call

In Claude Code, this section applies to every `AskUserQuestion` call. The tool is mandatory (see **Required Tool In Claude Code** above) — these rules govern how to shape the call, not whether to make it.

Classify each question or branch you are considering:

1. **Strategic** — Changes scope, approach, or whether other questions even apply
2. **Tactical** — Implementation detail that only matters after a strategic choice is made
3. **Independent** — Answer doesn't affect any other question
4. **Branch preview candidate** — A strategic fork with 2-4 plausible branches you can name from the available context

Then apply these rules:

### Rule 1: Strategic Questions Go First, Alone

If you have a strategic question whose answer could change downstream questions, ask it **by itself** or with other truly independent questions. Wait for the answer before formulating tactical follow-ups.

**Bad:**
```text
Q1: "Should we add caching?" (strategic)
Q2: "Redis or Memcached?" (tactical — depends on Q1)
Q3: "What TTL?" (tactical — depends on Q1 AND Q2)
```

**Good:**
```text
Round 1: "Should we add caching?" (strategic)
[user answers yes]
Round 2: "Redis or Memcached?" (tactical, now relevant)
[user answers Redis]
Round 3: "What TTL?" (now has full context)
```

### Rule 2: Independent Questions Can Batch

Questions with no dependency between them should be batched for efficiency.

**Good batch:**
```text
Q1: "Which license: MIT or Apache?" (independent)
Q2: "Include CI/CD config?" (independent)
Q3: "Target Node version?" (independent)
```

All three are safe to ask together because no answer changes another.

### Rule 3: Test Each Batch

Before sending a batch, for each pair of questions ask:

`If the user answered Q1 differently, would I reword or remove Q2?`

- **Yes** → Split them. Ask Q1 first.
- **No** → Safe to batch.

### Rule 4: Re-evaluate After Each Answer

After receiving answers to a round of questions, reassess what you still need to ask. A strategic answer may:

- Eliminate questions entirely
- Spawn new questions you had not considered
- Change the framing of a follow-up

Do not ask stale questions from a pre-planned list.

### Rule 5: When The Fork Is Obvious, Show A Branch Preview

Use a branch preview when all of these are true:

- One strategic decision will change most downstream questions
- You can name 2-4 plausible branches from real context
- The user is likely to say "not that branch" unless you show the shape first

Format the preview like this:

1. State the root decision in plain language.
2. List numbered top-level options: `1`, `2`, `3`.
3. Mark one option as `recommended` and explain why in one sentence.
4. For the recommended option only, show subvariants as `1A`, `1B` when they materially change the next round.
5. Show a happy-path preview of at most 5 downstream nodes total.
6. End with one recalibration prompt: accept the recommendation, choose another number, or give a new starting point.

Guardrails:

- This is a recommendation, not a guessed user answer.
- Keep non-recommended branches brief. Do not print full trees for every option.
- If you cannot ground the options in the available context, ask the neutral strategic question instead.
- If the user already picked a branch, do not repackage it as a menu.
- If the branch involves legal, financial, security, or irreversible external action, call out the risk gate explicitly instead of burying it in the tree.
- Accept terse corrections like `2`, `1B`, or `none of these` as enough to re-anchor. Do not force the user to restate the whole problem.

## Compact Template

```text
Using `ask-cascade` to frame the next highest-impact fork.

Root decision: where this work should live.

1. Extend the existing module (recommended)
   Why: lowest migration cost and matches the current ownership boundary.
   1A. Keep the current data model
   1B. Add a new submodule under the same domain
   Happy path if we start here:
   - confirm module ownership
   - choose 1A or 1B
   - define the public entry point
   - decide tests and migration impact
2. Create a new sibling module
3. Extract a shared package

Reply with `1`, `2`, `3`, `1A`, `1B`, or give a better starting point.
```

## Examples

### Skill Creation With A Branch Preview

```text
Using `ask-cascade` to frame the first strategic fork.

Root decision: what form this reusable workflow should take.

1. Standalone skill (recommended)
   Why: the workflow is reusable, operator-invoked, and richer than a one-file note.
   1A. Manual trigger only
   1B. Manual trigger now, client overlay config later
   Happy path if we start here:
   - confirm this is a skill
   - choose 1A or 1B
   - define trigger phrases
   - decide bundled scripts or references
2. Hook
3. Project-local CLAUDE.md guidance only

Reply `1`, `2`, `3`, `1A`, `1B`, or give a new starting point.
```

### Feature Implementation Without A Branch Preview

```text
Round 1: "New feature, refactor, or bug fix?" (strategic)
[user: new feature]
Round 2: "Which module does this belong in?" (strategic)
[user: auth module]
Round 3: "OAuth or JWT?" + "Need refresh tokens?" (independent within the chosen module)
```

### Bad Pattern To Avoid

```text
Q1: "What language?"
Q2: "What test framework?"  ← depends on Q1
Q3: "What package manager?" ← depends on Q1
Q4: "Tab width?"            ← independent, safe to batch with Q1
```

## Closeout / Verification

Before handing control back, confirm the cascade did its job:

- In Claude Code, every user-facing choose/confirm/clarify step went through the `AskUserQuestion` tool — not a plain assistant message
- Every question asked either is strategic-first or was batched with truly independent peers only
- Every silent assumption that would have been encoded by acting without asking has been named
- Every blocker routable to code, `/wiki query`, `/wiki-duel`, `/dueling-idea-wizards`, or `/deep-research-prompt` was routed there before touching the human
- Every open-ended visual choice was routed through a show-don't-tell picker path, or the reason it was not was explicit
- No stale pre-planned questions were asked after a strategic answer reframed the tree

If any of these fail, revise the cascade and re-ask only the still-relevant questions instead of continuing on stale ground.

## Related

- [[skill-issue]]
