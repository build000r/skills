# Oracle Cloudflare egress (VPS datacenter canary)

**Bead:** `skillbox-invisible-oracle-subagent-hjuc.1.9`  
**Host:** `skillbox-portfolio-devbox` (canonical hidden-headful Chrome under Xvfb)  
**Measured:** 2026-08-06T19:30:05Z → 2026-08-06T19:31:17Z (UTC)  
**Evidence dir:** run-dir `WG-1-9_canary/` (not in git)

## Decision

| Field | Value |
|-------|-------|
| **Chosen egress** | **direct** (host / Chrome default route) |
| **Exit node** | **not enabled** |
| **Rationale** | N=5 hidden-headful `https://chatgpt.com/` loads from the VPS **datacenter** egress saw **0 Cloudflare challenges** and **0 blocks**. Enrolled production session stayed `challenge_clear` before and after. No need to route through a residential Tailscale exit node. |
| **Revisit when** | Any sustained challenge/block on doctor or ask; cold profile re-enroll from VPS IP; Chrome major upgrade; DO IP reputation shift |

Do **not** enable a Tailscale exit node on this host unless challenge/block rate rises. Persistent exit-node routing changes fleet egress and must be an explicit recorded decision.

## Mac baseline (epic, residential)

Epic architecture decision 1 was measured on a **residential Mac**:

| Lane | Observed on residential Mac |
|------|-----------------------------|
| True Chrome `--headless` | Cloudflare challenge path; stayed blocked (not accepted) |
| Hidden-headful (off-screen / background) | Steady-state operational path; no persistent CF challenge once enrolled |

That Mac finding is qualitative/binary for the headless vs hidden-headful fork. It is **not** a multi-trial rate table for datacenter IPs — that gap is what this canary closed.

For comparison bookkeeping, treat Mac **hidden-headful enrolled** challenge rate as **~0** (operational baseline), and Mac **true headless** as **~1** (blocked).

## VPS canary (this measurement)

### Egress identity

Chrome and host share the same public path (no exit node):

| Source | IP | ASN / org | Class |
|--------|----|-----------|-------|
| Host `ipinfo` | `167.71.91.180` | AS14061 DigitalOcean, LLC | datacenter |
| Browser temp-tab `ipinfo` (via CDP) | `167.71.91.180` | AS14061 DigitalOcean, LLC | datacenter |

City/region at measure time: Clifton / New Jersey / US.

### Method

- CDP port **19222** (loopback only; see `oracle-vps-host.md` — never fight tailscaled on 9222).
- Chrome **131.0.6778.204**, hidden-headful under Xvfb `:97`, units active.
- **Temporary** page targets only — production conversation tabs were not navigated.
- N=5 navigations to `https://chatgpt.com/`, settle 5s (+ up to 2 retries).
- Challenge probe **matches** `oracle-subagent-auth.mjs` auth observation:
  - title matches `/just a moment|attention required|checking your browser/i`
  - or DOM `iframe[src*='challenge']`, `#challenge-form`, `.cf-challenge`
- Block probe: body/title access-denied / “you have been blocked” / CF error patterns.
- Cookies/tokens never logged.

### Results

| Metric | Value |
|--------|-------|
| Trials (N) | **5** |
| `challenge_present` | **0** |
| `block_signal` | **0** |
| Errors | **0** |
| **challenge rate** | **0.0** (0/5) |
| **block rate** | **0.0** (0/5) |
| Protected tabs intact | **true** (2 production pages preserved) |

Per-trial titles were the normal ChatGPT app shell (`ChatGPT: Chat, Work, Create & Code with AI`); no CF interstitial titles; no challenge iframes.

### Auth doctor sandwich

| When | `state` | `challenge_clear` | notes |
|------|---------|-------------------|-------|
| Pre-canary | `ready` | `true` | all 17 checks true |
| Post-canary | `ready` | `true` | production tabs unchanged |

### Live send evidence (shared session; not re-flooded)

Sibling enrollment already proved a short Pro send on this same VPS host / direct egress:

- `oracle-ask --json`, model `gpt-5-6-pro`, ~20709ms
- conversation id `6a74df1d-d630-83e8-b56c-1b326016e76d`

This canary deliberately **did not** spam additional Pro asks (session is a scarce shared resource across concurrent wave nodes). Load-level CF challenge rate is the egress risk surface; the live send proves the full enrolled path still works on the same datacenter IP.

## Comparison

| Environment | Egress class | Lane | Challenge rate (measured / baseline) |
|-------------|--------------|------|--------------------------------------|
| Residential Mac | residential | true headless | **blocked** (epic smoke) |
| Residential Mac | residential | hidden-headful enrolled | **~0** (operational baseline) |
| `skillbox-portfolio-devbox` | datacenter (DO AS14061) | hidden-headful enrolled | **0/5 = 0.0** (this canary) |

**Conclusion:** With the enrolled hidden-headful profile on this VPS, Cloudflare challenge rate matches the Mac hidden-headful baseline for N≥5 cold loads. Datacenter IP risk is **unrealized** under current conditions → stay on **direct** egress.

## Fallback: Tailscale exit node (not activated)

If future canaries or doctor runs show challenge/block, route **Chrome host egress** through a residential peer exit node. Tailnet peers present at measure time (MagicDNS hostnames only — no raw tailnet IPs):

| Peer hostname | OS | Online at measure | Role |
|---------------|----|-------------------|------|
| `bs-macbook-air` | macOS | yes (active) | preferred residential exit candidate |
| `conference1` / `conference1-wsl` | windows / linux | present | alternate; prefer true residential Mac over lab boxes |

**Procedure (operator; do not leave on casually):**

1. Confirm peer advertises exit node and ACL allows it.
2. On `skillbox-portfolio-devbox` only:
   ```bash
   # dry check first — do not enable without recording the decision
   tailscale status   # confirm candidate online (MagicDNS names)
   sudo tailscale set --exit-node=bs-macbook-air
   # re-measure browser egress (temp CDP tab to ipinfo) — must NOT be DO ASN
   # re-run N>=5 canary; require challenge_rate == 0 and doctor ready
   ```
3. Record decision + new rates in this doc and the bead notes.
4. To clear:
   ```bash
   sudo tailscale set --exit-node=
   ```

**Constraints:**

- Never log cookies, tokens, or raw tailnet IPs (MagicDNS hostnames only).
- Do not stop/restart `oracle-*` units or wipe `~/.oracle/browser-profile` for an egress experiment.
- Exit node changes **all** host egress, not just Chrome — coordinate with other workloads.

## Operator re-run

```bash
# From run dir (or any scratch). Uses loopback CDP 19222.
# Script lives next to evidence: WG-1-9_canary/canary-cf-loads.mjs
ORACLE_CDP_PORT=19222 CANARY_N=5 CANARY_SETTLE_MS=5000 \
  CANARY_OUT=./canary-results.json \
  node canary-cf-loads.mjs

# Doctor still ready + challenge_clear
node deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs status --json
```

Validate doc presence:

```bash
test -s deep-research-prompt/references/oracle-cf-egress.md \
  && grep -c 'challenge' deep-research-prompt/references/oracle-cf-egress.md
```

## Related

- `references/oracle-vps-host.md` — host layout, CDP 19222, Xvfb
- `references/oracle-subagent-auth.md` — challenge observation contract
- Epic decision 1: hidden-headful required; true headless Cloudflare-blocked
