# Client Overlay Template

> **Legacy note**: This file was originally `mode-template.md` for the `modes/` pattern. It now serves as a structural reference for creating client overlays at `skillbox-config/clients/{client-name}/overlay.yaml`. Translate the sections below into YAML keys in the overlay file.

Copy the relevant sections into `skillbox-config/clients/{client-name}/overlay.yaml` and fill in each field. Omit any sections that don't apply.

---

# {Project Name} Client Overlay

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Output

- **File path**: `content/research/{slug}.mdx` (MDX pipeline) or `src/pages/research/{Name}ResearchPage.tsx` (TSX)
- **Framework**: React / Next.js / Vue / Svelte / HTML
- **MDX pipeline**: If the project has `content/research/` + `pages/research/[slug].tsx`, use MDX output. No TSX page needed.
- **Existing papers command**: `ls content/research/*.mdx` (MDX) or `ls src/pages/research/` (TSX)

## Companion Outputs

Describe the required derivatives that every paper should generate. Keep this narrow unless the project genuinely needs more than the default X article plus LinkedIn article/post bundle.

For MDX pipeline projects, companion defaults are sibling files in `content/research/`:
- `content/research/{slug}.x-article.md`
- `content/research/{slug}.linkedin-article.md`
- `content/research/{slug}.linkedin-post.md`

- **X article path**: `content/research/{slug}.x-article.md` (MDX) or `src/pages/research/{Name}ResearchPage.x-article.md` (TSX)
- **X article format**: Markdown / plain text / HTML / CMS draft
- **X article paste target**: `https://x.com/compose/articles/edit`
- **X article routing**: None / file-based / manual (describe exact pattern)
- **LinkedIn article path**: `src/pages/research/{Name}ResearchPage.linkedin-article.md` (or your preferred location)
- **LinkedIn article format**: Markdown / plain text / HTML / CMS draft
- **LinkedIn article paste target**: LinkedIn article editor / CMS draft / custom
- **LinkedIn article routing**: None / file-based / manual (describe exact pattern)
- **LinkedIn post path**: `src/pages/research/{Name}ResearchPage.linkedin-post.md` (or your preferred location)
- **LinkedIn post format**: Markdown / plain text / CMS draft
- **LinkedIn post paste target**: LinkedIn post composer / scheduler / custom
- **If site article also exists**: separate file / same source / generated from X article / generated from LinkedIn article
- **X primary discovery surface**: X Articles / search / feed / community / email / infer per topic
- **LinkedIn primary discovery surface**: feed / article / search / community / email / infer per topic
- **LinkedIn primary reader**: role / seniority / problem to call out early
- **LinkedIn dwell pattern**: checklist / framework / teardown / case study / infer per topic
- **Companion audience job**: "When ___, I want to ___, so I can ___"
- **Credibility pattern**: method line / author line / source-base line / custom
- **Default CTA**: subscribe / share / request full paper / none / custom
- **Extra derivative scope**: none by default; describe only if this client overlay truly requires more outputs

If you omit companion output paths, the skill defaults to a sibling file beside the paper:

- `{paper-base}.x-article.md`
- `{paper-base}.linkedin-article.md`
- `{paper-base}.linkedin-post.md`

## Routing

How to register the new page:

- **File-based**: No action needed (Next.js, Remix, etc.)
- **Manual**: Add import and route to `src/routes.tsx` (describe exact pattern)
- **None**: Standalone file, no routing needed

## Styling

- **System**: Tailwind / CSS Modules / styled-components
- **Primary color**: `#3f7d77` (replace with your brand color)
- **Secondary color**: `#1f2d3a`
- **Heading font**: `font-display` / `font-serif` / system
- **Body font**: `font-sans` / system
- **Container**: `max-w-4xl mx-auto px-4 py-12`
- **Table header bg**: Primary color
- **Table header text**: White

Override the table classes:

```
const thClass = "border border-gray-300 bg-[PRIMARY] px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-white";
const tdClass = "border border-gray-200 px-3 py-2 text-sm text-[SECONDARY]";
const trEven = "bg-gray-50";
```

## Data Sources

Describe how to gather project-specific data before writing. Examples:

- **Database**: SSH/docker command to query, or path to cached data file in `skillbox-config/clients/{client-name}/`
- **API**: Endpoint + required env var for auth
- **Reference files**: List files in `skillbox-config/clients/{client-name}/` to read
- **None**: Skip, use web research only

## Audience

- **Who**: Name/role of primary reader
- **Expertise**: Expert / intermediate / general
- **Job-to-be-done**: "When ___, I want to ___, so I can ___"
- **Jargon**: Use freely / define on first use / avoid

## Tone

Academic / clinical / conversational / contrarian / technical

## Paper Sections

Custom section structure for this project. Replace the generic structure:

1. **Title**: "{Your title pattern with {Topic} placeholder}"
2. **Abstract**: 150-200 words. What to emphasize.
3. **Introduction**: What angle to take.
4. (Define 3-7 body sections specific to your domain)
5. **Conclusion**: What to tie together.
6. **References**: Format preference.

## Page Template

If you have a component template, place it at `skillbox-config/clients/{client-name}/page-template.tsx` (or `.vue`, `.svelte`, `.html`). Reference it here:

```
Read skillbox-config/clients/{client-name}/page-template.tsx for the structural template.
```

## Validation

Command to run after writing:

```bash
cd ~/repos/{project-name} && npx tsc --noEmit --pretty
```

## SEO

- **Robots**: `noindex, nofollow` (default for internal papers)
- **Title pattern**: "{Topic} | {Site Name}"
- **Description pattern**: "Internal Research Brief — {Org Name}. {Topic description}"

## Post-Creation

List every required follow-up step after writing the bundle.

**MDX pipeline projects**: Homepage listing and API endpoints (`.md`/`.txt`) are auto-generated from `content/research/` at build time. No manual registration for those. List only additional tasks here.

Examples:

- Register the paper in a manifest
- Add the X article to a content index
- Append the X article to a shared social-drafts file
- Append the LinkedIn article/post drafts to a shared social-drafts file
- Update `llms.txt` or other discovery surfaces
- Add homepage/nav links (not needed for MDX pipeline — auto-generated)

Keep this list limited to artifacts and registrations the project actually needs. Do not add channel-by-channel distribution tasks unless they are truly required by the client overlay.

## Existing Papers

List known papers to avoid duplicates:

- `/research/example-topic` — Description (ExamplePage.tsx)
