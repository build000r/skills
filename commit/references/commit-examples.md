# Commit Message Examples

Conventional commit examples with bodies and footers, organized by type.

## Feature

```
feat(auth): add Google OAuth login flow

Users can now sign in with their Google accounts. This adds:
- OAuth callback handler
- Token refresh logic
- User profile sync

Closes #142
```

## Feature with Breaking Change

```
feat(api)!: require authentication for all endpoints

BREAKING CHANGE: All API endpoints now require Bearer token auth.

Previously, read-only endpoints were public. This change improves
security but requires all clients to authenticate.

Migration:
1. Generate API key in dashboard
2. Add Authorization header to requests
3. Handle 401 responses

Refs #301
```

## Bug Fix with Root Cause

```
fix(webhooks): prevent duplicate deliveries on worker restart

Webhook deliveries were duplicated when the worker process
restarted during message processing.

Root cause: Queue acknowledgment happened after HTTP call,
so unfinished deliveries were re-queued on restart.

Fix: Generate idempotency key from delivery ID. Receivers
can deduplicate using X-Delivery-Id header.

Fixes #287
```

## Performance

```
perf(api): cache user profile lookups

Added Redis cache for user profiles with 5-minute TTL.

Before: p50=45ms, p99=230ms
After:  p50=3ms,  p99=48ms (cache hit)

Refs #333
```

## Refactor

```
refactor(db): extract query builder from repository classes

Moved SQL generation into dedicated QueryBuilder class to:
- Reduce duplication across repositories
- Enable query composition
- Simplify testing with mock builder

No behavior changes. All existing tests pass.
```

## Test

```
test(auth): add edge cases for token validation

New test cases:
- Expired token (should return 401)
- Malformed JWT (should return 400)
- Valid token with revoked user (should return 403)
- Token without required scopes (should return 403)

Coverage: 89% -> 94%
```

## Chore

```
chore(deps): update react to 19.0.0

- Updated react and react-dom to 19.0.0
- Fixed deprecated lifecycle warnings
- Updated test snapshots

No breaking changes in application.
```

## CI/Build

```
ci(github): add automated release workflow

New workflow triggers on version tags (v*) and:
- Runs full test suite
- Builds production artifacts
- Creates GitHub release with changelog
- Publishes to npm registry
```

```
build(docker): reduce image size from 1.2GB to 340MB

Changes:
- Multi-stage build (builder + runtime)
- Alpine base instead of Ubuntu
- Only copy production dependencies
- Remove dev files from final image
```
