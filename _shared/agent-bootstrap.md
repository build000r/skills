# Agent Identity Bootstrap

Canonical bootstrap snippet for all OpenClaw skills. Each skill inlines this logic
in its Phase 0 since skills are self-contained markdown files.

## Resolution Order

1. `.claude/agents/*.env` — per-agent identity files (preferred)
2. `services/approval_feedback_api/.env` — legacy single-agent fallback

## Bootstrap Snippet

```bash
# ── Agent identity bootstrap ──
AGENTS_DIR=".claude/agents"
AGENT_ENV=""

if [ -d "$AGENTS_DIR" ]; then
  AGENT_FILES=($AGENTS_DIR/*.env)
  if [ ${#AGENT_FILES[@]} -eq 1 ] && [ -f "${AGENT_FILES[0]}" ]; then
    AGENT_ENV="${AGENT_FILES[0]}"
  elif [ ${#AGENT_FILES[@]} -gt 1 ]; then
    if [ -n "$OPENCLAW_AGENT_ID" ] && [ -f "$AGENTS_DIR/${OPENCLAW_AGENT_ID}.env" ]; then
      AGENT_ENV="$AGENTS_DIR/${OPENCLAW_AGENT_ID}.env"
    else
      echo "Multiple agents found:"
      for f in $AGENTS_DIR/*.env; do echo "  - $(basename "$f" .env)"; done
      echo "Set OPENCLAW_AGENT_ID to pick one."
      exit 1
    fi
  fi
fi

if [ -z "$AGENT_ENV" ] && [ -f "services/approval_feedback_api/.env" ]; then
  AGENT_ENV="services/approval_feedback_api/.env"
fi

if [ -z "$AGENT_ENV" ]; then
  echo "No agent identity found. Run /unclawg-onboard or create .claude/agents/<agent-id>.env"
  exit 1
fi

set -a && source "$AGENT_ENV" && set +a
```

## Agent File Convention

Each file in `.claude/agents/` is named `<agent-id>.env` and contains all 6 vars:

```bash
OPENCLAW_API_URL=http://localhost:8010
OPENCLAW_API_KEY=<set-me>
OPENCLAW_TENANT_ID=tenant-dev
OPENCLAW_AGENT_ID=my-trading-bot
OPENCLAW_MACHINE_KEY_ID=mk_abc123
OPENCLAW_MACHINE_SECRET=sk_xyz789
```
