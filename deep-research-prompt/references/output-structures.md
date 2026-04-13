# Output structures for deep research prompts

Pick the structure that matches the task shape, then fill in the template. Most tasks fit N-entity structured. Use the others as specializations.

## N-entity structured report

**When to use:** you have N discrete entities (states, competitors, products, papers, companies, regulations) and you want the same set of fields filled in for each, plus cross-entity synthesis.

**Shape:**

- Executive summary (300-500 words): clusters, outliers, recommended exclusions, common misconceptions
- Cross-entity comparison table: one row per entity, 4-6 columns for at-a-glance scanning
- Entity-by-entity detail: 8-15 fields per entity, same field set for every entity
- Appendix A — entities recommended for exclusion: entities where the topic does not meaningfully apply
- Appendix B — entities flagged for human review: low-confidence or actively-changing entities
- Appendix C — timeline or dependency list: time-sensitive items downstream work needs to know about

**Anti-pattern:** producing N entity sections without an executive summary or cross-entity comparison. That is a list, not a report. Force the synthesis step.

## Cross-jurisdiction legal research

**When to use:** specialization of N-entity for state-by-state or country-by-country legal research.

**Extra required fields per jurisdiction beyond generic N-entity:**

- Governing framework (chapter, act, section citations) — name both chapters if the topic is split (e.g., HOA vs. condominium statutes)
- Rule posture classification (mandatory / elective / silent / hybrid / in-transition)
- Mechanism details (vote thresholds, procedural requirements, timing)
- Applicability scope (which communities, size thresholds, cutoff dates, opt-in/opt-out)
- Framework transitions (active repeals, effective dates, which communities affected)
- Primary source URL (legislature/official domain only — `.gov` or equivalent)
- "What is actually different about this jurisdiction" — forces the agent to name concrete operational differences, defends against slop

Full template at `assets/templates/cross-jurisdiction-legal.md`.

## Academic literature map

**When to use:** the user wants to understand the state of research on a topic. N = papers.

**Fields per paper:**

- Full citation (authors, year, venue)
- DOI or permanent URL on an academic domain
- Methodology classification
- Key findings (2-3 bullets)
- Backward citations (what it builds on)
- Forward citations (what builds on it), if computable
- Position in the debate: consensus / dispute / outlier
- Confidence the paper was read vs. skimmed

**Extra synthesis sections:**

- Consensus claims (where multiple papers agree)
- Dispute zones (where the literature is actively split)
- Methodology clusters
- Gaps the literature has not addressed

**Source authority:** peer-reviewed venues, preprint servers (arXiv, bioRxiv, SSRN) with version noted, institutional repositories. NOT blogs, press coverage, or AI-generated summaries.

## Competitive intelligence sweep

**When to use:** the user wants to understand a handful of companies or products in a market. N = companies.

**Fields per company:**

- Official name and primary URL
- Positioning statement (quoted from their own site)
- Pricing (public tiers with URLs)
- Product surfaces (features, modules, integrations)
- Go-to-market (segments served, acquisition channels if observable)
- Recent public announcements (last 12 months, dated)
- Named public customers (from their own reference pages)
- Data freshness assessment (scraped-from-site-today vs. older sources)

**Source authority:** the company's own domain, SEC filings for public companies, press releases from recognized wires, verifiable customer reference pages. NOT Crunchbase summaries (often stale), NOT unverified LinkedIn posts, NOT industry analyst reports behind paywalls.

**Red flag to call out:** companies that have recently restyled their marketing may have stale data in aggregators. Cross-check against the company's own site and note the freshness gap.

## Decision-support research

**When to use:** the user is choosing between a small number of options and wants research to inform the decision.

**Shape:**

- Options-by-criteria matrix (options as rows, criteria as columns)
- One detailed section per option
- One section per criterion explaining how it was weighted
- Final recommendation with the trade-off it accepts

**Constraint:** the research agent must state which criteria are most load-bearing and flag where two criteria trade off against each other. A research report that ranks options without naming trade-offs is not useful for decision-making.

## Custom structure

If the task does not fit any of the above, construct from first principles using the SKILL.md contract:

- Role + mission
- Context
- Research questions (numbered, concrete)
- Output format (shown, not described)
- Hard constraints
- What to report back

Most "custom" tasks turn out to be N-entity with an unusual field set. Default to N-entity before going fully custom.
