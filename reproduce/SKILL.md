---
name: reproduce
description: >
  Command-first verification workflow that forces agents to test changes before
  asking the user to test, and treats browser DevTools as a last resort. Use
  when: "reproduce", "/reproduce", "reproduce this bug", "test this", "verify
  this fix", "can you test it", "debug this", "how should we test this",
  "manual QA", "browser bug", "devtools", or when an agent is about to hand
  testing back to the user without first trying test-suite, API, CLI, log, or
  DB verification.
---

# Reproduce

Verify behavior with automation, APIs, logs, and data checks before opening
browser DevTools.

## Rules

1. Do not ask the user to test until you attempted at least two independent verification paths and reported command outputs.
2. Prefer existing test suite and repo-native scripts first.
3. Prefer CLI/API/log/DB probes over browser inspection.
4. Propose at least three non-DevTools alternatives before escalating to DevTools.
5. If blocked by missing access, request the minimum required access with exact purpose and command.
6. Open DevTools only if non-browser paths cannot observe the behavior.
7. If DevTools is used, include the DevTools Justification block.
8. Finalize with regression protection: add or update tests so the issue is prevented from silently returning.
9. For local-environment bugs, codify seed/restart/env-sync steps in `.env-manager` automation so future runs are one command.

## Workflow

### 1) Discover how the repo is testable

Run fast discovery commands:

```bash
rg --files | rg -i '(^|/)(README|Makefile|Justfile|package\.json|pyproject\.toml|go\.mod|docker-compose.*\.ya?ml)$'
rg -n -S 'pytest|vitest|jest|playwright|cypress|e2e|smoke|integration|health|make test|npm run test|pnpm test|uv run pytest'
```

Select the fastest useful signal in this order:
1. Existing focused test.
2. Existing health/smoke check.
3. Direct API or CLI probe.
4. Log and DB state verification.
5. New minimal regression test.
6. DevTools (last).

### 2) Run command-first probes

Use [references/probe-ladder.md](references/probe-ladder.md) for symptom-to-command mappings.

Minimum bar for "I tested it":
1. One behavior assertion (test/API response/status code/CLI output).
2. One side-effect assertion (log line, DB row/state transition, emitted event, email/job artifact).

Before escalating, list and try multiple ideas from different surfaces:
1. Test surface: run focused existing tests, then add a minimal failing regression test if missing.
2. API surface: replay the flow with `curl`/CLI and assert response contract.
3. Runtime surface: inspect app, worker, and proxy logs around the event window.
4. Data surface: verify DB/cache/queue side effects directly.
5. Infra surface: health, container state, env wiring, dependency reachability.

### 3) Use ecosystem checks when available

If `.env-manager` exists (HTMA/OpenClaw local ecosystem), run:

```bash
if [ -d ../.env-manager ]; then
  ENVM="$(cd ../.env-manager && pwd)"
elif [ -d "$HOME/repos/.env-manager" ]; then
  ENVM="$HOME/repos/.env-manager"
fi
REPOS_ROOT="${REPOS_ROOT:-$(cd "$ENVM/.." && pwd)}"
SANITY="$(ls ~/.codex/skills/dev-sanity/scripts/sanity_check.sh ~/.claude/skills/dev-sanity/scripts/sanity_check.sh "$REPOS_ROOT/opensource/skills/dev-sanity/scripts/sanity_check.sh" 2>/dev/null | head -1)"
bash "$SANITY" --errors-only
```

For Google/email workflows, prefer `gog` plus service logs instead of manual inbox/browser checks.

For local bug closeout, also run:

```bash
bash "$SANITY" --health-only
bash "$SANITY" --wiring-only
```

Reference `$dev-sanity` whenever the issue is local runtime/configuration behavior.

### 4) Fill gaps instead of punting

If no deterministic path exists, add the smallest regression test or smoke script that proves the fix.

Preferred pattern:
1. Add one failing test reproducing the bug.
2. Implement the fix.
3. Re-run the focused test and nearest related suite.

If still blocked, propose at least three concrete next ideas, each with:
1. Command(s) to run.
2. Expected signal.
3. Why it may isolate the bug.

Example idea set:
1. Add temporary request/response logging around the suspected handler and re-run a `curl` probe.
2. Replay production-like payload from logs into local API to test parser/validation drift.
3. Run headless E2E from CLI (Playwright/Cypress) before any interactive browser tooling.

### 5) Access request protocol (before DevTools)

If a better verification path exists but requires access, request it directly instead of jumping to DevTools.

Use this format:

```markdown
Access Request
- Missing access: <credential/service/env/host/container>
- Why needed: <specific verification goal>
- Command once granted: `<exact command>`
- Expected evidence: <what pass/fail output will show>
- Fallback if denied: <next-best command-first path>
```

Ask for the minimum needed. Prefer read-only access for verification tasks.

### 6) DevTools gate (last resort)

Only use DevTools if all are true:
1. Behavior is browser-runtime-only (layout, paint, client-only state, extension-specific issue).
2. No API/log/test/CLI assertion can observe it.
3. At least two non-DevTools probes were attempted first.

When used, report:

```markdown
DevTools Justification
- Target behavior: <what must be observed>
- Why command-line probes are insufficient: <reason>
- Non-DevTools attempts:
  1. `<command>` -> `<result>`
  2. `<command>` -> `<result>`
- DevTools action: <panel + exact check>
- Evidence captured: <console/network/screenshot/log reference>
```

### 7) Regression lock-in (required final step)

When root cause is clear and test coverage is feasible, end by codifying the bug as a regression test.

Required sequence:
1. Write or update a focused test that fails on the buggy behavior.
2. Apply the fix.
3. Re-run the focused test (must pass).
4. Re-run nearest related suite to catch collateral breakage.

If no test can be added, explicitly state why and provide the closest durable alternative (for example: a deterministic smoke script with clear assertions).

### 8) Local automation lock-in (required for local env bugs)

If resolution required manual seeding, startup ordering, env sync, or restarts, update `.env-manager` so the same class of bug is faster to catch and recover.

Required sequence:
1. Promote manual local commands into `.env-manager` automation (typically `Makefile` targets and scripts it calls).
2. Ensure seeding and restart flows are idempotent or clearly split into explicit safe targets.
3. Validate from automation entrypoint (not ad-hoc one-off commands).
4. Re-run `$dev-sanity` checks to verify the loop is healthy.

Preferred path in this repo layout:
1. Update `../../.env-manager/Makefile` (or referenced scripts) when local seed/restart behavior should be standardized.
2. Start/restart using `.env-manager` targets.
3. Run `bash "$SANITY" --errors-only`, `--health-only`, and `--wiring-only`.

Do not leave critical local recovery steps as undocumented manual commands in chat output.

## Response Template

After verification, reply with:

```markdown
Verification Summary
- Claim: <what works or fails>
- Commands run:
  1. `<command>`
  2. `<command>`
- Evidence:
  - Assertion: <output/status/log/test evidence>
  - Side effect: <db/log/event artifact>
- Alternatives attempted: <3+ non-DevTools ideas tried or ruled out>
- Access requested (if any): <what was requested and why>
- Regression protection: <failing test added/updated, file path, and pass result; or why not feasible>
- Local automation updates: <.env-manager Makefile/script changes for seed/restart/env sync; or not applicable>
- Dev sanity closeout: <errors/health/wiring results; or not applicable>
- Decision: PASS | FAIL | PARTIAL
- Next command (if needed): `<command>`
```

If blocked, state exactly what prevented testing and the next concrete command needed to unblock. Do not stop at "please test this" without attempting a path first.
