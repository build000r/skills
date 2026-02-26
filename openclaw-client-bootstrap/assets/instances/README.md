# Deployed Instance Configs

This directory is the **source of truth** for all non-secret claw config.

Droplets are ephemeral. If a droplet is rebuilt, all files here can be re-deployed
with no data loss. The `.env` (secrets) lives only on the server and in your secrets
manager — never committed here.

## Directory Structure

```
assets/instances/
  <claw-name>/
    openclaw.json       ← full config minus secrets (secrets use env var references)
    SOUL.md             ← agent identity and constraints
    AGENTS.md           ← write-gateway contract and tool permissions
    USER.md             ← operator instructions
    .env.example        ← all keys present, values are placeholders
    checklists/         ← deployment and ops checklists (optional)
```

## What Lives Here vs What Stays on Server

| File | Here (skill) | Server only |
|------|-------------|-------------|
| `openclaw.json` | ✅ (no secrets inline) | Copy of this |
| `SOUL.md` | ✅ | Copy of this |
| `AGENTS.md` | ✅ | Copy of this |
| `USER.md` | ✅ | Copy of this |
| `.env.example` | ✅ (placeholders only) | — |
| `.env` | ❌ never | ✅ real secrets |

## Redeploy from Skill

If the droplet root disk is lost:

```bash
# Copy this instance's config to the new droplet
scp -r assets/instances/<claw-name>/ openclaw@<tailnet-ip>:/opt/<claw-name>-openclaw/

# Re-create .env from your secrets manager, then:
ssh openclaw@<tailnet-ip>
cd /opt/<claw-name>-openclaw
scripts/03-install-openclaw.sh
scripts/04-validate.sh
```

If this is a brand-new droplet, run bootstrap + tailscale scripts first as root, then switch to non-root Tailnet SSH for day-2 operations.

## Adding a New Instance

After bootstrapping a new claw:
1. Copy the generated kit's non-secret files into `assets/instances/<claw-name>/`
2. Replace real secret values in `.env` with placeholders → save as `.env.example`
3. Commit — the skill now has the full claw identity backed up
4. Add the instance to `references/deployed-instances.md`
