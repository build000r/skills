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
