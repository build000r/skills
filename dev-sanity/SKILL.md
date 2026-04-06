---
name: dev-sanity
description: Run a mode-driven local development health check across repos, env files, containers, and health endpoints. Use for "dev sanity", "what's broken locally", "check my local stack", "startup checks", "service status", or "why won't this local environment boot".
---

# Dev Sanity

Check whether a local development environment is wired correctly before you
start deeper debugging.

This skill is for **local environment health**, not production operations.

## Default Marker

Start with a stable first progress update such as:

`Using dev-sanity to run the configured local checks and surface the first real failure.`

## Client Overlay

Config lives in the skillbox client overlay under a `dev_sanity` section:

```yaml
# skillbox-config/clients/{client}/overlay.yaml
dev_sanity:
  repos:
    - label: api
      path: ~/repos/api
    - label: frontend
      path: ~/repos/frontend
  env_files:
    - label: api env
      path: ~/repos/api/.env
    - label: frontend env
      path: ~/repos/frontend/.env.local
  containers:
    - label: api container
      name: local-api-1
    - label: postgres
      name: local-postgres-1
  health_urls:
    - label: api
      url: http://localhost:8000/health
    - label: frontend
      url: http://localhost:3000
```

If no overlay matches the current cwd, delegate to skill-issue to create one:

```bash
python3 ~/.claude/skills/skill-issue/scripts/manage_overlays.py create --client-id {CLIENT_ID} --cwd "$PWD" --json
```

Then add the `dev_sanity` section and re-run. Do not guess repo roots or fall
back to generic checks.

## On Trigger

Run the bundled script immediately:

```bash
bash scripts/sanity_check.sh
```

For narrower requests, use focused flags:

```bash
bash scripts/sanity_check.sh --repos-only
bash scripts/sanity_check.sh --env-only
bash scripts/sanity_check.sh --docker-only
bash scripts/sanity_check.sh --health-only
```

To override overlay resolution with a specific context file:

```bash
bash scripts/sanity_check.sh --config /abs/path/to/context.yaml
```

Any check group may be omitted from the client overlay when it does not apply to
the current stack.

## What To Report

Summarize only:

- what passed
- what failed
- the first likely root cause
- the next exact command to run

Do not bury the first failure under a full wall of green checks.

## Fixing Failures

### Missing repo

- confirm the path in the client overlay
- clone or restore the repo before continuing

### Missing env file

- regenerate it from the environment manager or repo bootstrap flow
- if the env file is intentionally optional, remove it from the overlay

### Missing container

- start the relevant local stack
- if the service is no longer containerized, remove it from the overlay
- if Docker itself is unavailable, install or start Docker before debugging the
  app layer

### Failing health endpoint

- inspect the app logs for that service
- verify the configured local port matches the service that is actually running
- check env wiring before assuming the app code is broken
- if `curl` is missing, install it or use an equivalent HTTP probe command

### iOS device build fails (signing / provisioning errors)

This is a project wiring problem, not a code problem. Read
`references/ios-device-build.md` for the complete checklist. Short version:

1. Add `CODE_SIGN_STYLE: Automatic` + `DEVELOPMENT_TEAM: <team-id>` to `project.yml`
2. Regenerate: `xcodegen generate`
3. Build with `-allowProvisioningUpdates` and `generic/platform=iOS`

Reference implementation: `~/repos/dream/Makefile` (`ios-phone-build` target).

## Validation

Before shipping changes to this skill:

```bash
SKILLS_ROOT="/path/to/skills/root"
python3 "$SKILLS_ROOT/skill-issue/scripts/quick_validate.py" "$SKILLS_ROOT/dev-sanity"
bash "$SKILLS_ROOT/dev-sanity/scripts/sanity_check.sh" >/tmp/dev-sanity.out 2>/tmp/dev-sanity.err || true
head -n 2 /tmp/dev-sanity.out /tmp/dev-sanity.err
```

The helper should fail cleanly with a missing-config message when no overlay
matches and should return non-zero when a configured check fails.
