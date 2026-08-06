# Oracle fleet live proof — blocked at caller enrollment

Observed 2026-08-06 on `skillbox-portfolio-devbox`. This is a partial live
proof, not tagged-caller acceptance. A real second Tailnet peer was enlisted,
but no current node had `tag:oracle-client` and the policy had no entry for that
peer. The successful file-backed RPC path, receipt identity, replay rejection,
and result-file guarantees therefore remain untested live.

## Verdict

| Requirement | Live result |
|---|---|
| MagicDNS transport from a second peer | **Observed.** `conference1-wsl` reached `skillbox-portfolio-devbox`; the application returned `caller_tag_rejected`, not a transport error. |
| Tailscale LocalAPI `whois` | **Partially observed.** The deployed server can return `caller_tag_rejected` only after LocalAPI `whois` returns a valid node and its tags are normalized. No accepted receipt exists, so no receipt-stamped whois identity is claimed. |
| Tagged-caller acceptance and file-backed answer | **Untested — blocked.** Tagged node count was zero. |
| Non-null policy receipt and quota decrement | **Untested — blocked.** Policy listed only `local`, not `conference1-wsl`. The rejected control caused no quota mutation. |
| Result digest and client `0600` write | **Untested live.** No accepted RPC response or result file existed. Fixture coverage is not substituted here. |
| Replay rejection | **Untested live.** Replay claiming occurs after tag acceptance; an untagged caller cannot reach it. |
| Untagged peer rejection before browser contact | **Observed.** The second peer received `caller_tag_rejected`; deployed source orders whois/tag resolution before body parsing, replay, policy, and `runOracle`. |
| Non-tailnet source rejection | **Untested live.** No non-tailnet execution vantage point was available. |
| No browser/profile material returned | **Observed for the live denial only.** Client output contained only the typed rejection. No receipt, result body, browser state, profile path, or authentication material was returned. |

## Live topology and enrollment gate

The status query selected hostnames and tags only; no raw Tailnet addresses were
printed.

```text
{
  "self": {
    "hostname": "skillbox-portfolio-devbox",
    "dns_name": "skillbox-portfolio-devbox.taila8fde7.ts.net",
    "tags": []
  },
  "online_peers": [
    {
      "hostname": "sweet-potato-prod",
      "dns_name": "sweet-potato-prod.taila8fde7.ts.net",
      "tags": []
    },
    {
      "hostname": "Conference1",
      "dns_name": "conference1.tail4c481e.ts.net",
      "tags": []
    },
    {
      "hostname": "b’s MacBook Air",
      "dns_name": "bs-macbook-air.taila8fde7.ts.net",
      "tags": []
    },
    {
      "hostname": "skillbox-jeremy",
      "dns_name": "skillbox-jeremy-3.taila8fde7.ts.net",
      "tags": [
        "tag:gha-deploy"
      ]
    },
    {
      "hostname": "conference1-wsl",
      "dns_name": "conference1-wsl.taila8fde7.ts.net",
      "tags": []
    }
  ],
  "oracle_client_tagged_count": 0
}
```

The active policy file was also inspected through a field allowlist:

```text
{
  "schema": "skillbox.oracle-policy.v1",
  "callers": [
    {
      "caller_id": "local",
      "modes": [
        "standard",
        "deep-research"
      ],
      "max_requests_per_window": 30,
      "window_seconds": 3600,
      "max_concurrent": 2
    }
  ]
}
```

This is the blocking mismatch: the broker derives a caller ID from the whois
node name, while the only explicit policy caller is `local`.

## Second-peer live negative control

`conference1-wsl` was reached through Tailscale SSH using its MagicDNS name.
It had Node available and a checked-out RPC client. Because its `/srv/...`
client path resolves through a symlink whose main-module guard does not run,
the current client module was streamed without a remote file write and its
exported `submitOracleFleetRequest` was invoked directly. The prompt remained
in process input; no prompt, credential, or authentication value was placed in
the RPC client argv.

Literal sanitized output:

```text
control_started=2026-08-06T19:33:28Z
Warning: Permanently added '<redacted-tailnet-address>' (ED25519) to the list of known hosts.
client_error=caller_tag_rejected
pipeline_exit=2
control_finished=2026-08-06T19:33:29Z
```

This proves live MagicDNS application transport and the untagged decision. It
does not prove tagged acceptance.

The deployed server source digest was
`34807ce02236472b0a6b7f1c24c4be86dfd76b438ba9cc78be34f2103996ef03`.
The process started at `Thu Aug 6 19:03:16 2026`, after the server file mtime
`2026-08-06 18:58:27.251858930 +0000`, so the inspected ordering is the code
loaded by this process:

- `oracle-rpc-server.mjs:396-434`: call LocalAPI `whois`, normalize identity
  and tags, then return `caller_tag_rejected` when the required tag is absent.
- `oracle-rpc-server.mjs:768-799`: caller resolution precedes request parsing,
  replay claim, policy authorization, and `runOracle`.

Therefore this typed live rejection occurred before the browser runner could
be called. The server has no per-request browser-contact counter, so this proof
does not claim an independently instrumented zero-contact measurement.

## Quota non-mutation and service preservation

After the 19:33:28Z control, the quota and authority heads retained their
18:50:43Z mtimes:

```text
quota_state_mtime=2026-08-06 18:50:43.688392036 +0000 mode=600 links=1
authority_head_mtime=2026-08-06 18:50:43.704392540 +0000 mode=600 links=1
observed_at=2026-08-06T19:33:38Z
```

That is evidence that the rejected peer did not consume quota. It is not the
required accepted-call quota decrement.

All three supervised units remained active, and post-control readiness stayed
green:

```text
Id=oracle-xvfb.service
ActiveState=active
SubState=running

Id=oracle-chatgpt-cdp.service
ActiveState=active
SubState=running

Id=oracle-rpc.service
ActiveState=active
SubState=running
```

```text
{"schema":"oracle-fleet.health.v1","ok":true,"service":{"ready":true},"policy":{"ready":true,"policy_id":"skillbox-oracle-v1"},"browser":{"ready":true,"authenticated":true}}
health_exit=0
```

No unit was stopped or restarted, and no browser profile or authenticated
session state was modified.

## Required follow-up before acceptance

An authority-owned prerequisite must:

1. approve exactly one real peer such as `conference1-wsl` with
   `tag:oracle-client` in Tailnet policy;
2. add that whois-derived caller ID as an explicit Oracle policy caller and
   complete the policy authority re-enrollment procedure without weakening the
   current fail-closed state; and
3. hand this node the enrolled peer without exposing raw Tailnet addresses or
   disturbing the authenticated browser profile.

Then rerun from that peer and capture: accepted caller-bearing whois receipt,
non-null policy receipt with before/after remaining quota, result SHA-256,
client result mode `0600`, duplicate request-ID rejection, and a live
non-tailnet control. Until then this document is intentionally **BLOCKED**, not
PASS.
