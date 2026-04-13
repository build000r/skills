# Anti-patterns and their fixes

## Terminal leak

**Symptom:** the research tool spends significant output on meta-topics unrelated to the research question — shell startup, permission modes, tool UIs, error messages.

**Cause:** the user pasted the prompt alongside terminal output. The research tool dutifully "explained" the noise.

**Fix:** self-announcing opening line + copy instructions outside the block telling the user to paste only the code block content.

**History:** first observed April 2026 when a taxonomy-research prompt was pasted alongside Claude Code session chrome. Output was roughly 60% noise.

## Confidence inflation

**Symptom:** a 50-entity research report marks 45 entities as high-confidence.

**Cause:** the research agent optimizes for appearing competent. Real 50-jurisdiction research hits uncertainty frequently.

**Fix:** explicitly require an uncertainty distribution in the "what to report back when done" section ("how many high / medium / low confidence"). Tell the user to watch for a suspiciously flat distribution as a red flag.

## Prose drift

**Symptom:** the research report starts answering questions in essay form instead of structured fields.

**Cause:** the agent found the fields confining and reverted to natural prose.

**Fix:** show the output structure with explicit example headings and bullet labels in the prompt, not just describe it. The agent will pattern-match on the shown structure. Description alone is not enough.

## Aggregator citations

**Symptom:** source URLs point to Wikipedia, Justia, FindLaw, LexisNexis, blog posts, law-firm marketing pages, Crunchbase.

**Cause:** aggregators rank well in search, so the research agent finds them first.

**Fix:** explicitly enumerate disallowed domain classes in the hard-constraint stanza by name. Require `.gov` / `.edu` / official domains. Accept that some claims will be marked "source not verified on official domain" — that is better than fabricated authority.

## Topic drift

**Symptom:** a prompt about reserve funding rules comes back with sections on meeting notice, records access, and fines.

**Cause:** adjacent topics are related and the agent volunteers them.

**Fix:** explicit "one topic only" constraint and enumerate the adjacent topics the agent should NOT drift into by name.

## Pad-to-length

**Symptom:** N entity sections that each restate the same boilerplate with minor keyword swaps.

**Cause:** the agent tries to produce N equally-sized sections regardless of real variation.

**Fix:** explicit "do not pad — if multiple entities have substantively identical findings, say so in the executive summary." Combined with a required "what is actually different about this entity" field per section.

## Completion-criteria amnesia

**Symptom:** the research agent returns a long report but the user cannot tell if the task is done or partial.

**Cause:** no explicit completion criteria.

**Fix:** "what to report back when done" section with 3-5 concrete items the agent must include at the top of the final output. Example: "(1) the full report, (2) count of entities by confidence tier, (3) the single biggest uncertainty, (4) how many entities you recommend excluding."

## Too many clarifying questions

**Symptom:** the current agent asks 5+ clarifying questions before producing the prompt, creating friction.

**Cause:** treating prompt authoring as requirements-gathering instead of first-draft-then-iterate.

**Fix:** ask at most one clarifying question — the one thing you genuinely cannot infer from the conversation. Produce a first draft fast. The user can correct the draft in one round, which is cheaper than dragging them through a requirements cascade.

## Embedded placeholders that ship unfilled

**Symptom:** the prompt the user pastes into the research tool contains `[FILL IN]`, `<REPLACE>`, `{TOPIC}`, or similar tokens. The research tool treats them as literal.

**Cause:** the current agent used a template as the final output instead of filling it in.

**Fix:** never ship a template. Either fill in every placeholder with a concrete value, or flag it to the user outside the block as "you will need to replace [X] before sending." If the user needs to supply a value, say so explicitly above the block — do not hope they notice.
