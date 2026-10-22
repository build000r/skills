# Grok Sidecar Task Selection

Use this reference only when the selected route and the user's instructions
permit Grok. Follow the current tier decision in `workgraph-synthesis.md`;
historical model or CLI versions do not select today's route. An explicit
all-Codex request applies to sidecars too.

## Scope and authority

A sidecar supplies bounded work. The root owns integration, acceptance, Beads
closeout, and authority decisions. Use the configured interactive or headless
transport after its normal preflight. Do not create another session merely to
format facts the lead already has.

| Tier | Suitable work | Permission boundary | Acceptance |
| --- | --- | --- | --- |
| G0 router | cwd and skill extraction, prompt cleanup | read-only supplied context or search | lead checks dispatch inputs |
| G1 evidence | file inventories, source leads, outlines, summaries | read-only shell/search within named scope | reproduce important claims and inspect output |
| G2 task runner | mechanical scripts, fixtures, scoped codemods, authorized commit execution | exact named files and actions | independent risk-appropriate review and required checks |
| G3 excluded authority | secrets, deploys, production changes, final review, architecture decisions | no delegated authority from this reference | route through the owning workflow |

G2 requires a Bead with write scope, validation, stop conditions, acceptance
owner, and a reversible change. Use `med` for ordinary implementation under the
current route contract and `high` for acceptance that requires that tier. This
reference does not grant a sidecar permission to choose a different model,
bypass an operator choice, or broaden a task.

Good candidates have explicit inputs and output that can be checked with
`rg`, `git diff`, tests, or existing Beads state. Use the normal agent response
or a temporary file. Retain a file only when a named downstream consumer or an
explicit deliverable needs it; clean temporary prompt/output files when their
consumer finishes.

Avoid sidecars for broad repo roaming, subtle multi-repo invariants, secret
access, authorization/payment policy, NTM recovery, or liveness judgments.
For UI/design work, follow the selected design route and its acceptance owner;
this reference does not make Grok the final design authority.

## Verify the route before depending on it

CLI behavior varies across releases and transports. Check the installed
version and help, then use one small bounded smoke task with observable output
when that route is uncertain. Historical successes and failures are evidence
for a hypothesis, not proof of current behavior.

- Exit zero or an installed binary does not prove useful work. Require
  nonempty, relevant output and verify the content before using it.
- Distinguish a plain prompt command from JSON-RPC or relay transports; use the
  supported prompt-file form when available. Avoid shell interpolation of
  multiline prompts and resolve aliases before combining approval flags.
- Respect the existing permission policy. Do not add broad approval flags to
  make an uncertain invocation work.
- Missing MCP tools limit the tasks the route can perform. Verify whether the
  required operation succeeded; neither ignore all spawn errors nor assume
  unrelated shell work failed.
- If a bounded run returns no useful output, make at most one evidence-backed
  retry while it remains non-blocking. Then use the selected working route.
  Raising a turn cap repeatedly is not a recovery strategy.
- For a small ready frontier, the lead should inspect disjoint write scopes
  directly when dispatching a formatting sidecar would take longer.

Source-discovery output is a lead list. Verify claims, metrics, and exact URLs
against their original sources. Failed access leaves an evidence gap; it does
not establish that a claim is false or that a metric is zero.

## Mechanical commit execution

The lead decides the grouping and verifies the diff before delegating an
already authorized commit. Name exact paths, the commit message, and any
unrelated state to preserve. Require explicit path staging and prohibit broad
staging (`git add -A`, `git add .`, `git add -u`, wildcards, or `git commit -a`).
The staged path set must match the agreed batch. Never unstage another worker's
state to make it match; stop and resolve ownership when unrelated staging is
present.

After execution, verify the actual commit paths, hash, index, and remaining
working changes. A successful command or prose report is insufficient. Push,
amend, further edits, and scope changes require their own existing task
authority; a commit-runner assignment does not imply them.

## Progress and memory

Observe work according to its task budget and actual progress signals: process
state, output, required checks, and Beads state. Research providers may have a
specific documented SLA; do not apply a blanket 30-minute quiet window or
2-hour stall threshold to ordinary delegated tasks. Keep waiting in the
controller/scheduler when independent work remains, and investigate bounded
no-progress intervals before relaunching a job.

Use CASS when a current failure or a proposed permission expansion needs prior
context. Search the task class and failure, then narrow to a relevant session:

```bash
sbp cass search "grok prompt-file empty output" --robot --limit 10 --days 90
sbp cass search "grok commit-runner explicit paths" --robot --limit 10 --days 90
sbp cass search "grok source discovery validation" --robot --limit 10 --days 90
```

Keep invocation details in their existing session/Bead records. Update this
reference only with a reviewed reusable rule; do not append trial tables,
commit/session histories, or pass-count anecdotes. Use temporary notes for a
comparison when needed, then remove them.

Completion requires the expected result, terminal process/session state, the
owning Bead, and independent validation to agree. Otherwise treat the output as
advisory and keep the task open.
