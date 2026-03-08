---
name: describe
description: >
  Distill a conversation into discrete, well-defined test cases before
  patching. Lightweight alternative to domain-planner for bug fixes, small
  features, and refactors. Uses ask-cascade for hierarchical coverage.
  Use when: "describe", "/describe", "what are the test cases",
  "define done", "what should we test", "spec this out",
  "before we patch", "test coverage for this", or when about to implement
  a fix without clearly defined pass/fail criteria.
---

# Describe

Define what "done" looks like before writing code. Produces a structured
test case spec that makes implementation and review unambiguous.

**Lifecycle position:**
- **domain-planner** = full feature slices (6 plan files, multi-phase)
- **describe** = patches, bug fixes, small features (single test spec)
- **reproduce** = verify the fix after implementation

## Workflow

### 1) Scope (infer first; ask only if ambiguous)

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
```

### 3) Define the change (ask-cascade: depends on scope + code reading)

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

### 4) Generate test spec

Produce the test case spec using the output template below.

Rules for test cases:
- Each test case is **binary pass/fail** — no subjective judgment
- Each has concrete **Given/When/Then** with actual values, not placeholders
- Include the **type** so implementers know what they're protecting against
- Reference actual file paths and line numbers from Step 2
- For API changes, include HTTP method, path, status code, error code

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

Present the spec. Ask one final question (not generic approval):

> "I have N test cases covering [summary]. Is there a scenario I'm
> missing, or should we adjust any expected values?"

If the user adds cases or corrections, update the spec and re-present.

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

## Coverage
- Happy paths: N
- Error cases: N
- Regression guards: N
- Edge cases: N
- Total: N
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
