# {slice_name} Frontend Spec

> Screens, interactions, and states per role. See [shared.md](./shared.md) for API contract, [flows.md](./flows.md) for user journeys.
> Implementation details (component structure, widget primitives, data fetching patterns) are the scaffolder's job.

---

## Screens

### Screen: [Name]

**Who sees it:** [Role 1 / Role 2 / Both]
**Purpose:** [What the user accomplishes here]

**What's on screen:**
1. [Section/area] — [What it shows, what actions are available]
2. [Section/area] — [What it shows, what actions are available]

**Key interactions:**
- [Click X] → [What happens]
- [Submit form] → [What happens, what feedback user sees]

---

### Screen: [Name 2]

<!-- Repeat format -->

---

## States Per Screen

| Screen | Loading | Empty | Error | Populated |
|--------|---------|-------|-------|-----------|
| [List view] | [What user sees] | [Message + CTA] | [Message + retry?] | [What's shown] |
| [Detail view] | [What user sees] | N/A | [Message + retry?] | [What's shown] |

---

## Role Differences

| Capability | Role 1 View | Role 2 View |
|-----------|-------------|-------------|
| [View list] | All own records | Only assigned records |
| [Create] | Yes, with full form | No |
| [Edit] | Yes | No |
| [Delete] | Yes, with confirmation | No |

---

## Inline vs Separate Page Decisions

<!-- Document the rationale for each screen's placement -->

| Feature | Decision | Rationale |
|---------|----------|-----------|
| [Feature 1] | Inline in [Widget] | Keeps context |
| [Feature 2] | Separate page | Standalone CRUD workflow |

---

## Test Focus Areas

- [ ] All screens render in each state (loading, empty, error, populated)
- [ ] Role-based visibility (role 1 sees X, role 2 sees Y)
- [ ] [Key interaction] works end-to-end

---

## Implementation Notes

**Use the domain-scaffolder skill with `surface=frontend` to generate code from this spec.**
