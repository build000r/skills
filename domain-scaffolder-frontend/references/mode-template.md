# {Project Name} Frontend Mode

## Detection
cwd_match: ~/repos/{frontend-repo}

## Frontend Framework
framework: {e.g., "React + Vite", "Preact + Vite", "Next.js"}
language: {e.g., "TypeScript 5.x"}

## Component Library
library: {e.g., "Custom primitives", "ShadCN UI", "Material UI"}
patterns_reference: {path to patterns file, skill name, or "See Key Component Primitives below"}

## Key Component Primitives
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

## Data Fetching
pattern: {e.g., "Push-first via WebSocket events", "React Query v5", "SWR"}
query_key_convention: {e.g., "Centralized factory per feature"}

## State Management
server_state: {e.g., "event-driven store", "@tanstack/react-query v5"}
client_state: {e.g., "zustand", "React Context only"}
ui_preferences: {e.g., "typed storage helper", "useLocalStorageState"}
forms: {e.g., "react-hook-form + zod", "native useState"}

## HTTP Client
client: {e.g., "fetch wrapper", "apiRequest()", "axios"}
auth_injection: {e.g., "TokenManager", "N/A"}
error_class: {e.g., "HttpError", "DomainError"}

## Auth Pattern
hook: {e.g., "useAuth()", "N/A"}
roles: {e.g., "'admin' | 'user'", "N/A"}
protected_routes: {e.g., "ProtectedRoute", "N/A"}
feature_gating: {e.g., "isFeatureEnabled", "N/A"}

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

## Routing
library: {e.g., "react-router-dom", "wouter", "Next.js router"}
config_location: {e.g., "src/routes/AppRoutes.tsx"}
conventions: {route conventions}

## File Structure
features_path: {e.g., "src/features/{slice}/"}
types_path: {e.g., "src/types/"}
services_path: {e.g., "src/services/"}
hooks_path: {e.g., "src/hooks/"}
components_path: {e.g., "src/components/"}
pages_path: {e.g., "src/features/{slice}/pages/"}
state_path: {e.g., "src/features/{slice}/state/"}
api_path: {e.g., "src/lib/api/"}
contexts_path: {e.g., "src/contexts/"}

## Styling
approach: {e.g., "Tailwind", "CSS Modules", "vanilla CSS"}
class_utility: {e.g., "cn()"}
design_system: {design language summary}

## Performance Constraints (Optional, Required for Performance-Critical Products)

- Live state updates are push-first (avoid polling loops on healthy realtime paths)
- Render strategy for high-cardinality views (Canvas/virtualization/off-main-thread where needed)
- Input/resize event throttling/debouncing policy
- Rerender containment policy for streaming/high-frequency updates
- Explicit latency/throughput UX targets (frame-time, interaction delay)

If this section is present, reviewers should treat violations as High severity.

## Design Tokens
colors: {token summary}
fonts: {token summary}
animations: {token summary}

## Icons
library: {icon package}

## Component Size Limits
preferred_max: {number} LOC
absolute_max: {number} LOC

## Testing
framework: {e.g., "vitest + testing-library", "playwright"}
test_command: {command}
test_locations: {paths}

## Validation Commands
type_check: {command}
build: {command}
lint: {command}
test: {command or "N/A"}

## Import Aliases
aliases: {e.g., "@/ -> src/"}

## Plan Root
plan_root: {path}

## Backend Repo
backend_repo: {path or "N/A"}

## Key Dependencies
{critical packages and versions}
