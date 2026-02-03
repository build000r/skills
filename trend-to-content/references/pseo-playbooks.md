# PSEO Playbooks

12 proven patterns for programmatic SEO at scale.

## Core Principles

1. **Unique value per page** - Not just swapped variables
2. **Proprietary data wins** - First-party > scraped > public
3. **Subfolder URLs** - `/category/page/` not `page.example.com`
4. **Match search intent** - Answer what people actually search
5. **Quality over quantity** - 100 great pages > 10,000 thin ones

---

## The 12 Playbooks

### 1. Templates

**Pattern**: "[Type] template"
**URL**: `/templates/[type]/`

Examples: "resume template", "invoice template", "pitch deck template"

**Requirements**:
- Actually usable (not just previews)
- Multiple variations per type
- Easy download/use flow

**Trend integration**: Template types mentioned in trending "how to" searches

---

### 2. Curation

**Pattern**: "best [category]"
**URL**: `/best/[category]/`

Examples: "best website builders", "best CRM software"

**Requirements**:
- Genuine evaluation criteria
- Regular updates (show date)
- Real testing/expertise

**Trend integration**: Create "best" pages for trending product categories

---

### 3. Comparisons

**Pattern**: "[X] vs [Y]"
**URL**: `/compare/[x]-vs-[y]/`

Examples: "Notion vs Coda", "React vs Vue"

**Requirements**:
- Honest, balanced analysis
- Feature-by-feature comparison
- Clear recommendation by use case

**Trend integration**: Compare trending products/tools

---

### 4. Conversions

**Pattern**: "[X] to [Y]"
**URL**: `/convert/[from]-to-[to]/`

Examples: "$10 USD to GBP", "PDF to Word"

**Requirements**:
- Accurate, real-time data
- Fast, functional tool
- Related conversions suggested

**Trend integration**: New units/formats people search for

---

### 5. Examples

**Pattern**: "[type] examples"
**URL**: `/examples/[type]/`

Examples: "landing page examples", "email subject line examples"

**Requirements**:
- Real, high-quality examples
- Screenshots or embeds
- Analysis of why they work

**Trend integration**: Examples of trending styles/formats

---

### 6. Locations

**Pattern**: "[service] in [location]"
**URL**: `/[service]/[city]/`

Examples: "coworking in Austin", "coffee shops in SF"

**Requirements**:
- Actual local data (not city-name-swapped)
- Location-specific insights
- Map integration

**Trend integration**: Trending services + location targeting

---

### 7. Personas

**Pattern**: "[product] for [audience]"
**URL**: `/for/[persona]/`

Examples: "CRM for startups", "yoga for beginners"

**Requirements**:
- Persona-specific content
- Relevant features highlighted
- Testimonials from that segment

**Trend integration**: Trending topics + audience segments

---

### 8. Integrations

**Pattern**: "[product A] + [product B]"
**URL**: `/integrations/[product]/`

Examples: "Slack + Asana", "Zapier + Airtable"

**Requirements**:
- Real integration details
- Setup instructions
- Use cases for the combination

**Trend integration**: New tools people want to connect

---

### 9. Glossary

**Pattern**: "what is [term]"
**URL**: `/glossary/[term]/`

Examples: "what is pSEO", "what is API"

**Requirements**:
- Clear, accurate definitions
- Examples and context
- More depth than a dictionary

**Trend integration**: New terms/concepts trending in your niche

---

### 10. Translations

**Pattern**: Content in multiple languages
**URL**: `/[lang]/[page]/`

**Requirements**:
- Quality translation (not Google Translate)
- Cultural localization
- hreflang tags implemented

**Trend integration**: Trends specific to language markets

---

### 11. Directory

**Pattern**: "[category] tools"
**URL**: `/directory/[category]/`

Examples: "AI copywriting tools", "email marketing software"

**Requirements**:
- Comprehensive coverage
- Useful filtering/sorting
- Details per listing

**Trend integration**: Directories for trending product categories

---

### 12. Profiles

**Pattern**: "[entity name]"
**URL**: `/people/[name]/` or `/companies/[name]/`

Examples: "Stripe CEO", "Airbnb founding story"

**Requirements**:
- Accurate, sourced information
- Regularly updated
- Unique insights

**Trend integration**: Profiles of trending people/companies

---

## Page Template Structure

Every PSEO page needs:

```typescript
interface PSEOPage {
  // SEO Meta
  slug: string;                    // URL path
  metaTitle: string;               // 50-60 chars
  metaDescription: string;         // 150-160 chars

  // Content
  h1: string;                      // Different from title
  intro: string;                   // Connect to search intent
  sections: ContentSection[];       // Unique value

  // Internal Linking
  relatedSlugs: string[];          // Same playbook links
  breadcrumbs: string[];           // Category hierarchy

  // Conversion
  cta: {
    text: string;
    url: string;
  };
}
```

### Meta Title Formula

`[Primary Keyword] | [Secondary Keyword] | [Brand]`

Example: "CRM for Startups | Best Startup CRM | Acme"

### Meta Description Formula

`[What it is]. [Key benefit]. [Proof point or CTA].`

Example: "Compare the top 10 CRMs for startups. Find the right tool for your team size and budget. Updated January 2026."

---

## Combining Playbooks

Layer multiple patterns for long-tail targeting:

| Combination | Example |
|-------------|---------|
| Locations + Personas | "Marketing agencies for startups in Austin" |
| Curation + Locations | "Best coworking spaces in San Diego" |
| Comparisons + Personas | "Notion vs Coda for remote teams" |
| Templates + Personas | "Resume templates for developers" |

---

## Quality Checklist

Before publishing PSEO pages:

**Content**:
- [ ] Each page provides unique value
- [ ] Answers search intent
- [ ] Readable and useful to humans

**Technical**:
- [ ] Unique titles and meta descriptions
- [ ] Proper heading structure (H1 → H2 → H3)
- [ ] Schema markup (FAQ, HowTo, etc.)
- [ ] Page speed acceptable

**Linking**:
- [ ] Connected to site architecture
- [ ] Related pages linked
- [ ] No orphan pages
- [ ] In XML sitemap

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Thin content | Add unique analysis/insights per page |
| Keyword cannibalization | One page per keyword intent |
| Over-generation | Only create pages with search demand |
| Poor data | Verify accuracy, update regularly |
| Ignoring UX | Pages must serve users, not just Google |
