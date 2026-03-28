# {Project Name} Domain Scaffolder Mode

## Detection
cwd_match: ~/repos/{repo}
surface: backend | frontend | both

## Plan Root
plan_root: {path}
plan_index: {path or "N/A"}

## Auth Service Integration (Optional)

The shared auth/payments/identity service is the canonical auth layer.

```text
auth_packages_root: ../{auth-service}/packages
auth_python_packages: [<required package names>]
auth_npm_packages: [<required package names>]
```

Rules:

- Reuse existing auth service packages first
- Do not scaffold parallel local auth/payments/identity systems
- If a capability is missing, raise an auth-scope proposal
- If temporary local link/symlink loading is needed, validate against published/live packages before closeout

## Backend Surface (Fill When `surface: backend` or `both`)

### Backend Framework
framework: {e.g., "FastAPI + SQLAlchemy"}
language: {e.g., "Python 3.12"}
test_framework: {e.g., "pytest with async support"}

### File Structure Convention
backend_repo: {path}
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

### Convention Files
- `{backend-repo}/AGENTS.md`
- `{backend-repo}/tests/AGENTS.md` (if present)

### Migration
migration_path: {path}
migration_naming: {pattern}
migration_tool: {tool}
migration_tool_command: {command}

### Access Control Pattern
{describe RLS, RBAC, capability checks, or equivalent}

### Error Handling
{describe error typing + mapping convention}

### Router Registration
{how to register new routes}

### Backend Validation
test_command: {command}

## Frontend Surface (Fill When `surface: frontend` or `both`)

### Frontend Framework
framework: {e.g., "React + Vite"}
language: {e.g., "TypeScript 5.x"}

### Component Library
library: {e.g., "Custom primitives"}
patterns_reference: {path to patterns file or skill name}

### Data Fetching
pattern: {e.g., "React Query v5"}
query_key_convention: {e.g., "Centralized factory per feature"}

### HTTP Client
client: {e.g., "apiRequest()"}
auth_injection: {e.g., "TokenManager"}
error_class: {e.g., "HttpError"}

### Routing
library: {e.g., "react-router-dom"}
config_location: {path}

### File Structure
frontend_repo: {path}
features_path: {path}
types_path: {path}
services_path: {path}
hooks_path: {path}
components_path: {path}
pages_path: {path}
state_path: {path}
api_path: {path}
contexts_path: {path}

### Styling
approach: {e.g., "Tailwind"}
design_system: {summary}

### Component Size Limits
preferred_max: {number}
absolute_max: {number}

### Validation Commands
type_check: {command}
build: {command}
lint: {command}
test: {command or "N/A"}

## Performance Constraints (Optional)

- Hot-path blocking policy
- Queue/channel bounds policy
- Buffer/memory bounds policy
- Render-path constraints
- Required latency/concurrency checks

If present, treat violations as high severity.
