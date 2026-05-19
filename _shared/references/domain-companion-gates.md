# Domain Companion Skill Gates

Use this reference when a domain skill needs to coordinate with operator-level
planning, reality-check, and Beads skills without copying their full contracts
into every `SKILL.md`.

The domain suite is public and portable. Some companion skills may be
operator-private or globally installed rather than public dependencies. When a
companion skill is not visible in the current harness, keep following the
behavioral gate locally and report the missing skill instead of pretending the
handoff ran.

## Gate Matrix

| Gate | Use when | Owner |
|---|---|---|
| Future-success contract | The work is high-stakes, reusable, multi-step, or another agent will inherit the result | `no-ragrets` |
| Strategic current-state check | Existing code, docs, plans, or Beads may not match the stated project vision | `reality-check-for-project` |
| Plan-to-Beads conversion | An accepted plan or bridge plan needs durable execution state | `beads-workflow` |
| Issue lifecycle mechanics | Creating, claiming, blocking, closing, syncing, or explaining `br` issues | `beads-br` |
| Graph health and priority | Choosing the next frontier, spotting bottlenecks, cycles, blocked work, or stale priority | `beads-bv` |
| Worker execution | Implementation or audit needs scoped parallel workers and fresh-context review | `divide-and-conquer` |

## Usage By Domain Skill

### `domain-planner`

- At slice start, use `no-ragrets` to name the future outcome, evidence, and
  failure avoided before locking the slice premise.
- If the repo already has implementation, roadmap docs, or Beads state, use
  `reality-check-for-project` before creating new plan work. The question is
  whether code, docs, and Beads already cover or contradict the slice premise.
- After human plan acceptance, use `beads-workflow` to mint or polish the `br`
  epic and child issues from the accepted plan.
- Before handoff, use `beads-bv` to inspect ready frontier, dependency order,
  blocked nodes, and priority before `/divide-and-conquer` executes the graph.
- Use `beads-br` for the concrete `br` issue lifecycle and sync commands.

### `domain-reviewer`

- In "what's left", retire, or closeout workflows, use
  `reality-check-for-project` when the core question is whether the
  implementation actually delivers the vision rather than only satisfying one
  local plan.
- Before turning audit findings into remediation Beads, use `no-ragrets` to
  state which future failure the fixes must prevent and what evidence will prove
  it.
- Use `beads-br` to create or update finding and fix issues with acceptance
  criteria, writes, validation, and blocker notes.
- Use `beads-bv` before launching fix waves to check that the remediation graph
  has a sane ready frontier and no hidden priority or dependency drift.
- After fixes and retirement, use a reality-check gate when the answer must be
  "the project is strategically done", not merely "the audit score is green".

### `domain-scaffolder`

- Do not become a planner. For substantive work, consume an upstream accepted
  plan and `br` issue from `domain-planner`, `domain-reviewer`, or
  `/divide-and-conquer`.
- Use `no-ragrets` as a small entry check: what regret does this scaffolding
  prevent, and what proof will show it satisfies the upstream issue?
- Use `beads-br` for claim, blocker, close, and sync mechanics.
- Use `beads-bv` only when local scaffolding exposes graph inconsistency:
  wrong ready item, missing dependency, duplicate fix issue, stale blocker, or
  priority conflict.
- Do not run a broad `reality-check-for-project` inline. Hand broader
  code/docs/vision drift back to `domain-reviewer` or `domain-planner`.

## Public/Private Dependency Rule

Do not add hard `depends_on` entries from public domain skills to
operator-private companion skills unless the skill is intentionally being
converted into an operator-private overlay. Public `SKILL.md` files should name
private/global companions as optional gates in body text. Private wrappers or
overlays may add hard dependencies when the operator wants those gates always on.

## Validation Expectations

After changing a domain skill's companion references:

```bash
python3 skill-issue/scripts/quick_validate.py domain-planner
python3 skill-issue/scripts/quick_validate.py domain-reviewer
python3 skill-issue/scripts/quick_validate.py domain-scaffolder
python3 skill-issue/scripts/check_skill_deps.py --changed-skill domain-planner --roots . ../skills-private --json
```

Run the dependency check for each changed skill when frontmatter dependencies
or advertised companion relationships change.
