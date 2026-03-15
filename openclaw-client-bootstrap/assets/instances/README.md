# Private Instance Snapshots

This directory is for local, private, per-instance snapshots only.

The public repo should track reusable runtime-safe skills in
`../runtime-skills/`, not live client or environment-specific instance trees.
If you keep per-claw non-secret snapshots locally for disaster recovery, put
them here and keep them ignored.

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

## What Lives Here vs What Stays In The Public Repo

| File | Ignored locally | Public repo |
|------|-------------|-------------|
| `openclaw.json` | ✅ (no secrets inline) | ❌ |
| `SOUL.md` | ✅ | ❌ |
| `AGENTS.md` | ✅ | ❌ |
| `USER.md` | ✅ | ❌ |
| `.env.example` | ✅ (placeholders only) | ❌ |
| `.env` | ❌ never | ❌ |
| `assets/runtime-skills/<skill>/` | ❌ | ✅ tracked reusable bundle |

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

## Adding A New Local Snapshot

After bootstrapping a new claw:
1. Copy the generated kit's non-secret files into `assets/instances/<claw-name>/`
2. Replace real secret values in `.env` with placeholders → save as `.env.example`
3. Do **not** commit the instance directory in the public repo
4. Keep tracked reusable runtime-safe skills in `assets/runtime-skills/`
