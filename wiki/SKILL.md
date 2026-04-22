---
name: wiki
description: Maintain a Karpathy-style LLM Wiki in an Obsidian vault. Three operations — ingest (process a source, update concept pages and cross-references), query (answer against the wiki, file good answers back), lint (health-check for contradictions, orphans, staleness). Use for "wiki ingest", "wiki query", "wiki lint", "/wiki", "ingest this source", "what does the wiki say about", "lint the wiki", or when connecting knowledge across repos and skills.
license: Complete terms in LICENSE
---

# Wiki

Maintain a Karpathy-style LLM Wiki in an Obsidian vault. The human curates sources and asks questions. The LLM handles all bookkeeping — summarizing, cross-referencing, filing, updating.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using wiki`.

Preferred format: `Using wiki to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

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
- A note already filed in `_sources/notes/` by another skill run
- An app idea or product-bet note. Run the App Idea Intake Gate before treating it like a normal source.
- A path to an external file (read directly, don't symlink unless it has VISION.md/SKILL.md)
- "all" or "all sources" (re-ingest everything in `_sources/`)

**Steps:**

1. Read the vault's `CLAUDE.md` to load conventions
2. Read `index.md` to understand current wiki state
3. If `_ops/focus-sweeps/` exists, read the single `status: active` sweep note if present. Treat it as an operator hint about the current working set, not as source material.
4. Read the source file(s)
5. If a source is an app idea, product bet, feature bet, or "new repo" concept, run the App Idea Intake Gate before editing concept pages
6. Scan existing `_concepts/` pages to find which concepts the source touches
7. For each touched concept:
   - Read the concept page
   - Update with new information from the source
   - Add source to `sources:` frontmatter if not listed
   - Flag contradictions explicitly — do not silently overwrite existing claims
   - Add/update wikilinks to related concepts and articles
8. Scan relevant published `/research/*.md` articles for drift against the updated concept layer
   - Classify each finding as either `research discrepancy` or `research improvement opportunity`
   - Do not edit published articles yet; prepare a concise recommendation set for the human
9. If the source introduces concepts not yet covered:
   - Create new concept pages in `_concepts/` following the frontmatter schema
   - Use noun-phrase slugs: `operator-velocity.md`, not `about-operator-velocity.md`
10. Append to `log.md`
11. Regenerate the Concepts and Sources sections of `index.md`

#### App Idea Intake Gate

Use this gate when a note proposes a new app, product, feature bet, startup
thesis, "maybe build this" idea, or README/VISION/new-repo direction.

Do not automatically turn app ideas into concept pages, repos, VISION docs, or
README drafts. First decide what kind of object the idea is:

- `park` — too raw, speculative, private, or off-strategy. Recommend moving it
  to `~/notes/`; do not create or update concept pages unless it reveals a
  broader reusable pattern.
- `ingest_as_signal` — the idea is not a product candidate yet, but it sharpens
  an existing concept such as [[operator-portfolio]], [[professional-monetization]],
  [[competitive-quadrant-positioning]], [[skill-as-workflow]], or
  [[decision-grade-analytics]]. Update only the canonical concept page(s).
- `skill_candidate` — the idea is mainly a repeatable operator workflow, admin
  surface, or agent capability. Route to `skill-issue` instead of product docs.
- `readiness_needed` — the idea might be real, but launch, adoption, economics,
  permissions, data, compliance, workflow, or timing prerequisites are unresolved.
  Route through a prerequisite-readiness check when available.
- `build_vs_clone_needed` — the idea is feasible enough to place, but ownership
  and ecosystem fit are still open. Route through `build-vs-clone` before
  deciding existing repo vs cross-repo slice vs new repo vs adopt/borrow/build.
- `vision_candidate` — the idea has a named user, buyer/payer path, trigger,
  proof artifact or usage loop, plausible retention surface, and a placement
  decision. Route to `readme-writing` for `docs/VISION.md` first, then README.

For every app idea gate, record the decision in the ingest notes/log using this
compact shape:

```text
App idea routing:
- target user:
- advocate / buyer / payer:
- trigger:
- paid artifact or usage loop:
- error-cost band:
- adjacent concepts:
- existing surfaces/repos/skills:
- unresolved prerequisites:
- route: park | ingest_as_signal | skill_candidate | readiness_needed | build_vs_clone_needed | vision_candidate
```

If the source lives in `_sources/notes/`, leave it in place for audit even when
the recommended route is `park`; report the recommendation instead of silently
moving or deleting the note.

**What NOT to do during ingest:**
- Do not modify source files (they're symlinks to external repos)
- Do not create concept pages for trivial or single-source observations
- Do not create app-specific concept pages for raw app ideas unless the idea is
  durable enough to become a product/source, or it reveals a cross-source theme
  worth preserving
- Do not draft `README.md` or `docs/VISION.md` during ingest; route qualified
  candidates to `readme-writing` after readiness and build-vs-clone checks
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

## Agent-Authored Notes in `_sources/notes/`

Not every durable source is a symlink. Skills that synthesize external
research, Oracle runs, or adversarial duels should file distilled notes under
`_sources/notes/` and then ingest those notes.

Use filename pattern:

```text
_sources/notes/<skill>-<topic>-<YYYY-MM-DD>.md
_sources/notes/app-idea-<topic>-<YYYY-MM-DD>.md
```

Each note should include enough metadata for later audit:

- originating skill / run
- question or thesis being tested
- key findings
- source links and/or session IDs
- affected concept pages and published articles
- for app ideas: target user, advocate/buyer/payer, trigger, paid artifact or
  usage loop, prerequisite risks, build-vs-clone placement hypothesis, and the
  intended route

Prefer ingesting the distilled note, not a raw browser transcript and not the
final published paper. The note is the bridge between live research and the
wiki concept layer.

## Relationship to Other Skills

- **research-paper**: produces published articles. The wiki feeds it context — concept pages make research-paper's output more grounded. research-paper should file a distilled note to `_sources/notes/` and ingest it after each substantive paper run. research-paper owns the Papers section of `index.md`.
- **readme-writing**: VISION-grade README / positioning work should query the wiki first, then file any durable external research findings to `_sources/notes/` and ingest them before patching docs.
- **trend-to-content**: identifies what to write about. The wiki answers "what's our angle on X?" from existing concept pages.
- **cass / cass-memory**: mine agent sessions. Session insights can become wiki ingest sources when they surface durable knowledge (not ephemeral debugging).
- **build-vs-clone**: makes placement decisions. Entity knowledge from wiki sources (repo visions, skill capabilities) informs where work should live. When build-vs-clone runs Deep Research, file the durable findings to `_sources/notes/` and ingest them.
- **prerequisite-readiness**: when available, classifies app ideas and product
  bets as `real_node`, `ripening_node`, `phantom_node`, or `build_the_parent`
  before the wiki treats them as buildable product candidates.
- **skill-issue**: app ideas that are really reusable agent/admin workflows
  should become skill candidates, not product READMEs.
- **power-map**: maps industry power dynamics and challenges customer assumptions for each product. Reads existing wiki positioning (acquisition pages, competitive quadrant, professional monetization) as input, writes updated concept pages and acquisition pages as output. Optionally spawns dueling-idea-wizards to adversarially stress-test positioning. Power map findings are filed as concept pages (`upstream-industry-leverage.md`, product-specific power maps) and acquisition page updates.
- **wiki-forge**: identifies the highest-lever concept in the wiki, runs an adversarial multi-model duel on it, optionally finishes with a Pro / Deep Research pass, and files the result back. Use when the wiki needs to confront its own assumptions, deepen its most important concept, or stress-test a thesis. wiki-forge reads from and writes back to this wiki.
- **unclawg-discover**: discovery runs queries derived from the wiki's acquisition concept pages (one per product — for example `{product}-acquisition`). The wiki answers "what should we be searching for to get clients for X?" via query against acquisition pages. Discover returns gap signals (high-scoring conversations that matched no product) which can trigger new or updated acquisition pages via ingest. The wiki never generates platform-specific queries — that's overlay generation. The wiki provides product → buyer → pain signal; the overlay translates to platform queries.

## Output

After any operation, report:
- What pages were read
- What pages were created or updated (with diffs if updates)
- What was appended to `log.md`
- Any published-article discrepancies or improvement opportunities that should be discussed before edits
- Any active `focus-sweep` implications the user may want to refresh manually
- Any findings or suggestions for the user

## Verification / Closeout Contract

For skill-contract edits, rerun:

```bash
python3 skill-issue/scripts/quick_validate.py wiki
```

Before returning, confirm all of the following:

1. The vault schema (`CLAUDE.md`) and current index were read first.
2. The operation mode and source type were identified correctly.
3. Any concept/log/index updates were completed and reported explicitly.
4. Published article drift was surfaced without silently editing those
   articles.
5. If the source was a note in `_sources/notes/`, it was treated as a source
   artifact and left in place for future audit.
