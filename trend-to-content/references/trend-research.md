# Trend Research Guide

Find what's trending to fuel content creation.

## Trend Sources

### 1. Virlo API

**Base URL**: `https://api.virlo.ai`
**Auth**: `Authorization: Bearer $VIRLO_API_KEY`
**Versioning**: all current endpoints use `/v1`
**Naming**: Virlo V1 uses `snake_case` for request and response fields

If `$VIRLO_API_KEY` is empty (Claude Code runs bash, not zsh — never `source ~/.zshrc`):
```bash
export VIRLO_API_KEY=$(grep 'VIRLO_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

#### Which Virlo lane to use

- **Trends**: broad scan of trend groups and the curated digest. Best for top-of-funnel attention sensing.
- **Orbit**: async keyword-based social listening across YouTube, TikTok, and Instagram. Best when you already know the buyer lane and want signal density.
- **Comet**: recurring niche monitor with scheduled runs. Best after a lane has already proven valuable.
- **MCP / AI-agent integration**: use when the trend work is being orchestrated through an agent client rather than raw HTTP.

For buildooor-style portfolio GTM, the sequencing should be:

`acquisition page -> Virlo signal -> evidence hydration -> route`

Do not start from raw trends alone. Use the product acquisition page, README,
VISION, or positioning doc to decide the lane first, then use Virlo to rank
which topics inside or adjacent to that lane are accelerating.

#### Trends

```bash
# Trend groups in a date range
curl -G https://api.virlo.ai/v1/trends \
  -H "Authorization: Bearer $VIRLO_API_KEY" \
  -d start_date=2025-10-14 \
  -d end_date=2025-10-16 \
  -d limit=25

# Curated daily digest
curl -s -H "Authorization: Bearer $VIRLO_API_KEY" \
  "https://api.virlo.ai/v1/trends/digest" | jq '.data'
```

Response shape (trends / digest):
```json
{
  "data": [
    {
      "id": "...",
      "title": "Trends for Oct 15th",
      "trends": [
        {
          "ranking": 1,
          "trend": {
            "name": "Topic Name",
            "description": "Why this is trending and what creators are doing with it",
            "trend_type": "content"
          }
        }
      ]
    }
  ]
}
```

Access trend names: `jq '.data[0].trends[].trend | {name, description}'`

#### Orbit

Orbit is the highest-leverage Virlo primitive when you already know the topic
lane you care about.

```bash
curl -X POST https://api.virlo.ai/v1/orbit \
  -H "Authorization: Bearer $VIRLO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI coding agents",
    "keywords": ["ai coding agents", "claude code", "cursor workflow"],
    "time_period": "this_week",
    "platforms": ["youtube", "tiktok", "instagram"],
    "min_views": 10000
  }'
```

Use specific multi-word phrases. Generic one-word keywords create noisy result
sets. Orbit queues a job and returns an ID; polling and result retrieval are the
follow-up steps.

#### Comet

Comet is the recurring-monitor lane:

```bash
curl -X POST https://api.virlo.ai/v1/comet \
  -H "Authorization: Bearer $VIRLO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI coding workflow monitor",
    "keywords": ["claude code workflow", "cursor workflow", "ai coding agent"],
    "platforms": ["youtube", "tiktok"],
    "cadence": "daily",
    "min_views": 10000,
    "time_range": "this_week",
    "is_active": false,
    "intent": "Track durable topics after manual validation"
  }'
```

Keep `Comet` off until the lane is already proven. It is a monitor, not the
first discovery step.

#### Hashtags

Hashtag analytics are still useful, but the endpoint is now `/v1/hashtags` and
uses snake_case params:

```bash
curl -G https://api.virlo.ai/v1/hashtags \
  -H "Authorization: Bearer $VIRLO_API_KEY" \
  -d start_date=2026-01-25 \
  -d end_date=2026-02-01 \
  -d order_by=views \
  -d limit=30
```

Use hashtag research after you already have a lane and want packaging ideas,
distribution handles, or supporting metadata. It is not the strategy layer.

#### MCP / AI Agents

Virlo also ships an MCP / AI-agent layer. Use it when the work is agent-driven
and you want tool-style access instead of hand-written `curl` calls. Keep the
same guardrail: the buyer lane still comes from the acquisition page or
positioning doc, not from the trend API.

### 2. Google Trends

Use WebSearch or the unofficial API:

```
WebSearch: "[niche] site:trends.google.com"
WebSearch: "Google Trends [niche] [year]"
```

### 3. WebSearch Patterns

When no API available, these queries work:

| Query Pattern | Finds |
|---------------|-------|
| `"[niche] trending 2026"` | Current trends |
| `"[niche] TikTok viral"` | Social viral content |
| `"[niche] what's popular"` | General popularity |
| `"[niche] Reddit hot"` | Community discussions |
| `"[niche] rising search"` | Search demand growth |

### 4. Platform-Specific Research

**TikTok**: Search for niche hashtags, check "Discover" tab
**Instagram**: Explore page for your niche, trending Reels audio
**YouTube**: Trending tab, "most viewed this week [niche]"
**Twitter/X**: Trending topics, influential account activity

---

## Filtering for Your Niche

Raw trends are generic. Filter for relevance:

### Step 1: Keyword Matching

Check if trend contains your niche keywords:
- Direct match: "AI tools" in a developer tools trend
- Semantic match: "coding agent" or "copilot" for AI dev tools

### Step 2: Audience Overlap

Ask: Would my target audience care about this?
- **Yes**: Proceed
- **Maybe**: Test with smaller content piece first
- **No**: Skip

### Step 3: Competition Check

Search the trend + your angle:
- Few results = opportunity
- Many results = need differentiation

---

## Trend Validation

Before investing in content, validate:

### Search Volume Check

```
WebSearch: "[trend] keyword volume"
WebSearch: "[trend] how many searches"
```

Or use free tools:
- Ubersuggest
- Keywords Everywhere extension
- Google Keyword Planner

### Durability Assessment

| Trend Type | Duration | Content Strategy |
|------------|----------|------------------|
| Viral moment | Days | Quick social post only |
| Seasonal | Weeks | Plan ahead, evergreen angle |
| Emerging | Months | PSEO pages, video series |
| Evergreen | Years | Full content investment |

### Questions to Ask

1. Is this trend growing or declining?
2. Does it align with my business goals?
3. Can I add unique value vs existing content?
4. What format best serves this trend? (page, video, post)

---

## Trend-to-Content Mapping

| Trend Signal | Best Content Format |
|--------------|---------------------|
| "how to" searches rising | Tutorial video, PSEO glossary page |
| Product comparisons | PSEO comparison pages |
| New term/concept | PSEO glossary + explainer video |
| Visual/aesthetic | Instagram Reels, TikTok |
| Controversy/debate | Twitter thread, YouTube video |
| Statistics/data | PSEO pages with original analysis |

---

## Building a Trend Radar

Set up recurring trend monitoring:

### Weekly Routine (30 min)

1. **Check trend APIs** (5 min)
2. **WebSearch "[niche] this week"** (10 min)
3. **Review competitor content** (10 min)
4. **Log 3-5 trends** worth acting on (5 min)

### Monthly Review

1. Which trends converted to content?
2. Which performed best?
3. What patterns emerge?
4. Adjust research queries based on learnings

---

## Example: Developer Tools Niche

### Trend Research Queries

```
"developer tools trending 2026"
"coding productivity TikTok viral"
"AI coding tools trending"
"developer workflow what's popular"
"programming tools rising search"
```

### Filter Results

From "AI coding agents trending":
- Niche match: Yes (developer tools/productivity)
- Audience overlap: High (developers exploring AI workflows)
- Competition: Medium (many generic listicles, few specific comparisons)

### Content Decision

- **PSEO page**: `/tools/ai-coding-agents-compared/` (Comparisons playbook)
- **Video**: "3 AI coding tools you haven't tried" (TikTok/Reels)
- **Social**: Thread comparing AI coding workflows
