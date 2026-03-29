# Audit Report Template

Use this template for AUDIT_REPORT.md output.

---

# {Slice Name} - Implementation Audit

**Audit Date:** {YYYY-MM-DD}
**Implementation Date:** {Date implementation was completed}
**Implementing Agent:** {Agent} ({Model})
**Auditor:** {Agent} ({Model})
**Status:** {COMPLIANT | MOSTLY COMPLIANT | NEEDS WORK | CRITICAL ISSUES}

---

## Executive Summary

{1-2 paragraph overview of findings. Include:
- What was implemented
- Overall quality assessment
- Critical issues if any
- Recommendation (deploy/don't deploy)}

### Overall Compliance Score: **{XX}/100**

**Breakdown:**
- Backend Structure: **{XX}%** {brief note}
- API Contract: **{XX}%** {brief note}
- Frontend Patterns: **{XX}%** {brief note}
- Test Coverage: **{XX}%** {brief note}
- Type Safety: **{XX}%** {brief note}
- Documentation: **{XX}%** {brief note}
- Auth service Auth/Payments/Identity Compliance: **{XX}%** {brief note}
- Delivery Strategy Discipline (Big-Bang): **{XX}%** {brief note}
- Performance Envelope: **{XX}%** {brief note}

---

## Compliance Scorecard

| Category | Plan Requirement | Implemented | Compliant | Score |
|----------|-----------------|-------------|-----------|-------|
| **Backend - Models** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Backend - Service** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Backend - Router** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Backend - Tests** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Frontend - Components** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Frontend - Hooks** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Frontend - Tests** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Shared - API Contract** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Shared - Error Codes** | {requirement} | {status} | {Yes/No/Partial} | {XX}% |
| **Auth service Integration** | Existing Auth service package reuse + gap proposal + local-link to published/live validation | {status} | {Yes/No/Partial} | {XX}% |
| **Delivery Strategy** | Target-state big-bang implementation; no unrequested legacy compatibility; DB transition section if production data impacted | {status} | {Yes/No/Partial} | {XX}% |
| **Performance Envelope** | {mode/plan performance constraints} | {status} | {Yes/No/Partial} | {XX}% |

---

## What Was Implemented Correctly

### 1. {Category Name} - **{STATUS}**

**Status:** {PERFECT MATCH | MINOR DEVIATION | etc.}

{Description of what was done correctly. Include:
- Specific files and line numbers
- How it matches the plan
- Code snippets if helpful}

**Evidence:** {file:line references}

### 2. {Next Category}...

---

## What Was NOT Implemented

### 1. {Missing Item} - **{SEVERITY}**

**Plan Requirements ({file}:{lines}):**
{Quote from plan showing what was expected}

**What was done:** {Describe what's missing or placeholder}

**Impact:**
- {Consequence 1}
- {Consequence 2}

**Verdict:** {Assessment and recommendation}

### 2. {Next Missing Item}...

---

## Deviations

### Critical Deviations

1. **{Deviation Title}** (Severity: {Critical|High|Medium|Low})
   - Plan said: {quote}
   - Implementation did: {description}
   - Reason: {why this happened}
   - Impact: {consequences}
   - **Action required:** {what to do}

### Positive Deviations

1. **{Improvement Title}**
   - Plan said: {quote}
   - Implementation did: {better approach}
   - **BETTER** than plan because: {reasoning}

---

## Pattern Compliance

### Frontend Pattern Compliance

| Pattern | Required | Found | Compliant |
|---------|----------|-------|-----------|
| Shared panel/card primitives | No inline panels | {count} violations | {Yes/No} |
| Loading state component | No inline spinners | {count} violations | {Yes/No} |
| Error state component | With retry support | {count} missing retry | {Yes/No} |
| Query hooks | No manual state + effect | {count} violations | {Yes/No} |
| Storage hooks | No manual storage access | {count} violations | {Yes/No} |
| Component size | <300 LOC | {count} over 400 LOC | {Yes/No} |

### Backend Convention Compliance

| Pattern | Required | Found | Compliant |
|---------|----------|-------|-----------|
| Domain structure | Mode-specified standards | {count} files | {Yes/No} |
| TDD | Tests exist | {coverage}% | {Yes/No} |
| Access control policies | Correct syntax | {count} issues | {Yes/No} |
| Error handling | Service error to HTTP mapping | {count} missing | {Yes/No} |
| Migration naming | Mode-specified convention | {Yes/No} | {Yes/No} |
| Performance envelope | Mode/plan-declared SLOs + bounds | {count} issues | {Yes/No} |

### Auth service Integration Compliance

| Pattern | Required | Found | Compliant |
|---------|----------|-------|-----------|
| Existing Auth service package reuse | No local replacement auth/payments/identity layer | {count} violations | {Yes/No} |
| Auth service gap handling | Missing functionality documented as auth-scope proposal | {count} missing proposals | {Yes/No} |
| Versioning workflow | Local symlink/link use followed by published/live Auth service validation | {count} missing validations | {Yes/No} |

### Delivery Strategy Compliance

| Pattern | Required | Found | Compliant |
|---------|----------|-------|-----------|
| Big-bang target-state contract | No unrequested legacy endpoint compatibility layers | {count} violations | {Yes/No} |
| DB transition runbook (if data-impacting) | Backup + raw `psql` + transaction/idempotency + rollback | {status} | {Yes/No} |

---

## Recommendations

### For Immediate Action (Priority: Critical/High)

1. **{Action Title}**
   - Issue: {description}
   - Fix: {what to do}
   - Files: {file paths}

### For Near-Term (Priority: Medium)

1. **{Action Title}**
   - Issue: {description}
   - Fix: {what to do}

### For Future Phases (Priority: Low)

1. **{Action Title}**
   - Note: {description}

### Process Improvements

1. **{Improvement}**
   - Observation: {what went wrong/right}
   - Suggestion: {how to improve}

---

## Unfinished Work Checklist

### From Plan (Explicitly Deferred)

- [ ] {Item from plan marked as future phase}
- [ ] {Item marked out-of-scope}

### Discovered During Audit

- [ ] {Missing test coverage for X}
- [ ] {Placeholder implementation in Y}
- [ ] {Documentation not updated for Z}

---

## Risk Assessment

### High Risk
1. **{Risk}:** {description and mitigation}

### Medium Risk
1. **{Risk}:** {description and mitigation}

### Low Risk
1. **{Risk}:** {description and mitigation}

---

## Final Verdict

**Status:** {COMPLIANT | MOSTLY COMPLIANT | NEEDS WORK | CRITICAL ISSUES}

{Final assessment paragraph. Include:
- Overall quality
- Key strengths
- Key weaknesses
- Deploy/don't deploy recommendation with conditions}

**Recommendation:**
- **DEPLOY** if: {conditions}
- **DO NOT DEPLOY** until: {blockers resolved}

---

## Plan Compliance Checklist

### Implemented from Plan
- [x] {Item 1}
- [x] {Item 2}
- [x] {Item 3 with note}

### Not Implemented from Plan
- [ ] {Missing item 1} ({reason})
- [ ] {Missing item 2} ({reason})

### Partially Implemented
- [~] {Item} ({percentage} - {details})

---

## Agent Handoffs

Use these copy-paste blocks to hand off issues to implementor agents.

### For Backend Issues

{Only include if backend issues exist}

```
Fix the backend issues found in the {slice} slice audit.

FIRST: Load the domain-scaffolder skill with `surface=backend` for {slice} to get backend patterns and standards.

READ: {plan_root}/{slice}/AUDIT_REPORT.md

Key issues to address:
- {Backend Issue 1}
- {Backend Issue 2}
- {Backend Issue 3}

Plan: {plan_root}/{slice}/backend.md

Remember: TDD-first per backend conventions - write tests before fixing implementation.
Auth service rule: reuse existing `{auth_packages_root}` auth/payments/identity packages first. If functionality is missing, include a auth-scope proposal instead of building a local substitute.
```

### For Frontend Issues

{Only include if frontend issues exist}

```
Fix the frontend issues found in the {slice} slice audit.

FIRST: Load the domain-scaffolder skill with `surface=frontend` for {slice} to get frontend patterns.

READ: {plan_root}/{slice}/AUDIT_REPORT.md

Key issues to address:
- {Frontend Issue 1}
- {Frontend Issue 2}

Plan: {plan_root}/{slice}/frontend.md
Auth service rule: reuse existing `{auth_packages_root}` auth/payments/identity packages first. If functionality is missing, include a auth-scope proposal instead of building a local substitute.
```

---

## Re-Review History

{This section is appended after each re-review cycle}

### Re-Review #1 - {YYYY-MM-DD}

**Baseline commit:** `{commit-hash}` ({repo})
**Changes reviewed:** `git diff {baseline}..HEAD`

**Issues Resolved:**
- [x] {Issue from original audit} - Fixed in `{file:line}`
- [x] {Issue 2} - Fixed in `{file:line}`

**Issues Remaining:**
- [ ] {Issue 3} - Not addressed
- [ ] {Issue 4} - Partially fixed, still needs {detail}

**New Issues Found:**
- {New issue introduced by fix, if any}

**Updated Score:** **{XX}/100** (was {YY}/100)

**Updated Handoffs:** {Include updated handoff blocks if issues remain, or "None - ready for deploy"}

---

## References

**Plan Documents:**
- `plan.md` - {brief description}
- `shared.md` - {brief description}
- `backend.md` - {brief description}
- `frontend.md` - {brief description}

**Implementation Files:**
- `{file path}` - {description} ({lines} lines)

**Standards Checked:**
- Mode-specified frontend patterns reference
- Mode-specified backend convention files
- Mode-specified Auth service integration requirements (`{auth_packages_root}`)

---

**Auditor Signature:** {Agent} ({Model})
**Audit Completed:** {YYYY-MM-DD}
**Re-Reviews:** {count} | **Final Score:** {XX}/100
**Status:** {OPEN - awaiting fixes | CLOSED - ready for deploy}
