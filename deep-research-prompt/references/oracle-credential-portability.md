# Oracle credential portability: can d3/d3c run without the Mac?

**Short answer: yes. d3 and d3c can run fully self-sufficiently. RPC back to the Mac is *not* required.**

The only thing the Mac is needed for is the *initial* login — a human logging into ChatGPT
in a visible browser, once. After that a small copied secret refreshes itself indefinitely
on any Linux box, with no browser, no Chrome profile, and no macOS.

Measured live on 2026-07-28 against the operator's real account, read-only (no prompts
submitted). Tooling: `assets/scripts/oracle-credential.mjs`.

---

## Why the existing lane cannot travel

The hidden-headful browser lane is deliberately welded to one machine. Four independent
walls, all verified present:

| # | Wall | Location |
|---|------|----------|
| 1 | macOS Keychain encrypts Chrome's cookie DB, so a copied `~/.oracle/browser-profile` is inert off-Mac | OS-level |
| 2 | Literal `uname -s = Darwin` gate: *"hidden-headful supervisor currently requires macOS"* | `assets/scripts/launch-chatgpt-cdp.sh:1028` |
| 3 | Required Gatekeeper/`codesign` attestation booleans (`gatekeeper_assessed`, `dynamic_code_verified`, `chrome_signature_verified`) that no Linux box can produce | `assets/scripts/oracle-subagent-auth.mjs:244-249` |
| 4 | `profile_fingerprint = sha256("<abs profile path>\0<profile dir>")` — cryptographically binds enrollment to `/Users/b` | `assets/scripts/oracle-subagent-auth.mjs:553-555` |

Walls 1 and 4 are the fatal ones. Even if you deleted the `uname` check and faked the
attestation booleans, the profile directory itself is undecryptable off-Mac and the
fingerprint would not match. **Transporting the profile is a dead end.** The portable
lane therefore transports a different artifact entirely.

---

## What is actually portable

Not the profile — the **NextAuth session cookie**, `__Secure-next-auth.session-token`
(~3.7 KB). It is the only artifact that both (a) mints fresh credentials and (b) carries
no machine binding.

### The crux experiment

The question that decides self-sufficiency: *can a headless `fetch`, with just the session
cookie and no browser, mint a fresh accessToken?*

```
POST-less GET https://chatgpt.com/api/auth/session
  cookie: __Secure-next-auth.session-token=<value>
  user-agent: <browser-like>
```

Result, from a plain Node `fetch` with **no browser process involved at all**:

```
A) session-token only          -> HTTP 200 | has_accessToken: true
B) session-token + cf_clearance -> HTTP 200 | has_accessToken: true
C) all cookies                 -> HTTP 200 | has_accessToken: true
```

**`cf_clearance` is not required. No Cloudflare challenge, no TLS-fingerprint problem,
no browser.** Case A — the single cookie alone — is sufficient.

### It works from Linux

The one and only machine-shaped requirement is a plausible User-Agent:

| User-Agent sent | Result |
|---|---|
| macOS Chrome | HTTP 200, accessToken returned |
| **Linux Chrome (d3/d3c)** | **HTTP 200, accessToken returned** |
| `curl/8.7.1` | HTTP 200, accessToken returned |
| `node` | **HTTP 403** |
| *(no UA header)* | **HTTP 403** |

The edge rejects a non-browser UA, not a non-Mac one. `oracle-credential.mjs` therefore
defaults to a **Linux** Chrome UA — the credential behaves identically on every box.

### Token shapes and lifetimes

| Artifact | Lifetime | Notes |
|---|---|---|
| `accessToken` | **exactly 10 days** (`exp - iat` = 864000s) | JWT, `iss: https://auth.openai.com`, `aud: https://api.openai.com/v1`. Verified usable as `Bearer` against `backend-api/me` → HTTP 200 |
| session cookie | **~90 days**, sliding | `expires` advances on every call, so an actively-refreshed credential never ages out |

`/api/auth/session` returns the *same* accessToken until it approaches expiry — it is
cached, not re-minted per call. Refresh therefore costs nothing to run often.

### The critical finding: **the session cookie does not rotate**

This is the operationally decisive result, and it is the **opposite** of the OAuth
refresh-token behaviour that caused the `d3`/Codex "refresh token already used" war.

Measured across repeated refreshes:

- `/api/auth/session` returns **no `Set-Cookie` for `__Secure-next-auth.session-token`**.
  (It sets only `oai-did`, `__oailb`, `__cf_bm`, `__cflb`, `_cfuvid`.)
- The original cookie **replays successfully** after many refreshes from elsewhere.
- The response body *does* contain a freshly re-signed `sessionToken`, which **also works**
  as a next cookie — and adopting it **does not invalidate the previous one**.

**Cross-box coexistence was then proven directly:** a simulated d3 store (separate path,
dead CDP port, Linux UA) rolled its token forward twice; the Mac's store was re-checked
afterwards and still refreshed cleanly, same account. **The boxes do not fight.**

This means the copied credential can live on the Mac, d3, and d3c simultaneously, each
refreshing on its own schedule, with no coordination and no rotation war.

### Roll-forward: the 90-day window is not a deadline

Because the response body carries a re-signed `sessionToken`, `refresh` adopts it by
default. Each refresh slides the ~90-day window forward **without a browser**. A box that
refreshes at least once every 90 days stays authenticated indefinitely. Pass `--no-roll`
to pin the stored cookie instead.

---

## The verdict

| Capability | Mac | d3 / d3c |
|---|---|---|
| Initial login (human, visible browser) | **required** | not possible |
| `acquire` (read cookie from live browser via CDP) | yes | no — fails cleanly with `browser_unreachable` |
| **`refresh` (mint fresh accessToken)** | yes | **yes — no browser, no macOS** |
| `doctor`, `print-access-token`, `import`/`export` | yes | **yes** |

Verified d3 simulation — copied store, CDP port pointed at a dead socket, Linux UA:

```
refreshed: .../d3sim/credential.json     refresh exit=0
doctor: ready
  [ok] portable: no host/path/OS binding in envelope
  [ok] live_refresh: browserless refresh works
  [ok] account_match: same account
```

**RPC back to the Mac is unnecessary.** The Mac is a one-time enrollment point, not a
runtime dependency. The only event that requires returning to it is a full session death
(explicit logout, password change, or 90+ days with no refresh anywhere).

---

## The security tradeoff, stated honestly

**Creating this credential creates a real, exfiltratable secret. That is precisely why the
prior design refused to make one.** The tradeoff is genuine and should be understood, not
waved away.

What the stored file grants to anyone who obtains it:

- Full ChatGPT account access as the operator, for up to ~90 days, **renewable
  indefinitely** by the same roll-forward mechanism that makes it useful.
- Because the cookie does **not** rotate, a stolen copy is **silent**: it keeps working
  alongside the legitimate one, and its use produces no visible symptom on the operator's
  boxes. There is no "token already used" alarm — the property that makes the credential
  operationally pleasant also removes the natural theft tripwire.
- Copying it to d3/d3c widens the blast radius from one physically-controlled laptop to
  two remote hosts. A box compromise is now an account compromise.

The browser lane avoids all of this by making the credential non-transportable *by
construction* — Keychain encryption and the path fingerprint mean there is simply nothing
worth stealing that would work anywhere else. That is a real security property being
traded away for portability. **This lane is added beside the browser lane, not in place of
it; the operator chooses which to keep.**

### Mitigations implemented

| Risk | Mitigation |
|---|---|
| Secret at rest readable by others | 0600 file, 0700 directory, atomic write created with the final mode (never briefly world-readable). Reads **refuse** a store that is group/world-accessible or owned by another user |
| Secret leaking into terminal scrollback | `print-access-token` and `export` **refuse to run when stdout is a TTY** unless explicitly forced |
| Secret leaking into the repo, logs, or reports | Nothing writes a secret anywhere but the 0600 store. All human/JSON output is fingerprints (12 hex of SHA-256), masked email, and expiry timestamps only. This document contains no token material |
| Secret leaking via environment | The token is never exported as an env var. Exposure is a **command** (`print-access-token`), matching the `caam.zsh` / `spaps-token-fresh` convention |
| **Stale token shadowing a good one** (the 8-week outage) | `print-access-token` auto-refreshes when under 24h remain, so a stale bearer is never served. `doctor` additionally **warns** when `OPENAI_ACCESS_TOKEN`, `CHATGPT_SESSION_TOKEN`, etc. are set, since a static value there can shadow this refreshable store |
| Credential silently pointing at the wrong account | `doctor` compares the live account fingerprint against the stored one and fails on mismatch |
| A dead credential installed and mistaken for working auth | `import` verifies against the live service before writing (bypass with `--no-verify`) |
| Accidental machine binding creeping back in | `doctor`'s `portable` check asserts the envelope contains no home path and no `profile_root`/`hostname`/`platform`-shaped field, and **fails** if one appears |

### Residual risks not mitigated here

- **No revocation primitive.** Nothing in this tool can invalidate a leaked copy. Because
  the cookie does not rotate, the only revocation is a global session invalidation
  (logout-everywhere / password change) from the ChatGPT UI — which also kills every
  legitimate box and forces re-enrollment on the Mac.
- **Transport is the operator's responsibility.** The documented path pipes `export`
  straight into `ssh … import` so the secret never touches a file on disk in between. It
  must never be pasted into a chat, a commit, a CI variable, or a shared note.
- **Shortening TTL is not available.** The 10-day accessToken lifetime and 90-day session
  window are set by the service; neither can be reduced client-side. "Short TTL" is
  therefore approximated by *refresh over storage* — hold the long-lived cookie, derive
  short-lived bearers on demand, never cache a bearer for downstream tools.

---

## Operating it

```sh
S=assets/scripts/oracle-credential.mjs

# Mac, once (needs the hidden-headful browser running and logged in):
node $S acquire
node $S doctor

# Transport to a remote box — secret never lands on disk in between:
node $S export | ssh d3 'node ~/bin/oracle-credential.mjs import'
ssh d3 'node ~/bin/oracle-credential.mjs doctor'

# On d3/d3c thereafter — no browser, no Mac:
node $S refresh
API_TOKEN="$(node $S print-access-token)"   # auto-refreshes when stale
```

Store: `~/.oracle/oracle-subagent/credential.json` (override with
`ORACLE_CREDENTIAL_STORE`). The path is intentionally **not** XDG-derived: conference1's
login shell sets `XDG_CONFIG_HOME`, which silently relocates credential paths and has
already cost one debugging session. A fixed `~/.oracle` path resolves identically
everywhere.

Keep a `refresh` on a timer (weekly is ample) on each box. That single habit keeps the
90-day window sliding forward forever and means the Mac is never needed again.

### Requirements

- `refresh` / `doctor` / `print-access-token` / `import` / `export`: **Node >= 18**
  (global `fetch`). No native modules, no dependencies.
- `acquire`: **Node >= 22** (global `WebSocket` for CDP) plus the running browser. Mac only
  — and only ever needed once.
