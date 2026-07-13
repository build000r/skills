# Troubleshooting

Use this after mode load and basic preflight. Use only the variables and
surfaces declared by the selected overlay.

## Fast Read-Only Triage

```bash
test -z "${MODE_RELEASE_MANIFEST_DIR:-}" || ls -lt "$MODE_RELEASE_MANIFEST_DIR" | head
curl -fsS "$MODE_HEALTH_URL"
ssh "$MODE_DROPLET_SSH" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE' --tail 120"
ssh "$MODE_DROPLET_SSH" "df -h"
```

## Deploy Failed

Symptoms:
- local release command failed
- release manifest is absent or reports failure
- artifact transport or activation failed
- compose update failed
- health check never recovered

Debug:

```bash
ssh "$MODE_DROPLET_SSH" \
  "cd '$MODE_DEPLOY_ROOT' && docker compose -p '$MODE_COMPOSE_PROJECT' ps"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE' --tail 200"
```

If the manual hosted fallback was the path that failed, inspect that run after
the local release evidence. A red fallback does not make a proven local release
unhealthy, but it does mean recovery parity is degraded.

Common causes:
- missing env key
- bad migration
- image or artifact not found
- port conflict
- disk full

## Health Check Fails

First split:
- timeout: app down, route missing, or network issue
- 5xx: app booted but failing during request handling
- stale success: old version still serving

Useful checks:

```bash
curl -v "$MODE_HEALTH_URL"
ssh "$MODE_DROPLET_SSH" "curl -fsS '$MODE_HEALTH_URL'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE' --tail 200 | tail -n 80"
```

If the server-local curl works but the public URL fails, inspect proxy, CDN, or firewall layers next.

## Container Restarts Or Crash Loops

Debug:

```bash
ssh "$MODE_DROPLET_SSH" "docker inspect '$MODE_COMPOSE_SERVICE' --format '{{.State.Status}} {{.State.ExitCode}}'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE' --tail 200"
```

Likely causes:
- invalid env or missing secret file
- migration mismatch
- bad image tag
- dependency container unavailable

## Frontend Looks Stale

Questions:
- Did the frontend deploy happen?
- Is the frontend served directly, through Pages, or through a worker/proxy?
- Is the API updated while the assets are still old?

Checks:

```bash
curl -I "$MODE_HEALTH_URL"
```

Then inspect the frontend deploy surface defined in the project runbook or local mode notes.

## Browser Login Or API Calls Denied

First split:
- preflight denied: browser origin, method, or header allowlist drift
- login route intercepted by protected middleware: public auth facade route is
  not mounted where the frontend expects
- `401`: missing/stale credential, token refresh, cookie, or header issue
- `403`: authenticated subject lacks the app/company/project access the route expects

Do not use a health check as CORS proof. Probe the actual browser route with
the actual origin, method, and non-simple headers. Replace the header list with
the headers the browser sends, including custom publishable-key or refresh
headers when the stack uses them.

```bash
FRONTEND_ORIGIN="https://www.example.com"
API_ORIGIN="https://api.example.com"

curl -sS -D- -o /dev/null -X OPTIONS "$API_ORIGIN/api/auth/login" \
  -H "Origin: $FRONTEND_ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,authorization,x-api-key"
```

Expected CORS result for credentialed browser calls:
- status is `2xx` or `204`
- `access-control-allow-origin` matches `$FRONTEND_ORIGIN`
- `access-control-allow-credentials: true`
- `access-control-allow-headers` includes every requested non-simple header

Run the same preflight for each canonical frontend origin, first-party alias,
and browser-called API/auth backend. Multi-service apps commonly have more than
one gate: frontend host routing, auth service CORS, app API CORS, app-level
allowed origins, callback URLs, and checkout return URLs.

Interpretation:
- `400` or a body like `Disallowed CORS origin`: diff deployed CORS env/secrets
  against every overlay origin and alias.
- `401` with a body like `Authorization header missing` when posting to
  `/api/auth/login` without credentials: the login path is probably routed to
  protected application middleware instead of the auth facade. Check API router
  order, reverse-proxy rules, and whether the live runtime version matches the
  expected commit. Then rerun the unauthenticated login probe.
- Preflight passes, then `401`: clear or refresh the browser session, compare
  cookies/headers, and retry the authenticated route.
- Preflight passes, then `403`: inspect route guards and the subject's
  app/company/project access. This is not a CORS failure.
- Header missing from `access-control-allow-headers`: add the exact browser-sent
  header to the deployed CORS config and rerun the preflight.

### Auth Facade Regression Probe

Use this when a browser login form reports `401`, or after any deploy that
changes auth, routing, reverse-proxy, frontend env, or API route order.

```bash
AUTH_ORIGIN="https://api.example.com"
LOGIN_PATH="/api/auth/login"

curl -sS -i -X POST "${AUTH_ORIGIN}${LOGIN_PATH}" \
  -H "content-type: application/json" \
  --data '{"email":"__probe_invalid__@example.invalid","password":"__probe_invalid__"}' \
  | sed -n '1,80p'
```

Expected: the auth service returns an invalid-credentials response. Block or
roll back if the response is a generic protected-route failure, proxy auth
challenge, or route-not-found response from the app API.

Also verify runtime state, not just behavior:

```bash
curl -fsS "$MODE_HEALTH_URL"
# Then compare the reported version, container image tag, or deploy metadata
# with the commit/tag intended for this release.
```

If health is green but the version is stale or unknown, treat the release as
not verified.

### Browser Bundle Secret Probe

After a frontend deploy, fetch production assets and fail the release if a
server-only secret pattern appears in JavaScript served to browsers.

```bash
FRONTEND_ORIGIN="https://www.example.com"
html="$(curl -fsS "$FRONTEND_ORIGIN/")"
printf '%s\n' "$html" | rg -o '/assets/[^"]+\.js' | sort -u | while read -r asset; do
  curl -fsS "${FRONTEND_ORIGIN}${asset}" |
    rg -n '(_sec_|secret|private|sk_live|BEGIN [A-Z ]*PRIVATE KEY)' && exit 1
done
```

If this fails after a deploy, rotate the exposed credential before shipping the
next bundle. Replacing the bundle alone is not enough once a secret has been
publicly served.

## Package Release Problems

Checks:

```bash
git -C "$MODE_REPO_ROOT" describe --tags --always
npm view "$MODE_PACKAGE_NAME" version
python -m pip index versions "$MODE_PACKAGE_NAME"
```

Likely causes:
- wrong version bump
- auth token missing
- tag/release mismatch
- package published under unexpected scope or registry

## Disk Or Backup Pressure

Checks:

```bash
ssh "$MODE_DROPLET_SSH" "df -h"
ssh "$MODE_DROPLET_SSH" "df -h '$MODE_STORAGE_ROOT'"
test -z "${MODE_BACKUP_ROOT:-}" || ssh "$MODE_DROPLET_SSH" "ls -lah '$MODE_BACKUP_ROOT' | tail -n 20"
```

If storage pressure is the root cause, stop deploy work until cleanup or capacity planning is explicit.

## When To Escalate

Ask before proceeding when the next step would:
- restart production
- run migrations
- mutate production data
- roll back to a previous release
- change proxy or DNS configuration
