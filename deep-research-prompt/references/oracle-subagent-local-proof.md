# Oracle subagent local proof

This is the release gate between deterministic browser-contract tests and the
remote/native Oracle surfaces. It makes two bounded live submissions through
the hidden, enrolled browser: one standard Pro run and one Deep Research run.
It also proves the main fail-closed paths without mutating or logging auth
state.

## Preconditions

Resolve the `skills` Oracle overlay and launch its exact dedicated target:

```bash
. skill-issue/scripts/overlay_env.sh
overlay_env_load oracle --cwd "$PWD" --require || exit 1
deep-research-prompt/assets/scripts/launch-chatgpt-cdp.sh \
  --no-submit-smoke --json
```

`overlay_env_load` rather than `eval "$(...)"`: this proof asserts fail-closed
behaviour, and the bare `eval` form cannot see a resolver failure at all — it
discards the exit status, including `--require`'s, and would run the proof
against default config while reporting success.

The first-ever setup, or an expired ChatGPT session, requires the only visible
browser interaction in this workflow:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs \
  login --enroll-current-account --json
```

Use `login --json` instead when an enrollment policy already exists. The login
command reveals only the launcher-attested target, waits for the selected
account to expose a unique active Pro workspace and canonical Pro model, then
hides the browser again. It stores fingerprints only. Never copy the cookie
database, Chrome profile, auth policy, browser port, or session data.

Before the live proof, this must exit zero:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs \
  doctor --json
```

## Run

The destination must be a new normalized directory below
`/tmp/oracle-subagent-e2e/`. The canonical release invocation is:

```bash
deep-research-prompt/tests/live/oracle-subagent-local-proof.sh \
  --out /tmp/oracle-subagent-e2e/FINAL/local
jq -e '.hard_gates == "pass"' \
  /tmp/oracle-subagent-e2e/FINAL/local/manifest.json
```

The script intentionally refuses an existing destination. A failed attempt
keeps its evidence and writes `manifest.json` with `hard_gates: "fail"`; use a
new sibling attempt directory rather than deleting evidence in place.

Two live sends occur, both containing a fresh synthetic nonce:

- Pro must complete and return its run-bound result.
- Deep Research first demonstrates a one-second observer timeout without
  terminalizing the run, then completes through the same run ID.

The completed Pro fingerprint is submitted a second time only to prove
reattachment; it must reuse the canonical run with no worker and no resend. An
unwritable result destination must also fail without changing the completed
receipt.

The remaining destructive or identity-changing failure cases use deterministic
local fixtures:

- logged-out or ambiguous session;
- wrong/stale model or Deep Research tool proof;
- historical assistant output;
- browser death during a CDP request.

This split is deliberate. A release proof must not log out the operator, alter
the enrolled account, deliberately select the wrong model/tool, or kill the
trusted browser merely to demonstrate a gate already covered by an executable
fixture.

## Proof bundle

The output is private (`0700` directories, `0600` files) and contains:

```text
manifest.json
receipt.json
pro/receipt.json
pro/result.md
deep-research/receipt.json
deep-research/result.md
failures/*.json
security-audit.json
logs/
private/
runs/
```

Public proof receipts contain run IDs, lifecycle state, byte counts, and result
hashes. They exclude target IDs, target/project URLs, profile paths,
fingerprints, prompt text, cookies, tokens, and backend payloads. Prompt nonces
may appear only in the private prompt files and the two expected results.

`security-audit.json` re-runs the hard doctor after completion and requires the
browser to remain loopback-only, exact-target-bound, hidden, authenticated,
enrolled-account-matched, and project-authorized. It also rejects any
group/world-readable proof file or nonce leakage into command/status logs.

## Interpretation

`manifest.json` is authoritative only when all of these are true:

- `hard_gates == "pass"`;
- both live modes are `completed` with distinct nonempty result hashes;
- every `negative_gates[]` entry is `pass`;
- `security-audit.json` is `pass`;
- the command itself exited zero.

Anything else is a blocker. Do not call a user-turn-only conversation
“started,” do not call a missing result “completed,” and do not substitute a
root chat for a configured Project target.
