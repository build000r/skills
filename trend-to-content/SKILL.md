---
name: trend-to-content
description: |
  Transform social media trends into SEO pages, videos, and copy at scale.
  Use when: "what's trending", "content ideas", "viral content", "PSEO",
  "programmatic SEO", "video content ideas", "trend research",
  "content from trends", "what should I create", "content calendar".

  Three modes:
  1. **Research** - Find trending topics via API or web search
  2. **PSEO** - Generate SEO pages at scale from trends
  3. **Video** - Create video content scripts/compositions from hooks

  Works for any niche. Pluggable trend sources (Virlo API, Google Trends, WebSearch).
---

# Trend to Content

Transform trending topics into content at scale: PSEO pages, videos, and copy.

## Prerequisites

Required env vars (should be in `~/.zshrc`):
```bash
export VIRLO_API_KEY="virlo_tkn_..."       # Trend research
export ELEVENLABS_API_KEY="sk_..."          # Text-to-speech for video voiceovers
```

**If env vars are empty in Bash** (Claude Code runs bash, not zsh — `source ~/.zshrc` will break):
```bash
export VIRLO_API_KEY=$(grep 'VIRLO_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
export ELEVENLABS_API_KEY=$(grep 'ELEVENLABS_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

## The Workflow

```
TRENDS → IDEAS → CONTENT → PUBLISH
   ↓        ↓        ↓         ↓
Research  Filter   Create    SEO/
(APIs,    for      (PSEO,    Distribute
WebSearch) niche   video,
                   social)
```

## Quick Start by Mode

### Research Mode
"What's trending in [niche]?"

1. Query trend sources (see [references/trend-research.md](references/trend-research.md))
2. Filter for niche relevance
3. Identify content gaps (what's trending but not covered?)

### PSEO Mode
"Create pages at scale for [pattern]"

1. Choose playbook (see [references/pseo-playbooks.md](references/pseo-playbooks.md))
2. Define template structure
3. Generate pages from data + trends

### Video Mode
"Create video content about [trend]"

1. Extract hook from trend
2. Choose format (see [references/video-patterns.md](references/video-patterns.md))
3. Generate script/composition
4. **Remotion project setup**: [references/remotion-hub.md](references/remotion-hub.md)

---

## Trend Research

### Quick API Pattern

For APIs like Virlo, Google Trends, etc.:

```bash
# Generic pattern - replace with your API
curl -s -H "Authorization: Bearer $VIRLO_API_KEY" \
  "https://api.virlo.ai/trends/digest" | jq '.data'
```

### WebSearch Fallback

When no API available, use WebSearch queries:
- `"[niche] trending 2026"`
- `"[niche] TikTok viral"`
- `"what's trending in [niche]"`

**Full research guide**: [references/trend-research.md](references/trend-research.md)

---

## PSEO Quick Reference

### The 12 Playbooks

| Playbook | Pattern | Example |
|----------|---------|---------|
| Templates | "[Type] template" | "resume template" |
| Curation | "best [category]" | "best CRM software" |
| Comparisons | "[X] vs [Y]" | "Notion vs Coda" |
| Locations | "[service] in [city]" | "coworking in Austin" |
| Personas | "[product] for [audience]" | "CRM for startups" |
| Glossary | "what is [term]" | "what is pSEO" |

**Full playbooks + implementation**: [references/pseo-playbooks.md](references/pseo-playbooks.md)

### Page Template Structure

```
URL: /[playbook]/[variable]/

- Meta title: 50-60 chars with primary keyword
- Meta description: 150-160 chars with value prop
- H1: Compelling, different from title
- Intro: Connect to search intent
- Content sections: Unique value per page
- Internal links: Related pages in same playbook
- CTA: Clear conversion action
```

---

## Video Quick Reference

### Hook Formulas (First 3 Seconds)

See [references/video-patterns.md](references/video-patterns.md) for hook formulas (curiosity, contrarian, story, value, pattern interrupt) and full script structures.

### Platform Formats

| Platform | Length | Format |
|----------|--------|--------|
| TikTok | 15-60s | Vertical, fast cuts, captions |
| YouTube Shorts | 30-60s | Vertical, hook in 1s |
| Instagram Reels | 15-30s | Vertical, trending audio |
| YouTube | 8-15min | Horizontal, structured |

**Full video patterns**: [references/video-patterns.md](references/video-patterns.md)

---

## Copywriting Quick Reference

### Headlines

**Formula**: {Outcome} without {Pain Point}
**Formula**: The {Category} for {Audience}
**Formula**: {Number} {Things} that {Outcome}

### CTAs (avoid weak verbs)

- "Submit" → "Get My [Thing]"
- "Learn More" → "See How It Works"
- "Sign Up" → "Start Free Trial"

**Full copy frameworks**: [references/copywriting-formulas.md](references/copywriting-formulas.md)

---

## Cross-Reference Workflow

For maximum impact, find the intersection:

```
┌─────────────────┐
│  WHAT'S        │
│  TRENDING?     │ ← Trend APIs, WebSearch
└───────┬────────┘
        │
        ▼
┌─────────────────┐
│  WHAT DOES     │
│  YOUR AUDIENCE │ ← Customer research, keywords
│  CARE ABOUT?   │
└───────┬────────┘
        │
        ▼
┌─────────────────┐
│  WHAT HAVEN'T  │
│  YOU COVERED?  │ ← Content audit, gaps
└───────┬────────┘
        │
        ▼
   CREATE CONTENT
   AT INTERSECTION
```

### Example Workflow

1. **Trend**: "AI coding agents" trending on TikTok
2. **Audience**: Developers exploring AI-assisted workflows
3. **Gap**: No page targeting "best AI coding tools for solo devs"
4. **Content**:
   - PSEO page: `/tools/ai-coding-for-solo-devs/` (Personas playbook)
   - Video: 30s TikTok comparing top tools
   - Social: Thread with key points

---

## Content Calendar Integration

Plan content production:

| Week | Trend Research | PSEO | Video | Social |
|------|---------------|------|-------|--------|
| 1 | Identify 3 trends | Template 1 page | 1 explainer | 3 posts |
| 2 | Validate with data | Generate pages | B-roll shoots | Repurpose |
| 3 | Update calendar | Internal linking | Edit + publish | Promote |
| 4 | Review performance | Iterate | Plan next batch | Engage |

---

## Output Formats

### PSEO Page (TypeScript/JSON)

```typescript
{
  slug: "for-[topic]",
  metaTitle: "[Keyword] | [Brand]", // 50-60 chars
  metaDescription: "...", // 150-160 chars
  h1: "...",
  sections: [...],
  relatedSlugs: [...]
}
```

### Video Script

```
HOOK (0-3s): [Attention grabber]
PROBLEM (3-10s): [Why this matters]
SOLUTION (10-45s): [Your content]
CTA (45-60s): [What to do next]
```

### Social Post

```
HOOK: [First line that stops the scroll]
BODY: [3-5 key points]
CTA: [Engagement driver]
```

---

## Related Skills

- **programmatic-seo**: Deep dive on PSEO implementation
- **copywriting**: Line-by-line copy improvement
- **social-content**: Platform-specific social strategies
