---
name: domain-scaffolder-frontend
description: |
  Scaffold frontend code from an existing plan. REQUIRES loading project-specific
  UI patterns before generating components. Use when: "scaffold the frontend",
  "implement the frontend for {slice}", after domain-scaffolder-backend completes.
  Reads shared.md, frontend.md, and flows.md to generate types, services,
  hooks, components, and page/widget wrappers.
  NOT for: backend code, general frontend work outside domain slices.
  Supports multiple frontend frameworks via modes/ directory.
license: MIT
---

# Domain Scaffolder - Frontend

Generates frontend code from an existing domain slice plan.

**Skill root:** `~/.claude/skills/domain-scaffolder-frontend/` — all relative paths below resolve from here.

## Plan Storage (Mode-Defined)

Plan storage comes from the active frontend mode file (`~/.claude/skills/domain-scaffolder-frontend/modes/{mode}.md`):

```
plan_root: <mode value>
plan_index: <mode value>
```

To find a slice: read `{plan_root}/{slice}/`. DO NOT search the filesystem.
If no mode matches, require explicit plan paths before scaffolding.

## Modes (Implementation Context)

Modes provide **implementation-specific** context — framework, component library, file structure.

Check `~/.claude/skills/domain-scaffolder-frontend/modes/` for project-specific configuration. Each mode defines:

- **cwd_match** -- directory pattern for auto-detection
- **Frontend framework** -- React, Next.js, Vue, etc.
- **Component library** -- primitives, naming conventions, pattern references
- **Data fetching pattern** -- hooks, query keys, cache invalidation
- **File structure** -- where features, types, services, and components live
- **Validation commands** -- type-check, build, lint commands
- **Component size limits** -- preferred and absolute max LOC

**If no mode matches the current directory:**
1. You can still read plans if you provide explicit plan paths.
2. For scaffolding (which needs implementation paths), list available modes (from `~/.claude/skills/domain-scaffolder-frontend/modes/*.md` filenames) and ask the user which to use.
3. DO NOT search the filesystem. DO NOT spawn Explore agents.

See [references/mode-template.md](~/.claude/skills/domain-scaffolder-frontend/references/mode-template.md) for the mode file format.
See [references/example-patterns.md](~/.claude/skills/domain-scaffolder-frontend/references/example-patterns.md) for a complete example of what a patterns reference should look like — the level of opinionated detail that produces consistent, auditable code.

## Auth Service Requirements (All Modes)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical authentication, payments, and identity layer.

1. Reuse existing auth service packages first. Do not scaffold parallel local auth/payments/identity systems.
2. If required functionality is missing, raise an "auth-scope proposal" to the user (gap, impacted slice, proposed package/API, expected cross-product benefit).
3. If unpublished local package changes are required, use temporary local symlink/link loading from `{auth_packages_root}`, then switch to published/live auth service packages and run final checks before marking complete.

## Delivery Default (Big-Bang)

1. Implement the target-state UI/API contract from the plan directly.
2. Do not scaffold legacy API client fallbacks, dual-contract adapters, or compatibility toggles unless the plan explicitly requires them.
3. If backend planning includes a production DB transition section, treat it as backend operational work; do not add frontend compatibility logic for old/new data contracts unless explicitly requested.

## CRITICAL: Load Patterns First

**Before generating ANY components, you MUST load context-appropriate patterns.**

If the active mode defines a performance envelope, treat it as binding:
- No live-state polling on healthy WS paths.
- No architecture that couples terminal stream updates to global rerenders.
- Render-path constraints (Canvas/OffscreenCanvas at scale, throttle budgets) are acceptance requirements, not suggestions.

1. Read the mode's `patterns_reference` (a file path or skill name)
2. Understand the component library primitives and their usage
3. Follow all component and pattern requirements from the reference

Failure to load patterns results in audit failures (inline styling, missing component primitives, wrong data fetching patterns, etc.)

## Prerequisites

**Requires an existing plan.** Before scaffolding, ensure:

1. Plan exists at `{plan_root}/{slice}/` (from active mode, or explicit override)
2. Plan includes:
   - `shared.md` -- API contract (endpoints, schemas, error codes)
   - `frontend.md` -- Screens, interactions, states per role
   - `flows.md` -- User journeys and state transitions (optional but recommended)

If no plan exists:
> "No plan found for `{slice}`. Use the domain-planner skill first to create the plan."

## Generation Order

```
1. Load patterns from mode's patterns_reference    <- FIRST (REQUIRED)
2. {types_path}/{slice}.ts                         <- Types from shared.md
3. {services_path}/{slice}Service.ts               <- API client
4. {features_path}/{slice}/hooks/*.ts              <- Data fetching hooks
5. {features_path}/{slice}/components/*.tsx         <- Components (using library primitives)
6. {features_path}/{slice}/widgets/*.tsx            <- Page/widget wrappers
7. Run the mode's validation commands
```

Paths reference the mode's `types_path`, `services_path`, and `features_path` settings.

## Step-by-Step Process

### Step 1: Load Patterns

**This is REQUIRED, not optional.**

Read the mode's `patterns_reference` to learn:
- Component library primitives (panel, button, loading, error, empty state components)
- Data fetching patterns (query hooks, mutation hooks)
- Component size limits (preferred and absolute max LOC)
- Loading/error/empty state patterns

Without this, your generated code WILL fail audit.

### Step 2: Read the Plan

```
{plan_root}/{slice}/
+-- plan.md           # Strategic context, user stories
+-- schema.mmd        # Conceptual ERD
+-- shared.md         # API contract (THE SOURCE OF TRUTH)
+-- frontend.md       # Screens, interactions, states per role
+-- flows.md          # User journeys and state transitions
```

Extract:
- **From shared.md:** Endpoints, request/response shapes, error codes -- derive TypeScript types
- **From frontend.md:** Screens per role, key interactions, states (loading/empty/error/populated), inline vs page decisions
- **From flows.md:** User journeys per role, decision points, error paths, state transitions -- informs component flow and navigation
- **From plan scope:** Auth/payments/identity surfaces and corresponding auth service package usage requirements

### Step 3: Generate TypeScript Types

Create types at the mode's `types_path` or `features_path/{slice}/types.ts`:

- Types MUST match shared.md response/request shapes exactly
- Define `{Item}`, `{Item}CreateRequest`, `{Item}UpdateRequest` interfaces
- Define `{Slice}ErrorCode` union type from shared.md error codes
- Include timestamp fields (`created_at`, `updated_at`) on response types

### Step 4: Generate API Service

Create the API client at the mode's `services_path` or `features_path/{slice}/services/`:

- One static method per endpoint from shared.md (list, getById, create, update, delete)
- Map error codes from shared.md to user-friendly messages
- Use the mode's HTTP client conventions
- Use auth service packages for auth/payments/identity interactions instead of ad-hoc local implementations
- Do not add legacy endpoint fallback logic unless explicitly required by the plan

### Step 5: Generate Data Fetching Hooks

Create hooks at the mode's `features_path/{slice}/hooks/` using the mode's data fetching pattern.

Key requirements:
- Centralized, hierarchical query/cache keys
- Proper cache invalidation on mutations
- Stale time configuration appropriate to the data

Pattern shape (adapt to the mode's data fetching library):

- Centralized query key factory: `{slice}Keys.all`, `{slice}Keys.list(filters)`, `{slice}Keys.detail(id)`
- `use{Slice}List(filters?)` -- list hook with filter support
- `use{Slice}Detail(id)` -- detail hook with enabled guard
- `use{Slice}Mutations()` -- returns create, update, delete mutations that invalidate appropriate cache keys on success

### Step 6: Generate Components (Using Library Primitives)

**CRITICAL:** Use the mode's component library primitives. NO inline styling that duplicates what primitives provide.

```typescript
// CORRECT - Using the mode's component library
import { PanelComponent, ButtonComponent } from "{library_import_path}";

export function {Item}Card({ item, onEdit, onDelete }: {Item}CardProps) {
  return (
    <PanelComponent>
      {/* Content using library primitives */}
      <ButtonComponent onClick={onEdit}>Edit</ButtonComponent>
    </PanelComponent>
  );
}

// WRONG - Inline styling that duplicates library primitives
export function {Item}Card({ item }: {Item}CardProps) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      {/* Reinventing what the library already provides */}
    </div>
  );
}
```

### Step 7: Generate Page/Widget Wrapper

For dashboard widgets or page containers, use the mode's shell/wrapper components:

```typescript
export function {Slice}Widget({ contextId }: {Slice}WidgetProps) {
  const { data, isPending, error, refetch } = use{Slice}List({ contextId });

  return (
    <ShellComponent title="{Slice Title}">
      {isPending && <LoadingComponent message="Loading..." />}
      {error && <ErrorComponent message={error.message} onRetry={refetch} />}
      {!isPending && !error && (!data || data.length === 0) && (
        <EmptyComponent message="No items yet" />
      )}
      {data && data.length > 0 && (
        <div>
          {data.map((item) => (
            <{Item}Card key={item.id} item={item} />
          ))}
        </div>
      )}
    </ShellComponent>
  );
}
```

### Step 8: Verify Build

Run the mode's validation commands:

```bash
cd {frontend_repo}
{type_check_command}
{build_command}
{lint_command}
```

If local symlink/link auth service packages were used during development, switch to published/live package versions and re-run the mode validation commands before completion.

## File Output Structure

```
{frontend_repo}/
+-- {types_path}/
|   +-- {slice}.ts                             # OR in features/{slice}/types.ts
+-- {features_path}/{slice}/
|   +-- types.ts                               # TypeScript types
|   +-- services/
|   |   +-- {slice}Api.ts                      # API client
|   +-- hooks/
|   |   +-- use{Slice}.ts                      # Data fetching hooks
|   +-- components/
|   |   +-- {Item}Card.tsx
|   |   +-- {Item}List.tsx
|   |   +-- {Item}Form.tsx
|   |   +-- index.ts                           # Barrel export
|   +-- widgets/
|       +-- {Slice}Widget.tsx                   # Page/widget wrapper
```

Exact paths come from the mode's `types_path`, `services_path`, and `features_path` settings.

## Pattern Checklist

Before marking complete, verify:

### Component Library Primitives
- [ ] Using the mode's panel/card component, not inline border/shadow styling
- [ ] Using the mode's button component, not inline button styling
- [ ] Using the mode's loading state component, not custom spinners
- [ ] Using the mode's error state component with retry capability
- [ ] Using the mode's empty state component for empty lists
- [ ] Using the mode's header/shell components for page wrappers

### Data Fetching
- [ ] Using the mode's data fetching hooks, not manual state + effect patterns
- [ ] Using the mode's mutation pattern for write operations
- [ ] Query/cache keys are centralized and hierarchical
- [ ] Proper cache invalidation on mutations

### Component Size
- [ ] Components under preferred LOC limit (from mode)
- [ ] Components under absolute max LOC limit (from mode)
- [ ] Large components extracted to sub-components

### Async States
- [ ] Loading state handled (pending check)
- [ ] Error state handled (error check with retry)
- [ ] Empty state handled (empty array/null check)
- [ ] Success state renders data

### Type Safety
- [ ] Types match shared.md exactly
- [ ] No `any` types
- [ ] Props interfaces defined

### Auth Service Integration
- [ ] Auth/payments/identity behavior reuses existing auth service packages
- [ ] Missing auth service functionality is captured as an auth-scope proposal (if encountered)
- [ ] Temporary local symlink/link package usage is replaced with published/live auth service package verification before final completion (if applicable)

### Delivery Strategy
- [ ] Target-state big-bang contract implemented (no unrequested legacy compatibility UI/client paths)

## Next Step: Request Audit

After frontend implementation is complete, tell the user:

> "Frontend scaffolding complete for `{slice}`. Use the domain-reviewer skill to audit both backend and frontend against the plan."

The audit will check:
- Backend compliance with backend.md
- Frontend compliance with frontend.md + the mode's patterns
- API contract compliance with shared.md

## Related Skills

- **domain-planner** -- Creates the plan this skill implements
- **domain-scaffolder-backend** -- Backend implementation (do this first)
- **domain-reviewer** -- Audits implementation against plan
