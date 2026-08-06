# Oracle trusted browser host (skillbox-portfolio-devbox)

**Role:** the single fleet-canonical ChatGPT browser box.  
**Not:** conference1-wsl, not Mac, not every VPS. One host. No Chrome sprawl.

Hostname: `skillbox-portfolio-devbox`  
Lane: hidden-headful Chrome under Xvfb (true `--headless` is Cloudflare-blocked).

## Decisions (epic)

1. **Hidden-headful under Xvfb** — not true headless. Cloudflare blocks headless.
2. **One 0700 profile** — `~/.oracle/browser-profile` lives only on this host.
3. **Loopback CDP only** — `127.0.0.1:9222`. Never `0.0.0.0`.
4. **systemd --user units** — restart-on-fail, no root system units.
5. **Login is out of scope here** — owned by `skillbox-invisible-oracle-subagent-hjuc.1.8`.  
   `sbp oracle --doctor` past `cdp_unreachable` (including `NEEDS_REAUTH` /
   auth blocked reasons) is success for this host node.

## Layout

| Path | Mode | Purpose |
|------|------|---------|
| `~/.oracle` | `0700` | root of all oracle private state |
| `~/.oracle/browser-profile` | `0700` | Chrome `--user-data-dir` (canonical auth profile) |
| `~/.oracle/browser-profile/Default` | `0700` | Chrome profile directory |
| `~/.oracle/oracle-subagent/` | `0700` | runtime receipts (`browser.json`, attestation) |
| `~/.config/systemd/user/oracle-xvfb.service` | `0600` | Xvfb on `DISPLAY=:97` |
| `~/.config/systemd/user/oracle-chatgpt-cdp.service` | `0600` | Chrome CDP supervisor |

## Scripts

| Script | Role |
|--------|------|
| `assets/scripts/oracle-xvfb-host.sh` | prepare / install / start / stop / doctor for the host |
| `assets/scripts/launch-chatgpt-cdp.sh` | mint exact CDP target + production receipt (Linux + Darwin) |

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

# 1) create 0700 dirs, install user units, start Xvfb+Chrome, mint receipt
./oracle-xvfb-host.sh ensure

# 2) host-local health (no secrets)
./oracle-xvfb-host.sh doctor
./oracle-xvfb-host.sh status

# 3) product doctor (login may still be required — that is OK for this node)
sbp oracle --doctor

# 4) bind + perms proof
ss -tlnp | grep 9222
stat -c '%a %n' "$HOME/.oracle" "$HOME/.oracle/browser-profile"
```

### systemd lifecycle

```bash
systemctl --user status oracle-xvfb.service oracle-chatgpt-cdp.service
systemctl --user restart oracle-chatgpt-cdp.service
journalctl --user -u oracle-chatgpt-cdp.service -n 50 --no-pager
```

Linger must be on so units survive logout (`loginctl show-user $USER -p Linger`).
On this host: `Linger=yes`.

## Linux launcher notes

`launch-chatgpt-cdp.sh` on Linux:

- Requires `DISPLAY` pointing at the Xvfb server (`:97` via the host units).
- Launches or reuses Chrome with `--remote-debugging-address=127.0.0.1`.
- Skips Gatekeeper/`codesign` (macOS-only). Stamps the same receipt booleans
  the auth doctor requires after `/proc` binary+argv attestation.
- Visibility contract: process alive + virtual `DISPLAY` (no operator monitor).

Darwin behavior is unchanged.

## Health probe contract

| Check | Pass |
|-------|------|
| CDP HTTP | `GET http://127.0.0.1:9222/json/version` returns JSON |
| Bind | `ss -tln` shows `127.0.0.1:9222` only (no `*:9222`) |
| Profile | `stat -c %a ~/.oracle` → `700` |
| Doctor | `sbp oracle --doctor` reason is **not** `cdp_unreachable` |

`browser_receipt_invalid`, `visibility_unverifiable` (Darwin-only visibility
probe in the doctor), or auth `NEEDS_REAUTH` / blocked account reasons still
count as **past** `cdp_unreachable` once CDP is live and a receipt exists.

## Failure: ghost listener on 9222

If `ss` shows `127.0.0.1:9222` but `/json/version` RSTs / fails and `lsof`
shows no owner, a foreign or leaked socket is holding the port. User units
cannot reclaim it without root.

```bash
# detect
./oracle-xvfb-host.sh doctor   # cdp_http=dead_listener

# operator repair (pick one)
ss -K sport = :9222            # needs CAP_NET_ADMIN
# or reboot the box
```

Then re-run `./oracle-xvfb-host.sh ensure`.

## Non-goals

- Interactive ChatGPT login (node `.1.8`)
- Transporting the Chrome profile off this host
- Binding CDP on Tailnet / public interfaces
- System-level systemd units
- Running Chrome on conference1 / Mac / other fleet members for this lane

## Related

- `references/oracle-credential-portability.md` — portable cookie lane (separate)
- `references/oracle-subagent-auth.md` — doctor / receipt contract
- Bead: `skillbox-invisible-oracle-subagent-hjuc.1.7`
