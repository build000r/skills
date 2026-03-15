# Probe Ladder

Use this ladder before asking the user to manually test and before opening DevTools.

## Baseline Service Checks

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -sS -i http://localhost:<port>/health
```

If the service is down or unhealthy, fix that first; no UI testing will be reliable.

## Symptom to Probe Mapping

`API route seems broken`

```bash
rg -n '<route-or-handler-name>' .
curl -sS -i -X <METHOD> "http://localhost:<port>/<path>" -H 'content-type: application/json' -d '<json>'
```

`Background job did not run`

```bash
docker logs <worker-container> --since 10m 2>&1 | rg -i 'error|exception|failed|traceback|<job-name>'
docker logs <api-container> --since 10m 2>&1 | rg -i '<trigger-event>'
```

`Database state seems wrong`

```bash
docker exec <db-container> psql -U <user> -d <db> -c "<SELECT/COUNT query>"
```

`Email/notification was not delivered`

```bash
docker logs <worker-or-api-container> --since 30m 2>&1 | rg -i 'mail|email|smtp|send|notification|error'
gog gmail search 'newer_than:1d subject:(<subject-fragment>)' --max 10
```

`Frontend action appears broken`

```bash
rg -n '<action text|hook|api client name>' .
curl -sS -i "http://localhost:<api-port>/<underlying-endpoint>"
docker logs <api-container> --since 10m 2>&1 | rg -i '<endpoint|request id|error>'
```

If API and logs are correct, then consider headless E2E (Playwright/Cypress CLI) before DevTools.

## Strong Evidence Pattern

Report both:
1. Behavior assertion: response status/body or test output.
2. Side-effect assertion: log line, DB row, emitted event, queued job, or received email artifact.

This prevents false positives from single-surface checks.

## Local Seed/Restart Hardening

If local validation required manual seed/restart/env commands, move those steps into `.env-manager` automation so future repro is shorter.

Example closeout loop:

```bash
if [ -d ./.env-manager ]; then
  ENVM="$(cd ./.env-manager && pwd)"
elif [ -d ../.env-manager ]; then
  ENVM="$(cd ../.env-manager && pwd)"
elif [ -d ../../.env-manager ]; then
  ENVM="$(cd ../../.env-manager && pwd)"
fi
REPOS_ROOT="${REPOS_ROOT:-$(cd "$ENVM/.." && pwd)}"
SANITY="$(ls ~/.codex/skills/dev-sanity/scripts/sanity_check.sh ~/.claude/skills/dev-sanity/scripts/sanity_check.sh "$REPOS_ROOT/opensource/skills/dev-sanity/scripts/sanity_check.sh" 2>/dev/null | head -1)"
cd "$ENVM" && make project status
bash "$SANITY" --errors-only
bash "$SANITY" --health-only
bash "$SANITY" --wiring-only
```

When appropriate, update `.env-manager/Makefile` to expose deterministic targets for:
1. Seeding data needed to reproduce/fix the bug.
2. Correct restart ordering for dependent services.
3. One-command local recovery for the same failure class.
