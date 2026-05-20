# Smart Combo Routing

`/smart` still chooses one move. A skill combo is optional and only exists to
execute that move cleanly.

`smart` must not grow the global visible skill set. If a combo needs a skill
that is not visible in the current repo, route through `sbp` first:

```bash
sbp skill activate <skill> --cwd "$PWD" --dry-run
sbp skill activate <skill> --cwd "$PWD"
```

Prefer one explicit activation per needed skill. Do not create a pack or broad
global mapping until repeated real routing patterns justify that abstraction.

Use a combo only when all of these are true:

1. The move naturally breaks into a short sequence with clear handoffs.
2. Each step materially reduces ambiguity or risk for the next one.
3. The chain is still bounded at 2-4 steps max.

Prefer combos that pass artifacts forward rather than vague "also maybe use X"
bundles.

If a combo includes a code-writing skill and commit is authorized in the current
run, append `/commit` after validation unless the user explicitly asked not to
commit or the dirty worktree makes a clean scoped commit unsafe. If commit is
not authorized, say that the completion gate is pending rather than pretending
the work is fully closed out.

If a combo includes a long-running implementation step, prefer an NTM-backed
execution skill such as `/divide-and-conquer` rather than a detached transport
wrapper.

For any substantial implementation, `/smart` may identify the move, but
`/divide-and-conquer` owns the execution conversion into Beads: epic/child issue
creation, `br ready` frontier selection, claims, status updates, and worker
waves. Do not encode execution state in ad hoc smart-chain markdown or launch
parallel workers directly from the combo.

If any combo uses a swarm, NTM session, parallel worker wave, or NTM-backed
review loop, include `vibing-with-ntm`. If the task is large-ish, UI-facing,
multi-file, naturally parallel, or review-sensitive, use `divide-and-conquer`
before parallel execution. For UI or ambiguous review-heavy work, include Claude
Opus when available and finish with a fresh-eyes reviewer pass.

## When `cass` Should Open The Combo

Prefer `cass` as the first step when:

- there were prior attempts or abandoned work on the same problem
- the user is asking "what did we already decide?" or "what prompt worked?"
- the project has repeated rituals worth reusing instead of re-inventing
- context was lost and the fastest path is recovering prior reasoning

If history is thin or irrelevant, skip `cass`.

## Recommended Combo Shapes

| Situation | Good combo |
|---|---|
| Prior attempts exist and now the work needs a concrete contract | `cass -> describe -> reproduce` |
| Prior attempts exist but repo understanding is still thin | `cass -> codebase-archaeology -> describe` |
| Prior attempts exist and the work spans multiple repos or slices | `cass -> build-vs-clone -> domain-planner` |
| An accepted slice is ready for substantial implementation | `domain-planner -> divide-and-conquer -> commit -> reality-check-for-project` |
| The user asks for `smart goal`, an ambitious goal tracker, or a Gantt/`ganntt` plan | `reality-check-for-project -> wiki -> build-vs-clone -> mmdx` |
| The repo has drifted and priorities are unclear | `cass -> audit-plans -> domain-reviewer` |
| The project may be shipping the wrong thing despite progress | `reality-check-for-project -> audit-plans -> domain-planner` |
| The local environment may be the real blocker | `dev-sanity -> reproduce -> describe` |
| Broad rethink first, concrete plan second | `modes-of-reasoning-project-analysis -> describe` |
| The smartest move is to rank and fix the highest-value issues | `codebase-audit -> describe -> divide-and-conquer -> commit -> reality-check-for-project` |
| A module is risky and needs hardening after the shape is clear | `describe -> crap -> mutate -> commit -> reality-check-for-project` |
| A changed module has weak tests and unclear assertions | `describe -> reproduce -> crap -> mutate -> reality-check-for-project` |
| A supported hotspot is still above the acceptable risk floor | `crap -> describe -> divide-and-conquer -> commit -> reality-check-for-project` |
| A risky scope cannot produce a numeric CRAP score yet | `crap -> describe -> reproduce -> commit` |
| Docs, README, or examples have drifted from the code | `oss-doc-audit -> readme-writing -> de-slopify -> commit` |
| Public docs drift from the codebase | `oss-doc-audit -> readme-writing -> de-slopify -> commit` |
| The README is the missing surface | `readme-writing -> de-slopify -> commit` |
| A skill or workflow itself needs to evolve from evidence | `cass -> skill-issue -> commit` |

Treat these as patterns, not mandatory recipes.
