---
name: ssh-info
description: Server connection reference and targeted live status checks for containerized environments. Use when asking "ssh info", "server status", "what's running", "container status", "how do I connect", "check production", "which containers", or "show me the health checks" and the answer depends on a skillbox client overlay with host and service details.
---

# SSH Info

Return connection details and targeted status checks for a server or cluster.

This skill is for **operator lookup and focused inspection**. It is not a full
deploy skill and it should not invent a broad diagnostic sweep when the user
asked for one narrow check.

## Default Marker

Start with a stable first progress update such as:

`Using ssh-info to resolve the client overlay, then run only the requested server checks.`

## Use This For

- "ssh info", "how do I connect", "what host is this on"
- "server status", "what containers are running", "check prod"
- one-shot log, health, or container checks
- quick DB access patterns and container topology lookup

## Do Not Use This For

- deployment workflows or rollback execution
- code changes inside the target repo
- full environment bring-up or local-dev bootstrap

Use `deploy` for operational changes and `dev-sanity` for local ecosystem
health checks.

## Client Overlay

This skill requires a skillbox client overlay at
`skillbox-config/clients/{client}/overlay.yaml`, which is auto-generated into
`context.yaml` at install time.

Tracked files stay generic. The client overlay holds:

- SSH host/user details
- container names
- health endpoints
- any environment-specific aliases or labels

See [references/mode-template.md](references/mode-template.md) for the overlay
key reference.

If no client overlay exists, stop with a concise error and point the operator at
the overlay template. Do not guess a host or a production URL.

## Execution Policy

Run only what the user asked for.

1. Resolve the client overlay first.
2. Respect requested scope: connection info, containers, health, logs, DB, or
   full status.
3. If the request is vague, do the smallest useful baseline:
   - show connection target
   - show a short container summary
4. Do not restart services or run destructive DB commands. This skill is
   read-first.

## Common Requests

### Connection Info

Return:

- SSH target
- auth method notes from the client overlay
- relevant repo or deploy root hints, if the overlay defines them

### Container Status

Run the bundled helper:

```bash
bash scripts/status.sh prod
```

This should read the client overlay and either:

- run locally on the server, or
- wrap commands in SSH when `STATUS_REMOTE_SSH` is set

### Local Health URLs

When the user wants the known URLs without a full sweep:

```bash
bash scripts/status.sh local
```

### Full Status Sweep

Use this only when explicitly requested:

```bash
bash scripts/status.sh prod
bash scripts/status.sh local
```

Then summarize:

- which services are up
- which checks failed
- what to inspect next

## Safe Query Patterns

### Container List

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Logs

```bash
docker logs <container> --since 30m 2>&1 | tail -50
```

### DB Query

```bash
docker exec <db-container> psql -U <user> -d <db> -c "SELECT ...;"
```

Prefer `SELECT` queries. Treat write queries as out of scope unless the user
explicitly asks for them.

## Safety

- Production-first caution: default to read-only inspection
- No destructive SQL
- No service restarts
- No deploy or rollback actions
- No guesses when the client overlay is missing or incomplete

## Validation

Before shipping changes to this skill:

```bash
SKILLS_ROOT="/path/to/skills/root"
python3 "$SKILLS_ROOT/skill-issue/scripts/quick_validate.py" "$SKILLS_ROOT/ssh-info"
bash "$SKILLS_ROOT/ssh-info/scripts/status.sh" >/tmp/ssh-info.out 2>/tmp/ssh-info.err || true
head -n 2 /tmp/ssh-info.out /tmp/ssh-info.err
```

The helper should fail cleanly with usage or a missing-overlay message when no
client overlay exists.
