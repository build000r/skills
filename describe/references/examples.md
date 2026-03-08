# Describe: Worked Examples

## Example 1: Bug Fix (API auth endpoint)

User says: "Expired machine keys are still passing auth checks."

### ask-cascade trace

**R1 (strategic, alone):** "Bug fix, feature, or refactor?" → Bug fix

**R2 (core behavior, depends on R1):**
- "Which endpoint is affected — all authenticated routes or a specific one?"
  → All routes going through `verify_machine_key` dependency
- "What's the current expiry check?" → [agent reads code, finds
  `expires_at` is fetched but never compared to `now`]

**R3 (boundaries, batched — independent of each other):**
- "Should expired keys return 401 or 403?" → 401 (not authenticated)
- "Are there keys without an `expires_at` (null)?" → Yes, treat as
  non-expiring (legacy support)

### Output

```markdown
# Describe: Enforce machine key expiry in auth dependency

## Context
- **Type:** bug-fix
- **Affected:** services/api/app/dependencies/auth.py:L28
- **Current behavior:** `verify_machine_key` fetches `expires_at` but
  never checks it — expired keys pass auth
- **Desired behavior:** Reject expired keys with 401
- **Root cause:** `expires_at` comparison missing from the guard clause

## Test Cases

### TC-1: Valid non-expired key authenticates
- **Given:** Machine key with `expires_at` = tomorrow
- **When:** GET /v1/protected with `X-Machine-Key: {valid_key}`
- **Then:** 200 OK, request proceeds
- **Type:** happy

### TC-2: Expired key is rejected
- **Given:** Machine key with `expires_at` = yesterday
- **When:** GET /v1/protected with `X-Machine-Key: {expired_key}`
- **Then:** 401 `{"error": "MACHINE_KEY_EXPIRED"}`
- **Type:** error

### TC-3: Null expires_at key still works (legacy)
- **Given:** Machine key with `expires_at` = NULL
- **When:** GET /v1/protected with `X-Machine-Key: {legacy_key}`
- **Then:** 200 OK, request proceeds
- **Type:** regression

### TC-4: Key expiring at exact current time
- **Given:** Machine key with `expires_at` = now (to the second)
- **When:** GET /v1/protected with `X-Machine-Key: {boundary_key}`
- **Then:** 401 `{"error": "MACHINE_KEY_EXPIRED"}` (expired means <=, not <)
- **Type:** edge

## Coverage
- Happy paths: 1
- Error cases: 1
- Regression guards: 1
- Edge cases: 1
- Total: 4
```

---

## Example 2: Small Feature (utility function)

User says: "Add a helper that normalizes contact names — trim whitespace,
title case, collapse multiple spaces."

### ask-cascade trace

**R1 (strategic, alone):** "Bug fix, feature, or refactor?" → Small feature

**R2 (core behavior, depends on R1):**
- "Where will this be called — intake forms, search, or both?"
  → Intake form submission only

**R3 (boundaries, batched):**
- "Handle non-ASCII names (accents, CJK)?" → Yes, preserve as-is
- "Empty string or None input — raise or return empty?" → Return empty string

### Output

```markdown
# Describe: Contact name normalization helper

## Context
- **Type:** feature
- **Affected:** services/api/app/utils/text.py (new function)
- **Current behavior:** No normalization — raw form input stored as-is
- **Desired behavior:** `normalize_name(raw) -> str` trims, title-cases,
  collapses spaces

## Test Cases

### TC-1: Standard name
- **Given:** input = "  jane   doe  "
- **When:** normalize_name(input)
- **Then:** "Jane Doe"
- **Type:** happy

### TC-2: Already clean name
- **Given:** input = "Jane Doe"
- **When:** normalize_name(input)
- **Then:** "Jane Doe"
- **Type:** happy

### TC-3: Empty string
- **Given:** input = ""
- **When:** normalize_name(input)
- **Then:** ""
- **Type:** error

### TC-4: None input
- **Given:** input = None
- **When:** normalize_name(input)
- **Then:** ""
- **Type:** error

### TC-5: Accented characters preserved
- **Given:** input = "  maría   garcía-lópez  "
- **When:** normalize_name(input)
- **Then:** "María García-López"
- **Type:** edge

### TC-6: Existing names in DB are not affected
- **Given:** Contact with name "jane doe" already stored
- **When:** Read contact from DB
- **Then:** Returns "jane doe" unchanged (normalization is input-only)
- **Type:** regression

## Coverage
- Happy paths: 2
- Error cases: 2
- Regression guards: 1
- Edge cases: 1
- Total: 6
```

---

## Example 3: Refactor (extract shared logic)

User says: "The discount calculation is duplicated in three places —
consolidate it."

### ask-cascade trace

**R1 (strategic, alone):** "Bug fix, feature, or refactor?" → Refactor

**R2 (core behavior, depends on R1):**
- [Agent reads all three locations, finds they're identical except one
  uses `int()` truncation and two use `round()`]
- "The three implementations differ — one truncates, two round. Which
  is correct?" → Round (the truncating one is a latent bug)

**R3 (boundaries, batched):**
- "Should the consolidated function live in utils or in the pricing
  module?" → Pricing module
- "Fix the truncation bug in this PR or separate it?" → Fix it here,
  it's directly related

### Output

```markdown
# Describe: Consolidate discount calculation

## Context
- **Type:** refactor (with incidental bug fix)
- **Affected:**
  - billing/checkout.py:L88 (round — correct)
  - billing/invoice.py:L142 (round — correct)
  - billing/subscription.py:L55 (int truncation — bug)
- **Current behavior:** Three identical discount calculations, one with
  truncation bug
- **Desired behavior:** Single `calculate_discount()` in pricing module,
  all callers use it, rounding behavior everywhere

## Test Cases

### TC-1: Checkout produces same result as before
- **Given:** Cart with items totaling $100, 15% discount
- **When:** Checkout flow calculates total
- **Then:** Discount = $15.00, total = $85.00
- **Type:** regression

### TC-2: Invoice produces same result as before
- **Given:** Invoice with subtotal $99.99, 10% discount
- **When:** Invoice generation
- **Then:** Discount = $10.00, total = $89.99
- **Type:** regression

### TC-3: Subscription now rounds instead of truncating
- **Given:** Subscription with price $33.33, 7% discount
- **When:** Subscription renewal
- **Then:** Discount = $2.33 (was $2 with int truncation)
- **Type:** regression (behavior change — intentional fix)

### TC-4: Fractional cent rounding
- **Given:** Price $10.00, 33.33% discount
- **When:** calculate_discount(10.00, 33.33)
- **Then:** $3.33 (banker's rounding)
- **Type:** edge

### TC-5: Zero discount
- **Given:** Price $50.00, 0% discount
- **When:** calculate_discount(50.00, 0)
- **Then:** $0.00
- **Type:** happy

## Coverage
- Happy paths: 1
- Error cases: 0
- Regression guards: 3
- Edge cases: 1
- Total: 5
```

Note: refactor-heavy spec — 3 of 5 test cases are regression guards
ensuring the three call sites still produce correct results.
