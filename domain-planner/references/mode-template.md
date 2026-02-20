# {Project Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Repositories

| Role | Repo Name | Path | Stack |
|------|-----------|------|-------|
| Backend | {backend-repo} | ~/repos/{backend-repo} | {e.g., Rust Axum + Tokio} |
| Frontend | {frontend-repo} | ~/repos/{frontend-repo} | {e.g., TypeScript Preact + Vite} |
| Auth (if separate) | {auth-repo} | ~/repos/{auth-repo} | {e.g., Node.js Express} |

## Auth Service Integration (Optional)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical auth/payments/identity layer.

```
auth_packages_root: ../{auth-service}/packages
auth_python_packages: [<required package names>]
auth_npm_packages: [<required package names>]
```

Rules for every mode:
- Use existing auth service packages first; do not design duplicate local auth/payments/identity systems.
- If auth service functionality is missing, raise an auth-scope proposal with the gap, proposed package/API, and cross-product benefit.
- If local unpublished auth service versions are needed, temporarily symlink/link from `{auth_packages_root}`, then switch back to published/live versions for final validation.

## Plan Storage

All plans live centrally — even slices for other repos.

```
plan_root: ~/repos/{plan-repo}/path/to/plans
plan_draft: ~/repos/{plan-repo}/path/to/plans/planned
plan_index: ~/repos/{plan-repo}/path/to/INDEX.md
session_plans: ~/repos/{plan-repo}/path/to/session-plans
```

## Convention Files

Read these before planning each layer:

| Layer | File | Purpose |
|-------|------|---------|
| Backend | {backend-repo}/AGENTS.md | Coding conventions, patterns |
| Backend Tests | {backend-repo}/tests/AGENTS.md | Test philosophy, fixtures |
| Frontend | {frontend patterns skill or file path} | Component library, data fetching |

## Backend Context

```
backend_module: {import.path}          # e.g., "crate::backend"
domain_path: {relative path}           # e.g., "src/backend/domains"
test_path: {relative path}             # e.g., "tests/backend"
migration_tool: {tool}                 # e.g., "sqlx", "Alembic", or "Supabase"
migration_path: {relative path}        # e.g., "migrations"
migration_ext: {extension}             # e.g., ".sql.planning"
```

## Frontend Context

```
features_path: {relative path}         # e.g., "web/src/features"
types_path: {relative path}            # e.g., "web/src/types"
services_path: {relative path}         # e.g., "web/src/services"
api_only: false                        # Set true to skip frontend phase
```

## Performance Envelope (Optional, Required for Performance-Critical Products)

Use this section when low latency/high throughput is a core requirement.

- p95/p99 latency targets (with units and load assumptions)
- Throughput/concurrency targets
- Backpressure and queue bounds requirements
- Memory growth bounds (buffer limits, cache ceilings)
- Explicit anti-pattern bans (e.g., blocking calls in async hot paths, polling loops)

If present, these become required acceptance criteria and audit checks.

## Phase-Specific Notes

### Phase 3 (Backend)

- {Access control pattern, e.g., "RLS uses current_setting('app.user_id', true)"}
- {Error handling pattern, e.g., "Typed service errors map to HTTP statuses"}
- {Migration convention, e.g., "sqlx migration naming: {timestamp}_{domain}_{slug}.sql"}
- {Hot-path/runtime constraints if applicable}

### Phase 4 (Frontend)

- {Component library, e.g., "Uses shared panel/button primitives"}
- {Data fetching, e.g., "Push-first events + fallback query hooks"}
- {Component limits, e.g., "<300 LOC preferred, <400 LOC max"}
- {Rendering/perf constraints if applicable}

## Cross-Product Notes

{If slices can span multiple products, describe how to detect and handle that here.}
