---
name: research-paper
description: >
  Generate dense, academic research paper-style pages on any topic.
  Use when: "research paper", "write a paper on", "research page", "/research-paper",
  "internal paper on", "write up on [topic]".
  Supports project-specific modes (styling, data sources, routing) via local `modes/` directory.
  Takes a topic argument (e.g. "teeth", "longevity", "AI agents", "SaaS pricing").
license: Complete terms in LICENSE
---

# Research Paper Generator

Generate dense, academic research paper-style pages on any topic. Adapts to project context via optional mode files. Pages are noindex, unlinked, for internal reference.

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

Write the mode file to `modes/{project-name}.md` using `references/mode-template.md` as the structure. If the user has project-specific reference data or a component template, create `modes/{project-name}/` and place them there.

## Workflow

```
1. Detect mode (match cwd to modes/ or use generic)
2. Parse topic from arguments
3. Gather data (mode-specific data sources + web research)
4. Research the topic (WebSearch for publications, data, perspectives)
5. Map findings to paper structure
6. Write the page using divide-and-conquer
7. Add routing (if mode requires it)
8. Type-check / validate
```

## Step 2: Parse Topic

Extract the topic from skill arguments. Derive:
- **slug**: kebab-case URL segment (e.g. `creator-economy`, `ai-agents`)
- **display name**: Title case for headings (e.g. "Creator Economy", "AI Agents")
- **component name**: PascalCase for code (e.g. `CreatorEconomyResearchPage`)

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

## Step 6: Write the Page

Use divide-and-conquer with parallel agents when the mode requires multiple files (e.g. page + route update). Otherwise, single agent.

### With a Mode

Follow the mode's output path, framework patterns, and styling. Read any template in `modes/{project-name}/page-template.*` for structural reference.

### Generic (No Mode)

Write a standalone HTML or markdown file at the user's preferred location. Ask where to put it if unclear.

### Writing Style (All Modes)

- Dense paragraphs. Data-driven. No fluff.
- Liberal use of em-dashes for asides and clarifications.
- Tables for data-heavy sections (comparison matrices, reference ranges, benchmarks).
- Real numbers from research — not vague qualifiers.
- 600-1000 lines. Prioritize density over brevity.

## Step 7: Add Routing

Only if the mode specifies routing steps (e.g. "add import to AppRoutes.tsx" or "register in config"). Skip for file-based routing frameworks and generic mode.

## Step 8: Validate

Run the mode's validation command if specified (e.g. `npx tsc --noEmit`). For generic mode, verify the file was written correctly.

## Output

Report to the user:
- The file path (and URL path if applicable)
- Key sections and what they cover
- Notable findings from the research
- Reminder that it's noindex / not publicly linked (if applicable)

Before creating, check if the topic already has a page (per mode's output path pattern). If so, ask whether to update or create a new version.
