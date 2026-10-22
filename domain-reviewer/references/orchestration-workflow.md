# Implementation Review and Targeted Repair

Read the accepted task/plan, relevant implementation diff, standards and required
validation. Use one independent tracked reviewer on the selected substrate;
native Codex messaging supports review dialogue without another controller.

The reviewer returns exact acceptance evidence and actionable material findings.
Use the checks in [audit-workflow.md](audit-workflow.md). Repair findings inside
the authorized scope through disjoint owned tasks, then recheck affected behavior
and new risks. Reuse reviewer context where useful. Stop once accepted behavior
and required checks pass with no unresolved material finding. Additional reviews
or hardening need a concrete concern; optional improvements do not restart work.
Honor an explicitly requested score threshold in addition to acceptance.

A repeated unchanged finding is a reason to diagnose the blocker, not launch
another identical repair. Report the exact decision/dependency and continue work
that does not depend on it. Do not add permission loops for already authorized
repairs. Preserve teammate changes and never use blanket staging/reset commands.

Use the existing tracker and tracked result channel by default. Only a real file
consumer needs a report. The optional run_codex_audit_loop.py helper uses one
private temporary latest report and logs, cleaned after completion. Its default
requires exactly these current verdict lines:

```text
Acceptance: PASS
Required checks: PASS
```

Use FAIL when unresolved. Add `## Agent Handoffs` with `### For Backend Issues`
or `### For Frontend Issues` fenced blocks only for real remaining repairs.
The helper runs another review only after fixes. Missing or conflicting verdicts
refuse completion. Numeric scores are optional; `--threshold N` explicitly opts
into `### Overall Compliance Score: **XX/100**` as an additional gate.
`--max-iterations` is a bound, never a target. `--report-path` or `--log-dir`
explicitly selects retained outputs; interrupted runs retain their scratch for
recovery. Do not commit report history or create extra indexes by default.

After acceptance, record the concise outcome and commit identities in the task
store, then retire obsolete scratch. A separate retirement worker is opt-in.
Do not archive unmerged work or create completion narratives automatically.
