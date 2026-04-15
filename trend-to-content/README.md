# trend-to-content

Transform social media trends into SEO pages, videos, and copy at scale.

## Install

```bash
npx skills add build000r/trend-to-content
```

## What it does

- **Research trends** via Virlo (`Trends`, `Orbit`, `Comet`), Google Trends, or WebSearch
- **Generate PSEO pages** using 12 proven playbooks (templates, comparisons, personas, etc.)
- **Create video content** with hook formulas and platform-specific formats
- **Write copy** with headline, CTA, and transition frameworks

For portfolio GTM, this skill should not start from raw trends alone. The
correct flow is:

`acquisition page -> Virlo signal -> evidence hydration -> content`

## The Workflow

```
TRENDS → IDEAS → CONTENT → PUBLISH
   ↓        ↓        ↓         ↓
Research  Filter   Create    SEO/
(APIs,    for      (PSEO,    Distribute
WebSearch) niche   video,
                   social)
```

## Modes

### Research Mode
```
> What's trending in [your niche]?
```
Queries trend sources, filters for relevance, and identifies content gaps inside
an already-defined buyer lane.

### PSEO Mode
```
> Create pages at scale for [pattern]
```
Generates SEO pages using playbooks: templates, comparisons, personas, locations, etc.

### Video Mode
```
> Create video content about [trend]
```
Extracts hooks from trends, generates scripts for TikTok/YouTube/Reels.

## Example

**Input**: "Create content about AI coding agents trending on TikTok"

**Output**:
- PSEO page: `/tools/ai-coding-for-solo-devs/` (Personas playbook)
- Video script: 30s TikTok with hook + problem + solution + CTA
- Social post: LinkedIn/Twitter thread with key points

## References Included

- `trend-research.md` - Virlo `/v1` patterns, lane selection, WebSearch queries, validation
- `pseo-playbooks.md` - 12 playbooks with templates and examples
- `video-patterns.md` - Hooks, scripts, platform specs
- `copywriting-formulas.md` - Headlines, CTAs, transitions

## License

MIT
