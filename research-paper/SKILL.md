---
name: research-paper
description: Generate dense research-paper-style pages on any topic plus companion X and LinkedIn drafts that keep the same thesis. Use for "research paper", "write a paper on", "research page", "/research-paper", or internal write-ups on a topic, with optional project-specific modes for styling, data sources, and routing.
license: Complete terms in LICENSE
---

# Research Paper Generator

Generate dense, academic research paper-style pages on any topic. Adapts to project context via optional mode files. Pages are noindex, unlinked, for internal reference unless the active mode says otherwise.

Every run produces a companion bundle in this order:
- A canonical research paper (source of truth)
- A companion X article derived from that paper
- A companion LinkedIn article derived from that paper
- A companion LinkedIn post derived from that paper

Do the condensation in that order: research -> paper -> X article -> LinkedIn article -> LinkedIn post. Do not introduce claims in the companion outputs that are not supported by the paper.

## Intent Guardrails

- Keep the research paper as the canonical artifact. The X article and LinkedIn outputs are derivative packaging layers, not second research workflows.
- Use distribution principles to improve scanability, clarity, and shareability of the companion outputs, not to replace evidence with hype.
- Do not expand the default skill into a full content-marketing system (channel calendars, paid plans, multi-platform asset packs) unless the active mode explicitly requires it.

## Modes

Modes customize the skill for specific projects — styling, data sources, routing, paper structure, audience. Stored in `modes/` (gitignored, never committed).

### How Modes Work

Each mode is a markdown file: `modes/{project-name}.md`. The mode file contains everything project-specific: where to write files, how to route them, what data sources to query, what the paper sections look like, and who the audience is.

A mode can also have a subdirectory for project-specific references and assets:

```
modes/
├── my-saas.md                    # Mode instructions
├── my-saas/
│   ├── page-template.tsx         # Project-specific component template
│   └── reference-data.md         # Project-specific reference data
├── my-social-app.md
└── my-social-app/
    └── db-queries.md
```

### Mode Selection (Step 1)

1. List `.md` files in `modes/` (if directory exists)
2. Each mode file should have a `cwd_match` field near the top — a path prefix to match against cwd
3. If cwd matches exactly one mode → use it automatically
4. If cwd matches multiple or none → ask the user which mode (or generic)
5. If `modes/` doesn't exist → generic mode (web research only)

### Creating a Mode

When a user runs the skill with no matching mode, offer to create one. Walk through these questions:

1. **Project name**: kebab-case identifier (becomes filename)
2. **Cwd match**: Path prefix that triggers this mode (e.g. `~/repos/my-app`)
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

Write the mode file to `modes/{project-name}.md` using `references/mode-template.md` as the structure. If the user has project-specific reference data or a component template, create `modes/{project-name}/` and place them there.

## Workflow

```
1. Detect mode (match cwd to modes/ or use generic)
2. Parse topic from arguments
3. Gather data (mode-specific data sources + web research)
4. Research the topic (WebSearch for publications, data, perspectives)
5. Map findings to paper structure
6. Create the companion output briefs
7. Run title / hook passes
8. Write the canonical paper
9. Derive the companion outputs
10. Add routing / registration (if mode requires it)
11. Type-check / validate
12. Post-creation tasks (mode-specific: homepage links, nav updates, manifests, etc.)
```

## Step 2: Parse Topic

Extract the topic from skill arguments. Derive:
- **slug**: kebab-case URL segment (e.g. `creator-economy`, `ai-agents`)
- **display name**: Title case for headings (e.g. "Creator Economy", "AI Agents")
- **component name**: PascalCase for code (e.g. `CreatorEconomyResearchPage`)
- **base output name**: shared basename for paper/article outputs

## Step 3: Gather Data

### With a Mode

Read the mode file. If it specifies data sources (DB queries, reference files, APIs), gather that data now. Read any files in `modes/{project-name}/` that are referenced.

### Generic (No Mode)

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

### With a Mode

Follow the paper section structure defined in the mode file. Map gathered data and research findings to each section.

### Generic (No Mode)

Use the default structure from `references/paper-structure.md`.

## Step 6: Create the Companion Output Briefs

Before writing the companion outputs, define short packaging briefs. These are planning artifacts, not separate deliverables unless the mode explicitly asks for them.

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

If the mode already defines audience or companion defaults, use them. Otherwise infer the briefs from the topic and user context. The briefs shape framing and packaging only; they must not change the thesis or add claims the paper does not support.

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

### With a Mode

Follow the mode's output path, framework patterns, and styling. Read any template in `modes/{project-name}/page-template.*` for structural reference.

If the project exposes human-facing HTML pages that agents will also read, create or update explicit machine-readable alternates (`.md`, `.txt`, or the project's equivalent) instead of relying on user-agent sniffing. Prefer a shared registry/manifest when the project has multiple papers.

### Generic (No Mode)

Write a standalone HTML or markdown file at the user's preferred location. Ask where to put the output bundle if unclear.

### Writing Style (All Modes)

- Dense paragraphs. Data-driven. No fluff.
- Liberal use of em-dashes for asides and clarifications.
- Tables for data-heavy sections (comparison matrices, reference ranges, benchmarks).
- Real numbers from research — not vague qualifiers.
- 600-1000 lines. Prioritize density over brevity.
- Keep the canonical paper dense and research-led. Do not flatten it into a social-first article.
- Put most scanability and packaging optimizations into the companion outputs, not the paper.

If the mode does not define companion output locations, use these defaults beside the paper file:

- **X article**: `{paper-base}.x-article.md`
- **LinkedIn article**: `{paper-base}.linkedin-article.md`
- **LinkedIn post**: `{paper-base}.linkedin-post.md`

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
- Write the draft so sections can be excerpted into other surfaces later, but do not generate a full multi-channel package unless the mode explicitly asks.
- Format for direct paste into [X Articles](https://x.com/compose/articles/edit) unless the mode overrides it.
- Prefer markdown or plain text with clear headings, short paragraphs, and minimal cleanup required before paste.
- If the mode does not specify article routing, treat the article as a draft asset, not a live page.
- If the mode wants a publishable site article too, the X article still has to be generated as a separate derivative unless the mode explicitly says the site article doubles as the X article source.

### Companion LinkedIn Article

Requirements:
- Same core argument as the paper, with stronger professional relevance framing near the top.
- Use the LinkedIn brief to choose one primary reader role, one problem, and one promised outcome.
- Make the first screen explicit about who this is for and why it matters now.
- Optimize for dwell with skimmable structure: strong subheads, short paragraphs, specific examples, and one practical framework/checklist at most.
- Put proof near the top: method, named sources, dataset, case base, or lived experience.
- Keep the tone professional and concrete. Avoid hype, vague inspiration, and generic self-help framing.
- End with one conversation-worthy CTA that invites substantive comments, saves, or sends without engagement bait.
- Treat this as a draft asset unless the mode explicitly routes it into a publishable destination.

### Companion LinkedIn Post

Requirements:
- Distill the paper into one feed post with a clear first-screen hook, one core thesis, and one explicit CTA.
- Default target length is concise enough to skim, but stay within LinkedIn's post limits if the mode says to optimize for direct paste.
- Make the reader fit obvious in the opening lines: role, context, or pain.
- Front-load the payoff, then support it with one short framework, checklist, or proof block.
- Favor simple line breaks, short paragraphs, and plain formatting over clever gimmicks.
- Optional hashtags are allowed only when they improve discoverability or categorization. Keep them limited and place them at the end.
- Do not use engagement bait, vague "thoughts?" prompts, or unsupported performance claims.

Use the default companion output structure in `references/companion-outputs.md` unless the mode overrides it.

## Step 10: Add Routing

Only if the mode specifies routing or registration steps (e.g. "add import to AppRoutes.tsx", "register the paper in a manifest", or "promote the article draft into a blog route"). Skip for file-based routing frameworks and generic mode.

## Step 11: Validate

Run the mode's validation command if specified (e.g. `npx tsc --noEmit`). For generic mode, verify the paper and all companion output files were written correctly.

## Step 12: Post-Creation Tasks

Check the mode file for a "Post-Creation" section. If present, execute every step — these are required, not optional. Common post-creation tasks include adding the paper to a homepage link array, updating a navigation component, registering the paper in a manifest, or appending the X article / LinkedIn drafts to a social/content drafts ledger. **Do not skip this step.** Also update the mode's "Existing Papers" list with the new paper.

If the mode uses machine-readable paper alternates, treat registry updates and discovery surfaces (`llms.txt`, manifests, feed pages) as part of post-creation, not optional cleanup.

For generic mode, skip.

## Output

Report to the user:
- The paper and companion output file paths (and URL paths if applicable)
- Key sections and what they cover
- Notable findings from the research
- The inferred companion briefs (reader, surface, CTA) when they materially shaped the X or LinkedIn drafts
- The chosen X article angle and LinkedIn angle
- Reminder that the paper is noindex / not publicly linked unless the mode says otherwise

Before creating, check if the topic already has a page (per mode's output path pattern). If so, ask whether to update or create a new version. All companion outputs should follow the same update/new-version decision.
