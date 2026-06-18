# Grok Sidecar Task Selection

Use this reference when a divide-and-conquer run can use Grok or Composer 2.5
as a bounded task runner without turning that lane into an unsupervised
implementation or review owner.

## Default Posture

Grok/Composer is a task-runner lane, not an authority lane. Route it through the
NTM Grok plugin when interactive pane preflight passes; otherwise use the shared
dispatcher, a Swimmers hidden session, a direct headless prompt-file one-shot,
or the locally configured Composer 2.5 task-runner lane. Reconcile all output
through Beads and the normal result artifact.

Prefer Grok/Composer when the work is cheap to verify, read-only by default or
scoped to exact files, and useful even when the output is only a rough first
pass. Composer 2.5 is the preferred runner for narrow writer tasks when the
Bead names exact files, validation, stop rules, a stronger-model review owner,
and final authority. Avoid Grok/Composer when the work needs trusted final
judgment, secret-bearing access, UI taste, broad writes, or architecture
authority. If the runner stalls, produces no artifact, fails validation, edits
outside scope, or asks for a decision it does not own, escalate to Codex
`gpt-5.5` xhigh or Claude Opus 4.8 for design work instead of retrying
indefinitely.

## Good Grok Work

These tasks are good default sidecar candidates:

- cwd/workflow routing and skill-tag extraction
- cleanup of a messy user request into a worker-ready brief
- broad grep-backed inventory where the acceptance criterion is a list of files
  or evidence anchors
- duplicate concept clustering across skills or docs
- low-risk docs outline drafts that a stronger model will review
- command discovery, if the final command is independently verified by Codex or
  Claude before use
- public-clone assumption checks that do not require credentials or mutation
- mechanical scripting where inputs, outputs, and validation commands are
  explicit
- fixture, docs, or generated-file cleanup inside a narrow write scope
- manifest/file classification with a declared output artifact
- generated-command cleanup or deterministic codemods with a tiny revert path
- `$commit` / logical commit batching when the Bead names the intended scope,
  leave-list, no-wildcard staging rules, privacy scan, validation commands, and
  Codex `gpt-5.5` final acceptance owner

Good signs:

- the task has a bounded artifact path
- the answer can be checked with `rg`, `git diff`, tests, or Beads state
- a wrong answer costs minutes, not a corrupted repo
- the sidecar can run read-only, or a writer route has a small explicit write
  scope and an easy revert path

## Bad Grok Work

Do not use Grok as the primary owner for:

- final integration review, commit acceptance, or the last approval before
  handoff
- UI/UX/design-system judgment, visual polish, or screenshot parity
- secret-bearing auth, MCP token repair, deploys, pushes, or production writes
- broad refactors where correctness depends on subtle local invariants
- NTM pane tending, stuck-pane recovery, rate-limit diagnosis, root
  orchestration, no-ragrets bead composition, or Beads closeout
- long-running Oracle/deep-research liveness judgment, unless Grok is only
  summarizing already-collected artifacts after the deterministic poll window
  has opened
- tasks that require editing files outside an explicit write scope
- tasks where the only validation is "the model says it is done"

Bad signs:

- the sidecar needs broad write access before it can produce value
- completion depends on an NTM idle state instead of a result artifact
- the task spans several repos without a root-owned integration plan
- validation needs credentials the sidecar should not see
- direct `grok -p` runs burn the turn cap and return no usable packet; retry
  once with a higher cap only if the work is still non-blocking, then fall back
  to a normal read-only explorer and record the bad route

## Leeway Tiers

Use these tiers when deciding how much autonomy to give Grok:

| Tier | Use | Permissions | Required proof |
| --- | --- | --- | --- |
| G0 router | cwd, skill tags, prompt cleanup | read-only, no tools beyond search | lead inspects output before dispatch |
| G1 evidence sidecar | inventories, doc audits, candidate file lists | read-only shell/search | artifact plus reproducible commands |
| G2 task-runner | mechanical scripts, docs, fixtures, deterministic codemods, commit batching | explicit write scope only | diff/commit plan reviewed by Codex gpt-5.5 and validation rerun |
| G3 never | secrets, deploys, final review, architecture, UI taste | none | route to Codex gpt-5.5 xhigh or Claude Opus 4.8 for design |

Default fuzzy or exploratory work to G0/G1. When a Bead is already clear and
task-runner safe, default that execution node to G2 Composer 2.5 rather than a
smarter model doing clerk work. G2 requires exact files, an easy revert path,
deterministic validation, stop rules, and Codex `gpt-5.5` review before final
acceptance. A G2 `$commit` node may create the commit, but Codex `gpt-5.5` still
owns the final review and any amend/follow-up decision.

## CASS Search Recipes

Search CASS for prior Grok behavior before broadening its permissions. Good
queries are specific enough to surface runs with commands, artifacts, and
failure modes:

Start broad when the exact recipe returns zero hits. Some CASS indexes tokenize
newer notes differently, so run `cass search "*grok*" --robot --limit 20
--days 90` or `cass search "grok sidecar" --robot --limit 20 --days 90` first,
then narrow using the phrases below after you identify a relevant session,
workspace, or commit breadcrumb.

```bash
cass search "grok sidecar routing and mcp auth fix" --robot --limit 10 --days 30
cass search "create_hidden_grok_session SWIMMERS_DISPATCHER_GROK_BIN" --robot --limit 10 --days 30
cass search "ntm spawn --grok sidecar" --robot --limit 10 --days 30
cass search "grok invalid_token uidotsh skillbox MCP" --robot --limit 10 --days 30
cass search "grok cli prompt-file sandbox read-only" --robot --limit 10 --days 30
cass search "Grok dispatcher cwd selection skill-tag extraction" --robot --limit 10 --days 30
cass search "grok sidecar generated worker prompt Beads write scope" --robot --limit 10 --days 30
cass search "grok sidecar read-only post-commit review artifact" --robot --limit 10 --days 30
cass search "grok sidecar shared worktree active NTM panes conflict" --robot --limit 10 --days 30
cass search "grok -p max turns no output read-only sidecar" --robot --limit 10 --days 30
cass search "grok unsupported reasoningEffort sidecar source discovery" --robot --limit 10 --days 30
cass search "grok --help worked no useful stdout source discovery" --robot --limit 10 --days 30
cass search "Grok sidecar available locally but not useful" --robot --limit 10 --days 30
cass search "grok sidecar did not contribute sources verified directly" --robot --limit 10 --days 30
cass search "grok 0.2.14 fwc dcg MCP spawn errors usable discovery leads" --robot --limit 10 --days 30
cass search "grok sidecar source discovery no verified X metrics" --robot --limit 10 --days 30
cass search "grok useful lead URLs verified against primary sources diagram versioning" --robot --limit 10 --days 30
cass search "grok could not establish durable per-version Mermaid link claim" --robot --limit 10 --days 30
cass search "grok source discovery candidates independently verified GitHub API HN Algolia" --robot --limit 10 --days 30
cass search "grok sidecar Reddit JSON 403 no verified X Discord Slack engagement" --robot --limit 10 --days 30
cass search "docs(dac): add grok sidecar routing notes" --robot --limit 10 --days 90
cass search "docs(dac): record grok no-output sidecar risk" --robot --limit 10 --days 90
```

When a search returns useful sessions, capture the lesson rather than copying
long transcripts:

```text
Query:
Run/session:
Task type:
Route used: dispatcher | Swimmers hidden session | direct headless
Permission tier: G0 | G1 | G2 | G3
Outcome: good | mixed | bad
Evidence artifact:
Validation command:
Correction needed by lead:
Reusable rule:
```

## Local Evidence References

Use these repo-local commits as breadcrumbs before widening Grok from G0/G1 to
G2. They are not substitutes for CASS, but they give stable terms to search:

| Reference | Search terms | Lesson to confirm in CASS |
| --- | --- | --- |
| `47a5b29 docs(orchestration): route grok sidecars` | `grok sidecar routing shared orchestration contract` | Grok is a routing/preflight lane, not an NTM pane class. |
| `b1ccf0d docs(dac): add grok sidecar routing notes` | `docs(dac) grok sidecar routing notes` | Good work is bounded, read-only, and independently checkable. |
| `8404d52 docs(dac): record grok no-output sidecar risk` | `grok -p max turns no output read-only sidecar` | Direct headless Grok can consume turns and return no usable packet; record the failure and fall back. |

If CASS shows Grok doing well on a new task family, add a concrete row here only
after a stronger model reviewed the artifact and the validation command passed.
If CASS shows Grok needed correction, keep the task in G0/G1 or route it to
Codex/Claude and record the correction in the lesson packet.

## 2026-06-01/02 Live Sidecar Observations

These examples came from a Beads-backed multi-repo research wave. They are
negative/mixed evidence, so they should narrow Grok autonomy until CASS shows a
different pattern.

| Context | Grok route | Outcome | Reusable rule | CASS search terms |
| --- | --- | --- | --- | --- |
| `ingredient_server` GTM SEO research Bead `ingredient_server-deep-research-gtm-ingredient-seo-content-moat-rdjj` | Direct headless G1 source-discovery sidecar | First run failed because the CLI sent unsupported `reasoningEffort`; retry completed with empty output. Grok did not contribute sources. | Treat direct Grok source discovery as optional. Retry once only when non-blocking, then verify sources directly and record the bad route. | `grok unsupported reasoningEffort sidecar source discovery`, `Grok sidecar available locally but not useful` |
| `buildooor-backend` GEO research Bead `buildooor-backend-deep-research-gtm-geo-ai-search-mmdx-9zk` | Direct headless G1 source-discovery sidecar | `grok --help` worked, but the bounded source-discovery run returned no useful stdout. All cited material was verified directly by the worker. | Do not count an installed Grok binary as useful evidence. Require non-empty stdout or a concrete artifact before giving it credit in closeout. | `grok --help worked no useful stdout source discovery`, `grok sidecar did not contribute sources verified directly` |
| `opensource/skillbox` OSS CLI distribution Bead `skillbox-deep-research-gtm-oss-cli-distribution-cef` | Direct headless G1 source-discovery sidecar | `grok 0.2.14` ran and returned a few usable discovery leads, but emitted `fwc`/`dcg` MCP spawn errors and did not provide verified X metrics. | Grok can be useful for first-pass source discovery, but keep metric claims untrusted until primary sources verify them. MCP spawn errors should cap the route at G1. | `grok 0.2.14 fwc dcg MCP spawn errors usable discovery leads`, `grok sidecar source discovery no verified X metrics` |
| `buildooor-backend` diagram-versioning landscape Bead `buildooor-backend-deep-research-diagram-versioning-landscape-2y5` | Direct headless G1 source-discovery sidecar | Grok produced useful lead URLs, but every claim still needed primary-source verification. It could not establish the exact durable per-version Mermaid link claim, so that stayed an evidence gap. | Good Grok evidence is a lead list, not a conclusion. Use it to widen source discovery, then keep unverifiable claims marked `not found` or `inferred`. | `grok useful lead URLs verified against primary sources diagram versioning`, `grok could not establish durable per-version Mermaid link claim` |
| `skillbox-config` operator-config distribution Bead `skillbox-config-deep-research-gtm-operator-config-distribution-qiz` | Direct headless G1 source-discovery sidecar | Grok helped surface candidate sources, but Reddit direct JSON returned 403, no verified X/Discord/Slack engagement was found, and exact-niche HN breakout evidence was not found. The final packet verified evidence through GitHub APIs, HN Algolia, and official/project docs. | Use Grok as a lead finder only. Verify with primary APIs/docs and mark missing engagement channels as evidence gaps instead of filling them with estimates. | `grok source discovery candidates independently verified GitHub API HN Algolia`, `grok sidecar Reddit JSON 403 no verified X Discord Slack engagement` |
| `buildooor` RTMMDX Grok-art Beads `buildooor-rtmmdx-epic-ql29.7.1` through `.7.4` | No Grok sidecar; Codex workers implemented a feature-flagged Grok adapter/cache/guard with mocked tests | The code path was cheap to verify because the live `grok` dependency stayed behind an off-by-default flag, cache tests asserted zero repeated calls, and fallback tests kept static preview uploads nonblocking. This is not evidence that Grok should own code edits. | Grok-adjacent implementation work can be safe when a stronger coding agent owns the patch and tests mock the CLI boundary. Do not upgrade Grok autonomy from this; at most use Grok G0/G1 to inspect CLI output contracts or source examples. | `buildooor grok art adapter feature flag mocked tests`, `grok adjacent implementation not grok sidecar evidence`, `cache hit zero grok calls static fallback` |
| Long-running Oracle/deep-research work delegated from a workspace sweep | No Grok watcher; root delegates waiting to a separate controller or scheduler | Treating a slow Oracle/deep-research job as stalled too early wastes attention and can cause duplicate launches. The operator clarified that these jobs can legitimately run a long time. | Do not poll until 30 minutes after launch, then poll every 15 minutes, and do not call the job stalled until 2 hours have elapsed without useful progress. Grok may summarize result artifacts after they exist, but it should not be the liveness judge. | `oracle deep research do not poll until 30 minutes`, `poll every 15 minutes stalled after 2 hours`, `grok not watcher of record oracle deep research`, `delegate waiting continue root loop` |
| `voice-to-text` random-fix opportunity scout during a workspace sweep | Direct headless G0 read-only prompt using `grok -p`, `--max-turns 4`, `--permission-mode dontAsk`, and `--no-subagents` | The process exited 0 but printed empty stdout, so it produced no worker-ready opportunity packet. | Treat exit code 0 as insufficient for Grok one-shots. Require non-empty stdout or a named artifact before using the result, and otherwise route the scouting task to a normal read-only explorer or Codex worker. | `voice-to-text grok random fix scout empty stdout`, `grok -p permission-mode dontAsk no-subagents empty output`, `grok one-shot exit 0 no artifact` |
| Workspace next-wave target selector during a random-fix sweep | Direct headless G0 read-only prompt using `grok -p`, `--disable-web-search`, `--no-memory`, and `--max-turns 2` | The run produced no selector packet and exited with `Max turns reached (limit: 2)`. It did not return repo candidates, reasons, or worker-ready prompts. | Very low turn caps can make direct Grok selectors fail silently until the cap trips. Use a higher cap only for non-blocking G0 work, and still require non-empty stdout or a named artifact before dispatching from the result. | `grok workspace next wave selector max turns reached`, `grok -p disable web search no memory max turns no output`, `grok selector no repo candidates no artifact` |

## 2026-06-03 Live Sidecar Observations (workspace bead sweep)

These came from a root-operator `divide-and-conquer` bead sweep across the
skillbox workspace. Negative evidence again — keep direct headless Grok at
G0/G1 and never block dispatch on it.

| Context | Grok route | Outcome | Reusable rule | CASS search terms |
| --- | --- | --- | --- | --- |
| Root orchestrator wanted a write-overlap risk table for 7 ready beads across 6 separate repos. ALL input data was inlined in the prompt; the task was pure read-only text formatting (emit one markdown table), no tools/search needed. | Direct headless G1 clerk: `grok -p "<prompt>" --max-turns 3 --permission-mode dontAsk --no-subagents --disable-web-search --no-memory` | BAD. Exit code 0 but stdout was 1 byte (empty); stderr `Max turns reached` at limit 3. Produced no table at all. The lead built the trivial overlap table by hand in seconds (all 7 beads were in distinct repos → all parallel-safe). | Even a softball read-only formatting task with all data pre-supplied fails at `--max-turns 3`. Grok appears to burn turns before emitting the final answer. Exit 0 is NOT proof of output — always check stdout byte count. Do not block any dispatch on a Grok one-shot; for clerk/overlap analysis the lead doing it inline is faster and reliable. If retrying, raise `--max-turns` only on non-blocking work. | `grok write-overlap clerk max turns reached empty stdout`, `grok -p inline data table no output workspace bead sweep`, `grok one-shot exit 0 one byte stdout` |

Retry confirmation: re-running the identical prompt at `--max-turns 15`
(non-blocking, per the "retry once with a higher cap only if non-blocking"
rule) produced the same result — exit code 0, empty stderr, 1-byte stdout. So
the failure is not a too-low turn cap; direct headless Grok ran to clean
completion and emitted no answer at all. Both 3-turn and 15-turn attempts are
dead weight here.

Practical rule confirmed this session: the seven-bead overlap analysis the
sidecar was supposed to produce was a 30-second hand task for the lead because
every bead lived in a different repo. For small ready frontiers, skip the Grok
overlap clerk entirely and reason about write scopes directly. In this
workspace, the productive delegation lanes were harness sub-agents (one per
disjoint repo, returning verifiable result reports) and the already-running NTM
codex panes — not Grok one-shots.

## Current Routing Notes

When a live run has multiple NTM panes writing in the same git worktree, do not
use Grok/Composer as an implementation or integration sidecar for broad code
changes. The useful Grok lane in that situation is G0/G1, plus preferred G2
task-runner nodes when Beads prove non-overlapping writes and a Codex `gpt-5.5`
review node owns acceptance. Examples: clean up dispatch prompts, identify
likely write-overlap risks from Beads metadata, produce a read-only evidence
inventory, write a bounded helper script, classify a bounded repo set into a
declared artifact, or run a scoped `$commit` batch after validation.

Do not use Grok as the watcher of record for long-running Oracle or deep-research
jobs. Give those jobs a deterministic quiet window before the first check: wait
30 minutes after launch, poll every 15 minutes after that, and do not call the
job stalled until 2 hours have elapsed without useful progress. Delegate that
waiting loop to a controller or scheduler so the root orchestrator can continue
dispatching other Beads. Grok may summarize result artifacts after they exist,
but the scheduler should judge liveness from launch time, process/session state,
expected artifacts, Beads state, and validation evidence.

Example low-risk prompts to search for or reuse:

```text
Given br ready output and git status, identify which ready Beads have overlapping
write scopes. Return only a table with bead id, likely touched paths, conflict
risk, and suggested serial/parallel routing.

Given a messy user request, extract the repo cwd, named skills, required
validation commands, commit policy, and worker-safe prompt skeleton. Do not
invent implementation details.

Given a post-commit diff summary, list likely review hotspots and exact files to
inspect. Do not declare the commit safe.
```

## Operator Rule

A Grok sidecar is complete only when its expected artifact, process/session
state, Beads node, and independent validation agree. If those surfaces disagree,
treat Grok output as advisory evidence and keep the owning Beads node open.

## Observed Outcomes Log

A running log of real Grok Composer 2.5 sidecar runs so future rounds calibrate
task selection by evidence, not vibes. Append newest entries last. Each entry:
date, task class + leeway tier, prompt shape, outcome, and a CASS hook to find
the run. The lead always re-verifies independently — these "PASS" marks are
lead-verified, not Grok self-reports.

### 2026-06-13 — sbp epic divide-and-conquer round (Opus 4.8 lead + Grok sidecars)

Two **G2 commit-runner** tasks, both clean PASS:

1. **Baseline commit, clean repo.** Commit exactly N already-modified named
   files; explicit `git add <path>` per file; hard no-wildcard rules; leave
   untracked + unrelated dirty files; exact message; no push. Result: staged
   exactly the named files, self-verified the index before committing, left an
   untracked report and an unrelated `.beads/issues.jsonl` untouched, reported
   the hash + post-status. Lead reverified with `git show --name-only`.
2. **Path-scoped commit inside a minefield repo (harder).** Same prompt shape
   but the repo had ~60 OTHER unrelated dirty paths (incl. 51 staged-pending
   deletions) and was 3 commits ahead of origin. Result: committed exactly the 4
   named paths; left all ~60 dirty paths untouched (lead verified the dirty count
   was unchanged); no sweep, no push.

**Reusable G2 commit-runner recipe (what made these reliable):**
- Enumerate the EXACT file list; require one explicit `git add <path>` per file.
- Forbid `git add -A` / `git add .` / `git add -u` / `git commit -a` / wildcards
  by name in the prompt.
- Name what to LEAVE (untracked artifacts, unrelated dirty paths) explicitly.
- Require a self-verify step (`git diff --cached --name-only` must equal the
  list; unstage anything extra) BEFORE the commit.
- Require a final report with the commit hash + post-commit status; the lead
  re-verifies with `git show --name-only` and a dirty-path count. Never accept
  the prose alone.
- The lead validates the diff is green BEFORE handing the commit to Grok: Grok
  runs the commit; the lead owns correctness and acceptance.

**Leeway update:** two clean runs (incl. a 60-dirty-path minefield) → Grok
Composer 2.5 is reliable for **G2 `$commit` / commit-batching** when the prompt
names the exact paths, the no-wildcard rules, and the leave-list, and the lead
pre-validates the diff. Keep it **G3 (never)** for: deciding WHAT to commit,
judging whether a diff is correct, push/amend, or any commit whose scope is
fuzzy.

**Transport note:** `grok --prompt-file <path> --cwd <dir> --always-approve
--max-turns 30` ran each multi-step git task fine in a single headless
invocation. Stderr showed `Failed to spawn MCP server 'dcg' / 'fwc' (No such
file or directory)` — these did NOT block the shell/git task. For pure shell
sidecars, ignore those MCP-spawn lines.

CASS hooks to find these or similar runs:

```bash
cass search "grok commit-runner explicit git add no wildcard path-scoped" --robot --limit 10 --days 30
cass search "grok sidecar baseline commit minefield dirty paths leave-list" --robot --limit 10 --days 30
cass search "grok prompt-file always-approve dcg fwc MCP spawn failed shell ok" --robot --limit 10 --days 30
```

**Update (same session, +3 more clean runs → 5 total, 0 failures):** grok also cleanly executed (3) a **2-commit split** and (4) a **3-commit split** from a single multi-file diff, plus (5) another 2-commit opensource split — each commit's file list specified exactly in the prompt. Conclusion reinforced: when the prompt names the exact per-commit file lists + no-wildcard rules + the leave-list, and the lead pre-validates the diff and re-verifies after, Grok Composer 2.5 is a dependable G2 commit-runner even for multi-commit splits and minefield repos. The lead doing the *grouping decision* (which files → which commit) and grok doing the *mechanical staging+commit* is the reliable division of labor — do NOT ask grok to decide the grouping itself.

### 2026-06-14 — portfolio autonomous-burndown run (Opus 4.8 NTM lead, grok-composer-2.5-fast sidecar)

**Invocation gotcha (record this — it cost ~5 probe cycles).** In this devbox session the *only* reliable headless one-shot is the documented `--prompt-file` form. The `--output-format plain|json` top-level path **fails silently**: `grok --output-format plain "prompt"` returns `rc=1` with **empty stdout, empty stderr, and an empty `--debug-file`** — no error surfaced. `grok agent stdio` is a JSON-RPC channel (rejects a plain-text line: `failed to parse incoming message: expected value at line 1 column 1`). `grok agent headless` is the WebSocket-relay lane (needs relay/leader infra). Auth itself was fine throughout (`grok models` → "logged in with grok.com", default `grok-composer-2.5-fast`). **Working command:**

```bash
grok --prompt-file /tmp/task.txt --cwd <repo-or-portfolio-root> --always-approve --max-turns 20
```

**GOOD (G1 read-only clerk + single-file write).** Tasked grok to classify all 39 `.beads`-bearing repos under `/srv/skillbox/repos` into IOS_MAC / LINUX / OTHER by reading manifest files only and writing the result to one `/tmp` artifact. Wall-time **17s**, `rc=0`, artifact written exactly to spec. Accuracy on independent spot-check: **100%** — including the non-obvious `dream` → IOS_MAC (it carries both `Package.swift` and `Dream.xcodeproj`; a quick `ls` of the repo root would have mislabeled it). It also respected the manifest-scope rule precisely (`dogswipe`/`finalreceipts` → OTHER because no recognized top-level manifest, not because grok gave up). This is the canonical good-grok shape: a precise rule, read-only, one declared write target, bounded turns. The lead still verifies the surprising rows.

**Division of labor that worked:** lead writes the exact rule + the single output path into the prompt file; grok does the filesystem traversal + classification + write; lead independently re-checks the surprising buckets with `ls`/`find`. Token cost to the Opus lead: ~one Bash call to verify vs. doing the whole 39-repo traversal itself.

**Routing consequence for this run:** direct headless grok is GREEN for `--prompt-file` shell/clerk/commit-runner one-shots; sidecar work that needs `--output-format`-style streamed text should instead route through the `voice-to-text` dispatcher / Swimmers lane, or just be given a file-write target. When in doubt this run defaulted token-saving sidecar execution to **codex gpt-5.5** (proven live in the htma_server panes) and reserved grok for `--prompt-file` clerk/commit one-shots.

CASS hooks to find this or similar runs:

```bash
cass search "grok output-format plain silent rc=1 empty stderr debug-file prompt-file works" --robot --limit 10 --days 30
cass search "grok agent stdio JSON-RPC failed to parse expected value headless relay leader" --robot --limit 10 --days 30
cass search "grok prompt-file classify repos manifest IOS_MAC LINUX read-only single write 17s" --robot --limit 10 --days 30
cass search "design model unavailable route design opus ntm spawn cc opus" --robot --limit 10 --days 30
```

### 2026-06-14 — Sweet Potato open-bead revenue/auth wave

**GOOD non-use (route restraint).** A Sweet Potato `divide-and-conquer` wave
selected four backend Beads: Stripe subscription-missing-row revocation, CFO
service-admin token scoping, dayrate free-booking audit emission, and Mailgun
suppression fallback. All four were revenue/auth/security writer nodes with
deterministic `make pytest` + `make lint` validation and overlapping risk
around shared trust boundaries. The correct route was Codex `gpt-5.5` NTM panes
with Beads claims and narrow write scopes. Grok was deliberately not launched.

**Reusable rule:** treat "do not use Grok" as useful routing evidence when the
task family is authz, payment-to-access correctness, service-principal scope, or
audit emission. Safe Grok participation in this shape is G1 only: pre-supplied
facts -> edge-case checklist, route/file inventory, or commit-scope sanity
table. Do not let Grok choose the policy, write the patch, close the Bead, or
perform final review.

CASS hooks to find this or similar runs:

```bash
cass search "Sweet Potato open bead revenue auth wave grok deliberately not launched" --robot --limit 10 --days 30
cass search "sp-stripe-sub-missing-row-revoke cfo service admin token dayrate audit mailgun suppression codex ntm" --robot --limit 10 --days 30
cass search "grok not writer authz payment-to-access service-principal audit emission" --robot --limit 10 --days 30
cass search "grok G1 edge-case checklist pre-supplied facts auth revenue beads" --robot --limit 10 --days 30
```

### 2026-06-14 — Sweet Potato deploy-smoke review attempt

**BAD for multi-file deploy/auth/e2e review.** During Bead
`sp-post-deploy-synthetic-smoke-2an0`, the lead tried direct headless G1
read-only Grok review on the deploy workflow and e2e runner with
`grok --max-turns 1 -p ...` and `grok --max-turns 3 -p ...`. Both attempts hit
`Max turns reached` and produced no actionable report. `grok --help` was useful
only for discovering CLI knobs. Focused read-only subagents and Codex root
review produced the actual findings; Codex implemented and validated the
wallet nonce/sign-in smoke.

**Reusable rule:** do not use low-turn direct Grok as a repo-roaming reviewer
for deploy/auth/e2e changes. Good use here is G0 command discovery or a
facts-only checklist with tools disabled after the lead supplies exact context.
Require non-empty stdout or a named artifact before counting Grok as evidence.

CASS hooks to find this or similar runs:

```bash
cass search "grok max turns reached read-only multi-file review" --robot --limit 10 --days 30
cass search "grok sidecar too-tight max-turns no final report" --robot --limit 10 --days 30
cass search "grok CLI help discover options low risk" --robot --limit 10 --days 30
cass search "grok deploy workflow e2e runner review" --robot --limit 10 --days 30
cass search "sidecar suitability low risk command discovery" --robot --limit 10 --days 30
cass search "sp-post-deploy-synthetic-smoke-2an0 grok no report" --robot --limit 10 --days 30
```
