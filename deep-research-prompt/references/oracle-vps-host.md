# Oracle trusted browser host (skillbox-portfolio-devbox)

**Role:** the single fleet-canonical ChatGPT browser box.  
**Not:** conference1-wsl, not Mac, not every VPS. One host. No Chrome sprawl.

Hostname: `skillbox-portfolio-devbox`  
Lane: hidden-headful Chrome under Xvfb (true `--headless` is Cloudflare-blocked).

## Decisions (epic)

1. **Hidden-headful under Xvfb** — not true headless. Cloudflare blocks headless.
2. **One 0700 profile** — `~/.oracle/browser-profile` lives only on this host.
3. **Loopback CDP only** — bind `127.0.0.1:<cdp_port>` only. Never `0.0.0.0`.
4. **Config-driven CDP port** — do not hard-require 9222. On this host **9222 is
   owned by `tailscaled.service`** (cgroup `/system.slice/tailscaled.service`,
   root-only, no serve entry). It is **not reclaimable**. Use **19222**.
5. **systemd --user units** — Xvfb, Chrome, and the policy-gated tailnet RPC
   broker restart on failure; no root system units.
6. **Login is out of scope here** — owned by `skillbox-invisible-oracle-subagent-hjuc.1.8`.
   `sbp oracle --doctor` past `cdp_unreachable` / `listener_unverifiable` toward
   auth state (`NEEDS_REAUTH`-class ok) is success for this host node.

## CDP port resolution

First match wins (shared by launcher, host supervisor, and `oracle-ask` / `sbp oracle`):

| Priority | Source |
|----------|--------|
| 1 | CLI `--port` (launcher / oracle-ask) |
| 2 | `~/.oracle/config.json` field `cdp_port` (alias `cdpPort`) — **host pin** |
| 3 | `ORACLE_CDP_PORT` environment variable (may be set by skill overlays) |
| 4 | default `9222` |

Host config beats ambient overlay `ORACLE_CDP_PORT=9222` so `sbp oracle --doctor`
needs no `--port` on skillbox-portfolio-devbox.

**This host (skillbox-portfolio-devbox):**

```json
{
  "cdp_port": 19222
}
```

Merge into existing `~/.oracle/config.json` (mode `0600`). Do not paste other
config keys into chat/logs — the file may hold non-port secrets.

After changing `cdp_port`, re-run `./oracle-xvfb-host.sh install` so the systemd
user unit bakes the new `Environment=ORACLE_CDP_PORT=…`.

## Layout

| Path | Mode | Purpose |
|------|------|---------|
| `~/.oracle` | `0700` | root of all oracle private state |
| `~/.oracle/config.json` | `0600` | host config including `cdp_port` |
| `~/.oracle/browser-profile` | `0700` | Chrome `--user-data-dir` (canonical auth profile) |
| `~/.oracle/browser-profile/Default` | `0700` | Chrome profile directory |
| `~/.oracle/oracle-subagent/` | `0700` | runtime receipts (`browser.json`, attestation) |
| `~/.oracle/Xauthority` | `0600` | per-start MIT-MAGIC-COOKIE for the trusted display |
| `~/.config/systemd/user/oracle-xvfb.service` | `0600` | Xvfb on `DISPLAY=:97` |
| `~/.config/systemd/user/oracle-chatgpt-cdp.service` | `0600` | Chrome CDP supervisor |
| `~/.config/systemd/user/oracle-rpc.service` | `0600` | MagicDNS-only RPC broker on port 4117 |

## Scripts

| Script | Role |
|--------|------|
| `assets/scripts/oracle-xvfb-host.sh` | prepare / install / start / stop / doctor for the three supervised services |
| `assets/scripts/launch-chatgpt-cdp.sh` | mint exact CDP target + production receipt (Linux + Darwin) |
| `assets/scripts/oracle-ask.mjs` | `sbp oracle` front door; `--doctor` reads same port config |

Chrome binary default on this box:

```text
ORACLE_CHROME_BIN=$HOME/.local/bin/chrome-wrapper.sh
```

which execs the Puppeteer Chrome for Testing build under
`~/.cache/puppeteer/chrome/…` with the cypress-deps `LD_LIBRARY_PATH`.

Xvfb default:

```text
ORACLE_XVFB_BIN=$HOME/.local/bin/Xvfb   # wraps Xvfb.patched
ORACLE_XVFB_DISPLAY=97                 # DISPLAY=:97
```

## Operator bootstrap (this host only)

```bash
cd /path/to/skills/deep-research-prompt/assets/scripts

# 0) pin free CDP port (once) — never fight tailscaled's 9222
#    merge cdp_port:19222 into ~/.oracle/config.json (0600)

# 1) create 0700 dirs, install user units, start Xvfb+Chrome, mint receipt
./oracle-xvfb-host.sh ensure

# 2) host-local health (no secrets)
./oracle-xvfb-host.sh doctor
./oracle-xvfb-host.sh status

# 3) product doctor — no --port needed; reads config
sbp oracle --doctor

# 4) bind + perms proof (use the configured port)
ss -tlnp | grep 19222
stat -c '%a %n' "$HOME/.oracle" "$HOME/.oracle/browser-profile"
```

### systemd lifecycle

```bash
systemctl --user status oracle-xvfb.service oracle-chatgpt-cdp.service oracle-rpc.service
systemctl --user restart oracle-xvfb.service oracle-chatgpt-cdp.service oracle-rpc.service
journalctl --user -u oracle-chatgpt-cdp.service -n 50 --no-pager
```

Linger must be on so units survive logout (`loginctl show-user $USER -p Linger`).
On this host: `Linger=yes`.

## Linux launcher notes

`launch-chatgpt-cdp.sh` on Linux:

- Requires `DISPLAY` pointing at the Xvfb server (`:97` via the host units).
- Launches or reuses Chrome with `--remote-debugging-address=127.0.0.1`.
- Port from env/config as above; receipt records the resolved port.
- Skips Gatekeeper/`codesign` (macOS-only). Stamps the same receipt booleans
  the auth doctor requires after `/proc` binary+argv attestation.
- Visibility contract: process alive + virtual `DISPLAY` (no operator monitor).
- Target mint: `getTargets` → reuse exact-URL page or `createTarget`, then close
  surplus blank/exact-duplicate pages while preserving conversation pool targets.

Darwin behavior is unchanged (still defaults to 9222 unless config/env says otherwise).

## Health probe contract

| Check | Pass |
|-------|------|
| CDP HTTP | `GET http://127.0.0.1:<cdp_port>/json/version` returns JSON |
| Bind | `ss -tln` shows `127.0.0.1:<cdp_port>` only (no `*:<cdp_port>`) |
| Profile | `stat -c %a ~/.oracle` → `700` |
| Doctor | `sbp oracle --doctor` reason is **not** `cdp_unreachable` |
| Fleet RPC | `oracle-rpc-client.mjs --health --host <MagicDNS-host>` reports `service.ready`, a live policy-doctor decision under `policy.ready`, and browser readiness separately under `browser.ready` |

Fleet client probes resolve the named node from `tailscale status --json` and
connect through its current Tailnet address while retaining the MagicDNS name
as the HTTP authority. They do not use `/etc/hosts` short-name answers; a local
loopback mapping therefore cannot redirect a fleet probe away from the
tailnet-bound broker. Addresses remain runtime-only and are never emitted in
the health response or receipts.

`listener_unverifiable`, `browser_receipt_invalid`, `visibility_unverifiable`
(Darwin-only visibility probe), or auth `NEEDS_REAUTH` / blocked account reasons
still count as **past** `cdp_unreachable` once CDP is live and a receipt exists.

## Do not fight port 9222 on this host

Lead-verified: `ss -tlne` attributes `127.0.0.1:9222` to cgroup
`/system.slice/tailscaled.service` (root-only; no serve entry). User units
cannot reclaim it. **Stop trying.** Set `cdp_port` to a free loopback port
(**19222** on skillbox-portfolio-devbox) and reinstall units.

## Non-goals

- Interactive ChatGPT login (node `.1.8`)
- Transporting the Chrome profile off this host
- Binding CDP on Tailnet / public interfaces
- System-level systemd units
- Running Chrome on conference1 / Mac / other fleet members for this lane
- Killing or rebinding tailscaled's 9222 socket

## Host-audit caveat

Scope Oracle display audits to `oracle-xvfb.service` and its configured display
(`:97` on this host). A separate Cypress dependency workload may own display
`:99` and may use a different X access posture. It is not Oracle evidence: do
not kill it or reclassify it during an Oracle host audit.

## Related

- `references/oracle-credential-portability.md` — portable cookie lane (separate)
- `references/oracle-subagent-auth.md` — doctor / receipt contract
- Bead: `skillbox-invisible-oracle-subagent-hjuc.1.7`
