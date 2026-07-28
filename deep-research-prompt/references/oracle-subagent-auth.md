# Oracle subagent authentication

The Oracle subagent uses one dedicated persistent Chrome profile on the trusted
Mac. Cookies and profile data stay there. Remote callers on d3, d3c, or later
Skillbox integrations receive only narrow run/status/result RPCs; they never
receive a browser port, cookie database, session token, or copied profile.

True headless Chrome is currently blocked by ChatGPT's challenge path. The
steady state is therefore hidden-headful: the exact Google Chrome process is
loopback-only, non-frontmost, and offscreen. Authentication is the only time
the dedicated browser is intentionally visible.

## One-time clean login

First create a fresh exact target with the hardened launcher:

```bash
./deep-research-prompt/assets/scripts/launch-chatgpt-cdp.sh \
  --no-submit-smoke --json
```

For the first login, explicitly authorize the account currently chosen in the
visible ChatGPT session:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs \
  login --enroll-current-account --json
```

The command reveals only the dedicated, already-attested Chrome target and
waits for an authenticated Pro session. Log in normally in that window. Once
the account API and model catalog both prove Pro, the command stores only:

- a SHA-256 fingerprint of the canonical profile identity;
- a SHA-256 fingerprint of the ChatGPT user plus its unique accessible Pro
  workspace identity;
- the enrollment timestamp.

It does not read or persist email, account name, cookies, local/session
storage, tokens, page text, or model response payloads. It then moves any
window offscreen, hides Chrome, and runs the same doctor used before every
submission. `SIGINT`, `SIGTERM`, timeout, and ordinary failure also attempt to
re-hide the browser.

Before revealing anything, `login` requires a fresh receipt, private files,
one loopback-only listener, the live browser PID, the exact receipt URL/target,
and a hidden browser. It pins that browser/target/receipt for the whole login.
A launcher receipt rollover aborts enrollment and re-hides the originally
revealed process.

An existing enrollment is immutable. Later `login` invocations require the
same account fingerprint:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs \
  login --json
```

There is no implicit "use whichever account is open" fallback. Replacing the
account means deliberately removing the private policy outside this command,
launching a fresh target, and repeating the explicit enrollment.

## Status and hard doctor

`status` always exits zero when it can emit a safe diagnostic report, including
for an unhealthy session:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs status --json
```

`doctor` exits nonzero unless every hard gate passes:

```bash
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs doctor --json
```

The report contains only stable reason codes and booleans. It never prints
paths, URLs, target IDs, profile/account hashes, backend payloads, or exception
text. The doctor independently checks:

- production launcher receipt and freshness;
- current-UID private runtime, receipt, profile, and policy permissions;
- exactly one CDP listener on `127.0.0.1` or `::1`, never wildcard;
- live CDP browser PID equality and the exact launcher-created target;
- hidden/non-frontmost/offscreen browser state;
- fresh browser-derived auth observation and no current or stale challenge;
- non-guest session and exact enrolled account/profile fingerprints;
- requested project access, when a project path was requested;
- one unique active/non-delinquent Pro workspace plus an actually returned,
  available canonical `gpt-*-pro` model identifier (display text never counts);
- an available composer.

Common hard-failure codes include:

| Code | Meaning |
| --- | --- |
| `logged_out` | ChatGPT returned a guest session, even if `/backend-api/me` returned HTTP 200 |
| `wrong_account` | The live user fingerprint differs from the explicit enrollment |
| `project_denied` | The exact requested project rendered an access-denied state |
| `project_access_ambiguous` | The requested project route could not be proven |
| `challenge_present` / `stale_challenge` | A browser challenge is present or its evidence is stale |
| `wrong_permissions` | Runtime, receipt, profile, or policy is not private/current-UID owned |
| `wildcard_cdp` | The listener is not bound only to loopback |
| `pro_plan_missing` | The selected account is not a Pro plan |
| `pro_model_missing` | The live model catalog does not expose a Pro model |
| `exact_target_mismatch` | The launcher receipt no longer names the inspected page |
| `browser_visible` | Steady-state Chrome is visible, frontmost, or onscreen |

Deep Research availability is observed internally; the later exact model/tool
submission gate re-proves it in the bound composer. Authentication alone never
toggles a tool or sends a turn.

## Permission remediation

The expected modes are:

```text
~/.oracle/browser-profile                 0700
~/.oracle/browser-profile/<profile>       0700
~/.oracle/oracle-subagent                 0700
~/.oracle/oracle-subagent/browser.json    0600
~/.oracle/oracle-subagent/auth-policy.json 0600
```

Inspect the exact paths before changing them. A typical repair is:

```bash
chmod 700 "$HOME/.oracle/browser-profile" \
  "$HOME/.oracle/browser-profile/Default" \
  "$HOME/.oracle/oracle-subagent"
chmod 600 "$HOME/.oracle/oracle-subagent/browser.json" \
  "$HOME/.oracle/oracle-subagent/auth-policy.json"
```

Do not copy `Cookies`, profile directories, or the policy to d3/d3c. Do not
expose port 9222 through SSH, Tailnet, a wildcard bind, or a general browser
automation API. A future native Skillbox service should call this doctor on the
trusted Mac and export only its safe report.
