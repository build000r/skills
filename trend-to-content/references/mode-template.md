# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete any sections that don't apply.

---

# {Project Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Brand

- **Name**: {Your Brand Name}
- **Voice**: authoritative | conversational | playful | technical | provocative
- **Tone**: professional | casual | edgy | educational
- **Target audience**: {Who you're creating content for — e.g. "solo developers", "DTC founders", "fitness creators"}
- **Brand colors**: primary `#3f7d77`, secondary `#1f2d3a` (replace with your colors)
- **Logo path**: `modes/{project-name}/logo.svg` (optional)

## Content Types

Which content pipelines this project uses:

- **PSEO**: yes | no — programmatic SEO pages at scale
- **Video**: yes | no — video scripts and Remotion compositions
- **Social**: yes | no — social media posts, threads, captions
- **Blog**: yes | no — long-form blog content from trends
- **Email**: yes | no — newsletter content from trends

## SEO

- **Target keywords**: ["primary keyword", "secondary keyword", "long-tail phrase"]
- **Existing pages to interlink**: `ls src/pages/` or list known URLs
- **URL pattern**: `/blog/{slug}/` | `/tools/{category}/{slug}/` | custom
- **Meta title pattern**: "{Keyword} | {Brand Name}" (50-60 chars)
- **Meta description pattern**: "{Value prop}. {CTA}." (150-160 chars)
- **Robots**: index, follow | noindex, nofollow

## Video

- **Preferred format**: TikTok (15-60s vertical) | YouTube Shorts (30-60s) | YouTube (8-15min) | Reels (15-30s)
- **Platform**: TikTok | YouTube | Instagram | multi-platform
- **Default length**: 30s | 60s | custom
- **Remotion project path**: `~/repos/{project-name}/video/` (if using Remotion)
- **Voiceover**: ElevenLabs | no voiceover | manual
- **Caption style**: burned-in | SRT | none

## Trend Sources

- **Primary API**: Virlo | Google Trends | none
- **Niche keywords**: ["keyword1", "keyword2", "keyword3"]
- **Hashtags to track**: ["#hashtag1", "#hashtag2"]
- **Competitor accounts**: ["@competitor1", "@competitor2"] (for trend inspiration)
- **WebSearch queries**: ["{niche} trending 2026", "{niche} viral content"]
- **Update frequency**: daily | weekly | on-demand

## Publishing

- **CMS**: WordPress | Ghost | Contentful | markdown files | none
- **Deploy command**: `npm run build && npm run deploy` | `git push` | custom
- **Content directory**: `src/content/` | `content/` | `public/posts/`
- **Image directory**: `public/images/content/` | custom
- **Social scheduling**: Buffer | Hootsuite | manual | none
- **Review before publish**: yes (show draft first) | no (publish directly)
