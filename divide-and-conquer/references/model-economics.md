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

## Approved dispatch policy

| Work tier | Primary | Availability backups, in order |
| --- | --- | --- |
| `low`: bounded execution and NTM coordination | Grok 4.7 native `xhigh` | GPT-6 Luna Codex `max`; Grok 4.7 Cursor `xhigh` |
| `med`: ordinary implementation | GPT-6 Sol Codex `xhigh` | Claude Opus 5.5 Cursor `medium` |
| `high`: planning and final authority | GPT-6 Astra Codex `medium` | Claude Opus 5.5 Cursor `xhigh` |

SBP's effective route configuration owns executable IDs and availability
checks. Keep the exact decision returned by `sbp route <tier> --refresh --json`
and pass it unchanged to the adapter. A backup is used only when an earlier
route or harness is unavailable. Failed validation means repair or work-tier
escalation under the same Bead acceptance contract. Retain high-tier final
review for the integrated slice. An independent Grok design reviewer uses
`sbp route pick grok`, separate from the low-tier controller decision.

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
