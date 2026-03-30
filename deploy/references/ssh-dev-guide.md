# SSH Dev Guide

Use this when cwd is `<ssh-dev-root>/*` or another server-side dev workspace.

## Mental Model

- dev workspace paths are editable
- deployed prod roots are managed artifacts
- prod reads are cheaper than prod writes
- destructive ops still require explicit approval

## Safe Defaults

- read logs first
- prefer dev containers or dev DBs for exploration
- use container-local health checks before public URLs when diagnosing runtime issues
- do not edit deployed prod roots directly unless the user explicitly asks

## Typical Checks

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker compose ps
docker logs <service> --tail 100
curl -fsS http://localhost:<port>/health
```

## Permission Reminder

| Action | Permission |
| --- | --- |
| dev container ops | free |
| prod logs | free |
| prod `SELECT` / read-only inspection | ask once per session |
| prod writes / migrations / restarts | ask once per session |
| destructive schema ops | ask per query |
| git push | ask every time |
