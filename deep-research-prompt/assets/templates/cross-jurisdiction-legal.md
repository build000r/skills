# Cross-jurisdiction legal research template

Specialization of `n-entity-structured.md` for state-by-state or country-by-country legal research. Start from the generic N-entity skeleton, then add the legal-specific fields and constraints below.

## Extra required fields per jurisdiction

Beyond the generic N-entity fields, include:

1. **Governing framework.** Which statute(s), act, chapter, or code section? If the topic is split across multiple chapters (e.g., condominium law vs. planned-community law, civil vs. administrative code, state vs. federal), name ALL relevant chapters — they may be separate pages in the downstream taxonomy.

2. **Rule posture classification.** Assign each jurisdiction to a discrete category from an enumerated list. Typical values: `mandatory | elective | silent | hybrid | in-transition`. Enumerate the valid values explicitly in the prompt so the research agent does not invent new ones.

3. **Mechanism details.** Vote thresholds, procedural requirements, timing windows, who has standing, what remedies exist. Be specific. "A majority vote" is not enough — specify whether that is a majority of total members, a majority at a quorum-attaining meeting, a supermajority of board, etc.

4. **Formula or study requirements.** If the statute prescribes a calculation or requires a study, capture the formula shape and whether the output is binding on decision-makers.

5. **Applicability scope.** Which entities does the rule apply to? Size thresholds, formation-date cutoffs, declarant-control carve-outs, opt-in / opt-out provisions, community-type splits. **This is the single most frequently missed field and the one that most commonly makes downstream pages wrong.** A rule that says "applies to associations formed after January 1, 1999" cannot be summarized as "the rule in State X is..." without qualification.

6. **Framework transitions.** Is the jurisdiction in the middle of a statutory change? Effective dates, repeal dates, which entities the transition affects, and what changes. Examples worth surfacing: legacy chapter repeals with future effective dates, statutes that phase in by community age, pending amendments in active legislative session.

7. **"What is actually different about THIS jurisdiction"** — one to three sentences naming concrete operational differences that matter. If the research agent cannot articulate a concrete difference, the jurisdiction may not deserve a standalone downstream page under this topic — recommend exclusion instead of writing a thin page.

8. **Primary source URL.** A direct link to statute text on an official legislature, state-code, or state-agency domain. `.gov` or equivalent official domains only. NOT LexisNexis, Westlaw, Justia, FindLaw, Casetext, HOA-industry blogs, law-firm marketing pages, or state-bar CLE materials.

9. **Draft applicability sentence.** A single sentence, 40+ characters, suitable for a frontmatter field or callout on the downstream page. Name the governing chapter and the scope limit in plain language. Example format: "Florida Chapter 720 planned-community HOAs only. Does not cover condominiums under Chapter 718 — the post-Surfside structural-integrity reserve study rules apply to condos, not HOAs."

## Extra hard constraints beyond the generic stanza

- Do not invent case citations, section numbers, or effective dates. If you cite a statute, the URL must actually open to that statute.
- Jurisdictions with separate chapters for different community types (e.g., HOA vs. condo) get separate answers for each chapter. Do not collapse them into one row.
- Be honest about framework complexity. Active statutory transitions, pre/post-enactment applicability, and chapter splits are real. Do not flatten them.
- Pending legislation is not law. Note it in the appendix, not in the main per-jurisdiction entries.

## Calibration example pattern

If an anchor page already exists for one jurisdiction in the downstream project, reference it as a calibration example in the Context section. Tell the research agent to match its mechanical specificity but not copy its prose.

Example wording:

> An anchor page already exists for [JURISDICTION] ([GOVERNING FRAMEWORK], [STATUTE SECTION]), grounded on these facts: [2-4 concrete facts the research agent can use to check against its own findings for the anchor jurisdiction]. Use [JURISDICTION] as calibration for the level of mechanical specificity required. Do not copy its prose.

Calibration examples serve two purposes: they tell the agent what "good" looks like, and they let you spot-check the output by reading the anchor jurisdiction first — if the agent got the anchor wrong, trust no other rows.

## Red flags to name in post-block notes

Tell the user to watch for:

1. **Confidence inflation.** Real 50-jurisdiction legal research hits uncertainty frequently. A report with 40+ jurisdictions marked high-confidence is a report with fabricated authority somewhere. Distrust.
2. **Condo/HOA collapse.** If the research conflates condominium and planned-community regimes for a state that splits them (FL, WA, NC, and others), the downstream pages will be wrong. Spot-check the split states first.
3. **Stale transition data.** States with active framework changes (repeal dates, effective dates) are where bad reports break first. If the agent cites a statute that was repealed or is about to be, the page will age out fast.

## What this template does NOT cover

- Pending legislation or ballot measures — those are appendix material, not per-jurisdiction entries
- Administrative guidance that contradicts statute — flag as an open question for human review
- Case-law-driven variations within a state — this template is statute-centric; case-law research is a separate task
