# Oracle fleet RPC

`oracle-rpc-server.mjs` is the private fleet front door for the Oracle browser
on `skillbox-portfolio-devbox`. The browser session and every browser-derived
credential remain on that host. Fleet callers send only prompt text and
bounded file bytes over Tailscale.

This lane uses a direct MagicDNS bind. It does not use a wildcard listener,
expose CDP, or distribute an Oracle credential. Tailscale Serve can only replace
the direct bind after a separate proof shows how the original inbound peer is
preserved for LocalAPI `whois`; a loopback reverse-proxy socket is not accepted
as caller identity by this implementation.

## Security boundary

The request path is deliberately ordered:

1. Bound the HTTP body while streaming it.
2. Parse JSON and apply the exact PC-FLEET-1 schema.
3. Decode and hash-check every bounded attachment.
4. Resolve the inbound socket with Tailscale LocalAPI `whois`.
5. Require an allowlisted peer tag.
6. Claim the caller-scoped request ID in the replay guard.
7. Apply the per-caller policy/quota hook.
8. Only then invoke the local Oracle runner and browser.

Consequently malformed, oversized, untagged, off-tailnet, replayed, or
policy-denied requests cannot reach the browser handler.

The server also proves its configured MagicDNS name resolves exclusively to
addresses reported for `Self.TailscaleIPs` by LocalAPI before calling
`server.listen`. Configuration containing a wildcard, loopback name, or raw IP
is rejected. Receipts and logs retain the configured hostname, never a raw
tailnet address.

## PC-FLEET-1 request schema

The wire envelope is exact. No other top-level or nested keys are accepted.

```json
{
  "schema": "oracle-fleet.request.v1",
  "request_id": "e4d4f22d-6ba7-4cce-9bb0-bc53112766dd",
  "created_at": "2026-08-06T17:30:00.000Z",
  "prompt": "Research request read from stdin or a local file",
  "files": [
    {
      "name": "evidence.pdf",
      "media_type": "application/pdf",
      "bytes": 1234,
      "sha256": "<64 lowercase hex characters>",
      "data_base64": "<canonical base64>"
    }
  ]
}
```

The allowlist excludes hooks, environment injection, CDP fields, browser
configuration, cookie/session material, authorization headers, command or
executable fields, filesystem paths, profiles, and replay directives. A local
client file path is consumed only by `oracle-rpc-client.mjs`; the path is
replaced by a basename plus bytes before the request is serialized.

Default limits:

| Limit | Value |
|---|---:|
| HTTP body | 12 MiB |
| Prompt | 256 KiB |
| Files | 8 |
| One file | 4 MiB |
| All files | 8 MiB |
| Returned result | 32 MiB |
| Replay window | 5 minutes |

The request timestamp must be canonical RFC 3339 and fresh. Replays are keyed
by the Tailscale node identity plus `request_id`, so different callers cannot
poison one another's key space.

## Caller identity and quota integration

The server calls:

```text
GET /localapi/v0/whois?addr=<inbound socket address>
```

over `/var/run/tailscale/tailscaled.sock`. The socket address is used only for
that local lookup. It is not emitted. The normalized identity delivered to the
policy hook is:

```js
{
  node_id,
  node_name,
  user_login,
  tags
}
```

`createOracleRpcHandler` accepts an `authorizeCaller` hook. It receives the
identity and secret-free request metadata (`request_id`, byte counts, and file
count) before Oracle contact. The `.4.5` per-caller policy/quota implementation
plugs in here. It may return private handler context plus an optional public
receipt:

```js
{
  allowed: true,
  context: policyContext,
  receipt: {
    policy_id: "oracle-fleet-standard",
    quota_bucket: "interactive",
    remaining: 4
  }
}
```

Returning `allowed: false` or throwing fails closed before the local runner.
Arbitrary policy context is never serialized.

The successful receipt stamps the resolved caller, policy receipt, Oracle run
ID/state, and result digest. It does not contain prompt text, file contents,
client paths, browser coordinates, or credential values.

## Tailnet ACL

Tag the Oracle host `tag:oracle-server`. Tag only approved callers
`tag:oracle-client`. The tailnet policy must allow that source tag to reach only
the Oracle server tag and configured RPC port. No untagged peer or public source
gets that destination grant.

Equivalent ACL policy shape:

```json
{
  "tagOwners": {
    "tag:oracle-server": ["autogroup:admin"],
    "tag:oracle-client": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:oracle-client"],
      "dst": ["tag:oracle-server:4117"]
    }
  ]
}
```

Keep the RPC application check even with the network ACL. LocalAPI `whois`
plus the required tag is the application-side identity proof and feeds quota
accounting.

## Server

Run on `skillbox-portfolio-devbox`, using its MagicDNS hostname from the private
hosts registry. Example:

```bash
node assets/scripts/oracle-rpc-server.mjs \
  --bind-host skillbox-portfolio-devbox \
  --port 4117 \
  --artifact-root "$HOME/.oracle/oracle-subagent/runs" \
  --mode deep-research \
  --required-peer-tag tag:oracle-client
```

The command prints one secret-free JSON readiness line. Startup fails unless:

- LocalAPI is available;
- the hostname resolves only to this node's Tailscale addresses;
- the listener can bind that hostname; and
- at least one required peer tag is configured.

The default runner invokes the existing local `oracle-subagent.mjs` API. Prompt
bytes are passed in process memory, incoming file bytes are materialized in a
private directory under the server's Oracle artifact root, and that staging
directory is removed after the run. Cookie acquisition, browser launch, CDP,
and ChatGPT transport stay entirely inside the VPS process boundary.

The prior credential-portability lane is therefore internal bootstrap/recovery
for this one box only. It is not a fleet authentication mechanism and must not
copy a session value, browser profile, or access token to callers.

## Client

Prompt text is read from stdin or `--prompt-file`; it is never accepted in
argv. The client reads local files with no-follow semantics, checks size and
stability, and sends only their basename, media type, length, digest, and
bytes.

```bash
node assets/scripts/oracle-rpc-client.mjs \
  --host skillbox-portfolio-devbox \
  --port 4117 \
  --prompt-file ./request.md \
  --file ./evidence.pdf \
  --result ./oracle-result.md
```

Use `--https` only when HTTPS terminates without losing the original peer
identity contract. `--endpoint` is an alternative for a complete MagicDNS URL.
Raw IPs, URL credentials, query strings, fragments, redirects, public
hostnames, and localhost endpoints are rejected.

The client verifies the response schema, caller-bearing receipt, result size,
canonical base64, and SHA-256 before atomically writing the result with mode
`0600`. Stdout contains result metadata and the receipt; it never contains the
prompt or result body.

## Validation and proof status

The deterministic test lane may fixture LocalAPI status and `whois`. Such a
fixture proves schema ordering, identity propagation, replay control, and
handler non-contact; it is not live tailnet evidence.

Live closeout on `skillbox-portfolio-devbox` still needs three separate proofs:

1. A tagged tailnet caller receives a receipt bearing its `whois` identity.
2. A non-tailnet caller cannot establish a connection to the MagicDNS-bound
   listener.
3. An untagged tailnet caller is denied before the Oracle/browser handler.

Do not substitute a loopback test, wildcard listener, direct-port health check,
or fixture receipt for those live network proofs.
