# Resolution Routing

Load this reference when context, repository code, and local documentation do not settle a prerequisite. Pick the cheapest capable source and preserve its authority boundary.

| Source | Use when | Authority |
|---|---|---|
| Repository code/docs | The answer is observable locally. | Settles facts when evidence is clear. |
| `/wiki query` | Prior decisions, product context, or accumulated project knowledge may already answer it. | Settles current authoritative records; otherwise supplies evidence. |
| `/wiki-duel` | Two interpretations remain and the wiki can ground an adversarial comparison. | Advisory judgment; not consent. |
| `/dueling-idea-wizards` | A cold strategic, architecture, scope, or approach fork lacks a clear winner and no external-reality blocker dominates. | Advisory judgment; not consent. |
| Targeted prototype | Concrete behavior or appearance would make an abstract choice inspectable. | Evidence and recommendation; the human retains product/taste decisions. |
| Direct web check | A small number of current primary-source lookups can settle a bounded external fact. | Settles facts to the confidence of the sources. |
| `/escalate` | A consequential decision depends on current markets, regulation, vendor behavior, pricing, competition, or another external reality not visible locally. | Routes to `web-check`, `deep-research-prompt`, `thesis-gtm`, `research-paper`, `too-broad`, or `skip`. |
| Human | Preference, private context, priority, risk tolerance, scope, consent, or retained authority remains. | Settles the human-owned decision. |

## Routing Rules

1. Check whether a trusted recent result already answers the same question before launching another pass.
2. Escalate a prerequisite once through the narrowest capable route. If evidence remains inconclusive, present the conflict to the human rather than repeating the same route.
3. Adopt clear factual findings without a ceremonial checkpoint unless they are stale, conflicting, or materially consequential.
4. Convert advisory findings into a recommendation with rationale and tradeoffs. Ask the human when the underlying decision is human-owned.
5. Use a concise visible routing message only when the detour adds meaningful cost, delay, external access, conflicting evidence, or a route the user may reasonably redirect.
6. Keep unrelated frontier questions moving when a research prerequisite blocks only one branch and the runtime can continue safely.
7. Explicit human approval remains mandatory before risky side effects regardless of what any route recommends.

Example visible routing message:

> The blocker is current external API behavior. I am verifying that before asking you to choose the implementation path.
