# Plan Quality Rubric

10 dimensions × 10 points = 100. Used by the quality loop assessor and external reviewer to score plan files before sign-off.

## Scoring Instructions

For each dimension, start at 10 and deduct points per issue found. Minimum 0 per dimension.

**Deduction scale:**
- **-1** — Minor: easily fixable, low impact on implementability
- **-2** — Moderate: could cause confusion or require clarification during scaffolding
- **-5** — Major: would cause INCORRECT implementation or block a scaffolder agent

**Key:** `-5` is reserved for issues that produce WRONG code, not for missing operational details.

Report every deduction with: dimension, points lost, file:location, issue description, fix instruction.

### Calibration Guidelines

These rules prevent systematic over-penalization:

1. **Sibling conflicts are informational, not deductions.** If a sibling slice's contract needs updating, report it in the Sibling Conflicts section. Only deduct if the conflict would cause THIS plan's scaffolder to produce wrong code (e.g., referencing an endpoint that doesn't exist).

2. **Operational bounds are v1-optional by default.** Missing rate limits, pagination maxes, payload size limits, and timeout specs should NOT be deducted unless the plan explicitly claims to define them. These are operational hardening, not correctness requirements.

   **Performance-critical override:** If the active mode or the slice plan declares a performance envelope (latency/throughput/backpressure/memory bounds), those bounds are no longer optional. Missing or untestable bounds should be deducted as Moderate or Major issues because they can produce incorrect architecture and unsafe runtime behavior.

3. **Outcome-level test scenarios are acceptable.** "Happy: user books → 201, booking confirmed, capacity decremented" is a valid test scenario worth 7-8/10. Full JSON request/response payloads are ideal (9-10/10) but not required for a passing score. Only deduct -5 if test scenarios are so vague they can't be implemented (e.g., "it should work").

4. **Component names with behavioral descriptions ARE spec.** "CallStatusBadge — shows booked time or Book call prompt, states: booked/not-booked/loading, interactions: onBook/onReschedule/onCancel" is behavioral spec that communicates design intent. Deduct only for actual implementation code: TypeScript/Python/JSX bodies, import statements, hook implementation code, or prescribed file path trees.

5. **A well-communicated plan scores 85+ on the first assessment.** A plan that clearly defines business rules, user stories with acceptance criteria, API contracts with request/response shapes, sequence flows, and component behavior should score 85-95 even with minor gaps in operational details. The quality loop still targets `100/100` before sign-off, so first-pass strength does not replace the final pass requirement.

6. **Big-bang is the default.** Deduct for unrequested legacy compatibility plans (dual endpoints, adapter layers, deprecation windows, shadow writes/reads) unless the user explicitly asked for compatibility support.

7. **Highest-best-use / 80-20 cuts are mandatory.** Deduct when the plan does not preserve the minimum winning slice from the Core Value Gate, or when it spends disproportionate spec surface on admin polish, configurability, abstraction, or secondary actors before fully nailing the primary actor's visible win.

---

## Dimension 1: File Completeness (10 pts)

**What it checks:**
- All 6 files present and non-empty: plan.md, shared.md, backend.md, frontend.md, flows.md, schema.mmd
- Each file follows its template structure (correct heading hierarchy, required sections present)
- No placeholder content ("TODO", "TBD", "[fill in]", empty sections)

**Common failures:**
- schema.mmd missing or containing only the `erDiagram` keyword with no entities
- flows.md with section headers but no actual flow content
- frontend.md skipped for API-only slices without documenting why

**How to fix:**
- Populate every file from the planning session content. If a file is intentionally empty (e.g., frontend.md for API-only), add a one-line note: `> This slice has no frontend. See plan.md for rationale.`

---

## Dimension 2: Type Consistency (10 pts)

**What it checks:**
- Every TypeScript interface/type referenced in shared.md is fully defined in shared.md
- Types used in backend.md match the definitions in shared.md (same field names, same types)
- Types used in frontend.md match shared.md (no local redefinitions with different shapes)
- Entity names in schema.mmd match the types/interfaces in shared.md

**Common failures:**
- shared.md references `AvailableSection` but only defines `AvailableProduct[]`
- backend.md mentions a `status` field as enum but shared.md defines it as string
- frontend.md uses `ContentItem` while shared.md defines `ContentEntry`

**How to fix:**
- Pick the canonical name from shared.md (single source of truth). Update all other files to match. If a type is genuinely different per layer, document the mapping explicitly.

---

## Dimension 3: Slug/Constant Consistency (10 pts)

**What it checks:**
- Named constants (slugs, enum values, error codes, endpoint paths) agree across all files
- plan.md user story references match the constants defined in shared.md
- Test payload examples in backend.md/frontend.md use the exact constants from shared.md
- Error code patterns follow sibling conventions (e.g., `{SLICE}_NOT_FOUND`)

**Common failures:**
- plan.md says `content_type: "article"` but shared.md enum has `"blog_post"`
- backend.md test payload uses `status: "active"` but shared.md defines `status: "published"`
- Error codes inconsistent: `CONTENT_NOT_FOUND` in shared.md vs `NOT_FOUND` in backend.md

**How to fix:**
- Grep all named values across the 6 files. Build a constant registry. Fix mismatches to match shared.md definitions.

---

## Dimension 4: Test Payload Completeness (10 pts)

**What it checks:**
- Every user story has test scenarios (happy path and key error cases)
- Test scenarios include expected HTTP status and error code for error cases
- Test scenarios are specific enough for a scaffolder to write a test from them
- Response shapes in test scenarios are consistent with defined response types

**Scoring guide:**
- 9-10/10: Full JSON request/response payloads for each scenario with all required fields
- 7-8/10: Outcome-level scenarios with status codes and error codes (e.g., "Happy: user books → 201, booking confirmed, capacity decremented")
- 4-6/10: Some scenarios missing, or scenarios without status/error codes
- 0-3/10: Vague scenarios ("it should work") or missing entirely

**Common failures:**
- User story has acceptance criteria but no test scenarios at all (-2 per story)
- Error test only says "should return 400" without error code (-1)
- Test scenario references fields not in the interface definition (-1)

**How to fix:**
- For each user story, add at least happy path + primary error scenario. Include expected HTTP status and error code. Full JSON payloads are ideal but not required.

---

## Dimension 5: User Story Quality (10 pts)

**What it checks:**
- Every story follows "As a [role], I need to [action], so that [outcome]" format
- Each story has acceptance criteria (not just the story statement)
- Each acceptance criterion has at least one test scenario (happy path)
- Critical acceptance criteria have error/edge case test scenarios
- Roles mentioned in stories are defined and consistent

**Common failures:**
- Stories missing the "so that [outcome]" clause
- Acceptance criteria without test scenarios (just assertions)
- Stories using undefined roles (e.g., "admin" when the slice only defines "operator" and "end user")

**How to fix:**
- Complete the story format. Add test scenarios inline under each acceptance criterion. Verify roles against the role list in plan.md.

---

## Dimension 6: Spec/Implementation Boundary (10 pts)

**What it checks:**
- backend.md contains business rules, permissions, and edge cases — NOT implementation code or framework patterns
- frontend.md contains behavioral descriptions (screens, states, interactions, layout) — NOT code bodies or file structure trees
- No framework-specific implementation patterns (e.g., actual React/Python code, import statements, hook implementations)

**What IS acceptable (do NOT deduct):**
- Component names with behavioral descriptions: "CallStatusBadge — pill showing booked time or Book call prompt, states: booked/not-booked/loading"
- Hook names with behavioral descriptions: "useCallBooking — manages booking state, lazy-loads availability on open"
- Service class names with endpoint mappings: "CallBookingService — wraps /v1/booking/* endpoints"
- Named UI patterns: "WidgetPanel, WidgetPill" (existing design system references)
- Cache timing hints: "availability stale after ~30s" (behavioral, not code)

**What IS a deduction:**
- TypeScript/Python/JSX code bodies (`export function ...`, `class Service:`, JSX markup)
- Import statements (`import { useQuery } from ...`)
- File path trees (`src/features/call-booking/components/...`)
- Hook implementation code (actual `useQuery`/`useMutation` calls with options)
- SQL DDL (belongs in schema.mmd or migrations, not in behavioral specs)

**How to fix:**
- Rewrite code blocks as behavioral descriptions. Keep component/hook/service NAMES (they're design intent), remove their BODIES.

---

## Dimension 7: Schema Accuracy (10 pts)

**What it checks:**
- schema.mmd is a valid Mermaid erDiagram (parseable syntax)
- Entities represent actual database tables, not UI concepts
- Relationships (1:1, 1:N, M:N) are labeled and directional
- Foreign keys to sibling slice entities are present and correct
- Entity field names match the TypeScript interfaces in shared.md

**Common failures:**
- schema.mmd uses conceptual groupings ("ContentModule") instead of real tables
- Missing relationship labels (just lines without `||--o{` notation)
- FK to sibling entity references wrong table name
- Fields in schema don't match shared.md interface fields

**How to fix:**
- Map each entity to a real database table. Add proper Mermaid relationship notation. Cross-reference sibling schemas for FK accuracy. Align field names with shared.md.

---

## Dimension 8: Cross-File Reference Integrity (10 pts)

**What it checks:**
- Every endpoint in shared.md is referenced in at least one flow in flows.md
- Every entity in schema.mmd is referenced in backend.md (business rules)
- Frontend screens in frontend.md reference the endpoints they consume (from shared.md)
- User stories in plan.md map to endpoints in shared.md (coverage)
- Error codes defined in shared.md appear in backend.md error handling rules
- If mode declares a performance envelope, enforce cross-file alignment:
  - plan.md contains measurable SLO targets and load assumptions
  - shared.md contains runtime/backpressure contract semantics
  - backend.md contains implementation constraints + verification scenarios

**Common failures:**
- shared.md defines `DELETE /content/:id` but flows.md has no delete flow
- schema.mmd has an `audit_log` entity never mentioned in backend.md
- frontend.md screen references `GET /content/stats` not defined in shared.md

**How to fix:**
- Build a cross-reference matrix: stories → endpoints → flows → screens. Fill gaps. Remove orphaned definitions.

---

## Dimension 9: Scope Discipline (10 pts)

**What it checks:**
- The plan stays anchored to the Phase 0.5 Core Value Gate (primary actor, single visible outcome, minimum winning slice)
- The slice represents the highest-leverage / highest-best-use 80-20 cut rather than a broad "while we're here" bundle
- No out-of-scope features sneaking into the spec (features not in the original user stories)
- "Future" / "Out of Scope" section is terse pointers, not detailed specs
- No feature creep: ancillary features (analytics, notifications, export) are listed as future unless explicitly scoped
- Plan doesn't duplicate functionality owned by a sibling slice

**Common failures:**
- The primary actor's visible win is diluted by equal or greater detail for admin tooling, reporting, configurability, or secondary roles
- The minimum winning slice is undefined or contradicted by later sections that expand the contract surface without user approval
- The plan bundles multiple adjacent wins into one slice when one smaller cut would deliver the main outcome faster and with less coordination cost
- backend.md includes detailed analytics event tracking not in any user story
- "Future Considerations" section is 200+ lines with full endpoint specs
- Plan defines a notification system that overlaps with the `notifications` slice
- Plan adds legacy route compatibility (`/v1` + `/v2`) without an explicit user request
- Plan documents deprecation/parallel-run mechanics for old endpoints that were never requested

**How to fix:**
- Remove anything not traceable to a user story. Trim "Future" to one-line pointers: `- Analytics: track content views (future slice)`. Check sibling INDEX.md for scope overlaps.
- Remove unrequested compatibility layers and keep the spec on the target-state contract. If production data changes are required, put that in a separate DB transition section only.
- Re-anchor the slice to the Core Value Gate: name the primary actor, single visible outcome, and minimum winning slice, then cut or defer any story, endpoint, screen, or schema surface that does not materially improve that outcome or protect it from a top safety/risk failure.

---

## Dimension 10: Single Source of Truth (10 pts)

**What it checks:**
- TypeScript interfaces/types defined ONCE in shared.md, not duplicated in frontend.md or backend.md
- Endpoint paths defined ONCE in shared.md, referenced (not redefined) elsewhere
- Business rules defined ONCE in backend.md, not restated in frontend.md
- No contradictory definitions across files (e.g., different field sets for the same entity)

**Common failures:**
- shared.md defines `ContentResponse` and frontend.md redefines it with extra fields
- Endpoint path in shared.md is `/v1/content` but backend.md says `/api/content`
- Same validation rule stated differently in backend.md and frontend.md

**How to fix:**
- Keep definitions in their canonical file (types→shared.md, rules→backend.md, screens→frontend.md). Other files reference, never redefine. If a file needs to note a type, write "see shared.md `ContentResponse`" not the full definition.

---

## Assessment Output Format

The assessor MUST produce output in this exact format for machine parsing:

```markdown
## Plan Quality Assessment: {slice}
**Score: XX/100**

### Dimension Scores
| # | Dimension | Score | Notes |
|---|-----------|-------|-------|
| 1 | File completeness | X/10 | {brief note or "Clean"} |
| 2 | Type consistency | X/10 | {brief note or "Clean"} |
| 3 | Slug/constant consistency | X/10 | {brief note or "Clean"} |
| 4 | Test payload completeness | X/10 | {brief note or "Clean"} |
| 5 | User story quality | X/10 | {brief note or "Clean"} |
| 6 | Spec/implementation boundary | X/10 | {brief note or "Clean"} |
| 7 | Schema accuracy | X/10 | {brief note or "Clean"} |
| 8 | Cross-file reference integrity | X/10 | {brief note or "Clean"} |
| 9 | Scope discipline | X/10 | {brief note or "Clean"} |
| 10 | Single source of truth | X/10 | {brief note or "Clean"} |

### Issues
| # | Dimension | Points Lost | File | Issue | Fix |
|---|-----------|-------------|------|-------|-----|
| 1 | Type consistency | -2 | shared.md:141 | AvailableSection undefined | Define type or change to AvailableProduct[] |
| 2 | ... | ... | ... | ... | ... |

### Verdict
{PASS if 100/100, NEEDS FIX if < 100}
Remaining issues: {count}
```

**Key rules for assessors:**
- Be specific — cite file name and line/section, not vague descriptions
- Every point deducted MUST have a corresponding row in the Issues table
- The Fix column must be actionable — a fixer agent should be able to apply it without additional context
- Do NOT suggest "improvements" or "nice to haves" — only deduct for rubric violations
- Do NOT deduct for sibling slice issues — report them separately
