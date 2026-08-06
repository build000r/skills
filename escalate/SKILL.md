---
name: escalate
description: Decide whether the current run needs a bounded external-reality pass before committing to a strategic call, then route it to web-check, deep-research-prompt, thesis-gtm, research-paper, or skip. Centralizes the escalation gate that thesis-gtm, power-map, build-vs-clone, domain-planner, wiki-forge, and readme-writing each restated. Use for "escalate", "/escalate", "do we need a Pro pass here", "should we Oracle this", "is this gated by external reality", "bounded Deep Research pass", or when a calling skill's plan/recommendation depends on facts outside the local repo and wiki.
---

# Escalate

Single-purpose gate that decides whether the current decision is gated by **current external reality** (markets, competitive structure, regulation, live product behavior, public discourse) versus **internal corpus** (code, wiki, prior duels, repo history). When external reality dominates, route the question to the right research workflow. When it does not, return `skip` so the caller proceeds without burning a Pro run.

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

- **deep-research-prompt** — owns prompt construction and Oracle execution once this skill routes there
- **thesis-gtm** — owns full GTM thesis validation when the unknown affects customer, buyer, category, positioning, pricing, distribution, or wedge
- **research-paper** — owns academic/source-grounded paper creation when the desired output is a paper rather than a strategic decision
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

## Caller Packet

Caller skills should pass a packet like this before they ask this skill to decide:

```yaml
caller: domain-planner | power-map | build-vs-clone | wiki-forge | readme-writing | research-paper | thesis-gtm | other
decision_at_risk: "<what recommendation, artifact, plan, or claim changes if this fact is wrong>"
external_unknown: "<the current outside-world fact the repo/wiki cannot witness>"
internal_evidence_considered:
  - "<repo file, wiki concept, prior duel, local command, or web check already used>"
artifact_target: README | VISION | wiki | slice-plan | build-vs-buy-report | paper | one-shot
stakes: low | medium | high
freshness_need: static | current | live
bounded_question: "<single concrete research question, not a topic area>"
preferred_depth: web-check | deep | oracle
```

The caller owns the domain reason this matters. `/escalate` owns the route.

## Route Policy

Return exactly one route:

| Route | Use when |
|---|---|
| `skip` | The answer is internal, low-stakes, already answered recently, or has no downstream commit slot. |
| `web-check` | A few WebSearch/WebFetch calls can answer the bounded question. Do that directly instead of launching a Pro run. |
| `deep-research-prompt` | The question needs a bounded external-reality pass but is not a full GTM thesis. |
| `thesis-gtm` | The unknown changes customer, buyer/user split, category, positioning, pricing, distribution, competitive wedge, or README/VISION thesis. |
| `research-paper` | The caller is not already `research-paper`, and the desired artifact is a source-grounded paper or literature-style synthesis rather than a go/no-go decision. |
| `too-broad` | The caller gave a topic area, not a defensible bounded question. Ask the caller to narrow before research. |

Never route `caller: thesis-gtm` back to `thesis-gtm`. Inside `thesis-gtm`, return `deep-research-prompt`, `web-check`, `skip`, or `too-broad`.

## Caller-Aware Rules

Apply these overrides after scoring the five gate signals:

| Caller | Forced route rules |
|---|---|
| `domain-planner` | Route to `thesis-gtm --skip-vision` when a slice changes ICP, GTM, wedge, target buyer, pricing, packaging, or customer promise. Route to `deep-research-prompt` for narrow vendor, regulation, API, platform, or ecosystem facts. |
| `power-map` | Route to `thesis-gtm` when the answer could change who the product sells to or whether the product thesis survives. Route to `deep-research-prompt` for dated evidence about contested intermediaries, regulation, consolidation, pricing, funding, or adoption. |
| `build-vs-clone` | Route to `deep-research-prompt` for current OSS/package/vendor landscape, maintainer momentum, pricing, funding, or ecosystem fit. Route to `thesis-gtm` only when the build-vs-buy result changes product positioning, target customer, or whether the thing should exist as a product. |
| `wiki-forge` | Route to `deep-research-prompt` to stress-test the duel synthesis against dated facts. Route to `thesis-gtm` when the forged concept is explicitly a GTM, market, distribution, positioning, or customer thesis. |
| `readme-writing` | Route to `thesis-gtm` before locking strong customer, category, market, GTM, or wedge claims. Route to `deep-research-prompt` for factual ecosystem comparisons, current install/API behavior, or adjacent-tool facts. |
| `research-paper` | If another caller needs a paper as the artifact, route to `research-paper`. If the caller is already `research-paper`, let it continue its own paper workflow and route only the final outside-world check to `deep-research-prompt`, `thesis-gtm`, `web-check`, `skip`, or `too-broad`. |
| `thesis-gtm` | Treat the user or caller as already requesting GTM validation. Return `deep-research-prompt` when the selected topic is bounded, novel, high-stakes, and externally gated; return `too-broad`, `skip`, or `web-check` otherwise. |

## Handoff Contract

When the gate fires, return a routing packet:

```yaml
route: skip | web-check | deep-research-prompt | thesis-gtm | research-paper | too-broad
reason: "<why this route owns the decision>"
required_output: "<evidence or artifact needed before the caller can proceed>"
caller_continuation: "<where the original skill resumes after the routed pass>"
capture_destination: "<wiki note, plan field, README/VISION section, paper path, or one-shot summary>"
```

When routing to a research workflow:

1. **Frame the question** in one sentence the caller would defend in a duel
2. **List the internal evidence already considered** (repo files, wiki concepts, prior duels) so the Pro run doesn't restate what we already know
3. **Specify the decision the answer feeds** (which README section, which plan field, which VISION claim) — Pro runs without a downstream commit slot tend to drift
4. Hand off to the selected route. For `deep-research-prompt`, execute mode is
   preferred over paste mode. For a plain question, use its one-command
   `assets/scripts/oracle-ask.mjs` lane (name a Project with `--project`, and
   use `--model instant` while iterating so Pro usage is not spent on tests).
   For Deep Research and other browser-composer work, use the stable
   `assets/scripts/oracle-subagent.mjs run` command, then retain the returned
   run ID for `status`, `wait`, or `run --reattach`. Treat
   `--timeout-seconds` as an observer wait bound, and preserve any returned
   `resume_directive`; `monitor` or `reconcile_submission` must never become a
   duplicate send. Browser-mode Deep Research
   must go through that controller's verified composer flow (Oracle renders
   the bundle; CDP selects and proves Pro + Deep research, then submits) —
   never a raw `oracle --engine browser` submission, which has shipped runs on
   the wrong model with Deep research off.
5. On return, capture the result to the appropriate destination:
   - Wiki context → file as `_sources/oracle/<topic>-<date>.md` and trigger `/wiki ingest`
   - Plan/VISION context → quote the load-bearing claims inline with citations and link the full transcript
   - One-shot decision → summarize the answer in one paragraph for the caller

## Output

- **If escalating**: the route packet, the framed prompt, the handoff destination, the capture destination, and a one-line "why this gate fired"
- **If skipping**: a one-line `skip: <reason>` and a pointer to whatever internal source already answers the question
- **If too broad**: a one-line `too-broad: <missing bound>` and the narrowest question that would make the route legal

## Anti-Patterns

| Problem | Fix |
|---------|-----|
| Escalating for tone-of-voice or style decisions | Those are taste calls; Pro runs add no signal. Skip. |
| Escalating without a downstream commit slot | If no VISION/README/plan field is waiting for the answer, the Pro run is exploration — fine for the user, not for an autonomous escalate call |
| Restating the prompt-construction logic from `deep-research-prompt` | Don't. That's `deep-research-prompt`'s job. This skill is the gate, not the prompt builder |
| Absorbing caller workflows | Don't. `thesis-gtm`, `power-map`, `wiki-forge`, `domain-planner`, and `readme-writing` keep their own topic selection, grading, filing, and artifact updates. |
| Caller-aware logic becoming a stale registry | Keep route rules short, about ownership boundaries only. If a caller needs more than routing, that logic belongs in the caller skill. |
| Escalation loops | Never route `thesis-gtm` to itself. If a route would loop, return `too-broad` or ask the caller to supply the missing bounded question. |
| Re-escalating questions a recent Pro run already answered | Check `_sources/oracle/` (or equivalent) first; cite and skip |
| Letting "external reality" creep to mean "anything not in this file" | The repo + wiki count as internal even when their content is large. External = the world outside the corpus |

## Relationship to Other Skills

- **deep-research-prompt** owns prompt construction and Pro / Oracle execution. `/escalate` is upstream of it: route first, then prompt.
- **thesis-gtm** owns GTM thesis validation. `/escalate` may route other skills to it, but must not duplicate its topic selection, grading, wiki filing, or VISION/README delta workflow.
- **power-map**, **build-vs-clone**, **domain-planner**, **wiki-forge**, **readme-writing**, **research-paper** — each previously inlined this gate. They should now call `/escalate` at the gating step and then resume their own downstream artifact workflow.
- **wiki-duel** runs an internal-corpus duel; if its synthesis depends on external reality, follow with `/escalate`.
- **wiki-forge** Phase 7b is the canonical case: forge produces a synthesis, then `/escalate` routes the final outside-world check before filing back if the concept makes claims about external reality.

## Verification / Closeout Contract

Before returning, confirm:

1. The five gate signals were scored explicitly and the decision (`skip`, `web-check`, `deep-research-prompt`, `thesis-gtm`, `research-paper`, or `too-broad`) was justified against them, not asserted.
2. If routing to a research workflow: the framed prompt, the internal-evidence-already-considered list, and the downstream commit slot were all stated before handoff.
3. If `skip`: the reason was named and a pointer to the internal source that already answers the question was given (or "no answer needed" if the gate failed on stakes/scope).
4. If a Pro run executed: the result was captured to the documented destination (wiki source file, plan field, or one-paragraph summary) — not left dangling in the transcript.
5. The caller's downstream action is unblocked: either it has the external answer it needed, or it has a clear `skip` reason it can cite.
6. If this run was part of migrating a caller skill (thesis-gtm, power-map, build-vs-clone, domain-planner, wiki-forge, readme-writing) to depend on `/escalate`, run `quick_validate.py` on the caller's directory before considering the migration done.
