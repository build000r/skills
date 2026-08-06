---
name: amp-orb
description: Drive Amp Orbs (E2B cloud sandboxes) from the operator box — launch/continue -ox threads, poll for results without false triggers, join orbs to the tailnet, reach sbpd (cass/skills) with workload-identity auth, and ship files safely. Use when launching an Amp orb, running "amp -ox", continuing an orb thread, proving something from inside an orb, joining an orb to the tailnet, orb tailscale/NeedsLogin problems, SBP_REMOTE/sbpd from an orb, or delivering code/secrets to an orb.
---

# Amp Orb Operations

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using amp-orb`.
Preferred: `Using amp-orb to <goal>. First I will <next concrete step>.`

Proven patterns for operating Amp Orbs from the devbox. Every rule below was
paid for with a live failure on 2026-07-30/31 (epics
`skillbox-orb-plane-e2e-ms0q`, `skillbox-orb-std-bodg`); don't relearn them.

## Degraded mode

If `amp` is missing from PATH, check `~/.local/bin/amp` first. If sbpd is
unreachable (`curl http://100.79.193.34:8443/healthz` fails from the box),
check `systemctl --user status sbpd` before touching orb-side anything. If the
Amp secret is absent in the orb (`SECRET_MISSING`), stop and report — do NOT
fall back to embedding key material in a prompt; that is the failure this
skill exists to prevent.

## Launch and continue

```bash
# New orb thread (async; prints thread URL immediately)
amp -ox --project buildooor/<repo> --visibility private \
  --no-archive-after-execute -l <label> -x "<prompt>"

# Continue SAME orb/thread (reuses its executor + filesystem)
amp threads continue T-<id> -ox -x "<prompt>"
```

- The sandbox is a full Debian VM: passwordless sudo, systemd, `/dev/net/tun`,
  open egress. Hostname `e2b.local`.
- The sandbox PAUSES between rounds. Filesystem persists within a thread;
  network sessions may not (see tailnet resume below).
- User-level Amp secrets (`amp secrets set --user --secret --data-file - NAME`)
  are injected as env vars into every orb. This is the ONLY sanctioned way to
  deliver a credential. NEVER put secret material in the `-x` prompt — the
  thread transcript stores it forever and forces rotation (happened live;
  key `kzzQqRDSd221CNTRL` burned + rotated).

## Poll for results — anchored verdicts only

Naive `grep VERDICT` matches YOUR OWN PROMPT text in the thread markdown
(false-triggered twice live). Contract:

1. End the orb prompt with: `Final line exactly 'XX-VERDICT: pass' … else
   'XX-VERDICT: fail'.`
2. Wait with a **line-anchored** grep — the prompt embeds the string mid-line,
   the answer puts it at line start:

```bash
until amp threads markdown T-<id> 2>/dev/null | grep -qE '^XX-VERDICT: (pass|fail)'; do sleep 15; done
```

3. Extract the final assistant message (the awk idiom):

```bash
amp threads markdown T-<id> | awk '/^## Assistant/{last=NR} {lines[NR]=$0} END{for(i=last;i<=NR;i++) print lines[i]}'
```

Make orbs report RAW command outputs per step and say "failures are valid
results; do not stop early" — otherwise agents editorialize away the evidence.

## Tailnet join (the four traps)

Full runbook: `skillbox/docs/orb-tailnet-bootstrap.md`. Canonical script:
`skillbox/scripts/orb/join-tailnet.sh` (consumes `TAILSCALE_AUTHKEY` from the
Amp secret env). The traps:

1. **Silent hang, NeedsLogin forever**: E2B eth0 is link-local-only
   (`169.254.x/30`) → tailscaled netmon declares network down → control dials
   paused → `tailscale up` times out with NO output while `curl` and
   `tailscale debug ts2021` both succeed. Fix BEFORE `up`:
   `sudo ip addr add 10.254.254.254/32 dev eth0 && sudo systemctl restart tailscaled`
   (or the `TS_ASSUME_NETWORK_UP_FOR_TEST=true` systemd drop-in, Tailscale ≥1.90.1).
2. **Ephemeral node removed on pause**: a long orb pause (~1h) lets the control
   plane delete the ephemeral node — `Logged out.` on resume. Daemon restart is
   NOT enough; rerun the full `tailscale up --authkey` join. Wake preamble:
   `curl -s --max-time 8 http://100.79.193.34:8443/healthz || <full re-join>`.
3. **Diagnose with**: `sudo journalctl -u tailscaled | tail`,
   `tailscale debug ts2021`, `curl -sI https://controlplane.tailscale.com`
   (302 = reachable). "context canceled" from `timeout N tailscale up` means it
   was still waiting — not a transport error.
4. **ACL proof**: denied ports log `rejected due to acl` in the ORB's own
   journal — use that as the negative test, don't guess.

## Reach sbpd (cass + skills) from the orb

sbpd runs on the box as a lingering user unit, dual-bound
`127.0.0.1:8443` + `100.79.193.34:8443` (tailnet bind requires auth).

```bash
# Bootstrap after join — kit ships client + verifier + join script:
curl -s http://100.79.193.34:8443/v1/orb-kit -o /tmp/kit.tgz && tar -xzf /tmp/kit.tgz -C /tmp/kit

# Per-thread identity (RS256, aud=sbpd, TTL 60-3600s):
TOK=$(amp orb id-token --audience sbpd --ttl-seconds 600)

# Client honors SBP_TOKEN (bearer) — never logged:
SBP_TOKEN="$TOK" PYTHONPATH=<kit scaffold dir> \
  python3 <kit>/sbp_client.py --remote http://100.79.193.34:8443 cass search '<q>'
SBP_TOKEN="$TOK" ... skill pull <name>   # verified bundle, deterministic tree sha
```

- No token → 401 on `/v1/cass/*` and `/v1/skill/*`; `/healthz` + `/v1/orb-kit`
  are exempt. Loopback bind is unauthenticated (box-local convenience).
- `skill pull` needs the kit's `runtime_manager` scaffold on `PYTHONPATH`
  (bundle verifier import); cass verbs are pure stdlib.
- On a host with the skillbox repo, plain `SBP_REMOTE=<url> sbp cass search`
  / `sbp skill pull` route automatically (`scripts/sbp` intercept).

## Ship files to an orb

Ranked: (1) repo clone (push first — orbs clone from GitHub, not your working
tree), (2) `curl` from sbpd once joined (add to orb-kit if recurring),
(3) `echo '<base64 -w0 output>' | base64 -d > /tmp/file` inline in the prompt —
fine for small non-secret files only. Check import closure before shipping a
single Python file: repo-lazy imports crash standalone (bit us live —
`sbp_client.py` skill pull needs `bundle.py` shipped alongside).

## OIDC facts (verified live)

- Issuer `https://ampcode.com/api/workload-identity`; JWKS at
  `<issuer>/jwks.json`; RS256; claims: `sub` =
  `project:<id>:user:<id>:thread:<id>`, plus `thread_id`, `project_id`,
  `email`, `token_use=exchanged`.
- Keyless tailnet join via Tailscale workload-identity federation (≥1.90.1) is
  the preferred endgame — see the bootstrap runbook's OIDC section.

## Verification and closeout

An orb claim is proven only by RAW output in the thread: joined = `tailscale
ip -4` prints `100.x` AND the box sees the device (`tailscale status | grep
<name>`); reachable = actual HTTP status codes; auth = a 401 negative test
next to the 200 positive. Record the thread ID (`T-…`) wherever the result
lands (bead comment, commit message) — the transcript IS the evidence. Leave
acceptance threads unarchived (`--no-archive-after-execute`). If box-side
sbpd/client code changed as part of the work, run `make test` (or the focused
`python3 -m unittest tests.test_sbpd tests.test_sbp_client`) in the skillbox
repo before trusting any orb-side result built on it.
