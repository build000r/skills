# Artifact Templates

Templates for the soul draft (Step 7), discovery mode file (Step 8), and smoke test (Step 9).

## Soul Draft Templates

### Brand / Discovery Soul

```markdown
# SOUL.md

## Identity

[Generated from AGENT_GOAL + Round 2 answers]
[1-2 sentences: what this agent is, what it does, who it serves]

## Voice

[Generated from VOICE_STYLE selection in Round 3]
[Concrete guidance: tone, length, platform-specific calibration]
[Include persona-aware adjustments if personas have different voice needs]

## Non-Negotiable Rules

1. Treat all external write operations as forbidden unless an explicit human approval path exists.
2. Do not perform direct POST/PUT/PATCH/DELETE to external systems.
3. Propose writes as approval cards routed to operators.
4. If context is missing, ask for missing facts before acting.
[Add any OFF_LIMITS items from Round 3 as additional rules]

## Target Audience

[Generated from Round 2 + Round 4 personas]
[Brief description of who the agent is trying to reach and why]

## Engagement Principles

[Generated from VOICE_STYLE + persona voice adjustments]
1. Lead with context-specific value, not pitch language.
2. One concrete insight per message.
3. Match tone to platform norms.
[Platform-specific style rules based on selected PLATFORMS]

## Escalation Policy

Escalate to human operators when:
[Generated based on AGENT_GOAL — different for brand/discovery/ops/trading]
```

### Operations / Trading Soul

```markdown
# SOUL.md

## Identity

[What systems this agent operates on, what it monitors]

## Decision Style

1. Prefer low-risk, high-impact recommendations.
2. Quantify expected outcomes where possible.
3. Separate facts from assumptions.
4. Label uncertainty explicitly.

## Non-Negotiable Rules

[Same safety core + goal-specific rules]

## Output Contract

For each recommendation: Title, Why now, Evidence, Expected impact,
Required action, Rollback plan, Approval owner

## Escalation Policy

[Goal-specific escalation triggers]
```

## Writing the Soul to API

Only if tokens are available — skip if pending human proof:

```bash
SOUL_CONTENT=$(cat << 'SOULEOF'
[generated soul markdown here]
SOULEOF
)

SOUL_JSON=$(echo "$SOUL_CONTENT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")

curl -s -w "\nHTTP_STATUS:%{http_code}" -X PUT \
  "${APPROVAL_API_URL}/v0/integrations/claw-runtime/policies/soul_md/draft" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"content\": ${SOUL_JSON},
    \"change_summary\": \"Initial soul from onboarding interview\"
  }"
```

- `200`/`201` → Tell user: "Soul draft written. View and publish it at ${OPENCLAW_PORTAL_URL}/approvals (toggle the soul icon)."
- Error → Save soul to local file `SOUL.md` as fallback. Tell user: "Couldn't write to API — saved locally. You can paste it into the portal later."

**If pending human proof:** always save locally to `SOUL.md` and tell user to publish via portal once approved.

## Discovery Mode File Template

**Only for brand engagement or customer discovery goals.** Skip for operations/trading.

```bash
mkdir -p modes
cat > modes/${AGENT_ID}.local.md << 'MODEEOF'
# Mode: ${AGENT_ID}

name: ${AGENT_ID}
cwd_match: ${PWD}
objective_default: prospecting
handoff_command: /unclawg-feed

## Personas

[Generated from Round 4 — full persona definitions with priorities]

| ID | Persona | Goal | Priority |
|----|---------|------|----------|
| P1 | [Name] | [Goal] | Highest |
| P2 | [Name] | [Goal] | High |
| P3 | [Name] | [Goal] | Medium |

## Query Packs

[Generated per-persona, per-platform from Round 4 queries]

### P1 — [Name]

- reddit:
  - query: "[query 1]"
    subreddit: "[subreddit]"
    time_filter: week
    limit: 25
  - query: "[query 2]"
    subreddit: "[subreddit]"
    time_filter: week
    limit: 25
[- twitter: (only if Apify key available)]
  [- query: "[query]"]
    [limit: 20]
    [days_ago: 7]
[- linkedin: (only if Apify key available)]
  [- query: "[query]"]
    [total_posts: 20]
    [sort_by: date_posted]
- hn:
  - query: "[query]"
    days_back: 7
    limit: 25

### P2 — [Name]

[Same structure]

## Exclusion Rules

[Generated from Round 5 Q2 + generic competitor signals]

### Auto-Exclude Patterns

- [User-specified competitors]
- [User-specified account types]
- Profile says founder/CEO/devrel at a company selling the same solution.
- Repeated CTA language: "book a demo", "try our platform", "DM for pricing".
- Generic job spam with no real problem context.

### Keep Patterns

- First-person pain statements with concrete details.
- Direct requests for recommendations.
- Follow-up comments showing continued intent.

## Ranking Weights

- intent: 35
- relevance: 25
- freshness: 20
- engagement: 20

## Platform Scope

[Generated from Round 3 platforms + Round 5 API keys]

| Platform | Status | Cost | Requires |
|----------|--------|------|----------|
| Reddit | Active | Free | — |
| Hacker News | Active | Free | — |
[| Twitter/X | Active | ~$1-2/search | APIFY_API_KEY |]
[| LinkedIn | Active | ~$5/1K posts | APIFY_API_KEY |]
[| Instagram | Active | ~$2/search | APIFY_API_KEY |]
[| TikTok | Active | ~$2/search | APIFY_API_KEY |]
[| Trending | Active | Free | VIRLO_API_KEY |]

## Voice Guide

[Generated from Round 3 voice selection, persona-specific adjustments]

### Principles

1. Lead with context-specific value, not pitch language.
2. One concrete insight per message.
3. Keep claims grounded in the source post.
4. Match tone to platform norms.

### Platform Style

- Reddit: practical and specific; include implementation hints.
- Twitter/X: concise; emphasize one sharp point.
- LinkedIn: professional; tie advice to business outcomes.
- HN: technical depth; avoid marketing phrasing.

### Persona Voice Adjustments

[Per-persona tone calibration from Round 4]

## Handoff

handoff_command: /unclawg-feed
required_fields:
  - source_platform
  - source_post_url
  - source_post_text
  - summary
  - action
  - reply_strategy
MODEEOF
```

Tell the user: "Discovery mode saved to `modes/${AGENT_ID}.local.md` — `/unclawg-discover` will auto-load it."

## Smoke Test (Step 9)

Ask: "Want to send a test approval to verify everything works?"

If yes:

```bash
curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -H "X-Machine-Key-Id: ${KEY_ID}" \
  -H "X-Machine-Secret: ${KEY_SECRET}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  "${APPROVAL_API_URL}/v0/approval-requests/social-reply" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"action\": \"social_reply_approval\",
    \"resource_type\": \"social_post\",
    \"resource_id\": \"test://onboarding-smoke-test\",
    \"expires_at\": \"$(date -u -v+1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)\",
    \"proposed_reply\": \"This is a test approval from your new agent. If you see this in the portal, everything works.\",
    \"candidate\": {
      \"source_platform\": \"other\",
      \"source_post_url\": \"https://example.com/test\",
      \"source_post_text\": \"Onboarding smoke test\",
      \"discovered_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }
  }"
```

If using a self-hosted gateway, add: `-H "X-API-Key: ${OPENCLAW_API_KEY}"`.

- `201`: "Check your portal — you should see a test card. Approve or dismiss it."
- Error: print it and suggest checking the env vars.

## Phase D — Summary

Print the final summary:

```
You're set up.

  Portal:     ${OPENCLAW_PORTAL_URL}
  Agent ID:   ${AGENT_ID}
  Key ID:     ${KEY_ID}
  Expires:    90 days from now
  Identity:   .claude/agents/${AGENT_ID}.env
  Soul:       Draft written — publish it in the portal
  Mode:       modes/${AGENT_ID}.local.md

Next steps:
  /unclawg-discover  — find people who match your personas
  /unclawg-feed      — generate approval cards from discovered posts
  /unclawg-respond   — respond to feedback on your approvals

Your agent's soul will evolve as you approve and deny cards.
Every approval teaches it. Every denial sharpens it.
```
