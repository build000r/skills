# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete any sections that don't apply.

---

# {Project Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Output

- **File path**: `src/pages/research/{Name}ResearchPage.tsx`
- **Framework**: React / Next.js / Vue / Svelte / HTML
- **Existing papers command**: `ls src/pages/research/`

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

- **Database**: SSH/docker command to query, or path to cached data file in `modes/{project-name}/`
- **API**: Endpoint + required env var for auth
- **Reference files**: List files in `modes/{project-name}/` to read
- **None**: Skip, use web research only

## Audience

- **Who**: Name/role of primary reader
- **Expertise**: Expert / intermediate / general
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

If you have a component template, place it at `modes/{project-name}/page-template.tsx` (or `.vue`, `.svelte`, `.html`). Reference it here:

```
Read modes/{project-name}/page-template.tsx for the structural template.
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

## Existing Papers

List known papers to avoid duplicates:

- `/research/example-topic` — Description (ExamplePage.tsx)
