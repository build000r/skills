# {slice_name} User Flows

> How users move through this feature, step by step. One flow per goal.
> These flows drive screen design (frontend.md) and endpoint design (shared.md).

---

## Flow 1: [User creates a {slice_name}]

```
User opens the relevant view
  → clicks "{slice_name}" tab/section
  → sees existing list (or empty state with CTA)
  → clicks "Create new"
  → fills form: [field1, field2, ...]
  → submits
  → sees confirmation + new item in list
```

**Decision points:**
- [Does user pick from existing items or create freeform?]
- [Is there a draft/publish workflow or immediate save?]

**Error paths:**
- Validation fails → [inline errors, form stays open]
- Duplicate name → [toast with suggestion]

---

## Flow 2: [User views their {slice_name}s]

```
User opens their dashboard
  → sees {slice_name} section
  → clicks into a specific item
  → sees detail view (read-only)
```

**Notes:**
- [What can the user do here? Just view? Acknowledge?]

---

## Flow 3: [User edits/deletes]

```
User opens the relevant view
  → clicks existing {slice_name}
  → edits fields inline (or opens edit form)
  → saves changes
  → sees updated item

OR

  → clicks delete
  → sees confirmation dialog
  → confirms
  → item removed from list
```

---

## State Transitions

<!-- If items have lifecycle states (draft → active → archived), document here -->

```
[draft] --publish--> [active] --archive--> [archived]
                         |
                     --delete--> [deleted]
```

**Who can trigger each transition:**
| Transition | Role 1 | Role 2 | System |
|-----------|--------|--------|--------|
| draft → active | Yes | No | No |
| active → archived | Yes | No | After [condition]? |
