---
name: research-paper
description: Generate dense research-paper-style pages on any topic plus companion X and LinkedIn drafts that keep the same thesis. Also has a discover mode that mines recent session activity (via cass) and existing paper coverage to propose accretive topics rooted in actual work. Use for "research paper", "write a paper on", "research page", "/research-paper", "discover topics", "what should I write about", or internal write-ups on a topic, with optional client overlays for styling, data sources, and routing.
license: Complete terms in LICENSE
---

# Research Paper Generator

Generate dense, academic research paper-style pages on any topic. Adapts to project context via optional client overlays. Pages are noindex, unlinked, for internal reference unless the active client overlay says otherwise.

Every run produces a companion bundle in this order:
- A canonical research paper (source of truth)
- A companion X article derived from that paper
- A companion LinkedIn article derived from that paper
- A companion LinkedIn post derived from that paper

Do the condensation in that order: research -> paper -> X article -> LinkedIn article -> LinkedIn post. Do not introduce claims in the companion outputs that are not supported by the paper.

## Intent Guardrails

- Keep the research paper as the canonical artifact. The X article and LinkedIn outputs are derivative packaging layers, not second research workflows.
- Use distribution principles to improve scanability, clarity, and shareability of the companion outputs, not to replace evidence with hype.
- Do not expand the default skill into a full content-marketing system (channel calendars, paid plans, multi-platform asset packs) unless the active client overlay explicitly requires it.

## Client Overlays

Client overlays customize the skill for specific projects — styling, data sources, routing, paper structure, audience. Configuration lives in `skillbox-config/clients/{client}/overlay.yaml`, which is auto-generated into `context.yaml` by the skillbox toolchain.

### How Client Overlays Work

Each client overlay is defined in `skillbox-config/clients/{client}/overlay.yaml`. The overlay contains everything project-specific: where to write files, how to route them, what data sources to query, what the paper sections look like, and who the audience is. The skillbox toolchain merges the overlay with skill defaults and produces a `context.yaml` that the skill reads at runtime.

A client can also have a subdirectory for project-specific references and assets:

```
skillbox-config/clients/
├── my-saas/
│   ├── overlay.yaml                # Client overlay config
│   ├── page-template.tsx           # Project-specific component template
│   └── reference-data.md           # Project-specific reference data
└── my-social-app/
    ├── overlay.yaml
    └── db-queries.md
```

### Client Overlay Selection (Step 1)

1. Check for a `context.yaml` (auto-generated from the active client overlay)
2. If `context.yaml` exists and contains a `cwd_match` field, match it against cwd
3. If cwd matches → use the overlay automatically
4. If no match or no `context.yaml` → create an overlay before proceeding (see "Creating a Client Overlay" below)
5. If no client overlays are configured → create one first, do not fall back to generic mode

### Creating a Client Overlay

When a user runs the skill with no matching client overlay, offer to create one. Walk through these questions:

1. **Client name**: kebab-case identifier (becomes directory name under `skillbox-config/clients/`)
2. **Cwd match**: Path prefix that triggers this overlay (e.g. `~/repos/my-app`)
3. **Output path**: Where to write the page file (e.g. `src/pages/research/{Name}Page.tsx`)
4. **Routing**: How to add the route — file-based (Next.js/Remix), manual (add to routes file), or none
5. **Framework**: React, Next.js, Vue, Svelte, plain HTML, etc.
6. **Styling**: Tailwind classes, CSS modules, styled-components, brand colors
7. **Data sources**: DB queries, APIs, cached reference data, or none (web-only)
8. **Audience**: Who reads these papers — their expertise level and domain
9. **Tone**: Academic, conversational, contrarian, clinical, etc.
10. **Paper sections**: Custom section structure, or use the generic template
11. **Companion X article**: Output path/format/paste contract for the X article draft
12. **Companion LinkedIn outputs**: Output path/format/paste contract for the LinkedIn article and LinkedIn post drafts

Write the client overlay to `skillbox-config/clients/{client-name}/overlay.yaml` using `references/mode-template.md` as a structural reference. If the user has project-specific reference data or a component template, place them in the same client directory.

## Modes

The skill has two modes:

- **Generate mode** (default): A topic is provided. Run the full workflow from Step 2 onward to produce a paper.
- **Discover mode**: No topic is provided, or the user invokes with `discover`, `what should I write about`, `find a topic`, or similar. Run the discovery workflow first (see "Discover Mode" below) to propose 3-5 candidate topics rooted in recent activity and existing coverage gaps. Then, once the user picks one, flow into Generate mode at Step 2.

## Workflow

```
1. Detect client overlay (match cwd to context.yaml or use generic)
   - Also check for MDX pipeline: does content/research/ + pages/research/[slug].tsx exist?
   - If yes, output format is a unified .md file (see "MDX Pipeline" in Step 8)
   - If no topic provided → enter Discover Mode before Step 2
2. Parse topic from arguments (or from Discover Mode selection)
3. Gather data (overlay-specific data sources + web research)
4. Research the topic (WebSearch for publications, data, perspectives)
5. Map findings to paper structure
6. Create the companion output briefs
7. Run title / hook passes
8. Write the canonical paper (unified .md for MDX pipeline, or TSX per overlay)
9. Derive the companion outputs
10. Add routing / registration (MDX: skip — auto-routed; overlay: if required)
11. Type-check / validate
12. Post-creation tasks (MDX: update Obsidian index.md + rebuild; overlay: homepage links, nav updates, etc.)
```

## Discover Mode

Goal: propose accretive topic candidates grounded in the user's actual work — not generic industry trends. Every candidate must build on or extend existing papers AND be rooted in recent real activity.

### Step D1: Inventory existing coverage

For projects using the MDX pipeline:
- Read every `content/research/*.md` file's frontmatter (title, shortTitle, keywords, publishDate)
- Read the `## Website` section's `<ResearchAbstract>` content for each paper
- Read the `## Related` sections to understand the existing graph of cross-references
- Build a compact coverage map: what themes are covered, what the core thesis is for each, when it was written, which papers cite which

Skip the heavy body text — the abstracts and keywords are sufficient for coverage inventory.

For non-MDX projects with a known papers directory, use the same pattern with whatever file structure is in place.

### Step D2: Mine recent activity with cass

Use the `cass` skill/CLI to mine recent session history. Focus on the last 2-4 weeks of work in the relevant repo:

```bash
# Find recent sessions in the target repo
cass search --repo {repo-name} --since 2w

# Extract user prompts (lines 1-3 of each session often contain the best prompts)
cass export --repo {repo-name} --since 2w --format jsonl | jq -r 'select(.type=="user") | .message.content' | head -100
```

Look for:
- **Problems solved repeatedly** — patterns the user hit multiple times
- **Decisions made** — especially contrarian or non-obvious ones recorded in commits, plans, or conversation
- **Frameworks invented in conversation** — concepts that emerged from dialogue, not from research
- **Tools built** — new skills, scripts, or infrastructure the user created
- **Frustrations and workarounds** — real friction points with genuine stakes

If the `cass` CLI is not available in the runtime, fall back to:
- `git log --since="2 weeks ago" --pretty=format:"%s"` in the relevant repo
- Reading `CHANGELOG.md` or recent commits for themes
- Scanning `.claude/projects/*/memory/` files for captured lessons

### Step D3: Find the delta

Cross-reference D1 against D2:

- What recent activity is **not covered** by any existing paper?
- What recent activity **extends** an existing paper's thesis with new evidence?
- What recent activity **contradicts** or complicates a prior paper's framing?
- What patterns appear in the activity that could be generalized into a framework?
- What did the user build that is itself the evidence for a thesis (dogfooded claim)?

### Step D4: Score candidate topics

Generate 5-8 candidate topics. Score each on:

| Criterion | What to evaluate |
|---|---|
| **Groundedness** | Is this rooted in real work the user actually did, not hypothetical? |
| **Accretivity** | Does it build on or extend existing papers rather than duplicate them? |
| **Specificity** | Can concrete, evidence-based claims be made (with real numbers, real artifacts, real conversations)? |
| **Contrarian edge** | Does the user have a non-obvious angle or counter-consensus take? |
| **Evidence-to-thesis ratio** | Is there enough existing evidence to write the paper without inventing data? |

Discard candidates that are generic industry commentary. The user's advantage is that they have **first-person operator evidence** from their actual work — every topic should exploit that.

### Step D5: Present candidates

Return 3-5 top candidates to the user in this format:

```
## Candidate Topics

### 1. {Shortcut title}
**Thesis**: {One sentence — the contrarian claim or framework}
**Grounded in**: {What recent work this draws from — file paths, commits, conversations}
**Builds on**: {Which existing papers it cites/extends, with [[wikilinks]]}
**Evidence ready**: {What concrete artifacts can be cited — tables, benchmarks, case studies}
**Why now**: {What makes this timely}
**Score**: G:5 A:4 S:5 C:4 E:5

### 2. {...}
```

Rank by total score. Include a one-sentence "why not" for any candidates you discarded.

Stop after presenting. Wait for the user to pick one, then flow into Step 2 with the selected topic.

## Step 2: Parse Topic

Extract the topic from skill arguments or from the Discover Mode selection. Derive:
- **slug**: kebab-case URL segment (e.g. `creator-economy`, `ai-agents`)
- **display name**: Title case for headings (e.g. "Creator Economy", "AI Agents")
- **component name**: PascalCase for code (e.g. `CreatorEconomyResearchPage`)
- **base output name**: shared basename for paper/article outputs

## Step 3: Gather Data

### With a Client Overlay

Read the overlay config from `context.yaml`. If it specifies data sources (DB queries, reference files, APIs), gather that data now. Read any files in `skillbox-config/clients/{client-name}/` that are referenced.

### Generic (No Client Overlay)

Skip — proceed directly to web research.

## Step 4: Research the Topic

Use WebSearch to find:
- Published research, whitepapers, or case studies on the topic
- Data points: statistics, trends, benchmarks, real numbers
- Frameworks and models relevant to the topic
- Contrarian perspectives or critiques of mainstream approaches
- Controversies or commonly cited but poorly supported claims

Aim for 5-10 high-quality sources.

## Step 5: Map Findings to Paper Structure

### With a Client Overlay

Follow the paper section structure defined in the client overlay. Map gathered data and research findings to each section.

### Generic (No Client Overlay)

Use the default structure from `references/paper-structure.md`.

## Step 6: Create the Companion Output Briefs

Before writing the companion outputs, define short packaging briefs. These are planning artifacts, not separate deliverables unless the client overlay explicitly asks for them.

Create one brief for the X article and one brief for the LinkedIn outputs. Reuse the same thesis and evidence base, but do not assume both surfaces need identical framing.

Required fields for each brief:
- **Primary reader**: role, context, and sophistication level
- **Reader job**: "When ___, I want to ___, so I can ___"
- **Primary discovery surface**: the one place this draft should feel natively packaged for
- **Credibility requirement**: data, method, lived experience, or named sources needed near the top
- **Share trigger hypothesis**: utility, surprise, identity, concern, or another evidence-backed reason this would travel
- **CTA**: the one action the draft should ask for

For the LinkedIn brief, also define:
- **Professional reader fit**: role, seniority, and the problem the first screen should call out
- **Dwell strategy**: the structure that should keep the right reader moving (framework, teardown, checklist, case breakdown, etc.)
- **Conversation target**: the kind of substantive comment, save, or send behavior the draft should invite without engagement bait

If the client overlay already defines audience or companion defaults, use them. Otherwise infer the briefs from the topic and user context. The briefs shape framing and packaging only; they must not change the thesis or add claims the paper does not support.

## Step 7: Title / Hook Pass

Before writing the bundle, generate candidate titles for the paper and the companion outputs.

For the paper:
- Generate 5 candidate titles and select one with the scorecard below.

For the X article:
- Generate 3-5 title/deck pairs optimized for fast comprehension and scanability.
- The X article title can be more direct and outcome-led than the paper title, but it still has to match the evidence.

For the LinkedIn outputs:
- Generate 3-5 LinkedIn article title/deck pairs optimized for professional relevance, clarity, and dwell.
- Generate 5-8 LinkedIn post opening hooks optimized for first-screen clarity, role fit, and substantive conversation.
- The LinkedIn article and post can be more direct and role-specific than the paper title, but they still have to match the evidence.

Score each title 1-5 on:
- **Specificity**: Includes concrete domain terms, not generic abstractions.
- **Thesis clarity**: States what the paper argues, not just what it discusses.
- **Curiosity/tension**: Creates a reason to click.
- **Scanability**: Easy to parse in one glance.
- **Brevity**: Prefer concise title + subtitle over clause stacking.
- **Audience fit**: Feels native to the reader/job defined in the companion brief.

Selection constraints:
- Prefer 8-16 words total for the paper title.
- Prefer 8-14 words for the X article title, with nuance pushed into an optional deck.
- Prefer 8-16 words for the LinkedIn article title and 1-3 lines for the LinkedIn post hook.
- Avoid more than 2 commas.
- Avoid filler like "comprehensive", "ultimate", "complete guide".
- Keep one contrarian edge or strong claim in the subtitle.
- For the X article, favor simple language and a clear payoff over academic phrasing.
- For LinkedIn, favor explicit role/problem framing over cleverness.

If two titles score similarly and user preference matters, present the top 2 and let the user choose.

## Step 8: Write the Page

Use divide-and-conquer with parallel agents when the bundle requires multiple files (e.g. paper + X article + LinkedIn article + LinkedIn post + route update). Otherwise, single agent.

### MDX Pipeline (projects with MDX research support)

When the project has an MDX research pipeline (i.e. a `content/research/` directory with a `pages/research/[slug].tsx` dynamic route), write ONE unified `.md` file per paper that contains all four versions (website + linkedin article + linkedin post + x article).

**Output path**: `content/research/{slug}.md`

**File structure**: YAML frontmatter + H2 sections delimiting each version.

```markdown
---
title: "Full Academic Title: With Subtitle"
shortTitle: "casual homepage label"       # informal title for homepage listing
status: "thought"                         # "thought" or "v0" (has a live version)
description: "150-200 word abstract for SEO meta tags"
url: "https://example.com/research/{slug}"
author: "Your Name"
publishDate: "2026-04-10"                 # ISO date
version: "Working Paper v1.0"
keywords:
  - keyword one
  - keyword two
section: "Research"
dateLine: "Buildooor Research Brief -- April 2026"
versionHref: "https://example.com"        # optional: link to live product version
---

## Website

<ResearchAbstract>
  ...
</ResearchAbstract>

<ResearchSection number={1} title="...">
  ...
</ResearchSection>

<ResearchReferences>
  ...
</ResearchReferences>

<ResearchColophon citation="..." email="..." />

## LinkedIn Article

{LinkedIn article body — pure markdown, no JSX components}

## LinkedIn Post

{LinkedIn post body}

## X Article

{X article body}

## Related

- [[other-paper-slug]] — one line on how they relate
- [[another-paper-slug]] — another relationship
```

**Critical constraints for the Website section:**

- Use `<ResearchSection>` JSX for subsection headings — NEVER raw `## markdown` headings inside `## Website`. The renderer splits on `^## ` to extract the website section, so nested markdown H2s would break extraction.
- Components available (no imports needed): `<ResearchAbstract>`, `<ResearchSection number={N} title="...">`, `<ResearchTable caption columns rows footnote? compact?>`, `<ResearchCallout>`, `<ResearchReferences>`, `<ResearchColophon citation email>`
- Standard markdown (bold, italic, links, lists) works between components
- **Escape double quotes in JSX attributes**: if a `footnote` or `caption` contains nested `"`, wrap the whole value in `{'...'}` instead of `"..."` to avoid MDX parse errors. Example: `footnote={'This has "quoted" text inside.'}`

**How the renderer reads this file:**

- `lib/research/mdx.ts` parses frontmatter with gray-matter
- Extracts ONLY the `## Website` section (from `## Website` to the next `## ` heading)
- Feeds that to `next-mdx-remote` for server-side MDX compilation
- The LinkedIn, X, and Related sections are invisible to the website build
- The `## Related` section exists purely for Obsidian graph view wikilinks

**Companion outputs live in the same file**, not as separate siblings. There are no `.linkedin-article.md`, `.linkedin-post.md`, or `.x-article.md` files anymore.

**Obsidian workflow**: Open `content/research/` as a vault. Each `.md` file opens as one note with all four versions visible. The `## Related` section powers the graph view. Use wikilinks (`[[slug-name]]`) in the Related section — not in the Website section — since wikilinks don't render on the website.

### With a Client Overlay (non-MDX projects)

Follow the overlay's output path, framework patterns, and styling. Read any template in `skillbox-config/clients/{client-name}/page-template.*` for structural reference.

If the project exposes human-facing HTML pages that agents will also read, create or update explicit machine-readable alternates (`.md`, `.txt`, or the project's equivalent) instead of relying on user-agent sniffing. Prefer a shared registry/manifest when the project has multiple papers.

### Generic (No Client Overlay)

Write a standalone HTML or markdown file at the user's preferred location. Ask where to put the output bundle if unclear.

### Writing Style (All Modes)

- Dense paragraphs. Data-driven. No fluff.
- Liberal use of em-dashes for asides and clarifications.
- Tables for data-heavy sections — use `<ResearchTable>` in MDX projects, raw HTML/Tailwind elsewhere.
- Real numbers from research — not vague qualifiers.
- 600-1000 lines. Prioritize density over brevity.
- Keep the canonical paper dense and research-led. Do not flatten it into a social-first article.
- Put most scanability and packaging optimizations into the companion outputs, not the paper.

For canonical paper structure, use `references/paper-structure.md`. For companion output structure, use `references/companion-outputs.md`.

## Step 9: Derive the Companion Outputs

Turn the paper into companion drafts without changing the thesis.

### Companion X Article

Requirements:
- Same core argument as the paper, with lighter citation density and a stronger narrative opening.
- Use the X brief to choose one primary reader and one primary discovery surface. Do not optimize equally for every channel.
- Deliver the payoff in the first 100-150 words: what the reader will get and why it matters now.
- Add a short trust / credibility stamp near the top (method, dataset, experience, or named source base).
- Make headers read like conclusions and keep paragraphs short enough to scan quickly.
- Preserve the best numbers, the sharpest contrarian point, and one useful framework/table at most.
- End with one explicit next action or question that fits the chosen surface.
- Write the draft so sections can be excerpted into other surfaces later, but do not generate a full multi-channel package unless the client overlay explicitly asks.
- Format for direct paste into [X Articles](https://x.com/compose/articles/edit) unless the client overlay overrides it.
- Prefer markdown or plain text with clear headings, short paragraphs, and minimal cleanup required before paste.
- If the client overlay does not specify article routing, treat the article as a draft asset, not a live page.
- If the client overlay wants a publishable site article too, the X article still has to be generated as a separate derivative unless the client overlay explicitly says the site article doubles as the X article source.

### Companion LinkedIn Article

Requirements:
- Same core argument as the paper, with stronger professional relevance framing near the top.
- Use the LinkedIn brief to choose one primary reader role, one problem, and one promised outcome.
- Make the first screen explicit about who this is for and why it matters now.
- Optimize for dwell with skimmable structure: strong subheads, short paragraphs, specific examples, and one practical framework/checklist at most.
- Put proof near the top: method, named sources, dataset, case base, or lived experience.
- Keep the tone professional and concrete. Avoid hype, vague inspiration, and generic self-help framing.
- End with one conversation-worthy CTA that invites substantive comments, saves, or sends without engagement bait.
- Treat this as a draft asset unless the client overlay explicitly routes it into a publishable destination.

### Companion LinkedIn Post

Requirements:
- Distill the paper into one feed post with a clear first-screen hook, one core thesis, and one explicit CTA.
- Default target length is concise enough to skim, but stay within LinkedIn's post limits if the client overlay says to optimize for direct paste.
- Make the reader fit obvious in the opening lines: role, context, or pain.
- Front-load the payoff, then support it with one short framework, checklist, or proof block.
- Favor simple line breaks, short paragraphs, and plain formatting over clever gimmicks.
- Optional hashtags are allowed only when they improve discoverability or categorization. Keep them limited and place them at the end.
- Do not use engagement bait, vague "thoughts?" prompts, or unsupported performance claims.

Use the default companion output structure in `references/companion-outputs.md` unless the client overlay overrides it.

## Step 10: Add Routing

**MDX pipeline projects**: No routing step needed. The `pages/research/[slug].tsx` dynamic route automatically picks up new `.mdx` files from `content/research/` at build time. A rebuild/redeploy is required for the page to go live.

**Client overlay projects**: Only if the overlay specifies routing or registration steps (e.g. "add import to AppRoutes.tsx", "register the paper in a manifest", or "promote the article draft into a blog route"). Skip for file-based routing frameworks.

**Generic**: Skip.

## Step 11: Validate

Run the client overlay's validation command if specified (e.g. `npx tsc --noEmit`). For generic mode, verify the paper and all companion output files were written correctly.

## Step 12: Post-Creation Tasks

**MDX pipeline projects**: The homepage notes list and API serializer endpoints (`.md`/`.txt`) are auto-generated from the `content/research/` directory at build time. No manual registration is needed there. But the Obsidian index IS manual — if `content/research/index.md` exists, append a row for each new paper to its `## Papers` table. The file is explicitly excluded from the website renderer (`getMdxResearchSlugs` filters out `index.md`), so it exists purely as the Obsidian graph entry point. Missing rows mean the new paper is invisible in the user's vault view even though the website renders it. Pattern:

```markdown
| 2026-04-10 | [[new-paper-slug]] | thought |
```

Append the row after the latest-dated existing row, matching the date-ascending convention. Use `thought` status unless there is a live product version (then use `v0`). Do this for every new paper in the run, not just the last one.

After that, rebuild/redeploy. If the client overlay specifies additional tasks (social drafts ledger, `llms.txt` update), execute those too.

**Client overlay projects**: Check the client overlay for a "Post-Creation" section. If present, execute every step — these are required, not optional. Common post-creation tasks include adding the paper to a homepage link array, updating a navigation component, registering the paper in a manifest, or appending the X article / LinkedIn drafts to a social/content drafts ledger. **Do not skip this step.** Also update the overlay's "Existing Papers" list with the new paper.

If the client overlay uses machine-readable paper alternates, treat registry updates and discovery surfaces (`llms.txt`, manifests, feed pages) as part of post-creation, not optional cleanup.

**Generic**: Skip.

## Output

Report to the user:
- The paper and companion output file paths (and URL paths if applicable)
- Key sections and what they cover
- Notable findings from the research
- The inferred companion briefs (reader, surface, CTA) when they materially shaped the X or LinkedIn drafts
- The chosen X article angle and LinkedIn angle
- Reminder that the paper is noindex / not publicly linked unless the client overlay says otherwise

Before creating, check if the topic already has a page (per the client overlay's output path pattern). If so, ask whether to update or create a new version. All companion outputs should follow the same update/new-version decision.
