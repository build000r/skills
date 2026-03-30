---
name: domain-scaffolder
description: Scaffold backend or frontend domain code from an existing slice plan using a shared stack-aware workflow. Use for "scaffold a domain slice", "implement the backend for {slice}", "implement the frontend for {slice}", or "scaffold {slice}" after domain-planner finishes a slice plan. This is the only supported domain scaffolder skill.
license: MIT
---

# Domain Scaffolder

Canonical shared scaffolder for domain slices. This skill owns the shared contract,
mode system, validation shape, and audit handoff.

Plans, templates, and prompts should reference `domain-scaffolder` directly and
set the surface explicitly when the request is already scoped.

Bundled canonical references live here:

- `references/mode-template.md`
- `references/test-templates.md`
- `references/example-patterns.md`
- `references/orchestration-contract.md`

Those references now absorb the reusable legacy backend/frontend wrapper
material. Treat this skill as the source of truth.

Cross-skill worker, handoff, and shared-file ownership rules come from
`references/orchestration-contract.md`.

## Surfaces

This skill supports two surfaces:

- `backend`
- `frontend`

Surface selection rules:

1. Explicit `surface=backend|frontend` from the caller or handoff artifact wins.
2. If exactly one matching mode supports one surface, use that surface automatically.
3. Explicit backend wording => `backend`
4. Explicit frontend wording => `frontend`
5. Otherwise infer from the request and upstream artifacts.
6. Ask the user only if the surface is still genuinely ambiguous.

Use the backend surface for server/domain/migration/router work.
Use the frontend surface for types/API/hooks/components/widget work.

Greenfield direct-invocation examples:

- "scaffold the backend for reporting"
- "implement the frontend for report-request"
- "scaffold report-request" -> ask only if backend vs frontend is ambiguous

## On Trigger

1. Start with a stable first progress update:
   - `Using domain-scaffolder surface=<surface|resolving> for <slice|slice-resolution> with <mode|mode-resolution>.`
2. Resolve surface using the rules above.
3. Resolve mode from `{skill_root}/modes/*.md`, preferring the longest matching `cwd_match`.
4. Resolve `slice` and `plan path` from the explicit request, upstream handoff, or active plan context before asking the user.
5. Ask only when surface, mode, or slice remain materially ambiguous after those checks.

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

Use `.backend.md` / `.frontend.md` suffixes when a repo needs separate canonical
mode files per surface.

See `references/mode-template.md` for the canonical schema.

Mode-template files should target the canonical skill naming:

- `domain-scaffolder.md` when one mode file can cover the repo cleanly
- `domain-scaffolder.backend.md` and/or `domain-scaffolder.frontend.md` when you
  need separate source templates per surface

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

The mode's auth-service block is the canonical auth/payments/identity source.
Prefer the generic keys:

- `auth_packages_root`
- `auth_python_packages`
- `auth_npm_packages`

Legacy SPAPS-shaped keys remain valid in existing modes and mean the same thing:

- `spaps_root`
- `spaps_python_packages`
- `spaps_npm_packages`

If both generic and legacy keys appear, prefer the generic `auth_*` values.

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

The `audit handoff` must be ready to run without extra interpretation. It should name:

- `domain-reviewer`
- the resolved `slice`
- the implemented `surface`
- the exact `plan path`
- the validation commands already run
- any known risk areas the audit should verify first

If the implementation is incomplete, say exactly which artifact is still missing.

## Backend Surface

Use this when `surface=backend`.

### Required Inputs

Read from the active mode:

- backend repo path
- backend module/domain structure
- test paths
- test framework and validation commands
- migration tool and naming
- convention files
- access-control and error-handling patterns
- router-registration requirements
- auth-service package configuration
- any inline model/schema/auth snippets supplied by the mode

If the mode does not include stronger project-specific test guidance, use
`references/test-templates.md` as the canonical fallback starter.

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
- Read the mode's backend convention files before writing code
- Error codes must match `shared.md`
- Migration SQL must reflect permissions and DB transition rules from `backend.md`
- Route handlers must delegate auth/payments/identity behavior to auth-service-backed packages
- Register the router before closeout
- Use the mode's inline model/schema/auth examples when present instead of inventing fresh patterns

### Backend Validation

Before marking complete:

- tests were written first
- service tests pass
- route tests pass
- standard backend domain files exist
- migration exists and follows the mode's access-control pattern
- router registration is complete
- backend validation commands from the active mode were run

## Frontend Surface

Use this when `surface=frontend`.

### Required Inputs

Read from the active mode:

- frontend repo path
- file structure
- validation commands
- component library
- key component primitives
- data-fetching pattern
- state-management and auth patterns
- `patterns_reference`, if the mode points at a separate file or skill
- in-mode frontend reference sections when the mode inlines them directly

If the mode does not provide a project-specific patterns reference yet, use
`references/example-patterns.md` as the canonical fallback for shaping one.

### Generation Order

```text
1. load frontend reference context (`patterns_reference` or the mode's inlined equivalent)
2. types
3. API/service layer
4. data hooks
5. components using library primitives
6. widget/page wrapper
7. run validation commands
```

### Frontend Rules

- Loading `patterns_reference` or the mode's equivalent frontend reference
  context is mandatory before generating any components
- Use the mode's library primitives instead of re-implementing shells/buttons/states inline
- Query/cache keys must follow the mode's convention
- Reuse auth-service-backed packages for auth/payments/identity behavior
- Extend existing components/widgets before creating new siblings when the mode
  or patterns reference indicates an established surface
- Respect the mode's design tokens, icon package, and component-size limits when provided

### Frontend Validation

Before marking complete:

- patterns were loaded first
- type/build/lint commands pass
- types match `shared.md`
- loading/error/empty states are handled
- component size limits from the mode are respected
- data-fetching and mutation patterns follow the mode
- existing component/library patterns were reused instead of reimplemented

## Related Skills

- `domain-planner` -- creates the plan this skill implements
- `domain-reviewer` -- audits the implementation against the plan
