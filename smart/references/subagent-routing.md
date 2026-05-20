# Smart Subagent Routing

During the context-absorption phase, you may discover issues that do not need
user deliberation because they are obviously worth fixing now. For anything more
than a tiny single-file cleanup, route the work through `/divide-and-conquer` so
it gets a Bead, an owner claim, and a ready-frontier handoff before continuing
your main recommendation. When delegation is not available or not authorized,
keep the same discovery as an agentic route in the main recommendation instead
of asking the human by default.

| Discovery | Subagent action |
|---|---|
| README is missing, empty, or says "TODO" | Route a Bead through `/divide-and-conquer` with `/readme-writing` context |
| Docs contradict the code | Route a Bead through `/divide-and-conquer` with `/oss-doc-audit` or `/readme-writing` context to repair the specific docs against the current code state |
| SKILL.md description does not match what the skill actually does | Route a Bead through `/divide-and-conquer` to tighten the description and triggers |
| Plan INDEX.md has slices marked "in-progress" with no recent git activity | Route a Bead through `/divide-and-conquer` for `/domain-reviewer` audit on the stale slices |
| Tests exist but coverage is clearly missing for a critical path | Route a Bead through `/divide-and-conquer` for `/crap`, `/mutate`, or `/testing-metamorphic` on the hot module, depending on what kind of assertions are missing |
| A supported hotspot already has `FINAL_SCORE >= 30` | Route a Bead through `/divide-and-conquer` with `/crap` context to scope the hotspot and propose the smallest path to get it below `30` |
| Confusing or conflicting comments in code you are reading | Route a Bead through `/divide-and-conquer` for the specific file by deleting false comments or clarifying intent |

Rules:

- Only route side work for things that are unambiguously good to fix.
- Only route delegated work when the current runtime and user permissions allow it.
- Use `/divide-and-conquer` as the worker substrate so Beads own status and claims.
- Tell the user what you routed and why in your output.
- Limit to 1-2 routed worker issues per invocation.
- If the discovery is the smartest move, make it the main recommendation instead of a side-launch.
