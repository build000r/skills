---
name: domain-scaffolder-backend
description: |
  Scaffold backend domain code from an existing plan using TDD-first workflow.
  Writes tests BEFORE implementation. Use when: "scaffold the backend",
  "implement the backend for {slice}", after domain-planner completes a plan.
  Reads shared.md, backend.md, and schema.mmd to generate: tests first,
  then models, schemas, repository, service, router, migration.
  NOT for: frontend code, general backend work outside domain slices.
  Supports multiple backend frameworks via modes/ directory.
license: MIT
---

# Domain Scaffolder - Backend

Generates backend domain code from an existing plan. **TDD-first workflow:** tests are written BEFORE implementation.

**Skill root:** `~/.claude/skills/domain-scaffolder-backend/` — all relative paths below resolve from here.

## Plan Storage (Mode-Defined)

Plan storage comes from the active backend mode file (`~/.claude/skills/domain-scaffolder-backend/modes/{mode}.md`):

```
plan_root: <mode value>
plan_index: <mode value>
```

To find a slice: read `{plan_root}/{slice}/`. DO NOT search the filesystem.
If no mode matches, require explicit plan paths before scaffolding.

## Modes (Implementation Context)

Modes provide **implementation-specific** context — framework, file structure, conventions.

Check `~/.claude/skills/domain-scaffolder-backend/modes/` for project-specific configuration. Each mode defines:

- **cwd_match** -- directory pattern for auto-detection
- **Backend framework** -- language, ORM, test framework
- **File structure** -- where domain files, tests, and migrations live
- **Convention files** -- AGENTS.md location and key patterns
- **Migration tool** -- how to create and name migrations
- **Access control** -- RLS, RBAC, or other permission patterns

**If no mode matches the current directory:**
1. You can still read plans if you provide explicit plan paths.
2. For scaffolding (which needs implementation paths), list available modes (from `~/.claude/skills/domain-scaffolder-backend/modes/*.md` filenames) and ask the user which to use.
3. DO NOT search the filesystem. DO NOT spawn Explore agents.

See [references/mode-template.md](~/.claude/skills/domain-scaffolder-backend/references/mode-template.md) for the mode file format.

## Auth Service Requirements (All Modes)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical authentication, payments, and identity layer.

1. Reuse existing auth service packages first. Do not scaffold parallel local auth/payments/identity systems.
2. If required functionality is missing, raise an "auth-scope proposal" to the user (gap, impacted slice, proposed package/API, expected cross-product benefit).
3. If unpublished local package changes are required, use temporary local symlink/link loading from `{auth_packages_root}`, then switch to published/live auth service packages and run final checks before marking complete.

## Delivery Default (Big-Bang)

1. Implement the target-state contract from `shared.md` directly.
2. Do not scaffold legacy endpoint aliases, compatibility adapters, dual-write/read paths, or deprecation bridges unless the plan explicitly requires them.
3. If production data is impacted, follow the dedicated DB transition section in `backend.md` (backup + transactional/idempotent SQL + verification + rollback). Keep this separate from API/runtime compatibility logic.

## Prerequisites

**Requires an existing plan.** Before scaffolding, ensure:

1. Plan exists at `{plan_root}/{slice}/` (from active mode, or explicit override)
2. Plan includes:
   - `shared.md` -- API contract (endpoints, schemas, error codes)
   - `backend.md` -- Business rules, permissions, edge cases

If no plan exists:
> "No plan found for `{slice}`. Use the domain-planner skill first to create the plan."

## TDD-First Workflow

Per the mode's backend convention files:
> "Plan with TDD -- write or extend tests before touching implementation."

**Generation order (strict):**

```
1. tests/{test_structure.service_tests}    <- FIRST
2. tests/{test_structure.route_tests}      <- FIRST
3. {domain_structure.models}
4. {domain_structure.schemas}
5. {domain_structure.repository}
6. {domain_structure.service}
7. {domain_structure.router}
8. {migration_path}/{migration_naming}
9. Run tests to verify they pass
```

Paths above reference the mode's `domain_structure`, `test_structure`, and `migration_path` settings.

## Step-by-Step Process

### Step 1: Read the Plan

```
{plan_root}/{slice}/
+-- shared.md         # API contract (THE SOURCE OF TRUTH)
+-- backend.md        # Business rules, permissions, edge cases
+-- schema.mmd        # Conceptual ERD (entities + relationships)
```

`{plan_root}` is mode-defined unless explicitly overridden.

Extract:
- **From shared.md:** Endpoints, request/response shapes, error codes -- derive schemas, models, routes
- **From backend.md:** Business rules, permissions matrix, access control strategy, edge cases, algorithms
- **From schema.mmd:** Entity relationships -- derive models, foreign keys, table structure

### Step 2: Read Convention Files

**Before writing any code, read the mode's backend convention files** (AGENTS.md and related docs).

Key requirements vary by project but typically include:
- TDD: tests before implementation
- Domain structure: standard files per domain
- Access control pattern (RLS, RBAC, etc.)
- Error handling convention (e.g., ValueError to HTTP error mapping)
- Migration naming convention
- Auth service package reuse for auth/payments/identity scope (no local replacement layer)

### Performance-Critical Requirement (When Mode Defines a Performance Envelope)

If the active mode defines latency/throughput/backpressure targets, they are mandatory scaffold requirements:
- Add saturation tests for bounded queues and slow-consumer behavior.
- Add replay truncation and bounded-buffer behavior tests.
- Reject blocking operations in async/stream hot paths.
- Add observable counters/metrics required by the mode (queue depth, drops, p95/p99 if required).

### Step 3: Generate Service Tests (FIRST)

Create the service test file at the mode's `test_structure.service_tests` path.

**See [references/test-templates.md](~/.claude/skills/domain-scaffolder-backend/references/test-templates.md) for full patterns.**

Test coverage requirements:
- [ ] Happy path for each service method
- [ ] Error cases (not found, validation, permission)
- [ ] Edge cases from backend.md

Pattern shape (adapt imports and base classes to the mode's framework):

```python
# tests/domains/{slice}/test_service.py
from {backend_module}.{slice}.service import {Slice}Service
from {backend_module}.{slice}.schemas import {Schema}Create

class Test{Slice}Service:
    """Tests for {slice} service layer."""

    # fixture: service instance with test session

    async def test_create_{item}_success(self, service, sample_data):
        result = await service.create_{item}(sample_data)
        assert result.id is not None

    async def test_create_{item}_validation_error(self, service):
        with pytest.raises(ValueError, match="INVALID_DATA"):
            await service.create_{item}(invalid_data)

    async def test_get_{item}_not_found(self, service):
        with pytest.raises(ValueError, match="{SLICE}_NOT_FOUND"):
            await service.get_{item}(nonexistent_id)
```

### Step 4: Generate Route Tests (FIRST)

Create the route test file at the mode's `test_structure.route_tests` path.

Test coverage requirements:
- [ ] Each endpoint from shared.md
- [ ] Success responses (200, 201, 204)
- [ ] Error responses (400, 403, 404, 409)
- [ ] Auth failures (401)

Pattern shape:

```python
# tests/api/domains/{slice}/test_routes.py

class Test{Slice}Routes:
    """API route tests for {slice} domain."""

    async def test_list_{items}_success(self, client, auth_headers, seed_data):
        response = await client.get("/v1/{slice}", headers=auth_headers)
        assert response.status_code == 200

    async def test_create_{item}_success(self, client, auth_headers):
        response = await client.post("/v1/{slice}", json={...}, headers=auth_headers)
        assert response.status_code == 201

    async def test_create_{item}_unauthorized(self, client):
        response = await client.post("/v1/{slice}", json={})
        assert response.status_code == 401
```

### Step 5: Generate Models

Create the models file at the mode's `domain_structure.models` path.

Derive columns from shared.md response shapes and schema.mmd entities. Add indexes derived from query patterns. Use the mode's ORM and base class conventions.

### Step 6: Generate Schemas

Create the schemas file at the mode's `domain_structure.schemas` path.

Define Base, Create, Update, and Response schema variants. Fields must match shared.md exactly. Use the mode's schema/serialization library conventions.

### Step 7: Generate Repository

Create the repository file at the mode's `domain_structure.repository` path.

Implement data access functions: get by ID, list with filters, create, update, delete. Use the mode's ORM query patterns. Apply filters from backend.md.

### Step 8: Generate Service

Create the service file at the mode's `domain_structure.service` path.

Implement business logic: validation rules from backend.md, permission checks, error raising with codes matching shared.md. The service calls the repository and returns schema responses.
For auth/payments/identity behavior, call existing auth service packages rather than introducing parallel local implementations.

### Step 9: Generate Router

Create the router file at the mode's `domain_structure.router` path.

Map endpoints from shared.md to handler functions. Include error code to HTTP status mapping. Wire authentication and dependency injection per the mode's framework conventions.
When auth/payments/identity integration is required, route handlers must delegate to auth-service-backed packages.

Error code mapping pattern (from shared.md):

| Error Code Pattern | HTTP Status | When |
|--------------------|-------------|------|
| `*_NOT_FOUND` | 404 | Resource does not exist |
| `*_ALREADY_EXISTS` | 409 | Unique constraint violation |
| `*_NO_ACCESS` | 403 | Permission denied |
| `*_INVALID_*` | 400 | Validation error |
| `*_HAS_DEPENDENTS` | 400 | Cannot delete with children |

### Step 10: Generate Migration

Use the mode's migration tool and naming convention:

```bash
cd {backend_repo}
{migration_tool_command} {slice} "create_tables"
```

Fill in:
- Table creation (columns from shared.md + schema.mmd)
- Indexes (from query patterns in shared.md endpoints)
- Access control policies per backend.md permissions matrix
- If `backend.md` includes a production DB transition section, ensure migration SQL is transactional/idempotent with explicit verification and rollback steps.

### Step 11: Run Tests

```bash
cd {backend_repo}
{test_command} tests/domains/{slice}/ -v
{test_command} tests/api/domains/{slice}/ -v
```

All tests should pass before considering implementation complete.

### Step 12: Register Router

Register the new domain's router with the application using the mode's router registration convention.

## File Output Structure

```
{backend_repo}/
+-- tests/
|   +-- domains/{slice}/
|   |   +-- test_service.py        <- Written FIRST
|   |   +-- conftest.py            <- Fixtures
|   +-- api/domains/{slice}/
|       +-- test_routes.py         <- Written FIRST
+-- {domain_path}/{slice}/
|   +-- models.py
|   +-- schemas.py
|   +-- repository.py
|   +-- service.py
|   +-- router.py
+-- {migration_path}/
    +-- {migration_naming}
```

Exact paths come from the mode's `domain_structure`, `test_structure`, and `migration_path` settings.

## Validation Checklist

Before marking complete:

- [ ] Tests written FIRST (service + routes)
- [ ] All tests pass
- [ ] Domain has standard files (models, schemas, repo, service, router)
- [ ] Migration uses correct access control syntax per mode
- [ ] Error codes match shared.md
- [ ] Auth/payments/identity behavior uses existing auth service packages
- [ ] Missing auth service capability is documented as an auth-scope proposal (if encountered)
- [ ] Local symlink/link package usage is replaced by published/live auth service package validation before final completion (if applicable)
- [ ] Target-state big-bang contract implemented (no unrequested legacy compatibility code)
- [ ] If production data is impacted, DB transition requirements from backend.md are reflected in migration artifacts
- [ ] Router registered with the application

## Next Step: Request Audit

After backend implementation is complete, tell the user:

> "Backend scaffolding complete for `{slice}`. Next step: use the domain-reviewer skill to audit implementation against the plan."

If frontend also exists in the plan, scaffold that first before auditing:

> "Backend done. The plan includes frontend.md -- use the domain-scaffolder-frontend skill next, then audit both together."

## Related Skills

- **domain-planner** -- Creates the plan this skill implements
- **domain-scaffolder-frontend** -- Frontend implementation
- **domain-reviewer** -- Audits implementation against plan
