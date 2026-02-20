# {Project Name} Backend Mode

## Detection
cwd_match: ~/repos/{backend-repo}

## Backend Framework
framework: {e.g., "Rust Axum + Tokio", "FastAPI + SQLAlchemy"}
language: {e.g., "Rust 1.85", "Python 3.12"}
test_framework: {e.g., "cargo test", "pytest with async support"}

## File Structure Convention
backend_module: {import.path}
domain_structure:
  - models: domains/{slice}/models.ext
  - schemas: domains/{slice}/schemas.ext
  - repository: domains/{slice}/repository.ext
  - service: domains/{slice}/service.ext
  - router: domains/{slice}/router.ext
test_structure:
  - service_tests: tests/domains/{slice}/test_service.ext
  - route_tests: tests/api/domains/{slice}/test_routes.ext
  - conftest: tests/domains/{slice}/conftest.ext

## Convention Files
Read before writing any code:
- `{backend-repo}/AGENTS.md`
- `{backend-repo}/tests/AGENTS.md` (if present)

## Migration
migration_path: {path}
migration_naming: {pattern}
migration_tool: {tool}

## Access Control Pattern
{describe RLS, RBAC, capability checks, or equivalent}

## Error Handling
{describe error typing + mapping convention}

## Router Registration
{how to register new routes}

## Auth Service Integration (Optional)

The shared auth/payments/identity service (`{auth_packages_root}` from mode config) is the canonical auth/payments/identity layer.

```
auth_packages_root: ../{auth-service}/packages
auth_python_packages: [<required package names>]
auth_npm_packages: [<required package names>]
```

Rules:
- Reuse existing auth service packages first for auth/payments/identity scope.
- If a required capability is missing, document an auth-scope proposal (gap + proposed package/API + expected benefit).
- If local unpublished auth service package changes are needed, use temporary symlink/link loading and then validate on published/live packages before completion.

## Performance Constraints (Optional, Required for Performance-Critical Products)

- Hot-path blocking policy (e.g., no sync process/file/network calls)
- Queue/channel bounds policy (no unbounded queues)
- Buffer/memory bounds policy
- Backpressure policy and expected behavior under slow consumers
- Required latency/concurrency tests and benchmarks

If this section is present, reviewers should treat violations as High or Critical severity.
