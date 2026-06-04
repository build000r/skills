# Soft Score Rubric

Use this reference when reviewing, creating, or updating a skill whose outcome
contains soft judgment: elegance, clarity, usefulness, robustness, taste,
operator fit, or similar dimensions that are easy to discuss but hard to
optimize.

The goal is not fake precision. The goal is to turn subjective review into a
visible loss function that future agents can reduce.

## Required Review Outputs

Every skill review should keep two scores separate:

1. `skill_quality_score` from 0 to 1000: how good the skill contract is as an
   executable workflow.
2. `optimization_readiness_score` from 0 to 1000: whether the skill itself
   defines a usable scoring or loss model for its subjective decisions.

Then report:

```text
review_score = (0.70 * skill_quality_score) + (0.30 * optimization_readiness_score)
review_loss = 1000 - review_score
top_loss_contributors = the three dimensions with largest weighted loss
```

Keep the two component scores visible even when `review_score` is high. A skill
can be operationally strong while still lacking an optimization model.

## Skill Quality Dimensions

Score each dimension from 0 to 1000 and compute weighted loss:

```text
weighted_loss_i = weight_i * (1000 - score_i)
skill_quality_loss = sum(weighted_loss_i) / sum(weight_i)
skill_quality_score = 1000 - skill_quality_loss
```

| Dimension | Weight | What 1000 means |
|---|---:|---|
| Trigger precision | 120 | The description activates for intended prompts and avoids sibling-skill overreach |
| Instruction clarity | 160 | A cold future agent can follow the workflow without hidden context |
| Workflow completeness | 150 | Branches, stop conditions, and output shape cover the real task surface |
| Evidence and validation | 190 | The skill names concrete evidence, commands, or observations that prove success |
| Recovery and degraded mode | 120 | Missing tools, stale indexes, risky branches, and blockers have clear fallback behavior |
| Operator usability | 130 | The workflow minimizes unnecessary questions and produces compact, actionable output |
| Maintenance elegance | 130 | The contract is simple, reusable, low-duplication, and resistant to drift |

## Optimization Readiness Dimensions

Score whether the reviewed skill contains a real scoring/loss system. This is
about the target skill's own behavior, not about this review's opinion of it.

| Dimension | Weight | What 1000 means |
|---|---:|---|
| Objective named | 120 | The skill states what quality or outcome the score is optimizing |
| Soft dimensions defined | 170 | It defines 3 to 7 relevant factors such as elegance, reliability, utility, or risk |
| Scale anchors | 140 | It gives enough 0/500/1000 or low/medium/high anchors for consistent scoring |
| Weights and formula | 150 | It provides weights plus an aggregation formula |
| Loss framing | 150 | It converts scores into loss, penalties, thresholds, or top loss contributors |
| Decision linkage | 140 | The score changes what the agent does next, instead of being decorative |
| Evidence calibration | 80 | Scores are tied to transcript evidence, tests, user outcomes, or repeatable observations |
| Anti-gaming guardrails | 70 | It warns against Goodharting, boilerplate compliance, or false precision |

Suggested gates:

- `optimization_readiness_score >= 800`: strong scoring contract.
- `600 <= optimization_readiness_score < 800`: usable but incomplete.
- `< 600`: inadequate optimization concept. Say this clearly even if the skill
  is otherwise well-written.
- Missing `weights and formula` or `loss framing` should cap
  `optimization_readiness_score` at 700 unless the skill has a domain-specific
  replacement that makes the optimization loop explicit.

## Minimum Viable Optimization Contract

When creating or updating a skill with subjective judgment, add a compact block
or reference that includes:

```text
Optimization score
- Objective:
- Dimensions: 3 to 7 named soft factors
- Scale: what 0, 500, and 1000 mean for each factor, or clear low/mid/high anchors
- Weights:
- Formula:
- Loss: how the score becomes loss, penalties, thresholds, or top loss contributors
- Decision effect: what the agent changes when a dimension scores low
- Anti-gaming note:
```

Do not force this block when the skill is purely mechanical and has an existing
deterministic pass/fail validator. For mixed workflows, score only the
judgment-heavy branch.

## Review Output Template

```text
Soft score review
- skill_quality_score:
- optimization_readiness_score:
- review_score:
- review_loss:
- top_loss_contributors:
- scoring_concept_verdict:
- best_next_patch:
```

The best next patch should target the largest reducible weighted loss, not the
most interesting prose issue.

## Catalog Audit Mode

Use catalog mode when auditing a whole skill root:

```bash
python3 skill-issue/scripts/score_skill_contract.py . --catalog --json
```

Catalog mode returns two separate collections:

- `ranked`: subjective or mixed skills sorted by lowest
  `optimization_readiness_score`
- `exemptions`: deterministic/mechanical skills listed in
  `references/soft-score-exemptions.json`

Only add an exemption when the skill's success is already proven by concrete
commands, validators, or fixed output contracts and a soft score would not
change the agent's next action. Keep the exemption reason and validator explicit
so the absence of a score is reviewable rather than silent.
