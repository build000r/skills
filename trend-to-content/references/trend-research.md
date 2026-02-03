# Trend Research Guide

Find what's trending to fuel content creation.

## Trend Sources

### 1. Virlo API (Social Trends)

**Base URL**: `https://api.virlo.ai` (NOT `.com`, NOT `/api/` prefix)
**Auth**: `Authorization: Bearer $VIRLO_API_KEY`

If `$VIRLO_API_KEY` is empty (Claude Code runs bash, not zsh — never `source ~/.zshrc`):
```bash
export VIRLO_API_KEY=$(grep 'VIRLO_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

```bash
# Trending topics digest
curl -s -H "Authorization: Bearer $VIRLO_API_KEY" \
  "https://api.virlo.ai/trends/digest" | jq '.data'

# Hashtag research
curl -s -H "Authorization: Bearer $VIRLO_API_KEY" \
  "https://api.virlo.ai/hashtags?startDate=2026-01-25&endDate=2026-02-01&orderBy=views&limit=30"
```

Response format (trends/digest):
```json
{
  "results": 1,
  "data": [{
    "id": "...",
    "title": "Trends for Feb 3",
    "trends": [{
      "ranking": 1,
      "trend": {
        "id": "...",
        "name": "Topic Name",
        "description": "Why this is trending and what creators are doing with it",
        "trend_type": "content"
      }
    }]
  }]
}
```

Access trend names: `jq '.data[0].trends[].trend | {name, description}'`

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
