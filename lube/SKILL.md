---
name: lube
description: Friction-removal retrospective for agent sessions. Use when the user says "lube", "$lube", "/lube", "friction", "several frictions were observed", "how do we unblock this", "avoid this in the future", or asks to prevent similar or adjacent blockers across future sessions.
depends_on:
  - ask-cascade   # closeout cascade interviews the operator through remaining asks
---

# Lube

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using lube`.

Preferred format: `Using lube to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix. Usage review tooling depends on this stable
marker; without it, lube invocations look like path-touch heuristics instead of
confirmed skill use.

Several frictions were observed in our session that I believe could have been avoided. How do we unblock this and all similar or adjacent situations in the future?

Use the current session as evidence, then convert each friction into the smallest durable unblocker.

## Workflow

1. List the observed frictions as concrete moments. If details are missing, state the assumption instead of inventing evidence.
2. Classify the avoidable cause: missing skill trigger, unclear skill contract, absent API key, unavailable CLI/API/SDK, brittle manual step, missing environment setup, weak defaults, missing test, missing runbook, or missing automation.
3. Pick the smallest durable fix:
   - Use `$skill-issue` to create or improve a skill when the fix belongs in an agent workflow.
   - Set up or document credentials, environment variables, or one-time configuration when access blocked the work.
   - Check for an official CLI, API, or SDK when repeated browser/manual service work caused friction.
   - Add or improve a script when the same shell/API sequence is likely to recur.
   - Add a checklist, test, or repo doc when the prevention belongs next to the code.
4. Execute safe local fixes immediately. Ask only for secrets, paid external actions, destructive changes, or ambiguous policy decisions.
5. Before closeout, run at least one concrete verification command for every
   material fix. Use the owning workflow's validator for a skill change; the
   narrowest relevant test, syntax check, or smoke command for code; and the
   product's doctor or recalibration command plus a read-only state check for
   configuration, links, or runtime changes. Include the exact command and
   pass/fail result under `Action taken`.
6. Close with what changed, what still needs human input, and how the change
   prevents adjacent failures. If verification cannot run because it needs a
   secret, external gate, paid action, or unavailable tool, do not call the fix
   verified; put the blocker and the command that remains under `Remaining ask`.
7. Run the Closeout Cascade below: in an interactive session, every
   `Remaining ask` becomes an `ask-cascade` question, not parked prose.

## Evidence Miner

For broad "what should we improve?" or "$cass $skill-issue $lube" requests,
run the bundled miner instead of hand-assembling the same shell sequence:

```bash
python3 scripts/lube_evidence_miner.py --skills cass,skill-issue,lube --since month
```

The miner combines the portfolio-level `skill-issue` opportunity scan with
per-skill usage reviews, then emits the lube output shape below. It is evidence
gathering only; after reading it, still execute the smallest safe unblocker
directly when the fix is local and non-destructive.

For "mine cass for repeated agent pain" requests, do not hand-roll 10+
`sbp cass search` calls; run the frequency mode instead:

```bash
python3 scripts/lube_evidence_miner.py --mode frequency --top 5
```

It batch-searches a curated friction-signal list through the `sbp cass search`
backend, aggregates hits per pattern across sessions, ranks by
session-frequency × approximate matched tokens, and emits ranked JSON with
`pattern`, `score`, `session_ids`, `sample_snippet`, and a suggested
`lube_target` classification ready for bead creation. Add ad-hoc signals with
`--terms "signal one, signal two"`; override the backend with `--cass-command`
or `LUBE_CASS_COMMAND` (used by tests to mock the backend).

The miner enforces a process-level kill per search (`--timeout-seconds` + 15s
grace) and opens a circuit breaker after 2 consecutive process timeouts,
skipping remaining searches and emitting partial JSON. Exit 2 means every
search errored with zero sessions found — treat that as backend-down, check
`sbp cass status`, and fall back to grepping local transcripts under
`~/.claude/projects/*/*.jsonl` directly. Progress streams on stderr
(`[lube-miner] N/M searching: <pattern>`), so a backgrounded run shows
liveness.

## Skill Self-Verification

When this skill's contract or the bundled miner changes, run the bundled tests
from the skill directory and re-validate the contract before shipping:

```bash
pytest tests/ -q
python3 "$SKILL_ISSUE_DIR"/scripts/quick_validate.py .   # skill-issue's validator
```

## Skillbox Log Review

When the friction source is an orchestration or Skillbox runtime issue, inspect
recent events deliberately instead of reading the feed from the beginning. Call
`skillbox_events` once to see `total_events`, then tail with a cursor near the
end, for example `cursor = max(total_events - 100, 0)`.

Classify repeated `pulse.restart_failed` or cross-client service-noise entries
separately from target-repo blockers. Only turn them into implementation work
when they explain the current goal's failed proof; otherwise record them as
process noise and keep the closeout focused on the exact approval or runtime
gate that still blocks completion.

When a client-scoped event feed returns rows whose `client_id` or
`detail.client_id` differs from the requested client, treat those rows as
cross-client noise unless another field directly explains the current proof
failure. Do not let subject/name matches alone promote another client's pulse
failure into the target repo's blocker list.

## Output Shape

- Observed friction
- Root cause class
- Durable unblocker
- Action taken
- Remaining ask

Do not turn this into a blame postmortem. Do not stop at advice when a safe concrete fix can be made in the workspace.

## Closeout Cascade (Required When Asks Remain)

A written `Remaining ask` list is not a closeout in an interactive session —
it is where operator-owned blockers go to rot. After printing the output
shape, if one or more remaining asks need an operator decision or action,
invoke the `ask-cascade` skill and interview the operator through them:

- One question per remaining ask, dependency-ordered: decisions that unblock,
  reshape, or invalidate other asks come first.
- Offer concrete executable options with a recommended default, never an
  open-ended "what do you want?"; "leave it parked" is always a valid option
  and must be listed when parking is safe.
- Execute whatever each answer unlocks in the same session, appending the new
  actions and their verifications to the closeout.

Skip the cascade only when there are zero remaining asks, or the run is
non-interactive (headless, cron, subagent, or the operator asked for a
report-only pass); then the written `Remaining ask` list stands as the
handoff.
