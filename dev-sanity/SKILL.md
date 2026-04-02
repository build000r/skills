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

This skill reads project-specific config from `context.yaml`, auto-generated
from the client overlay at `skillbox-config/clients/{client}/overlay.yaml`.

The overlay defines one or more of these arrays:

- repo paths to verify
- env files that must exist
- docker container names
- local health endpoints

If no overlay is available, stop and point the operator at the skillbox client
overlay setup. Do not guess repo roots.

## On Trigger

Resolve the bundled script path, then run it immediately:

```bash
bash scripts/sanity_check.sh
```

For narrower requests, use the focused modes first:

```bash
bash scripts/sanity_check.sh --config /abs/path/to/context.yaml
bash scripts/sanity_check.sh --repos-only
bash scripts/sanity_check.sh --env-only
bash scripts/sanity_check.sh --docker-only
bash scripts/sanity_check.sh --health-only
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

- confirm the path in the client overlay (`context.yaml`)
- clone or restore the repo before continuing

### Missing env file

- regenerate it from the environment manager or repo bootstrap flow
- if the env file is intentionally optional, remove it from the client overlay

### Missing container

- start the relevant local stack
- if the service is no longer containerized, remove it from the client overlay
- if Docker itself is unavailable, install or start Docker before debugging the
  app layer

### Failing health endpoint

- inspect the app logs for that service
- verify the configured local port matches the service that is actually running
- check env wiring before assuming the app code is broken
- if `curl` is missing, install it or use an equivalent HTTP probe command

## Validation

Before shipping changes to this skill:

```bash
SKILLS_ROOT="/path/to/skills/root"
python3 "$SKILLS_ROOT/skill-issue/scripts/quick_validate.py" "$SKILLS_ROOT/dev-sanity"
bash "$SKILLS_ROOT/dev-sanity/scripts/sanity_check.sh" >/tmp/dev-sanity.out 2>/tmp/dev-sanity.err || true
head -n 2 /tmp/dev-sanity.out /tmp/dev-sanity.err
```

The helper should fail cleanly with a missing-mode message when no private mode
exists and should return non-zero when a configured check fails.
