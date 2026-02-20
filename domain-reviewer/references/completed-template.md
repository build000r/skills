# Completed Template

Use this template for COMPLETED.md output after retiring a slice.

**Principles:**
- User stories, not code references
- Impact of deferrals, not implementation difficulty
- Decisions that affect users or future development
- Lean - this replaces verbose planning docs
- Cross-reference related slices

---

# {Slice Name} - Completion Summary

**Consolidated:** {YYYY-MM-DD}
**Domain:** [{domain}]
**Stories:** {X}✓ {Y}→

> **IMPORTANT:** Always use symbol format `X✓ Y→` (e.g., `5✓ 8→`), NOT prose like "5 complete, 8 deferred".
> This matches INDEX.md format and enables automated parsing.

## What Users Can Now Do

{List completed user stories from the user's perspective}

- **{Story title}** - {One sentence describing what users can do}
- **{Story title}** - {One sentence describing what users can do}
- **{Story title}** - {One sentence describing what users can do}

## What's Deferred

{List deferred items with user impact and resolution status}

**Resolution states:**
- No marker = still open (may be done later)
- `→ **Resolved** in {slice}` = completed elsewhere
- `→ **Dismissed**` = explicitly won't do

### {Deferred Story - Still Open}
- **Why:** {Brief reason - scope, dependency, priority}
- **Impact:** {What users can't do because of this}
- **See also:** [{other_slice}](./../{other_slice}/COMPLETED.md) | TBD | v2

### {Deferred Story - Resolved Elsewhere}
- **Why:** {Brief reason}
- **Impact:** {What users couldn't do}
→ **Resolved** in `{other-slice}` ({YYYY-MM})

### {Deferred Story - Dismissed}
- **Why:** {Original reason for deferral}
→ **Dismissed** - {Brief reason: deprioritized, superseded, not aligned with product direction}

## Key Decisions

{Choices made during implementation that affect user experience or future work}

- **{Decision}** - {Why this choice was made}
- **{Decision}** - {Rationale}

## Gotchas

{Things the next developer should know - behavioral quirks, not code details}

- {Gotcha that could trip someone up}
- {Edge case or race condition discovered}

## Related Slices

{Connections to other slices in same domain or with shared concerns}

| Slice | Relationship | Notes |
|-------|--------------|-------|
| [{slice}](./../{slice}/) | Same domain | {Brief note} |
| [{slice}](./../{slice}/) | Shared tables | Uses {table_name} |
| [{slice}](./../{slice}/) | Deferred handoff | May pick up {story} |

## References

- **API Contract:** [shared.md](./shared.md)
- **Database Schema:** [schema.mmd](./schema.mmd)
- **Original Plan:** [_archived/plan.md](./_archived/plan.md) {if archived}

---

## Template Usage Notes

**What to include:**
- Every user story from the plan, categorized as complete or deferred
- User-facing impact of deferrals (not technical blockers)
- Resolution status for deferred items (open / resolved elsewhere / dismissed)
- Decisions that someone extending this feature should know
- Behavioral gotchas discovered during implementation

**Deferred item lifecycle:**
- When retiring: ask user for resolution status of each deferred item
- When completing previously-deferred work: add `→ **Resolved** in {slice}` to old COMPLETED.md
- When dismissing: add `→ **Dismissed** - {reason}` to mark as "won't do"
- Kanban/agent scans filter to items without resolution markers (still open)

**What NOT to include:**
- File paths or line numbers (code is the documentation)
- Implementation details (backend.md covered this, now archived)
- Audit scores or compliance percentages (served their purpose)
- Technical debt unless it affects user experience

**Sizing guide:**
- Aim for 50-100 lines total
- Each section should be skimmable in 30 seconds
- If you need more detail, it probably belongs in code comments
