---
name: smart
description: Ask the single most accretive question about the current project/conversation. Use when tagged with /smart, or when the user wants to identify the highest-leverage next move, most impactful addition, or smartest thing to do next.
---

# Smart

You've been invoked to deliver the single highest-leverage insight for whatever the user is working on right now.

## The Question

Ground yourself in everything available — the conversation so far, the codebase, recent git history, any active plans or tasks — then answer this:

> **What is the single smartest, most radically innovative, accretive, useful, and compelling thing you could do or suggest at this point to get us on the right track?**

## How to Answer

1. **Absorb context first.** Read the conversation history. Check `git log --oneline -20` and `git diff --stat` for recent momentum. Scan any open plan or task list. Understand what phase the work is in — exploration, building, debugging, shipping.

2. **Scope to what matters now.** If the user included a focus area (e.g., `/smart with regard to auth flow`), narrow to that. Otherwise, identify the current bottleneck or highest-value gap yourself.

3. **Be concrete and actionable.** Don't say "consider improving error handling." Say "add retry with exponential backoff to the webhook delivery in `src/webhooks/deliver.ts:47` — right now a single timeout kills the whole batch." Name files, functions, architectural decisions. If it's a strategic suggestion, name the first concrete step.

4. **Be bold.** This isn't a code review. The user wants the move they haven't thought of — the one that unblocks three other things, or the refactor that makes the next five features trivial, or the simplification that deletes 400 lines. Swing for impact.

5. **One answer.** Not a list of five options. Pick the single best one and commit to it. If you must caveat, do it in one sentence after the recommendation.

6. **Prefer extending to creating.** Bias toward hardening, extending, or modularizing what already exists. That includes code, docs, skills, and configuration. The smartest move is rarely "build a new thing from scratch" — it's usually "make the thing we have work better, cover more cases, or compose more cleanly." Hardening means: strengthening existing code, filling test gaps, clarifying confusing docs or READMEs, tightening skill descriptions that don't trigger well, fixing misleading comments, improving error messages, or wiring up existing pieces differently. Before suggesting new files, new abstractions, or new repos, check whether the goal can be reached by improving what's already there. This isn't a hard rule — sometimes the right answer genuinely is something new — but the bar for "create" should be higher than the bar for "improve."

## Skill-Aware Recommendations

Your answer can (but doesn't have to) recommend invoking a sibling skill as the next move. Consider which skill fits the current situation — the right tool often IS the smartest move:

| When the situation looks like... | Consider suggesting... |
|---|---|
| Code is untested, risky, or fragile | `/crap` — hotspot scoring to find where to harden |
| Post-crap, surviving mutants need triage | `/mutate` — mutation testing to close coverage gaps |
| Project lacks a README or docs are stale | `/readme-writing` — craft a proper README |
| Multi-repo feature needs coordination | `/domain-planner` — plan the slice across repos |
| A planned slice is ready to build | `/domain-scaffolder` — scaffold from the accepted plan |
| Work is in flight and needs a status check | `/domain-reviewer` — audit progress against plan |
| Complex task needs parallel decomposition | `/divide-and-conquer` — split into independent agents |
| Bug fix or feature lacks clear "done" criteria | `/describe` — define pass/fail test cases first |
| Changes are ready but uncommitted | `/commit` — clean, logical commit batches |
| Need to decide build vs. reuse vs. extract | `/build-vs-clone` — ecosystem-aware placement decision |
| Backlog is messy or priorities unclear | `/audit-plans` — plan hygiene and prioritization |
| A skill itself needs improvement | `/skill-issue` — review and iterate from real usage |
| Verification feels manual or hand-wavy | `/reproduce` — command-first verification workflow |
| Multiple dependent questions need answers | `/ask-cascade` — hierarchical question ordering |

Don't force a skill recommendation. If the smartest move is "delete this file" or "rename this function" or "talk to your backend team," say that. Skills are tools in the toolbox, not the only answer.

### Overlay and Planning Context

Before making your recommendation, check whether the project has an active client overlay and existing plans:

1. **Find the overlay**: Run `python3 _shared/scripts/resolve_context.py` (or check `skillbox-config/clients/`) to resolve the active client. The overlay tells you conventions, paths, and workflows already in place.

2. **Check for plans**: If the overlay defines a `plan_root`, scan it for existing slice plans. Each slice lives in `{plan_root}/{slice-name}/` and contains `plan.md` (master doc), `backend.md`, `frontend.md`, `shared.md`, `flows.md`, and `schema.mmd`. Check `{plan_root}/INDEX.md` for the catalog of all slices and their status.

3. **Read plan state**: Skim the INDEX for slice statuses — are there planned slices nobody has started? Draft slices that need review? Released slices with no implementation progress? Session plans that were started but abandoned? This is high-signal for what the smartest move is.

4. **Factor plans into your answer**: The smartest move might be "start implementing the auth slice that's been released for a week" (`/domain-scaffolder`), or "audit the three in-flight slices that have drifted" (`/domain-reviewer`), or "the backlog has 12 slices and no priorities — run `/audit-plans` before writing more code." Plans are context, not decoration.

If no overlay or plans exist, that's fine — not every project uses the planning system. Don't suggest adopting it unless the project's complexity genuinely warrants it.

## Immediate Subagent Launches

During the context-absorption phase (step 1), you may discover issues that don't need user deliberation — they're obviously worth fixing right now. Launch a background subagent immediately for these, then continue forming your main recommendation.

| Discovery | Subagent action |
|---|---|
| README is missing, empty, or says "TODO" | Launch agent with `/readme-writing` context to draft one |
| Docs contradict the code (stale API examples, wrong paths, outdated flags) | Launch agent to fix the specific docs — reference the actual code state |
| SKILL.md description doesn't match what the skill actually does | Launch agent to tighten the description and triggers |
| Plan INDEX.md has slices marked "in-progress" with no recent git activity | Launch agent to run `/domain-reviewer` audit on the stale slices |
| Tests exist but coverage is clearly missing for a critical path | Launch agent to run `/crap` on the hot module |
| Confusing or conflicting comments in code you're reading | Launch agent to clean up the specific file — delete lies, clarify intent |

**Rules for subagent launches:**

- Only launch for things that are **unambiguously good to fix** — no judgment calls, no architectural decisions, no "maybe we should restructure this"
- Launch in **background** so they don't block your main answer
- **Tell the user** what you launched and why in your output (add a line after First step)
- Limit to **1-2 subagents** per invocation — don't flood
- If the discovery IS the smartest move, make it your main recommendation instead of a side-launch

## Output Format

**The move:** [1-2 sentence headline of what to do]

**Why this, why now:** [2-4 sentences on why this is the highest-leverage action given current state]

**First step:** [The literal first thing to do — a command to run, a file to open, a skill to invoke]

**Already in motion:** [If you launched background subagents, list what and why. Omit this line if nothing was launched.]

---

*If the user keeps invoking /smart iteratively, treat each call as "given everything so far including your last suggestion, what's the next smartest move?" — build on prior answers, don't repeat them.*
