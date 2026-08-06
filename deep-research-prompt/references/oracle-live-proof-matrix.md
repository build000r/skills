# Oracle live success + failure proof matrix

Observed **2026-08-06** on `skillbox-portfolio-devbox` for bead
`skillbox-invisible-oracle-subagent-hjuc.6.3`.

Post-heal round **local-r2** is authoritative for the live success lane and the
four deliberate failure lanes. Bundle:
`/tmp/oracle-subagent-e2e/FINAL/local` (`hard_gates=pass`).

**No logout, profile wipe, or oracle-* unit stop.** No fix for the browser
receipt race (out of write scope; see `.2.11` row).

## Verdict

| Lane | Kind | Result | exit= | Typed outcome | Completed receipt? |
|---|---|---|---:|---|---|
| Auth re-probe ×2 (post-heal) | observe | **PASS** | exit=0 | both probes `ok=true state=ready reasons=[]` | n/a |
| Pro success (`oracle-ask`) | live sole send | **PASS** | exit=0 | model `gpt-5-6-pro`, nonce matched, SHA-256 result | yes (hashed only) |
| Model/tool proof (doctor) | live observe | **PASS** | exit=0 | `pro_model=true` `composer_available=true` | n/a |
| Bad target (nonexistent project) | live HTTP denial | **PASS** | exit=1 | `conversation_post_failed` HTTP 404; nothing submitted | **no** |
| Timeout (observer) | synthetic non-terminal | **PASS** | exit=1 | `error_code=wait_timeout`; state stays `created` | **no** |
| Cancelled run | synthetic state | **PASS** | exit=1 | status `cancelled`; wait `result_unavailable`; no result file | **no** |
| Stale-output attempt | fixture | **PASS** | exit=0 | historical assistant cannot complete later turn | **no** |
| **browser_receipt_invalid flap** | **known false-negative** | **DOCUMENTED** | exit=0 | non-atomic `browser.json` rewrite race; **do not treat single sample as session death** | n/a |
| Deep Research live | — | **UNTESTED** | exit=n/a | skipped: single shared live lane | — |

### Known false-negative — `browser_receipt_invalid` race (`.2.11`)

| Field | Value |
|---|---|
| Symptom | intermittent `state=blocked reasons=['browser_receipt_invalid']` under concurrent launch/status |
| Cause | `launch-chatgpt-cdp.sh` unlinks then rewrites browser receipt (not atomic `os.replace`); concurrent readers can observe a missing/partial file |
| Bead | `skillbox-invisible-oracle-subagent-hjuc.2.11` |
| This node | **does not fix** (out of `.6.3` write scope) |
| Operator rule | **re-probe once** before trusting any single not-ready sample |
| Matrix implication | a lone `browser_receipt_invalid` is **not** a live failure-lane success/failure; it is infrastructure noise |

Post-heal mitigation demonstrated:

```text
auth_probe1 exit=0 {"ok":true,"state":"ready","reasons":[]}
auth_probe2 exit=0 {"ok":true,"state":"ready","reasons":[]}
# only then proceed to live ask
```

## Environment

```text
host=skillbox-portfolio-devbox
DISPLAY=:97
ORACLE_CDP_PORT=19222   # config/unit; 9222 squatted by tailscaled
ORACLE_PROFILE_DIRECTORY=Default
round=local-r2-post-heal
```

## Success lane — unique-nonce Pro ask (live, sole send)

```bash
node deep-research-prompt/assets/scripts/oracle-ask.mjs \
  --json --quiet --timeout 180 \
  --prompt-file /tmp/oracle-subagent-e2e/FINAL/local/private/pro-prompt.md \
  --out /tmp/oracle-subagent-e2e/FINAL/local/pro/result.md
```

Literal:

```text
ask_success exit=0
{
  "model": "gpt-5-6-pro",
  "elapsed_ms": 20512,
  "conversation_id": "6a74e626-63bc-83e8-902e-abe7f9838c95",
  "source": "polled",
  "result_bytes": 54,
  "result_sha256": "f2bb141da36668ef447aad088c2810f931a1fbbdc25f5afd4a81e52cf6d0f7fc",
  "nonce_matched": true
}

auth_doctor_post exit=0
{"ok":true,"state":"ready","pro_model":true,"composer":true,"project":true}
```

## Failure lanes (never a completed receipt)

### Bad target

```text
bad_target exit=1
oracle-ask: ChatGPT returned an error for this turn [conversation_post_failed]
  detail: HTTP 404
Nothing was submitted for this attempt.
bad_target_no_result=1
```

### Timeout

```text
timeout exit=1
{"schema":"oracle-subagent.cli-result.v1","command":"wait","ok":false,"error_code":"wait_timeout"}

timeout_status
{"schema":"oracle-subagent.cli-result.v1","command":"status","ok":true,
 "run_id":"run-matrix-timeout-r2","state":"created","revision":0,"terminal":false}
```

### Cancelled

```text
cancel_status exit=0
{"schema":"oracle-subagent.cli-result.v1","command":"status","ok":false,
 "run_id":"run-matrix-cancel-r2","state":"cancelled","revision":1,"terminal":true,
 "result_path":null,"result_bytes":null}

cancel_wait exit=1
{"schema":"oracle-subagent.cli-result.v1","command":"wait","ok":false,"error_code":"result_unavailable"}
cancelled_no_result=1
```

### Stale-output

```text
stale_output exit=0
# Subtest: historical assistant content cannot complete a later user turn
ok 1 - historical assistant content cannot complete a later user turn
# pass 1
# fail 0
```

## Session after matrix

```text
auth_final1 exit=0 {"ok":true,"state":"ready","reasons":[]}
auth_final2 exit=0 {"ok":true,"state":"ready","reasons":[]}
```

## Bundle

```text
/tmp/oracle-subagent-e2e/FINAL/local/
  manifest.json          hard_gates=pass  round=local-r2-post-heal
  receipt.json
  pro/receipt.json pro/result.md
  failures/{bad-target,timeout,cancelled,stale-output,browser-receipt-race}.json
  evidence/*
  private/pro-prompt.md
```

Permissions: dirs `0700`, files `0600`. No cookies/tokens/raw Tailnet IPs.

## Untested / out of scope

- Live Deep Research E2E (lane budget).
- Fix for `launch-chatgpt-cdp.sh` non-atomic browser receipt write → **`.2.11`**.
- Live logout / browser kill (forbidden).

## Validate

```bash
test -s deep-research-prompt/references/oracle-live-proof-matrix.md \
  && grep -c 'exit=' deep-research-prompt/references/oracle-live-proof-matrix.md
jq -e '.hard_gates == "pass"' /tmp/oracle-subagent-e2e/FINAL/local/manifest.json
grep -q '2.11' deep-research-prompt/references/oracle-live-proof-matrix.md
```
