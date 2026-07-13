# Deploy Architecture Notes

Use this reference to reason about a typical multi-service deploy stack without
encoding one portfolio's exact topology.

## Common Surfaces

- API service deployed with Docker/Compose or systemd
- worker/cron service sharing the same image or repo
- Postgres and optional Redis
- public frontend on Pages, CDN, or edge frontdoor
- reverse proxy or worker forwarding public traffic to the API origin

## Common Filesystem Boundaries

- `<ssh-dev-root>/...` or repo checkout paths: editable dev workspace
- `/opt/...` or service-managed paths: deployed production roots
- `/mnt/...` or attached volume roots: backups, DB data, or persistent assets

Treat those as examples only. Use mode values for the real paths.

## Default Release Control Plane

Prefer a repo-owned local self-release command over a push-triggered hosted
workflow. The release host owns the exact-SHA worktree, canonical gate, artifact
build, transport, and release manifest. The production target activates the
artifact but does not build it. A hosted workflow may remain as a manual
fallback or for a deliberate exception such as untrusted contributor checks or
a platform that is unavailable on the trusted host.

Read `self-release.md` before designing or converting a release lane. It defines
the build-once invariant, credential cutover proof, target-specific transport,
behavior and state receipts, and migration-aware rollback contract.

## What Usually Changes Together

- app code + image tag
- env file + auth callback or header contract
- migration + app rollout
- frontend origin/frontdoor config + API deploy

## Useful Questions

Before deploying:

1. Which repo or service actually owns the change?
2. Which runtime surface must be healthy when this is done?
3. Is there a DB or secret change that forces a two-phase rollout?
4. What single command proves the runtime is on the expected version?
5. Which repo command is the canonical exact-SHA gate and release entry point?
6. Is the deployed artifact byte-for-byte or digest-identical to the gated artifact?
