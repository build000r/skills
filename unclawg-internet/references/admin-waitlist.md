# Operator Waitlist Triage (Admin Flow)

Use this when a signup returns `pending_human_proof`.

## Setup

1. Get your human auth token (portal login/session).
2. Export operator env vars:

```bash
export OPENCLAW_API_URL="${APPROVAL_API_URL:-https://api.unclawg.com}"
export OPENCLAW_TENANT_ID="${TENANT_ID:-tenant-prod}"
export OPENCLAW_ACCESS_TOKEN="<human_jwt>"
# Optional for self-hosted gateways:
export OPENCLAW_API_KEY="${OPENCLAW_API_KEY:-}"
export OPENCLAW_APP_ID="${OPENCLAW_APP_ID:-}"
```

## Commands

List pending waitlist entries:

```bash
bash scripts/waitlist.sh list 200
```

Inspect one:

```bash
bash scripts/waitlist.sh detail <approval_id>
```

Approve or deny:

```bash
bash scripts/waitlist.sh approve <approval_id>
bash scripts/waitlist.sh deny <approval_id>
```

`approve` unlocks onboarding for that user. `deny` keeps them blocked.

## Optional SSH/DB Fallback

If API auth is unavailable, use:

```bash
export WAITLIST_SSH_HOST="root@your-server"
export WAITLIST_DB_CONTAINER="spaps-python-db"
export WAITLIST_DB_USER="spaps"
export WAITLIST_DB_NAME="spaps"
bash scripts/waitlist.sh ssh-list 200
```

## Local Mode (Gitignored)

Put private host/db defaults in:

`../modes/unclawg.local.md`

`modes/` is gitignored in `../opensource/skills/.gitignore`, so this stays local.
