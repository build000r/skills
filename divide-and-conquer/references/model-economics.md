# Model economics and quality gate

Use this when assigning a model to a Beads node or reconsidering the route
after a model release. Benchmarks are candidate signals, not evidence that a
worker passed this repo's acceptance contract. Keep the node's `writes`,
`validate_cmds`, stop rules, and review authority fixed while comparing routes.

## Dated candidate evidence (2026-09-23)

- [OpenAI GPT-6 Sol and Luna](https://openai.com/index/introducing-gpt-6-sol-and-luna/):
  Sol input/output API prices fell 50% from GPT-5.6 Sol; Luna input fell
  from $0.20 to $0.10 and output from $1.20 to $0.50 per million tokens.
  GPT-6 Luna at maximum effort scored 66.6% on DeepSWE 1.1; Sol scored
  68.8% at maximum effort. These results do not compare either model directly
  with Claude Opus 5.5.
- [Anthropic Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5):
  Anthropic reports 54.4% on FrontierCode 1.1 Main and 66.4% on
  Terminal-Bench 4.0 at the stated efforts, plus 40% lower typical task cost
  than Opus 5. These are provider-reported results, not a local route test.
- [SpaceXAI Grok 4.7](https://x.ai/news/grok-4-7): Grok 4.7 costs the same
  per input/output token as Grok 4.6 and improves its reported CursorBench
  4.0 score from 40.4% to 46.3%. The published Grok table does not compare
  GPT-6 Luna or Claude Opus 5.5 on the same harness.

Do not compare percentages from different benchmark suites as if they were a
single ranking. Provider cost per task depends on effort, harness, caching,
retries, and acceptance rate. Subscription quota is not an API bill.

## Dispatch policy

| Node | Initial route | Cheaper or stronger candidate |
| --- | --- | --- |
| NTM runtime coordination | `low` via SBP | Grok 4.7 after the NTM route and controller behavior are qualified |
| Clerk work and deterministic edits | `low` via SBP | GPT-6 Luna for tracked native work; Grok 4.7 for Grok work, after exact transport qualification |
| Ordinary implementation with judgment and scoped tests | `med` via SBP | GPT-6 Sol or qualified Luna when its observed acceptance matches the baseline |
| Architecture, ambiguous/high-impact work, integration and final acceptance | `high` via SBP | Claude Opus 5.5 or GPT-6 Sol only after the same high-authority route and local proof; never infer authority from a release table |
| Design and visual review | Existing design route through SBP | Grok 4.7 when the route and visual acceptance are proven |

The table names *candidates*, not executable model IDs. SBP and the effective
operator overlay own NTM model/effort/runner tuples. Inspect the complete
`sbp route <low|med|high> --refresh --json` decision, retain and validate it,
and pass it unchanged to the adapter. A CLI default or API announcement does
not update SBP. A native subagent is an explicitly tracked allocation under
the bounded availability fallback, never a fabricated SBP decision. Do not
use that fallback to grant planning or final authority. If a new model needs
an unconfigured lane, record the gap and keep the runnable selected route.

## Qualification before promotion

For a candidate with no local execution proof, start with reversible,
well-specified nodes. Compare it with the incumbent on representative tasks
using the **same Beads contract**, tools, files, validation, and independent
review. Record model, actual effort, runner, cost or quota surface, token usage
when available, elapsed time, attempts, and accepted result per node. Include
at least one nontrivial code change and one failure or repair case before
making a general routing recommendation. If the sample is too small, keep the
claim provisional; do not assert statistical non-inferiority.

Hard gates for every node: no scope breach, no new blocker/severe review
finding, all required validation passes independently, and final authority
accepts the result. A failed candidate is repaired or escalated without
weakening acceptance. Track **cost per accepted node**, including retries and
review, rather than price per token. Promote a cheaper route only for the node
class where its observed acceptance and review burden match the incumbent;
retain the incumbent elsewhere. Keep a fresh high-tier final review for the
integrated slice. Never downgrade a Bead with an explicit user model/effort
requirement.

For subjective route fit, score each candidate from 0 to 1000 after hard
gates: verified correctness 35%, scope discipline 20%, review burden 20%,
cost per accepted node 15%, and latency 10%. `0` means the weakest accepted
result in the matched cohort, including repair burden; `1000` means accepted
without repair and best observed cost/latency. Leave unmeasured candidates
unscored. Weighted score is the sum of each
dimension times its weight; loss is `1000 - score`. Reduce correctness and
review loss first. Do not let low cost offset a failed hard gate, count a
model's own completion claim as proof, or compare cohorts with different tasks.
