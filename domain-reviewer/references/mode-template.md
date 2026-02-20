# {Project Name} Reviewer Mode

## Detection

```
cwd_match: ~/repos/{any-project-repo}
```

## Plan Storage

```
plan_root: ~/repos/{plan-repo}/path/to/plans/released
plan_index: ~/repos/{plan-repo}/path/to/INDEX.md
session_plan_index: ~/repos/{plan-repo}/path/to/SESSION_INDEX.md
```

## Implementation Locations

| Layer | Path Pattern | Standards |
|-------|-------------|-----------|
| Backend | {backend-repo}/{domain_path}/{slice}/ | {backend-repo}/AGENTS.md |
| Frontend | {frontend-repo}/{features_path}/{slice}/ | {frontend patterns reference} |
| Backend Tests | {backend-repo}/{test_path}/{slice}/ | Coverage requirements |

## Auth Service Integration (Optional)

If your project uses a shared auth/payments/identity service, configure it here.

```
auth_packages_root: ../{auth-service}/packages
auth_python_packages: [<required package names>]
auth_npm_packages: [<required package names>]
```

Reviewer checks must enforce:
- Existing auth service package reuse for auth/payments/identity scope
- Auth-scope proposal when capability gaps are discovered
- Local symlink/link usage followed by published/live validation before final compliance

## Compliance Standards

### Backend Patterns to Check

- Domain structure (standard files per domain: models, schemas, repository, service, router)
- TDD compliance (tests exist before or with implementation)
- Access control policies (correct syntax, proper user context)
- Error handling (service errors mapped to HTTP status codes)
- Migration naming and content

### Frontend Patterns to Check

- Component library usage (shared primitives vs inline styling)
- Data fetching patterns (query hooks vs manual state management)
- Storage patterns (shared hooks vs manual storage access)
- Component size limits
- Async state handling (loading, error, empty, success)
- Test coverage

### Performance Patterns to Check (Optional, Required for Performance-Critical Products)

- Latency/throughput targets from plan are measurable and evidenced
- Backpressure behavior is implemented and tested
- Queue/buffer bounds prevent unbounded memory growth
- Hot-path blocking and polling anti-patterns are absent
- Metrics for performance-critical paths are present

## Tag-to-Domain Mapping (for retire-session mode)

Maps session plan tags to domain folders for consolidation.

| Tag | Domain Folder | Notes |
|-----|--------------|-------|
| [auth] | auth | Authentication and authorization |
| [comms] | messaging | Communication features |
| [ui] | (misc) | UI-only, no backend domain |
| [data] | (misc) | Data/indexing, often standalone |
| [infra] | (misc) | Infrastructure, CI/CD |
| [research] | (misc) | Research tasks, always standalone |
| [misc] | misc-session-work | Catch-all for untagged work |

Tags mapping to `(misc)` go to the `misc-session-work` collector domain.

For plans with multiple tags, use the first domain-specific tag (ignore repo-level tags).

## Commit Conventions

```
audit_commit: "audit({slice}): {verdict} - score {XX}/100"
retire_commit: "retire({slice}): {X}V {Y}->"
session_retire_commit: "retire-session: consolidate {N} plans into {domains}"
```
