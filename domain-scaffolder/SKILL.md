---
name: domain-scaffolder
description: Scaffold backend or frontend domain code from an existing slice plan using a shared stack-aware workflow. Use for "scaffold a domain slice", "implement the backend for {slice}", "implement the frontend for {slice}", or "scaffold {slice}" after domain-planner finishes a slice plan. This is the canonical greenfield entrypoint; the legacy wrapper skills `domain-scaffolder-backend` and `domain-scaffolder-frontend` remain supported only for compatibility.
license: MIT
---

# Domain Scaffolder

Canonical shared scaffolder for domain slices. This skill owns the shared contract,
mode system, validation shape, and audit handoff. The legacy backend/frontend
skills are compatibility wrappers over this canonical flow.

Greenfield plans, templates, and prompts should reference `domain-scaffolder`
directly and set the surface explicitly when the request is already scoped.
Only mention the wrapper names when you are preserving compatibility with older
plans, prompts, or mode-template installers.

## Surfaces

This skill supports two surfaces:

- `backend`
- `frontend`

Surface selection rules:

1. `domain-scaffolder-backend` wrapper => `backend`
2. `domain-scaffolder-frontend` wrapper => `frontend`
3. Direct `domain-scaffolder` invocation => infer from the request
4. If direct invocation is ambiguous, ask the user which surface to scaffold

Use the backend surface for server/domain/migration/router work.
Use the frontend surface for types/API/hooks/components/widget work.

## Unified Private Mode Store

The canonical private mode store lives here:

```text
{skill_root}/modes/
```

Every mode file must include:

```text
cwd_match: <path prefix>
surface: backend | frontend | both
```

Legacy wrapper-local `modes/` paths remain valid through compatibility symlinks.
Edit the canonical files in this skill root when possible. The wrapper-local file
names are preserved for continuity, even when the canonical store had to rename
colliding files with `.backend.md` / `.frontend.md` suffixes.

See `references/mode-template.md` for the canonical schema.

Greenfield mode-template files should target the canonical skill naming:

- `domain-scaffolder.md` when one mode file can cover the repo cleanly
- `domain-scaffolder.backend.md` and/or `domain-scaffolder.frontend.md` when you
  need separate source templates per surface

Do not create new `domain-scaffolder-backend.md` or
`domain-scaffolder-frontend.md` template files for greenfield repos.

## Mode Selection

1. List mode files from `{skill_root}/modes/*.md`
2. Filter by `surface` matching the requested surface or `both`
3. Filter by `cwd_match`
4. If one mode matches, use it automatically
5. If multiple modes match, prefer the longest `cwd_match`
6. If a tie remains, ask the user which mode to use
7. If no mode matches:
   - you may still read a plan via explicit plan paths
   - do not scaffold implementation paths until a mode or explicit implementation context exists

Do not search the filesystem for plans or conventions. Read the plan root from the
mode or require explicit overrides.

## Shared Rules

### Plan Prerequisites

All scaffolding requires an existing slice plan.

Backend requires:

- `shared.md`
- `backend.md`
- `schema.mmd`

Frontend requires:

- `shared.md`
- `frontend.md`
- `flows.md` (preferred; require it when the plan says the surface is flow-heavy)

If the plan is missing, stop and tell the user to use `domain-planner` first.

### Auth Service Reuse

The mode's `auth_packages_root` is the canonical auth/payments/identity source.

1. Reuse existing auth packages first
2. Do not scaffold parallel local auth/payments/identity systems
3. If required capability is missing, raise an auth-scope proposal instead of inventing a local layer
4. If temporary local symlink/link loading is required, validate against published/live packages before closeout

### Delivery Default

1. Implement the target-state contract directly
2. Do not add legacy compatibility bridges unless the plan explicitly requires them
3. If production data is impacted, keep DB transition requirements in backend artifacts instead of inventing frontend compatibility paths

### Completion Contract

Every scaffolding run ends with a structured handoff:

- `surface`
- `slice`
- `mode file used`
- `plan path`
- `files emitted`
- `validation commands run`
- `validation result`
- `audit handoff`

If the implementation is incomplete, say exactly which artifact is still missing.

## Backend Surface

Use this when `surface=backend`.

### Required Inputs

Read from the active mode:

- backend repo path
- backend module/domain structure
- test paths
- migration tool and naming
- convention files

### Generation Order

```text
1. service tests
2. route tests
3. models
4. schemas
5. repository
6. service
7. router
8. migration
9. run tests
10. register router
```

### Backend Rules

- Tests are written before implementation
- Error codes must match `shared.md`
- Migration SQL must reflect permissions and DB transition rules from `backend.md`
- Route handlers must delegate auth/payments/identity behavior to auth-service-backed packages

### Backend Validation

Before marking complete:

- tests were written first
- service tests pass
- route tests pass
- standard backend domain files exist
- migration exists and follows the mode's access-control pattern
- router registration is complete

## Frontend Surface

Use this when `surface=frontend`.

### Required Inputs

Read from the active mode:

- frontend repo path
- file structure
- validation commands
- component library
- data-fetching pattern
- `patterns_reference`

### Generation Order

```text
1. load patterns_reference
2. types
3. API/service layer
4. data hooks
5. components using library primitives
6. widget/page wrapper
7. run validation commands
```

### Frontend Rules

- Loading `patterns_reference` is mandatory before generating any components
- Use the mode's library primitives instead of re-implementing shells/buttons/states inline
- Query/cache keys must follow the mode's convention
- Reuse auth-service-backed packages for auth/payments/identity behavior

### Frontend Validation

Before marking complete:

- patterns were loaded first
- type/build/lint commands pass
- types match `shared.md`
- loading/error/empty states are handled
- component size limits from the mode are respected
- data-fetching and mutation patterns follow the mode

## Direct Invocation Examples

```text
"scaffold the backend for reporting"
"implement the frontend for report-request"
"scaffold report-request"   # ask only if backend vs frontend is ambiguous
```

## Wrapper Compatibility

The following wrapper skills remain valid:

- `domain-scaffolder-backend`
- `domain-scaffolder-frontend`

They exist to preserve old triggers, stable names, and wrapper-local mode file
names. The shared workflow and canonical private modes now live in this skill.
Do not generate new wrapper references in greenfield docs or templates.

## Related Skills

- `domain-planner` -- creates the plan this skill implements
- `domain-reviewer` -- audits the implementation against the plan
