# Troubleshooting

Use this after mode load and basic preflight.
Use only the surfaces your stack actually has. If deploys are not GitHub-driven,
skip the `gh` commands. If the project does not publish a package, skip the
package checks.

## Fast Read-Only Triage

```bash
gh run list -R "$MODE_REPO_SLUG_API" --limit 5
curl -fsS "$MODE_HEALTH_URL_API"
ssh "$MODE_DROPLET_SSH" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE_API' --tail 120"
ssh "$MODE_DROPLET_SSH" "df -h"
```

## Deploy Failed

Symptoms:
- workflow red
- compose update failed
- health check never recovered

Debug:

```bash
gh run view -R "$MODE_REPO_SLUG_API" <run-id> --log-failed
ssh "$MODE_DROPLET_SSH" \
  "cd '$MODE_DEPLOY_ROOT_API' && docker compose -p '$MODE_COMPOSE_PROJECT_API' ps"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE_API' --tail 200"
```

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
curl -v "$MODE_HEALTH_URL_API"
ssh "$MODE_DROPLET_SSH" "curl -fsS '$MODE_HEALTH_URL_API'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE_API' --tail 200 | tail -n 80"
```

If the server-local curl works but the public URL fails, inspect proxy, CDN, or firewall layers next.

## Container Restarts Or Crash Loops

Debug:

```bash
ssh "$MODE_DROPLET_SSH" "docker inspect '$MODE_COMPOSE_SERVICE_API' --format '{{.State.Status}} {{.State.ExitCode}}'"
ssh "$MODE_DROPLET_SSH" "docker logs '$MODE_COMPOSE_SERVICE_API' --tail 200"
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
curl -I "$MODE_HEALTH_URL_FRONTEND"
```

Then inspect the frontend deploy surface defined in the project runbook or local mode notes.

## Browser Login Or API Calls Denied

First split:
- preflight denied: browser origin, method, or header allowlist drift
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
- Preflight passes, then `401`: clear or refresh the browser session, compare
  cookies/headers, and retry the authenticated route.
- Preflight passes, then `403`: inspect route guards and the subject's
  app/company/project access. This is not a CORS failure.
- Header missing from `access-control-allow-headers`: add the exact browser-sent
  header to the deployed CORS config and rerun the preflight.

## Package Release Problems

Checks:

```bash
git -C "$MODE_REPO_ROOT_API" describe --tags --always
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
ssh "$MODE_DROPLET_SSH" "ls -lah '$MODE_BACKUP_ROOT' | tail -n 20"
```

If storage pressure is the root cause, stop deploy work until cleanup or capacity planning is explicit.

## When To Escalate

Ask before proceeding when the next step would:
- restart production
- run migrations
- mutate production data
- roll back to a previous release
- change proxy or DNS configuration
