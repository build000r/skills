---
name: describe
description: Turn a conversation into discrete pass/fail test cases before patching, review existing Describe packets, or implement from accepted specs. Use for bug fixes, small features, refactors, "define done", "what should we test", "spec this out", or pre-patch work without clear pass/fail criteria.
---

# Describe

Define what "done" looks like before writing code. Produces a structured
test case spec that makes implementation and review unambiguous.

Default path for action-oriented requests:

`draft-spec -> review-spec -> implement-from-spec -> commit-after-spec`

Do not make the user manually repaste packets just to get the fresh review or
implementation branch. Carry the accepted packet forward yourself unless the
runtime boundary forces an explicit handoff prompt.

**Lifecycle position:**
- **domain-planner** = full feature slices (6 plan files, multi-phase)
- **describe** = patches, bug fixes, small features (single test spec)
- **reproduce** = verify the fix after implementation

## Execution Profiles

This skill is agent-platform neutral. Pick the strongest path your runtime
supports:

- **Profile A: Subagent-capable runtimes**
  - Use a fresh-context read-only subagent for `review-spec`.
  - Reuse the reviewed packet for `implement-from-spec` when implementation is
    handed to another agent or delegated via `/codex:rescue`.
- **Profile B: Single-agent runtimes**
  - Run the same review as an explicit second-pass inline check.
  - If the user explicitly requested a subagent, do not silently fake one;
    state the limitation and ask whether the inline fallback is acceptable.

Terminology used below:

- **"Fresh review"** = a second-pass check from fresh context that answers what
  the user is really asking for, challenges the spec, and identifies missing
  cases or decisions.
- **"Spawn subagent"** = delegate the fresh review if the runtime supports it;
  otherwise use the explicit inline fallback from Profile B.
- **"Implementation handoff"** = either inline implementation or a
  `/codex:rescue` delegation, depending on user request and task size.

## Modes

Choose one mode immediately and say it in the first progress update using the
stable marker:

`Using describe (draft-spec|review-spec|implement-from-spec|commit-after-spec) ...`

Mode selection:

- **`draft-spec`**
  - Entry point when the user gives a raw bug/feature/refactor request and no
    accepted `# Describe:` packet exists yet.
- **`review-spec`**
  - Entry point when the user pastes an existing `# Describe:` packet, asks for
    a second opinion, wants a fresh-agent read on the spec, or implementation
    is likely to follow and the spec should be challenged first.
- **`implement-from-spec`**
  - Entry point when an accepted or reviewed `# Describe:` packet exists and
    the user wants code, not more open-ended planning.
- **`commit-after-spec`**
  - Final branch when the describe-scoped implementation is validated and the
    user asked to commit or save progress.

Default chaining rules:

- If the user asks to fix/build something, start at `draft-spec`, then continue
  to `review-spec`, then `implement-from-spec` unless review finds a real
  decision or the user explicitly asked for spec-only output.
- If the user pastes a `# Describe:` packet, start at `review-spec` unless they
  explicitly say it is already accepted and want implementation immediately.
- If the user says `commit`, `save progress`, or `/commit` after describe-scoped
  implementation, finish with `commit-after-spec`.

## Workflow

### 0) Surface assumptions before drafting

Before classifying scope, declare the silent assumptions the spec is about to encode. For every assumption, pick the cheapest source that can actually answer it — route through `ask-cascade`'s resolution ladder (read code, `/wiki query`, `/wiki-duel`, `/dueling-idea-wizards`, `/deep-research-prompt`, then human).

Transform imperative requests into verifiable goals before writing any test case:

| Request shape | Verifiable reframe |
|---|---|
| "Fix the bug" | Write a failing test that reproduces it; done = test passes |
| "Add validation" | Write tests for each invalid input; done = all pass |
| "Refactor X" | Existing test suite green before and after; done = no behavior delta |
| "Make it faster" | Name the metric + target (p95, throughput, perceived) before touching code |
| "Make X work" | Unusable — push back and ask for an observable success signal |

If the request is still "make it work" after routing, that ambiguity is the first thing to resolve — not a scope classification.

### 1) Scope (draft-spec entry; infer first, ask only if ambiguous)

Skip this step when the user already provided a concrete `# Describe:` packet
and you are entering through `review-spec` or `implement-from-spec`.

Infer `bug fix`, `small feature`, or `refactor` from the user's request and
the code context whenever the answer is obvious. Do not stop to ask the user
to classify the work when the phrasing already makes the scope clear.

Examples:
- "fix", "broken", "regression", "why is X failing" → **bug fix**
- "add", "build", "new widget", "support X" → **small feature**
- "extract", "clean up", "dedupe", "reorganize without behavior change" → **refactor**

Ask only when multiple classifications are plausibly correct and the choice
would materially change the test plan. If you must ask, make the question
specific to the ambiguity rather than forcing the user to do meta-labeling.

Fallback question:

> "Should I treat this as a bug fix, a small feature, or a refactor for test coverage?"

This determines test case shape:
- **Bug fix** → regression test is mandatory, root cause must be identified
- **Small feature** → happy path + validation errors + permissions
- **Refactor** → existing behavior must not change (regression-heavy)

### 2) Locate

Find affected code. Read it. Understand current behavior before asking
more questions.

```
- Grep/Glob for the relevant code
- Read the files, note function signatures, existing tests, error handling
- Identify the boundary: where does input enter, where does output leave?
- If reviewing an existing `# Describe:` packet, verify the referenced files,
  tests, and line numbers still match the current code before trusting it
```

### 3) Define the change (ask-cascade only when code reading reveals a real decision)

Now that you've read the code, ask targeted questions. Batch only
independent questions. Apply ask-cascade rules:

- **Before batching, test:** "If the user answered Q1 differently, would I
  reword or remove Q2?" Yes → split. No → safe to batch.
- **Never ask generic approval** ("Does this look right?"). Ask specific
  uncertainties ("Should expired tokens return 401 or 403?").

Typical rounds:

**R2 — Core behavior (1-2 questions, depends on inferred or confirmed scope):**
- What's the exact input that triggers the bug / starts the feature?
- What's the expected output or state change?

**R3 — Boundaries (batch independent questions, depends on R2):**
- What inputs are invalid? What should happen?
- What existing behavior must NOT change?
- Any concurrency, ordering, or timing concerns?

**R4+ — Only if R3 reveals complexity.** Re-evaluate after each answer.
A strategic answer may eliminate questions or spawn new ones.

If `review-spec` reveals a genuine scope or behavior decision, route that
decision through ask-cascade here. Ask only the next blocking question; do not
fall back to a broad "does this look right?" checkpoint.

### 4) Generate test spec

Produce the test case spec using the output template below.

Rules for test cases:
- Each test case is **binary pass/fail** — no subjective judgment
- Each has concrete **Given/When/Then** with actual values, not placeholders
- Include the **type** so implementers know what they're protecting against
- Reference actual file paths and line numbers from Step 2
- For API changes, include HTTP method, path, status code, error code
- Include concrete **Validation Commands** whenever the repo has a credible
  command-first verification path; if none exist, say so explicitly

Test case types:
| Type | When to use |
|------|-------------|
| `happy` | Core success path — the thing that should work |
| `error` | Invalid input, missing data, permission denied |
| `regression` | Existing behavior that must NOT break |
| `edge` | Boundary values, empty collections, concurrent access |

**Minimum coverage by scope:**
- Bug fix: 1 happy + 1 regression + the root-cause error case
- Small feature: 2 happy + 2 error + 1 regression
- Refactor: 1 happy + 3+ regression

### 5) Coverage review

Present the spec.

If the user asked for spec-only output, ask one final question (not generic
approval):

> "I have N test cases covering [summary]. Is there a scenario I'm
> missing, or should we adjust any expected values?"

If the user adds cases or corrections, update the spec and re-present.

If the original request was action-oriented and no strategic ambiguity remains,
do not stop here for generic approval. Continue to `review-spec`.

### 6) Fresh-context spec review (`review-spec`; default before implementation)

Trigger this mode when any of these are true:

- The user pastes an existing `# Describe:` packet
- The user asks for a second opinion or fresh-agent pass
- The user says or strongly implies "if this looks good, implement it"
- The user asks to implement from an accepted describe spec
- You just finished `draft-spec` and implementation is likely to follow

Workflow:

1. Build a compact input packet:
   - original user request
   - current describe spec
   - key clarifications from the conversation
   - relevant repo/product context
2. Use [references/post-spec-prompts.md](references/post-spec-prompts.md) and
   run a fresh-context read-only review that answers the underlying ask,
   validates the spec against the code, and calls out missing cases, risky
   assumptions, non-goals, and decisions.
3. If the runtime has no subagent primitive, perform the same pass inline as a
   clearly labeled second review. Do not pretend it was a subagent.
4. Return a compact review summary to the user:
   - underlying ask in plain language
   - what the spec gets right
   - missing or risky cases
   - non-goals
5. If the review surfaces a real decision that changes coverage or scope, use
   ask-cascade to resolve that decision one question at a time. Then revise the
   spec. Re-run the review only if the revision is material.
6. If the user asked only for review, stop after the reviewed or revised spec.
7. If the original request was action-oriented and there are no open decisions,
   continue to `implement-from-spec` without another generic approval gate.

### 7) Implementation from spec (`implement-from-spec`)

Enter this mode when any of these are true:

- The user explicitly asks to implement
- The original request was a fix/build request and `review-spec` ended with no
  open decisions
- The user provides an accepted or reviewed `# Describe:` packet and asks for
  code

Rules:

1. Treat the reviewed describe spec as locked scope.
2. If the user explicitly asks to delegate to Codex, prefer `/codex:rescue`
   even for smaller tasks.
3. Also prefer `/codex:rescue` when the implementation is likely to take 5+
   minutes or benefits from fresh context.
4. If the packet does not already include concrete validation commands, derive
   them before coding and append them to the packet.
5. Build the implementation prompt from:
   - original request
   - reviewed describe spec
   - resolved decisions from review
   - relevant file refs
   - concrete validation commands
6. Use the prompt template in
   [references/post-spec-prompts.md](references/post-spec-prompts.md).
7. Use the stable commentary marker:
   - `Using describe (implement-from-spec). Locked scope from the reviewed spec; tests first, then implementation, then validation.`
8. After launching `/codex:rescue`, report that the job is running and remind
   the user to check with `/codex:status` and `/codex:result`.
9. If not using `/codex:rescue`, implement inline but still keep the locked-spec
   discipline.
10. After implementation, report:
   - what changed
   - what was validated
   - any remaining risks or blockers
11. If the user asked for a commit, continue to `commit-after-spec`.

### 8) Commit after spec (`commit-after-spec`)

Enter this mode when the describe-scoped implementation is validated and the
user asked to commit, save progress, or `/commit`.

Rules:

1. Prefer the existing `commit` skill discipline rather than inventing a new
   commit workflow here.
2. Commit only the files you changed for this describe-scoped work.
3. Never mix unrelated dirty worktree changes into the commit.
4. If validation is still failing, either fix it first or clearly tell the user
   why the commit would ship a known failure.
5. Report the repo(s), commit message(s), and any remaining dirty files that
   were intentionally left alone.

## Output Template

Use this structure. Adjust sections as needed but keep the Given/When/Then
format strict.

```markdown
# Describe: [Change Title]

## Context
- **Type:** bug-fix | feature | refactor
- **Affected:** path/to/file.py:L42, path/to/other.py:L15
- **Current behavior:** [what happens now — be specific]
- **Desired behavior:** [what should happen after the change]
- **Root cause:** [bug fixes only — why the current behavior is wrong]

## Test Cases

### TC-1: [Short descriptive name]
- **Given:** [preconditions — concrete values]
- **When:** [action — exact call, request, or user action]
- **Then:** [expected result — status code, return value, state change]
- **Type:** happy

### TC-2: [Short descriptive name]
- **Given:** [preconditions]
- **When:** [action]
- **Then:** [expected error/rejection]
- **Type:** error

### TC-3: [Short descriptive name]
- **Given:** [preconditions — existing working scenario]
- **When:** [same action that worked before the change]
- **Then:** [unchanged behavior — same result as before]
- **Type:** regression

## Validation Commands
- <command 1>
- <command 2>

## Open Decisions
- None
  or
- [specific question that still needs a user answer]

## Coverage
- Happy paths: N
- Error cases: N
- Regression guards: N
- Edge cases: N
- Total: N
```

### Optional Review Summary Template

If Step 6 is triggered, append a compact review summary after the spec:

```markdown
## Underlying Ask
- ...

## Spec Review
- Holds: ...
- Missing or risky cases: ...

## Decisions Needed
- None
  or
- [minimal ask-cascade question]

## Non-Goals
- ...
```

## Examples

See [references/examples.md](references/examples.md) for worked examples
at different granularities (API endpoint, utility function, UI behavior).

## Anti-patterns

- **Vague assertions:** "it should work correctly" → specify exact output
- **Missing regression guards:** every change risks breaking something —
  name what must survive unchanged
- **Unnecessary meta questions:** do not ask the user to classify obvious
  work as bug fix / feature / refactor when the request already answers it
- **Premature implementation:** if you catch yourself writing fix code,
  stop — finish the spec first
- **Over-specifying:** 20 test cases for a one-line fix is waste —
  match coverage to risk
- **Skipping code reading:** never generate test cases from the
  conversation alone — read the actual code first
- **Manual packet shuffling:** do not make the user paste the same
  `# Describe:` packet back to you just to get a fresh review or implementation
- **Over-checkpointing:** do not stop for generic approval after `review-spec`
  when there are no real decisions left
- **Silent review skipping:** if implementation is likely or the user pasted an
  existing spec, do not skip `review-spec`

## Related

- [[skill-issue]]
