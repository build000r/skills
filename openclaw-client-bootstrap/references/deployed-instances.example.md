# Deployed OpenClaw Instances (Example)

Use this file as a template for a local private inventory.

Copy to `references/deployed-instances.md` (gitignored) and fill with real values.

## Instance Index

| Client | Droplet | Public IP | Tailscale IP | Tag | Region | Size | Bot |
|--------|---------|-----------|--------------|-----|--------|------|-----|
| example_client | example-openclaw (droplet-id) | 203.0.113.10 | 100.64.0.10 | tag:openclaw | nyc1 | s-1vcpu-2gb | @example_openclaw_bot |

## SSH Access

```bash
# Public SSH should be blocked at cloud firewall + UFW.
# Tailnet (default operator login)
ssh openclaw@100.64.0.10

# Optional dedicated collaboration user (if enabled)
ssh aiops@100.64.0.10
```

## Per-Instance Details

### example_client

- **OS:** Ubuntu 24.04
- **Services:** openclaw.service, tailscaled, ufw, fail2ban, docker
- **App user:** `openclaw`
- **SSH users:** `openclaw` (default), `aiops` (optional collab)
- **OpenClaw version:** 2026.2.15
- **Model:** anthropic/claude-haiku-4-5-20251001
- **Sandbox:** Docker (mode: all, workspace: read-only)
- **Swap:** 2GB
- **Node heap:** 768MB
- **Config path:** `/home/openclaw/.openclaw/openclaw.json`
- **Env path:** `/home/openclaw/.openclaw/.env`
