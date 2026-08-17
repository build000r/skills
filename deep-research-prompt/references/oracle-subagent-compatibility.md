# Oracle subagent compatibility manifest and canary

The Oracle lane rides on four things nobody in this repo controls: the Chrome
build on the host, the CDP protocol it speaks, ChatGPT's composer DOM and auth
surface, and whatever Cloudflare decides to interpose. Any of them can change
under a working install. Without a canary the first symptom is a real research
run dying halfway through, at which point the failure looks like the Oracle and
not like an upgrade.

The canary moves that discovery earlier. It compares a **pinned compatibility
manifest** against what the host actually presents and classifies the
difference as typed drift, before production work starts.

- Script: `assets/scripts/oracle-subagent-canary.mjs`
- Tests: `tests/oracle-subagent-canary.test.mjs`

## It cannot submit

That is structural, not a promise, and it is the part to re-check if the module
is ever edited:

- **One CDP method.** `CDP_METHOD_ALLOWLIST` is exactly `["Runtime.evaluate"]`,
  enforced inside the single call helper. There is no code path to `Input.*`,
  `Page.navigate`, `Target.createTarget`, `Target.activateTarget`, or
  `Browser.setWindowBounds`. The allowlist holds only what is used — a spare
  entry is a hole waiting for a future edit.
- **The page probe is a pure reader.** It queries the DOM and returns counts and
  classifications. It never clicks, types, focuses, or dispatches an event.
- **The window is never raised**, so a steady-state hidden browser stays hidden.
  A live test asserts this against the fake CDP server's call log rather than by
  reading the source.
- **Loopback only.** The endpoint must be a literal `127.0.0.1` or `[::1]` with
  a non-privileged port. A hostname is refused outright (`endpoint_not_loopback`)
  because what a name resolves to can change under a running listener.
- **There is no `--submit`.** `runCanary({ submit: true })` refuses with
  `submit_forbidden`, so a caller asking for one gets an error instead of a
  canary that quietly complies. `--no-submit` is accepted as an affirmation of
  intent and does nothing else.

## It never carries page text out

A ChatGPT tab's title *is* the conversation title, and a `/c/...` path carries
the conversation id. Both are user content. The probe therefore classifies and
returns the classification: `title_class` is `challenge` or `normal`,
`path_class` is `conversation`, `root`, or `other`. `document.title` and
`location.href` never reach a report. A test runs the real probe against a fake
DOM whose title is a secret string and asserts neither the title nor the
conversation id appears in the serialized observation.

## The manifest

`DEFAULT_COMPATIBILITY_MANIFEST`, schema
`oracle-subagent.compatibility-manifest.v1`:

```json
{
  "schema": "oracle-subagent.compatibility-manifest.v1",
  "browser": { "product": "Chrome", "major": 150, "policy": "at_least_major" },
  "cdp_protocol_version": "1.3",
  "selector_observation_schema": "oracle-subagent.selector-observation.v1",
  "selector_proof_schema": "oracle-subagent.selector-proof.v1",
  "auth_observation_schema": "oracle-subagent.auth-observation.v1",
  "mode": "pro",
  "pro_model": "gpt-5-5-pro"
}
```

The key set is exact and every field fails closed on a bad value; an unknown key
is `manifest_invalid`.

**Why 150.** It is a floor, not a ceiling, and it is the major that
`oracle-credential.mjs` already pins in the user-agent this lane presents. Two
places in the tree now state "which Chrome generation we target", and pinning
them to the same number is what keeps them from drifting apart quietly.

**`policy`** is `at_least_major` (an upgrade is fine, a downgrade is drift) or
`exact_major` (any move is drift). Use `exact_major` when a specific build is
known-good and you are trying to hold it — for example while chasing a
regression — and go back to `at_least_major` afterwards.

Pass a different manifest with `--manifest path.json`, or as the `manifest`
option to `runCanary`. The manifest is deliberately an *input*: the test suite
pins against what the fake CDP server serves, and a host under investigation can
be checked against a hypothesis without editing the shipped baseline.

### Re-pinning

Re-pin deliberately. A manifest that drifts by accident proves nothing.

1. Run the canary against the host with `--endpoint` and read the `detail` on
   the failing checks — the observed product, version, and protocol are there.
2. Decide whether the new state is *acceptable*, not merely *current*. A Chrome
   that broke the composer selectors is drift you want to keep failing.
3. Edit `DEFAULT_COMPATIBILITY_MANIFEST`, and say in the commit what was
   verified on the new build.

## Checks

| Check | Scope | Fails with |
| --- | --- | --- |
| `selector_observation_schema` | static | `contract_schema_drift` |
| `selector_proof_schema` | static | `contract_schema_drift` |
| `auth_observation_schema` | static | `contract_schema_drift` |
| `browser_product` | live | `browser_product_drift` |
| `browser_version` | live | `browser_version_drift` |
| `cdp_protocol_version` | live | `cdp_protocol_drift` |
| `target_binding` | live | `target_absent`, `target_ambiguous` |
| `selector_contract` | live | the selector contract's own code — `composer_ambiguous`, `model_not_pro`, `model_catalog_ambiguous`, `tool_not_exact`, `observation_stale`, … |
| `target_origin` | live | `origin_drift` |
| `cloudflare` | live | `cloudflare_challenge` |
| `auth` | live | `auth_lost` |
| `composer_selectors` | live | `composer_absent`, `composer_ambiguous` |

**Static checks need no browser.** They catch an upstream module bumping a
schema out from under the pinned manifest — drift a live probe would only
surface later as a confusing parse failure.

**`target_binding` is exact.** Zero ChatGPT page targets and several are both
refusals. "Several" matters most: picking the first would report on a tab nobody
meant, and a green canary bound to the wrong tab is worse than a red one. When
binding fails, the page checks are `skipped`, never assumed.

**Cloudflare is checked before auth, and masks it.** A challenge interstitial
hides the composer and shows no login control, so evaluating auth first would
report "logged out" for what is really a challenge — and someone would go
re-authenticate a session that was never lost. When a challenge is present,
`auth` and `composer_selectors` come back `skipped` with `masked_by_challenge`,
so one cause produces one failure.

**`selector_contract` reuses `chatgpt-selector-contract.mjs` unchanged.** Model
and tool ambiguity fail closed there, which is also why a schema bump in that
module shows up as static drift here.

## Running it

Touching a browser is opt-in. With no `--endpoint` and no `ORACLE_CDP_ENDPOINT`,
the canary runs its static checks, reports every live check as `skipped`, and
says `live_proved: false` rather than implying compatibility it did not observe.

```bash
# Offline: static contract checks only. This is the form used in validation.
node deep-research-prompt/assets/scripts/oracle-subagent-canary.mjs --no-submit --json

# Against a running Oracle host, over its loopback CDP port.
node deep-research-prompt/assets/scripts/oracle-subagent-canary.mjs \
  --no-submit --json --require-live --endpoint http://127.0.0.1:9222
```

`--require-live` is what a production gate should use: it turns "I could not
observe the browser" into a non-zero exit instead of a quiet pass.

### Exit codes

| Code | Status | Meaning |
| --- | --- | --- |
| 0 | `pass` | every check ran and passed |
| 0 | `degraded` | no check failed, but live checks were skipped (without `--require-live`) |
| 1 | `drift` | at least one check failed; `drift` lists the codes |
| 2 | — | usage, manifest, or endpoint refusal |
| 3 | `degraded` | live checks skipped, with `--require-live` |

`status` is never `pass` unless the live checks actually ran, so a green exit
code and a green status are different claims and the report states both.

## Report

Schema `oracle-subagent.canary-report.v1`. Fields worth knowing:

- `checks` — every check with `scope`, `status` (`pass`/`fail`/`skipped`),
  `code`, and a non-sensitive `detail` (observed version, bound target id).
- `drift` — the deduplicated, sorted failure codes. Empty on a clean run.
- `blockers` — why live checks were skipped, named: `endpoint_unset`,
  `cdp_unreachable`.
- `live_proved` — `true` only when a target was bound and both probes ran.
- `submit` — always `false`. It is in the report so a receipt records it.
- `cdp_methods_allowed` — the allowlist, so a stored report shows what the run
  was capable of.

## Validation

```bash
cd "$HOME/repos/opensource/skills"
node --test deep-research-prompt/tests/oracle-subagent-canary.test.mjs
node deep-research-prompt/assets/scripts/oracle-subagent-canary.mjs --no-submit --json
```

The live path is exercised end to end over loopback HTTP and WebSocket against
`tests/fake-cdp.mjs`, not against a mock of the canary's own internals: pass,
browser drift, protocol drift, model ambiguity, tool ambiguity, a stale
observation, a Cloudflare challenge, two ambiguous tabs, and an unreachable
endpoint all run through the real code path. The fake server's call log is what
proves only `Runtime.evaluate` was issued.

### Not proven here

The canary has never been run against the real Oracle host's Chrome. This
harness is offline; nothing in it observes the live box, so the pinned major is
a declared floor rather than a measured one. To close that gap, run the
`--require-live --endpoint` form on the host (`references/oracle-vps-host.md`
for how to reach its CDP port) and record the observed `browser_version` detail
alongside the pin.

## Related

- `references/oracle-subagent-auth.md` — session, plan, and challenge policy.
- `references/oracle-live-proof-matrix.md` — the live success/failure matrix.
- `references/oracle-slo.md` — latency targets and the benchmark harness.
- `references/oracle-vps-host.md` — the host, its CDP port, and its doctor.
