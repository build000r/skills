# Grok Sidecar Task Selection

Use this reference when a divide-and-conquer run wants cheap Grok help without
turning Grok into an unsupervised implementation owner.

## Default Posture

Grok is a sidecar, not an NTM pane class. Route it through the shared dispatcher,
a Swimmers hidden session, or a direct headless one-shot, then reconcile the
output through Beads and the normal result artifact.

Prefer Grok when the work is cheap to verify, read-only by default, and useful
even when the output is only a rough first pass. Avoid Grok when the work needs
trusted final judgment, secret-bearing access, UI taste, or broad writes.

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

Good signs:

- the task has a bounded artifact path
- the answer can be checked with `rg`, `git diff`, tests, or Beads state
- a wrong answer costs minutes, not a corrupted repo
- the sidecar can run with `--sandbox read-only`, `--deny Edit`, and
  `--deny Write`

## Bad Grok Work

Do not use Grok as the primary owner for:

- final integration review or the last approval before commit
- UI/UX/design-system judgment, visual polish, or screenshot parity
- secret-bearing auth, MCP token repair, deploys, pushes, or production writes
- broad refactors where correctness depends on subtle local invariants
- NTM pane tending, stuck-pane recovery, rate-limit diagnosis, or Beads closeout
- tasks that require editing files outside an explicit write scope
- tasks where the only validation is "the model says it is done"

Bad signs:

- the sidecar needs write access before it can produce value
- completion depends on an NTM idle state instead of a result artifact
- the task spans several repos without a root-owned integration plan
- validation needs credentials the sidecar should not see

## Leeway Tiers

Use these tiers when deciding how much autonomy to give Grok:

| Tier | Use | Permissions | Required proof |
| --- | --- | --- | --- |
| G0 router | cwd, skill tags, prompt cleanup | read-only, no tools beyond search | lead inspects output before dispatch |
| G1 evidence sidecar | inventories, doc audits, candidate file lists | read-only shell/search | artifact plus reproducible commands |
| G2 narrow writer | mechanical docs or fixture edits | explicit write scope only | diff reviewed and validation rerun |
| G3 never | secrets, deploys, final review, UI taste | none | route to Codex or Claude Opus |

Default to G0 or G1. Use G2 only when the owning workflow names the exact files,
the diff is easy to revert, and a stronger model reviews it before commit.

## CASS Search Recipes

Search CASS for prior Grok behavior before broadening its permissions. Good
queries are specific enough to surface runs with commands, artifacts, and
failure modes:

```bash
cass search "grok sidecar routing and mcp auth fix" --robot --limit 10 --days 30
cass search "create_hidden_grok_session SWIMMERS_DISPATCHER_GROK_BIN" --robot --limit 10 --days 30
cass search "ntm spawn --grok sidecar" --robot --limit 10 --days 30
cass search "grok invalid_token uidotsh skillbox MCP" --robot --limit 10 --days 30
cass search "grok cli prompt-file sandbox read-only" --robot --limit 10 --days 30
cass search "Grok dispatcher cwd selection skill-tag extraction" --robot --limit 10 --days 30
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

## Operator Rule

A Grok sidecar is complete only when its expected artifact, process/session
state, Beads node, and independent validation agree. If those surfaces disagree,
treat Grok output as advisory evidence and keep the owning Beads node open.
