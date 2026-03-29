# {Project Name} Domain Scaffolder Mode

Use this canonical template for domain-scaffolder repos. Prefer repo-local
template names such as `domain-scaffolder.md`,
`domain-scaffolder.backend.md`, or `domain-scaffolder.frontend.md`.

Fill only the sections relevant to the selected `surface`. Leave optional fields
or sections out when the repo genuinely does not need them.

## Detection
cwd_match: ~/repos/{repo}
surface: backend | frontend | both

## Plan Root
plan_root: {path}
plan_index: {path or "N/A"}

## Auth Service Integration (Optional)

Preferred generic keys:

```text
auth_packages_root: ../{auth-service}/packages
auth_python_packages: [<required package names>]
auth_npm_packages: [<required package names>]
```

Legacy compatibility aliases are still accepted in existing modes when the auth
layer is SPAPS-shaped:

```text
spaps_root: ../sweet-potato/packages
spaps_python_packages: [<required package names>]
spaps_npm_packages: [<required package names>]
```

Rules:

- Reuse existing auth service packages first
- Do not scaffold parallel local auth/payments/identity systems
- If a capability is missing, raise an auth-scope proposal
- If temporary local link/symlink loading is needed, validate against published/live packages before closeout

## Backend Surface (Fill When `surface: backend` or `both`)

### Backend Framework
framework: {e.g., "Rust Axum + Tokio", "FastAPI + SQLAlchemy"}
language: {e.g., "Rust 1.85", "Python 3.12"}
test_framework: {e.g., "cargo test", "pytest with async support"}

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
Read before writing any code:

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

### Backend Reference Snippets (Optional)
Use these when the repo has opinionated inline examples that the scaffolder
should mirror instead of inventing from scratch.

#### Model Base Classes
{optional inline example or path}

#### Schema Base Classes
{optional inline example or path}

#### Auth Dependencies
{optional inline example or path}

#### Test Templates
{optional repo-specific path or "use canonical references/test-templates.md"}

## Frontend Surface (Fill When `surface: frontend` or `both`)

### Frontend Framework
framework: {e.g., "React + Vite", "Preact + Vite", "Next.js"}
language: {e.g., "TypeScript 5.x"}

### Component Library
library: {e.g., "Custom primitives", "ShadCN UI", "Material UI"}
patterns_reference: {path to patterns file, skill name, or "See Key Component Primitives below"}

If a repo does not already have a strong project-specific patterns reference,
start from the canonical `references/example-patterns.md` and tailor it.

### Key Component Primitives
- Panel/Card: {name and import path}
- Button: {name and import path}
- Loading state: {name and import path}
- Error state: {name and import path}
- Empty state: {name and import path}
- Locked/gated state: {name or "N/A"}
- Toolbar/Header: {name or "N/A"}
- Widget shell/wrapper: {name or "N/A"}
- Fullscreen overlay: {name or "N/A"}
- Status badge: {name or "N/A"}
- Filter chips: {name or "N/A"}
- Section heading: {name or "N/A"}
- Callout/notice: {name or "N/A"}

### Data Fetching
pattern: {e.g., "Push-first via WebSocket events", "React Query v5", "SWR"}
query_key_convention: {e.g., "Centralized factory per feature"}

### State Management
server_state: {e.g., "event-driven store", "@tanstack/react-query v5"}
client_state: {e.g., "zustand", "React Context only"}
ui_preferences: {e.g., "typed storage helper", "useLocalStorageState"}
forms: {e.g., "react-hook-form + zod", "native useState"}

### HTTP Client
client: {e.g., "fetch wrapper", "apiRequest()", "axios"}
auth_injection: {e.g., "TokenManager", "N/A"}
error_class: {e.g., "HttpError", "DomainError"}

### Auth Pattern
hook: {e.g., "useAuth()", "N/A"}
roles: {e.g., "'admin' | 'user'", "N/A"}
protected_routes: {e.g., "ProtectedRoute", "N/A"}
feature_gating: {e.g., "isFeatureEnabled", "N/A"}

### Routing
library: {e.g., "react-router-dom", "wouter", "Next.js router"}
config_location: {e.g., "src/routes/AppRoutes.tsx"}
conventions: {route conventions}

### File Structure
frontend_repo: {path}
features_path: {e.g., "src/features/{slice}/"}
types_path: {e.g., "src/types/"}
services_path: {e.g., "src/services/"}
hooks_path: {e.g., "src/hooks/"}
components_path: {e.g., "src/components/"}
pages_path: {e.g., "src/features/{slice}/pages/"}
state_path: {e.g., "src/features/{slice}/state/"}
api_path: {e.g., "src/lib/api/"}
contexts_path: {e.g., "src/contexts/"}
routes_path: {e.g., "src/routes/", or "N/A"}
lib_path: {e.g., "src/lib/", or "N/A"}
styles_path: {e.g., "src/styles/", or "N/A"}

### Styling
approach: {e.g., "Tailwind", "CSS Modules", "vanilla CSS"}
class_utility: {e.g., "cn()", "clsx()", or "N/A"}
design_system: {design language summary}

### Design Tokens
colors: {token summary}
fonts: {token summary}
animations: {token summary}

### Icons
library: {icon package}

### Component Size Limits
preferred_max: {number} LOC
absolute_max: {number} LOC

### Testing
framework: {e.g., "vitest + testing-library", "playwright"}
test_command: {command}
test_watch: {command or "N/A"}
test_e2e: {command or "N/A"}
test_growth: {command or "N/A"}
test_all: {command or "N/A"}
test_locations: {paths}

### Validation Commands
type_check: {command}
build: {command}
lint: {command}
test: {command or "N/A"}
dev: {command or "N/A"}

### Import Aliases
aliases: {e.g., "@/ -> src/"}

## Backend Repo (Optional for Frontend Modes)
backend_repo: {path or "N/A"}

## Key Dependencies (Optional)
{critical packages and versions}

## Performance Constraints (Optional)

- Hot-path blocking policy (e.g., no sync process/file/network calls)
- Queue/channel bounds policy (no unbounded queues)
- Buffer/memory bounds policy
- Backpressure policy and expected behavior under slow consumers
- Live state updates are push-first (avoid polling loops on healthy realtime paths)
- Render strategy for high-cardinality views (Canvas/virtualization/off-main-thread where needed)
- Render-path constraints
- Input/resize event throttling/debouncing policy
- Rerender containment policy for streaming/high-frequency updates
- Explicit latency/throughput UX targets (frame-time, interaction delay)
- Required latency/concurrency tests and benchmarks

If present, treat violations as high severity.
