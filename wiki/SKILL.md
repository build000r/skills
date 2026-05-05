---
name: wiki
description: >-
  Maintain a Karpathy-style LLM Wiki in an Obsidian vault. Default bare
  invocation ("wiki", "/wiki", "$wiki", or a wiki tag with no operation) runs
  orient mode: reality-check the vault, choose one smart wiki goal, and get to
  work on the safest highest-leverage wiki operation. Also use for "wiki
  ingest", "wiki query", "wiki lint", "ingest this source", "what does the
  wiki say about", "lint the wiki", or when connecting knowledge across repos
  and skills.
depends_on:
  - reality-check-for-project
  - smart
  - wiki-dry
  - wiki-forge
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

## Default Posture

Bare wiki invocation is an instruction to orient, choose a smart wiki goal, and
act. Do not ask "what should I do with the wiki?" just because the user omitted
an operation. Treat the vault like a project whose promise is defined by its
schema, index, sources, concept layer, log, exclusions, focus sweeps, and
published-article relationships.

Use a reality-check-for-project style lens:

- What is working in the vault right now?
- What is stale, sparse, contradictory, orphaned, unindexed, or unlogged?
- What source, note, concept, or article relationship is blocking the wiki from
  being useful as an operator knowledge system?
- What single action would most improve the wiki's truthfulness, connectivity,
  or strategic leverage today?

Then apply the smart rule: pick one move, name the success criteria, and execute
the safest concrete wiki operation that advances it. Ask only when the next
action would publish, move, delete, override an active exclusion, create a
buildable product route from an app idea, or when the evidence leaves a genuinely
irreducible choice between incompatible operations.

Treat `wiki-dry` and `wiki-forge` as final escalation routes, not the default
first move. Reach for them after the orient scan has identified a structural or
strategic gap that ordinary ingest/query/lint work will not resolve.

## Vault Location

Read the vault's `CLAUDE.md` first. It is the source of truth for page types, directory layout, frontmatter schemas, and conventions. This skill encodes the operations; the schema encodes the structure.

### Resolving the target vault

Vaults are resolved through the operator-wide registry at `~/repos/skillbox-config/wikis.yaml`, which points at per-client overlays under `clients/{client}/wikis.yaml`. Resolution order:

1. **Explicit `--vault=<id>`** — search across `client_wiki_overlays` in the top-level `wikis.yaml` for the matching wiki id; load that client's `wikis.yaml`; use its `path`.
2. **Implicit by `cwd`** — if the current working directory is inside any per-client overlay's `wikis[].path`, use that vault.
3. **`defaults.default_vault`** — fall back to the registry's default vault (resolved through the same client-overlay lookup).
4. **Legacy fallback** — if no registry exists, use `content/research/` relative to cwd.

If the registry exists, prefer it. If the resolved path has no `CLAUDE.md`, this skill cannot operate — the schema must be written first.

### Autoblog awareness (REQUIRED before any write or move)

Every per-client wiki overlay declares an `autoblog_sources:` list. Before writing, moving, archiving, or migrating any file inside a wiki path, check whether the destination (and source) intersects an autoblog source:

1. Resolve the wiki's per-client overlay (`clients/{client}/wikis.yaml`).
2. For each entry in `autoblog_sources`, check whether the planned operation's path matches the `path` + `glob` pattern.
3. If yes, surface the entry's `published_to`, `triggered_by`, and `publication_gate` to the user before acting. Do not proceed silently.
4. If the operation would *remove* a file from an autoblog path that is *not* gated (`publication_gate: none`), warn that the published URL will start 404'ing on next build.
5. If the operation would *add* a file to a non-gated autoblog path, warn that it will publish on next build.
6. Files in `safe_zones:` skip this check.

Symlinks need extra care: a symlink in `_sources/articles/` pointing into `content/articles/heavy-metals.md` does not itself publish, but editing the *target* publishes — because the target is the production markdown.

### Multi-vault operations

When a request implies cross-vault work (`wiki list`, `wiki lint --all`, `wiki migrate --from=X --to=Y`), iterate over the registry. Each vault is operated on under its own local `CLAUDE.md` schema; do not assume one schema across vaults.

## Operations

The skill has five primary modes plus two registry-aware modes. Determine which from the user's request:

- Bare "wiki", "/wiki", "$wiki", "tag wiki", "wiki do your thing", or no explicit operation → **orient** (default; do not ask)
- "ingest", "add source", "process this", "wire up", "new source" → **ingest**
- "what does the wiki say", "query", "look up", "find", "synthesize" → **query** (for deep adversarial synthesis, use `/wiki-forge`)
- "lint", "health check", "audit wiki", "find orphans", "stale" → **lint** (add `--all` to lint every registered vault)
- "exclude", "park this", "mark as rejected", "don't consider", "tried and rejected" → **exclude**
- "list wikis", "which wikis", "show registry" → **list** (read `wikis.yaml`, report each wiki's id/role/path/parent and flag any registered path that is missing or any unregistered Obsidian vault discovered under a registered tree)
- "migrate concept", "move to child wiki", "promote to parent" → **migrate** (move a concept page between vaults, rewriting frontmatter to the destination's `schema_dialect` and leaving a breadcrumb cross-link in the source)

If the request is operation-free, use orient mode. If the request names multiple
incompatible operations or the safe next write is blocked by autoblog,
exclusion, migration, deletion, or app-idea gates, ask the smallest direct
question needed to proceed.

### Orient (default for bare wiki)

**Input:** no explicit operation, or a broad instruction to work on the wiki.

**Goal:** run a reality-check on the vault, derive one smart wiki goal, and do
the highest-leverage safe operation without waiting for the human to choose a
mode.

**Steps:**

1. Resolve the target vault, then read the vault's `CLAUDE.md` first.
2. Read `index.md`, the recent end of `log.md`, `_ops/exclusion-ledger.md` if
   it exists, and the single active `_ops/focus-sweeps/` note if present.
3. Check autoblog sources before planning any write, move, archive, or
   migration.
4. Build a compact **Wiki Reality Checklist** from the schema and current vault:
   sources resolve, source changes are ingested, note sources are routed,
   concept pages are indexed, important concepts are cross-linked, exclusions are
   not stale, and published articles are not drifting from the concept layer.
5. Run the smallest evidence scan needed for that checklist:
   - source symlink health
   - source target freshness against recent `log.md`
   - concept/index drift
   - sparse or orphan concept indicators
   - unlogged `_sources/notes/`
   - article drift or improvement opportunities, reported without silent edits
6. Pick exactly one smart wiki goal from the evidence. Prefer goals that make
   the wiki more truthful, connected, and reusable across future skills or repo
   decisions. Do not present a menu.
7. Execute one safe operation end-to-end. Priority order:
   - ingest or route unlogged note sources
   - ingest a clearly stale source
   - update an existing concept with a clear source-backed synthesis
   - repair index/log drift
   - run lint and report fixes when the remaining fixes require confirmation
8. Pause only when the next action would publish, move, delete, override an
   active exclusion, route an app idea into buildable product work, or choose
   between genuinely tied incompatible goals.
9. Run the final escalation check:
   - If the evidence shows concept duplication, sprawl, weak abstraction
     boundaries, or repeated frameworks across pages, route the next step to
     `/wiki-dry --target wiki --mode audit`.
   - If the evidence shows one high-leverage concept with unresolved strategic
     tension, contradiction, or untested assumptions, route the next step to
     `/wiki-forge`.
   - If neither condition is present, do not force an escalation.
10. Close out with:
   - reality-check takeaway
   - smart wiki goal
   - operation performed
   - final escalation route, if any
   - pages read
   - pages created or updated
   - `log.md` and `index.md` updates
   - published-article drift or improvement opportunities
   - any blocker and exact resume condition

If orient mode reveals multiple strategic moves that are truly tied, route the
decision through `/wiki-forge` or `/wiki-duel` instead of guessing.

### Cross-vault lint additions (when `--all` is used)

In addition to each vault's own lint checks, also flag:

- **Unregistered vaults** — directories under a registered vault's tree that contain `.obsidian/` but are not themselves the registered vault. These are "phantom vaults" (see `wikis.yaml > phantoms:`).
- **Stale registry entries** — registry paths that no longer resolve.
- **Cross-vault link drift** — breadcrumbs of the form "See <id> wiki: [[slug]]" where the target slug no longer exists in the named vault.

### Ingest

**Input:** a source to process. This can be:
- A repo name (looks for symlink in `_sources/repos/{name}.md`)
- A skill name (looks for symlink in `_sources/skills/{name}.md`)
- A note already filed in `_sources/notes/` by another skill run
- An app idea or product-bet note. Run the App Idea Intake Gate before treating it like a normal source.
- A path to an external file (read directly, don't symlink unless it has VISION.md/SKILL.md)
- "all" or "all sources" (re-ingest everything in `_sources/`)

If the user says only `wiki ingest` or otherwise omits a source, do not silently map the request to the cwd repo. First inspect `_sources/notes/` for files modified since the last relevant ingest log entry, unlisted in `index.md`, or not mentioned in `log.md`. If recent/unlogged notes exist, treat them as the candidate source set and ingest or route them before falling back to the cwd repo source. Only use the cwd repo source as the implicit target when no newer or unlogged note source is present.

**Steps:**

1. Read `_ops/exclusion-ledger.md` if it exists. For each concept the source
   would plausibly touch, check for active exclusions:
   - If excluded and `reconsider_after` has NOT passed: warn the operator
     "`{concept}` was excluded on {date} by {source}: {reason}. Override and
     ingest?" If declined, skip writes to that concept and log
     `exclusion: upheld`.
   - If excluded and `reconsider_after` HAS passed: note "`{concept}`
     exclusion expired — proceeding. Updating ledger status to `reconsidered`."
     Flip the row's `status` to `reconsidered` before continuing. If the
     ingest subsequently writes a real update to the concept, the Exclude
     operation's status lifecycle (see "Exclusion Ledger Format") flips the
     row to `readmitted` at close-out.
2. Read the vault's `CLAUDE.md` to load conventions
3. Read `index.md` to understand current wiki state
4. If `_ops/focus-sweeps/` exists, read the single `status: active` sweep note if present. Treat it as an operator hint about the current working set, not as source material.
   When the source was implicit, record the note-source discovery result in the closeout even if no notes were selected.
5. Read the source file(s)
6. If a source is an app idea, product bet, feature bet, or "new repo" concept, run the App Idea Intake Gate before editing concept pages
7. Scan existing `_concepts/` pages to find which concepts the source touches
8. For each touched concept:
   - Read the concept page
   - Update with new information from the source
   - Add source to `sources:` frontmatter if not listed
   - Flag contradictions explicitly — do not silently overwrite existing claims
   - Add/update wikilinks to related concepts and articles
9. Scan relevant published `/research/*.md` articles for drift against the updated concept layer
   - Classify each finding as either `research discrepancy` or `research improvement opportunity`
   - Do not edit published articles yet; prepare a concise recommendation set for the human
10. If the source introduces concepts not yet covered:
    - Create new concept pages in `_concepts/` following the frontmatter schema
    - Use noun-phrase slugs: `operator-velocity.md`, not `about-operator-velocity.md`
11. Append to `log.md`
12. Regenerate the Concepts and Sources sections of `index.md`

#### App Idea Intake Gate

Use this gate when a note proposes a new app, product, feature bet, startup
thesis, "maybe build this" idea, or README/VISION/new-repo direction.

Do not automatically turn app ideas into concept pages, repos, VISION docs, or
README drafts. First decide what kind of object the idea is:

- `park` — too raw, speculative, private, or off-strategy. Recommend moving it
  to `~/notes/`; do not create or update concept pages unless it reveals a
  broader reusable pattern. Also append one row to `_ops/exclusion-ledger.md`:
  `| {concept_key} | {today} | intake_gate | {routing reason, ≤120 chars} | {+90d} | active |`
  so the parking reasoning is not lost to append-only `log.md` prose.
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
   - **Skill-hub backlinks** — every skill source in `_sources/skills/` must contain a `[[skill-issue]]` wikilink so the skill cluster traces back to the meta-skill hub. Resolve each symlink and grep the target `SKILL.md`; flag any skill (other than `skill-issue` itself) that omits the backlink. Suggested fix: append a `## Related` section with `- [[skill-issue]]` (or add the bullet to an existing `## Related`).
   - **Exclusion staleness** — scan `_ops/exclusion-ledger.md` for rows whose `reconsider_after` has passed while `status` is still `active`. These are former NO decisions due for re-evaluation. Suggested fix: run `/wiki ingest` on the excluded concept (which will flip the row to `reconsidered` via ingest step 1) or extend the `reconsider_after` date with a short justification appended to the reason cell.
4. Append lint report to `log.md`
5. Present findings to user with suggested fixes
6. Apply fixes only with human confirmation

### Exclude

Records a concept or topic as explicitly excluded from the wiki. Use when the
operator wants to mark a direction as tried-and-rejected or out-of-scope. The
ledger is the wiki's anti-knowledge artifact — it remembers what was
considered and rejected so the same ground is not re-walked without
acknowledgment.

**Input:** a concept key and reason. Optionally a `reconsider_after` date
(defaults to `+90d` from today).

**Steps:**

1. Read `_ops/exclusion-ledger.md` (create the file with a one-row header if
   absent — see "Exclusion Ledger Format" below).
2. Check if `concept_key` already has an active entry:
   - If yes and `status: active`: update reason and `reconsider_after` in
     place rather than appending a duplicate row.
   - If yes and `status: readmitted`: warn the operator "This concept was
     previously readmitted on {date} — excluding again will re-open the
     rejection." Require explicit confirmation before writing.
3. Append a row:
   `| {concept_key} | {today} | operator | {reason} | {reconsider_after or +90d} | active |`
4. If `_concepts/{concept_key}.md` exists, add `excluded: true` to the
   frontmatter and prepend `> **Excluded {date}:** {reason}` to the body.
   Do NOT delete the concept page — exclusion is reversible.
5. Append to `log.md`.

### Exclusion Ledger Format

`_ops/exclusion-ledger.md` is a single markdown table:

```markdown
# Exclusion Ledger

| concept_key | excluded_at | source | reason | reconsider_after | status |
|---|---|---|---|---|---|
```

- `source` is one of: `operator`, `intake_gate`, `forge_kill`.
- `status` values: `active` → `reconsidered` → `readmitted`. Entries stay
  `active` indefinitely until lint surfaces staleness or an ingest
  readmits them.
- When a `reconsidered` entry leads to a successful ingest, flip status to
  `readmitted` and append the readmission date to the reason cell.

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

## Related

- [[skill-issue]]
