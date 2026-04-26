---
name: escalate
description: Decide whether the current run needs a bounded external-reality pass (GPT-5 Pro / Deep Research / Oracle) before committing to a strategic call, and hand off to deep-research-prompt when it does. Centralizes the escalation gate that thesis-gtm, power-map, build-vs-clone, domain-planner, wiki-forge, and readme-writing each restated. Use for "escalate", "/escalate", "do we need a Pro pass here", "should we Oracle this", "is this gated by external reality", "bounded Deep Research pass", or when a calling skill's plan/recommendation depends on facts outside the local repo and wiki.
---

# Escalate

Single-purpose gate that decides whether the current decision is gated by **current external reality** (markets, competitive structure, regulation, live product behavior, public discourse) versus **internal corpus** (code, wiki, prior duels, repo history). When external reality dominates, package the question and hand off to `deep-research-prompt`. When it doesn't, return `skip` so the caller proceeds without burning a Pro run.

This skill exists because the same gate logic was duplicated nearly verbatim across at least six skills. They each said "if the answer depends on live external facts, escalate to GPT-5 Pro / Deep Research." That gate now lives here.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using escalate`.

Preferred format: `Using escalate to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

## When to Use

- Another skill is about to commit to a strategic recommendation (positioning, GTM call, build-vs-buy, plan acceptance, concept synthesis) and the recommendation rests on facts outside the repo
- The user explicitly asks "should we Oracle this", "do we need a Pro pass", or "/escalate"
- A wiki concept's claims about markets or competition haven't been validated against current external reality and the next step would lock them in

## When NOT to Use

- The question can be answered from `WebFetch` / `WebSearch` in a handful of calls → just do that
- The question is about local code, repo history, or wiki content → answer it directly
- The user has already run a Pro pass on this exact question recently → cite the prior result
- Only a prompt-craft handoff is needed with no gating decision → call `deep-research-prompt` directly

## Dependencies

- **deep-research-prompt** — owns prompt construction and Oracle execution; this skill calls into it once the gate fires
- **wiki** (optional) — if the calling context is wiki-based, file the result back as a source via `/wiki ingest` after the run

## The Gate

Score the decision on five signals. If 3+ are present, escalate. If fewer, return `skip` with the reason.

| Signal | Present when |
|--------|--------------|
| **External-reality dominance** | The decision turns on facts the repo and wiki cannot witness — current market structure, live regulation, recent public events, competitor product behavior |
| **Stakes** | The recommendation will be locked into a VISION, README, plan, or commit — not a throwaway exploration |
| **Staleness** | Existing internal evidence is older than ~3 months in a fast-moving domain, or no internal evidence exists |
| **Asymmetry** | A wrong answer is much more expensive than the cost of a Pro run (~$1–3 and a few minutes of latency) |
| **Bounded scope** | The question can be stated as a single concrete research prompt, not an open-ended fishing expedition |

If `bounded scope` is missing, do NOT escalate — escalation requires a tight question. Push back on the caller and ask them to narrow first.

## Handoff Contract

When the gate fires:

1. **Frame the question** in one sentence the caller would defend in a duel
2. **List the internal evidence already considered** (repo files, wiki concepts, prior duels) so the Pro run doesn't restate what we already know
3. **Specify the decision the answer feeds** (which README section, which plan field, which VISION claim) — Pro runs without a downstream commit slot tend to drift
4. Hand off to `deep-research-prompt` with execute mode (oracle on PATH) preferred over paste mode
5. On return, capture the result to the appropriate destination:
   - Wiki context → file as `_sources/oracle/<topic>-<date>.md` and trigger `/wiki ingest`
   - Plan/VISION context → quote the load-bearing claims inline with citations and link the full transcript
   - One-shot decision → summarize the answer in one paragraph for the caller

## Output

- **If escalating**: the framed prompt, the handoff to `deep-research-prompt`, the capture destination, and a one-line "why this gate fired"
- **If skipping**: a one-line `skip: <reason>` and a pointer to whatever internal source already answers the question

## Anti-Patterns

| Problem | Fix |
|---------|-----|
| Escalating for tone-of-voice or style decisions | Those are taste calls; Pro runs add no signal. Skip. |
| Escalating without a downstream commit slot | If no VISION/README/plan field is waiting for the answer, the Pro run is exploration — fine for the user, not for an autonomous escalate call |
| Restating the prompt-construction logic from `deep-research-prompt` | Don't. That's `deep-research-prompt`'s job. This skill is the gate, not the prompt builder |
| Re-escalating questions a recent Pro run already answered | Check `_sources/oracle/` (or equivalent) first; cite and skip |
| Letting "external reality" creep to mean "anything not in this file" | The repo + wiki count as internal even when their content is large. External = the world outside the corpus |

## Relationship to Other Skills

- **deep-research-prompt** owns the actual Pro / Oracle handoff. `/escalate` is upstream of it: gate first, then prompt.
- **thesis-gtm**, **power-map**, **build-vs-clone**, **domain-planner**, **wiki-forge**, **readme-writing** — each previously inlined this gate. They should now call `/escalate` at the gating step instead of restating the contract.
- **wiki-duel** runs an internal-corpus duel; if its synthesis depends on external reality, follow with `/escalate`.
- **wiki-forge** Phase 5 is the canonical case: forge produces a synthesis, then escalate before filing back if the concept makes claims about external reality.

## Verification / Closeout Contract

Before returning, confirm:

1. The five gate signals were scored explicitly and the decision (`escalate` or `skip`) was justified against them, not asserted.
2. If `escalate`: the framed prompt, the internal-evidence-already-considered list, and the downstream commit slot were all stated before handoff to `deep-research-prompt`.
3. If `skip`: the reason was named and a pointer to the internal source that already answers the question was given (or "no answer needed" if the gate failed on stakes/scope).
4. If a Pro run executed: the result was captured to the documented destination (wiki source file, plan field, or one-paragraph summary) — not left dangling in the transcript.
5. The caller's downstream action is unblocked: either it has the external answer it needed, or it has a clear `skip` reason it can cite.
6. If this run was part of migrating a caller skill (thesis-gtm, power-map, build-vs-clone, domain-planner, wiki-forge, readme-writing) to depend on `/escalate`, run `quick_validate.py` on the caller's directory before considering the migration done.

