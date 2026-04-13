# N-entity structured research prompt template

Starting skeleton for any task where N discrete entities get the same set of fields researched, plus cross-entity synthesis. Replace bracketed placeholders with task-specific content before shipping.

---

```
You are a [DOMAIN]-research agent. Your sole task is to produce one structured research report on [SUBJECT] — for [ENTITY SET, e.g., "all 50 US states plus DC" or "the following N companies"] — so a downstream [CONSUMER, e.g., "content team" or "decision owner"] can [DOWNSTREAM ACTION] without redoing the research. You produce facts and citations. You do NOT [EXCLUDED ACTION, e.g., "write finished prose" or "make the decision yourself"].

## Context

[2-4 short paragraphs explaining why this research exists, who uses the output, and what calibration examples look like. Include a named example of the level of specificity you expect — ideally a real entity from the set the agent can reference. If an anchor page/example already exists in the project, quote it and say: "Use [entity name] as calibration for the level of mechanical specificity required. Do not copy its prose."]

## The research question

For each of the [N] entities, answer:

1. **[Field 1 name].** [What it captures. Include an example value format.]

2. **[Field 2 name].** [If this is a classification, enumerate the valid values explicitly.]

3. **[Field 3 name].** ...

(Continue to 8-12 fields total. Depth per field beats breadth. Resist the urge to add a 13th field "just in case.")

N. **Primary source URL.** A direct link on [AUTHORIZED DOMAIN CLASS, e.g., "official state legislature or state-code domains"]. NOT [DISALLOWED DOMAIN CLASS 1 — by name], NOT [DISALLOWED CLASS 2 — by name]. If the only reachable copy is on an aggregator, note it as a secondary source and flag the gap.

N+1. **Confidence / open questions.** Honest assessment of what could not be verified, what required inference, and what a human [DOMAIN EXPERT] would need to check before [DOWNSTREAM ACTION].

## Output format — exactly one markdown document

Structure it like this:

# [SUBJECT] — [N]-entity research report

## Executive summary
300-500 words. Cluster entities by [PRIMARY DIMENSION]. Name outliers. Call out entities where the topic does not meaningfully exist and should be excluded from downstream work. Identify the 2-3 entities where [COMMON MISCONCEPTION FOR THIS DOMAIN] is most likely, so downstream writers know where to add myth-busting.

## Cross-entity comparison table
A single table with these columns, [N] rows in [ORDERING, e.g., "alphabetical"] order:
| [Entity] | [Short field 1] | [Short field 2] | [Short field 3] | [Short field 4] | Confidence |

## Entity-by-entity detail
For each of the [N] entities, in [ORDERING] order, a section with the fields above. Use level-3 headings (###) for entity names. Use bolded inline labels for each field.

### [First entity name]
- **[Field 1]:** ...
- **[Field 2]:** ...
- ... (all the fields from the research question section)
- **Confidence / open questions:** ...

(Repeat for every entity in the set.)

## Appendix A — entities recommended for exclusion
Entities where [TOPIC] does not meaningfully apply and a per-entity output would be thin. One-line reason each.

## Appendix B — entities flagged for human review before use
Entities with [ACTIVE CHANGE / AMBIGUITY / LOW CONFIDENCE]. One-line reason and what a reviewer should check.

## Appendix C — [timeline / dependencies / open-item list]
[Short list of time-sensitive items the consumer needs to know about.]

## Hard constraints

- [TOPIC] only. Do NOT drift into [ADJACENT TOPIC 1], [ADJACENT TOPIC 2], [ADJACENT TOPIC 3]. Those are separate research passes.
- Authoritative sources only. Every citation must resolve to [AUTHORIZED DOMAIN CLASS]. Aggregators are not authoritative. Specifically NOT [DISALLOWED DOMAIN 1], [DISALLOWED DOMAIN 2], ...
- Every factual claim must be traceable to a cited source. If you cannot find a direct citation, say "not found" or "inferred from [X]" — do not make it up.
- Do not invent citations, identifiers, or dates. If you cite something, the URL must actually open to that thing.
- Do not write finished prose for [END AUDIENCE]. The output is facts and citations, not [END PRODUCT FORMAT, e.g., "marketing copy" or "plain-language explainer pages"]. A downstream step handles [END PRODUCT CONCERN, e.g., "voice and framing"].
- Do not pad. If multiple entities have substantively identical findings, say so in the executive summary and let the reader decide whether all deserve downstream pages.
- Be honest about [KNOWN COMPLEXITY — framework transitions, methodology disputes, stale data, etc. NAME THE SPECIFIC NUANCE]. Do not flatten it.
- Be honest about uncertainty. A row marked "confidence: low, needs human review" is more valuable than a confident-sounding fabrication.

## What to report back when you're done

1. The full markdown report itself.
2. A count of how many entities you marked high-confidence, medium-confidence, and low-confidence.
3. The single biggest uncertainty in the report — the one thing that, if wrong, would invalidate the most downstream work.
4. How many entities you recommend excluding entirely from the downstream work, and why.
```

---

## How to use this template

1. Copy everything between the triple-backtick markers above.
2. Replace every `[BRACKETED PLACEHOLDER]` with a concrete value from the task. Do not ship placeholders — the research tool will treat them as literal.
3. Read the filled-in prompt top-to-bottom and check the validation list in SKILL.md. Fix anything that fails.
4. Wrap with copy instructions above the block and post-block notes below (see SKILL.md workflow step 5).
