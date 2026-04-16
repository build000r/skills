---
name: wiki
description: Maintain a Karpathy-style LLM Wiki in an Obsidian vault. Three operations — ingest (process a source, update concept pages and cross-references), query (answer against the wiki, file good answers back), lint (health-check for contradictions, orphans, staleness). Use for "wiki ingest", "wiki query", "wiki lint", "/wiki", "ingest this source", "what does the wiki say about", "lint the wiki", or when connecting knowledge across repos and skills.
license: Complete terms in LICENSE
---

# Wiki

Maintain a Karpathy-style LLM Wiki in an Obsidian vault. The human curates sources and asks questions. The LLM handles all bookkeeping — summarizing, cross-referencing, filing, updating.

The wiki has three layers:

1. **Raw sources** — symlinks to repo VISION.md and skill SKILL.md files. Immutable.
2. **Wiki** — LLM-owned concept pages that synthesize across sources. The only original content.
3. **Schema** — a CLAUDE.md inside the vault that defines conventions.

## Vault Location

Read the vault's `CLAUDE.md` first. It is the source of truth for page types, directory layout, frontmatter schemas, and conventions. This skill encodes the operations; the schema encodes the structure.

Default vault path: `content/research/`

If working in a different vault, look for a `CLAUDE.md` in the vault root that defines the wiki schema. If none exists, this skill cannot operate — the schema must be written first.

## Operations

The skill has three modes. Determine which from the user's request:

- "ingest", "add source", "process this", "wire up", "new source" → **ingest**
- "what does the wiki say", "query", "look up", "find", "synthesize" → **query** (for deep adversarial synthesis, use `/wiki-forge`)
- "lint", "health check", "audit wiki", "find orphans", "stale" → **lint**

If ambiguous, ask.

### Ingest

**Input:** a source to process. This can be:
- A repo name (looks for symlink in `_sources/repos/{name}.md`)
- A skill name (looks for symlink in `_sources/skills/{name}.md`)
- A path to an external file (read directly, don't symlink unless it has VISION.md/SKILL.md)
- "all" or "all sources" (re-ingest everything in `_sources/`)

**Steps:**

1. Read the vault's `CLAUDE.md` to load conventions
2. Read `index.md` to understand current wiki state
3. If `_ops/focus-sweeps/` exists, read the single `status: active` sweep note if present. Treat it as an operator hint about the current working set, not as source material.
4. Read the source file(s)
5. Scan existing `_concepts/` pages to find which concepts the source touches
6. For each touched concept:
   - Read the concept page
   - Update with new information from the source
   - Add source to `sources:` frontmatter if not listed
   - Flag contradictions explicitly — do not silently overwrite existing claims
   - Add/update wikilinks to related concepts and articles
7. Scan relevant published `/research/*.md` articles for drift against the updated concept layer
   - Classify each finding as either `research discrepancy` or `research improvement opportunity`
   - Do not edit published articles yet; prepare a concise recommendation set for the human
8. If the source introduces concepts not yet covered:
   - Create new concept pages in `_concepts/` following the frontmatter schema
   - Use noun-phrase slugs: `operator-velocity.md`, not `about-operator-velocity.md`
9. Append to `log.md`
10. Regenerate the Concepts and Sources sections of `index.md`

**What NOT to do during ingest:**
- Do not modify source files (they're symlinks to external repos)
- Do not create concept pages for trivial or single-source observations
- Do not duplicate source content — synthesize across sources
- Do not touch the Papers section of `index.md` (owned by research-paper skill)
- Do not rewrite `focus-sweep` notes during routine ingest unless the user explicitly asked to refresh the working set coverage
- Do not silently edit published research articles. Ask first, then patch only with confirmation.

### Query

**Input:** a question about the wiki's knowledge.

**Steps:**

1. Read `index.md` to identify relevant pages
2. If `_ops/focus-sweeps/` exists, read the single active sweep note when it is relevant to the question. Treat it as current-working-set context, not canonical evidence.
3. Read relevant concept pages and source pages
4. Synthesize an answer grounded in wiki content
5. If the answer reveals a gap or novel synthesis:
   - Update an existing concept page, or create a new one
   - Append to `log.md`
   - Update `index.md` if new pages were created
6. If the answer reveals that a published `/research/*.md` article is stale, overstated, or now improvable, surface that explicitly and ask before editing it
7. Return the answer to the user

Prefer updating existing concept pages over creating new ones. A query that touches 1-2 pages is normal; one that creates 5 new pages is suspicious.

### Lint

**Input:** none required, or a specific focus area ("lint sources", "lint orphans").

**Steps:**

1. Read `CLAUDE.md` and `index.md`
2. Scan all `_concepts/` pages and `_sources/` symlinks
3. Check for:
   - **Broken symlinks** — source targets that no longer exist
   - **Stale sources** — check `git log -1 --format=%ci` on each symlink target; flag if changed since last ingest (compare to `log.md`)
   - **Orphan concepts** — concept pages with no inbound wikilinks from other concepts or articles
   - **Sparse concepts** — concept pages with fewer than 2 sources
   - **Missing cross-references** — concepts that discuss overlapping themes but don't link to each other
   - **Index drift** — concept pages that exist on disk but aren't in `index.md`
   - **Contradictions** — claims in one concept that conflict with another or with source material
   - **Article drift** — published `/research/*.md` articles whose thesis, examples, or recommendations lag behind the current concept layer
   - **Research improvement opportunities** — articles that are directionally right but should be deepened or tightened based on newer findings
   - **Focus-sweep hygiene** — more than one `status: active` sweep, no active sweep when the working set clearly changed, or sweep links that point to missing notes
4. Append lint report to `log.md`
5. Present findings to user with suggested fixes
6. Apply fixes only with human confirmation

## Wiring New Sources

When the user wants to add a new repo or skill to the wiki:

**Repo:**
```bash
# From the vault's _sources/repos/ directory
ln -s ../../../../../{repo-name}/docs/VISION.md {repo-name}.md
```

Verify the symlink resolves: `cat _sources/repos/{repo-name}.md | head -1`

If the repo has no `docs/VISION.md`, tell the user. Do not symlink README.md or CLAUDE.md as substitutes.

**Skill:**
```bash
# From the vault's _sources/skills/ directory  
ln -s ../../../../../opensource/skills/{skill-name}/SKILL.md {skill-name}.md
```

After wiring, run ingest on the new source.

## Relationship to Other Skills

- **research-paper**: produces published articles. The wiki feeds it context — concept pages make research-paper's output more grounded. research-paper owns the Papers section of `index.md`.
- **trend-to-content**: identifies what to write about. The wiki answers "what's our angle on X?" from existing concept pages.
- **cass / cass-memory**: mine agent sessions. Session insights can become wiki ingest sources when they surface durable knowledge (not ephemeral debugging).
- **build-vs-clone**: makes placement decisions. Entity knowledge from wiki sources (repo visions, skill capabilities) informs where work should live.
- **power-map**: maps industry power dynamics and challenges customer assumptions for each product. Reads existing wiki positioning (acquisition pages, competitive quadrant, professional monetization) as input, writes updated concept pages and acquisition pages as output. Optionally spawns dueling-idea-wizards to adversarially stress-test positioning. Power map findings are filed as concept pages (`upstream-industry-leverage.md`, product-specific power maps) and acquisition page updates.
- **wiki-forge**: identifies the highest-lever concept in the wiki, runs an adversarial multi-model duel on it, and files the synthesis back. Use when the wiki needs to confront its own assumptions, deepen its most important concept, or stress-test a thesis. wiki-forge reads from and writes back to this wiki.
- **unclawg-discover**: discovery runs queries derived from the wiki's acquisition concept pages (one per product — for example `{product}-acquisition`). The wiki answers "what should we be searching for to get clients for X?" via query against acquisition pages. Discover returns gap signals (high-scoring conversations that matched no product) which can trigger new or updated acquisition pages via ingest. The wiki never generates platform-specific queries — that's overlay generation. The wiki provides product → buyer → pain signal; the overlay translates to platform queries.

## Output

After any operation, report:
- What pages were read
- What pages were created or updated (with diffs if updates)
- What was appended to `log.md`
- Any published-article discrepancies or improvement opportunities that should be discussed before edits
- Any active `focus-sweep` implications the user may want to refresh manually
- Any findings or suggestions for the user
