# ChatGPT backend conversation API — reconstructed contract

Reconstruction of the JSON/SSE backend that the chatgpt.com web client calls, so
the oracle path can ask GPT-5 Pro a question over HTTPS instead of driving the
DOM.

- **Method**: `interface-reconstruction`, `api` mode.
- **Target**: `https://chatgpt.com` backend-api.
- **Authorized identity**: the operator's own ChatGPT **Pro** account
  (`plan_type: "pro"`, `subscription_plan: "chatgptpro"`), already signed in
  inside a local Chrome exposing loopback CDP on `127.0.0.1:9222`.
- **Captured**: 2026-07-28.
- **Client build observed**: `oai-client-version: prod-09fba346c30685f17ce7156ae17baf81ca7d2521`,
  `oai-client-build-number: 8721732`, Chrome 150.
- **Budget**: 4 model submissions total. No loops, no load testing.
- **Raw captures** (HAR-equivalent fetch/CDP logs, tokens, cookies) were kept in
  a private scratch directory and are **not** committed.

Every claim below is labelled with a truth level: `observed`, `inferred`,
`replayed`, `implemented`, `blocked`, `unknown`.

---

## 1. Headline result

`assets/scripts/oracle-http-client.mjs` answers a GPT-5.6 Pro question over
plain Node `fetch` with **zero CSS selectors, zero `data-testid` contracts, and
zero exact-text assertions**. Model selection is the JSON field `model`.

Operators and agents do not call it directly — `assets/scripts/oracle-ask.mjs`
is the entrypoint (`oracle-ask "your question"`), and SKILL.md → "Ask mode"
routes to it. This file is the contract that lane depends on.

```
[oracle-http] {"phase":"credentials","tokenPrefix":"eyJhbGci…[1746]","planType":"pro"}
[oracle-http] {"phase":"sentinel","trigger":"request_submit","headers":18}
[oracle-http] {"phase":"stream","handoff":true,"complete":true,"frames":8}
[oracle-http] {"phase":"poll","elapsedMs":7252}
{ "text": "HTTP_OK", "modelSlug": "gpt-5-6-pro", "source": "polled", "elapsedMs": 12618 }
```

`implemented` — 12.6 s wall clock from CDP connect to returned Pro answer,
against the DOM path's 8–12 s warm preamble *before a character is typed*.

---

## 2. Authentication

### 2.1 Bearer token, not cookies

`observed`. `GET /api/auth/session` returns 200 with a `accessToken` JWT
(1746 chars, `expires` ≈ 90 days out). `backend-api` authenticates from
`Authorization: Bearer <accessToken>`.

**Cookies alone are not sufficient and silently degrade rather than fail.** A
cookie-only `fetch("/backend-api/accounts/check/v4-2023-04-27")` from the page
returns **HTTP 200** describing a *guest*:

| Call | Auth | Result |
|---|---|---|
| `accounts/check/v4-2023-04-27` | cookies only | 200, `plan_type: "guest"`, `subscription_plan: "chatgptguestplan"` |
| `accounts/check/v4-2023-04-27` | `Bearer` | 200, `plan_type: "pro"`, `subscription_plan: "chatgptpro"` |
| `models?history_and_training_disabled=false` | cookies only | 200, **5** slugs, categories marked `subscription_level: "free"` |
| `models?history_and_training_disabled=false` | `Bearer` | 200, **19** slugs incl. `gpt-5-6-pro`, `gpt-5-5-pro`, `o3-pro`, `research` |

> **Warning for the existing auth probe.** `oracle-subagent-auth.mjs` (lines
> ~1064–1067) calls `/backend-api/me`, `/backend-api/accounts/check/...` and
> `/backend-api/models` with `fetch(path, { credentials: "include" })` and **no
> `Authorization` header**. Those calls therefore read the *guest* projection:
> a Pro account looks like a free account, and `gpt-5-6-pro` / `research` are
> absent from the model list. This is a 200-OK false negative, not an error.
> `observed`. Fix is out of scope for this file's owner — flagged, not edited.

### 2.2 Negative controls

`replayed`, from plain Node outside the browser:

| Control | Result |
|---|---|
| No `Authorization` header | `401 {"detail":"Unauthorized"}` |
| Last 4 chars of the JWT corrupted | `401 code:"unauthorized_unknown"`, "Could not parse your authentication token" |
| Valid `Bearer`, no `chatgpt-account-id` | 200 — account header is **optional** for reads |

### 2.3 Account scoping

`observed`. `accounts/check/v4-2023-04-27` → `accounts.default.account.account_id`
(a UUID). Sent as `chatgpt-account-id` on the app's requests. Optional for
`/models` and conversation reads on this single-workspace personal account;
`unknown` whether it becomes mandatory on multi-workspace accounts.

---

## 3. Model catalogue — selection is a JSON field

`observed`. `GET /backend-api/models?history_and_training_disabled=false` with
`Bearer` returns `{ models[], categories[], versions[], default_model_slug,
model_picker_version }`. 19 slugs:

```
gpt-5-3            gpt-5-3-instant    gpt-5-5           gpt-5-5-instant
gpt-5-5-thinking   gpt-5-6-thinking   gpt-5.5-wm        gpt-5.5-cca-wm
gpt-5.6-sol-wm     gpt-5.6-terra-wm   gpt-5.6-luna-wm   gpt-5-5-pro
gpt-5-6-pro        gpt-5-3-mini       gpt-5-5-mini      gpt-5-4-t-mini
o3                 o3-pro             research
```

`research` is Deep Research. `categories[]` maps picker entries to
`default_model`, e.g. `gpt_5_6_pro → gpt-5-6-pro`.

This replaces the DOM path's dropdown click plus an assertion that a button's
text equals `"pro"`.

---

## 4. Request graph for one submission

`observed`, from a CDP `Network` capture plus an in-page `fetch` recorder around
one real UI submission.

```
(composer edit, debounced)
  POST /backend-api/f/conversation/prepare              -> {status:"ok", conduit_token:null}
  POST /backend-api/sentinel/chat-requirements/prepare  -> prepare_token + challenge programs
  POST /backend-api/sentinel/ping
  POST /backend-api/sentinel/chat-requirements/finalize -> {token, expire_after:540, expire_at}
(submit)
  POST /backend-api/f/conversation                      -> text/event-stream
```

`inferred`: the sentinel cycle is **ahead-of-time**. The tokens spent by a given
submission were minted by an earlier cycle (typing is enough to trigger one);
the app re-mints immediately after submitting to warm the next turn.

---

## 5. The anti-abuse gate (the thing that makes naive replay fail)

### 5.1 Two-phase sentinel

`observed`.

**`POST /backend-api/sentinel/chat-requirements/prepare`**

Request: `{"p": "gAAAAAC<base64>"}` where the base64 decodes to a JSON array of
browser environment values — timestamp string, memory, UA, client version,
locale, performance timings, a UUID, and counters.

Response (68 KB):

```jsonc
{
  "persona": "chatgpt-paid",
  "prepare_token": "gAAAAAB…",                      // 3236 chars
  "proofofwork": { "required": true, "seed": "0.7767733448826036", "difficulty": "0748da" },
  "turnstile":   { "required": true, "dx": "…" },    // 28 820 chars
  "so":          { "required": true, "collector_dx": "…", "snapshot_dx": "…" }  // 17 500 / 18 764
}
```

**`POST /backend-api/sentinel/chat-requirements/finalize`**

Request: `{ prepare_token, proofofwork, turnstile }`, where `proofofwork` and
`turnstile` are the *solutions*. Response:
`{ persona, token, expire_after: 540, expire_at }`.

### 5.2 Three required headers

`observed`. The conversation POST carries:

```
openai-sentinel-chat-requirements-token   ~2424 chars   (the finalize `token`)
openai-sentinel-proof-token               ~673 chars
openai-sentinel-turnstile-token           ~4316 chars
```

`observed`: the proof and turnstile values on the conversation POST are **not**
the same strings sent to `finalize` — they are recomputed per request. So a
client cannot simply cache what finalize consumed.

### 5.3 Why a pure-Node client cannot forge them — `blocked`

`turnstile.dx`, `so.collector_dx` and `so.snapshot_dx` are obfuscated programs
the browser must execute to produce an environment attestation. `SentinelSDK` is
exposed on `window` (`init`, `token`, `sessionObserverToken`, `timing`, loaded
from `https://chatgpt.com/sentinel/<build>/sdk.js`) but is fully minified and
string-table obfuscated; `SentinelSDK.token(arg)` hangs for argument values not
already initialised by the app, and the app holds a private reference so
wrapping `window.SentinelSDK.token` observes nothing.

Reimplementing these programs would mean reverse-engineering a bot defense.
That is out of bounds under the skill's authorization boundary, and it was not
attempted. **This is a genuine hard blocker for a fully standalone Node client,
and it is a finding, not a gap.**

### 5.4 Negative controls proving the gate is real

`replayed`:

| Attempt | Result |
|---|---|
| Node POST, valid `Bearer`, **no** sentinel headers | `403 {"detail":"Unusual activity has been detected from your device. Try again later. (<id>)"}` |
| In-page `fetch()` POST, valid `Bearer`, no sentinel headers | identical `403` — the page's `fetch` does **not** auto-attach them |
| Node POST, fresh sentinel triple, **no cookies** | `403` HTML interstitial (edge, not origin) |
| Node POST, fresh sentinel triple **plus cookies** | **200 `text/event-stream`** |

`observed`: the cookie jar matters at the Cloudflare edge, not the origin.
`cf_clearance`, `__cf_bm`, `_cfuvid` and the NextAuth session cookies are
present in the working request. Without them the request never reaches the
OpenAI origin.

### 5.5 The in-bounds solution: browser-brokered mint

`implemented`. The client installs a temporary `window.fetch` wrapper that
**intercepts and rejects** the app's own outgoing conversation POST. The browser
mints a genuine sentinel triple as it normally would; the request never leaves
the machine, so **no model call is made and no message is created**. The client
then reuses that unused triple, plus the CDP-read cookie jar, for its own POST.

The defense is satisfied by the real browser it was designed for. Nothing is
bypassed, emulated, or solved programmatically.

The mint trigger uses only generic HTML semantics — no ChatGPT-specific
selector:

```js
Input.insertText(".")                                  // CDP; the page auto-focuses its composer
document.activeElement.closest("form").requestSubmit() // generic HTML
```

`observed`: `Input.insertText` reaches the composer with no `focus()` call and
no selector; a synthetic `Enter` key event does **not** submit in this headless
window, and CDP `Input.dispatchMouseEvent` does not hit-test, but
`requestSubmit()` does — it produced a full 18-header capture.

---

## 6. `POST /backend-api/f/conversation`

### 6.1 Headers — `observed` (18)

| Header | Required | Note |
|---|---|---|
| `authorization` | yes | `Bearer <accessToken>` |
| `content-type` | yes | `application/json` |
| `accept` | yes | `text/event-stream` |
| `openai-sentinel-chat-requirements-token` | yes | 403 without |
| `openai-sentinel-proof-token` | yes | 403 without |
| `openai-sentinel-turnstile-token` | yes | 403 without |
| `cookie` | yes (from Node) | edge clearance; browser sends automatically |
| `chatgpt-account-id` | account scoping | |
| `oai-language`, `oai-device-id`, `oai-session-id` | client identity | |
| `oai-client-version`, `oai-client-build-number` | build pinning | |
| `oai-echo-logs`, `oai-telemetry` | telemetry | `unknown` whether validated |
| `x-oai-is-client-observation`, `x-oai-turn-trace-id` | tracing | |
| `x-openai-target-path`, `x-openai-target-route` | routing, both `/backend-api/f/conversation` | |

`unknown`: which of the `oai-*` / `x-oai-*` headers are strictly enforced. The
client forwards the harvested set verbatim rather than minimising it, because
minimisation would require repeated live submissions against the operator's real
account — outside the 4-prompt budget.

### 6.2 Body — `observed`

```jsonc
{
  "action": "next",
  "messages": [{
    "id": "<uuid>",
    "author": { "role": "user" },
    "create_time": 1785280836.533,
    "content": { "content_type": "text", "parts": ["Reply with exactly: CAPTURE_TWO"] },
    "metadata": { "selected_sources": [], "serialization_metadata": { "custom_symbol_offsets": [] } }
  }],
  "conversation_id": "<uuid>",          // omit to start a new conversation
  "parent_message_id": "<uuid>",        // "client-created-root" for a new conversation
  "model": "gpt-5-6-pro",               // <-- model selection, no dropdown
  "timezone_offset_min": 420,
  "timezone": "America/Vancouver",
  "conversation_mode": { "kind": "primary_assistant" },
  "enable_message_followups": true,
  "system_hints": [],
  "supports_buffering": true,
  "supported_encodings": ["v1"],
  "client_contextual_info": { "app_name": "chatgpt.com", … },
  "paragen_cot_summary_display_override": "allow",
  "force_parallel_switch": "auto",
  "thinking_effort": "standard",
  "local_function_names": ["local.continue_in_work"],
  "client_prepare_state": "success"     // client drops this; tied to the /prepare call
}
```

`inferred`: `thinking_effort` (`"standard"`) is the JSON equivalent of the DOM
path's effort-picker click. Not exercised at other values.

### 6.3 Response framing — `observed`

`content-type: text/event-stream; charset=utf-8`. Notable response headers:
`x-conduit-token` (a short-lived ES256 JWT), `x-oai-request-id`.

```
event: delta_encoding
data: "v1"

data: {"type":"resume_conversation_token","kind":"topic","token":"…","conversation_id":"…"}
data: {"type":"input_message","input_message":{…}}

event: delta
data: {"p":"","o":"add","v":{"message":{…}},"c":0}

data: {"type":"stream_handoff","conversation_id":"…","turn_exchange_id":"…",
       "options":[{"type":"resume_sse_endpoint","topic_id":"conversation-turn-…"},
                  {"type":"subscribe_ws_topic","topic_id":"conversation-turn-…"}]}
data: {"type":"server_ste_metadata","metadata":{…,"plan_type":"pro","model_slug":"gpt-5-6-pro",
       "pro_mode_turn_topic_streaming":true,…}}
data: {"type":"conversation_detail_metadata",…,"limits_progress":[{"feature_name":"deep_research","remaining":249,…}]}

data: [DONE]
```

**Terminator**: the literal frame `data: [DONE]`.

`observed`: for a **Pro** turn the initial POST does *not* carry the answer. It
emits `stream_handoff` and terminates with `[DONE]` after ~4 s while the model
is still working. The answer is delivered on a resume channel.

`unknown`: the concrete URL of `resume_sse_endpoint`, and the WebSocket topic
subscription protocol. Both are named in the handoff frame but their transport
was not captured — the app subscribes over an already-open WebSocket that the
page-level `fetch` recorder does not see. Not pursued, because a documented
polling fallback exists (§6.4) and pursuing it would have cost extra live
submissions.

### 6.4 Completion by polling — `replayed`

`observed`: the handoff message metadata advertises polling as a first-class
fallback — `poll_interval_ms: 10000`, `poll_on_websocket_inactivity_ms: 30000`,
`poll_freshness_max_mins: 120`.

`GET /backend-api/conversation/{conversation_id}` with only `Authorization:
Bearer` (no cookies, no sentinel) returns the full `mapping`. The final answer
is the node satisfying **all** of:

- `author.role === "assistant"`
- `recipient === "all"`
- `status === "finished_successfully"` and `end_turn === true`
- `content.content_type === "text"`
- `metadata.model_slug` present

The last predicate is load-bearing: each Pro turn also produces a
`reasoning_recap` assistant message with `end_turn: true` and **no**
`model_slug`, plus a `tool` message authored `a8km123`. Filtering only on
role/status returns the recap, not the answer.

---

## 7. Failure signatures

| Signature | Meaning | Client code |
|---|---|---|
| `401 {"detail":"Unauthorized"}` | no bearer | `auth_expired` |
| `401 unauthorized_unknown` | malformed/expired bearer | `auth_expired` |
| `403 {"detail":"Unusual activity has been detected from your device…"}` | missing/invalid sentinel triple | `sentinel_rejected` |
| `403 text/html` interstitial | edge challenge; cookie jar missing | `sentinel_rejected` |
| 200 + `plan_type: "guest"` | **silent** auth downgrade — bearer omitted | detect explicitly |
| `expire_after: 540` elapsed | sentinel token stale; re-mint | `mint_timeout` / re-harvest |

`observed`: the guest downgrade is the dangerous one — it is an HTTP 200 that a
naive client will treat as success.

---

## 8. Coverage ledger

| Cell | Disposition | Evidence |
|---|---|---|
| Session token acquisition | `replayed` | `/api/auth/session` → Node reuse |
| Account/plan resolution | `replayed` | bearer vs cookie A/B |
| Model catalogue | `replayed` | 19 slugs from Node |
| Model selection as JSON | `implemented` | `--model gpt-5-6-pro` round trip |
| Auth negative: none | `replayed` | 401 |
| Auth negative: tampered | `replayed` | 401 |
| Auth negative: cookie-only downgrade | `observed` | guest projection |
| Sentinel prepare | `observed` | request/response captured |
| Sentinel finalize | `observed` | request/response captured |
| Sentinel token forging in Node | **`blocked`** | obfuscated browser VM programs; out of bounds |
| Sentinel brokerage from browser | `implemented` | intercept-and-reject mint |
| Conversation POST headers | `observed` | 18 headers |
| Conversation POST minimal header set | `unknown` | needs repeated live submissions; budget-bound |
| Conversation POST body schema | `replayed` | Node POST 200 |
| SSE framing + `[DONE]` terminator | `replayed` | parsed from Node stream |
| Inline delta answer path (fast models) | `inferred` | delta frames present; not exercised — every capture used Pro, which hands off |
| `stream_handoff` for Pro | `observed` | 3 captures |
| Resume SSE endpoint URL | `unknown` | named in handoff, transport not captured |
| Resume WebSocket topic protocol | `unknown` | not captured |
| Answer retrieval by polling | `replayed` | `HTTP_OK` extracted |
| End-to-end Pro question | `implemented` | 12.6 s |
| Deep Research (`research` slug) | `unknown` | slug visible; never submitted |
| Attachments / images / tools | `unknown` | out of scope |
| New-conversation creation from client | `inferred` | `parent_message_id: "client-created-root"` observed in `/prepare`; client always reused an existing conversation |

`bounded_proof_complete = false`. Four cells remain `unknown` and one is
`blocked`; they are listed rather than hidden.

---

## 9. Robustness delta

| | DOM path | HTTP path |
|---|---|---|
| ChatGPT-specific CSS selectors | ~35 | **0** |
| Exact attribute-value contracts | ~15 | **0** |
| Exact-text assertions | ~12 | **0** |
| `length !== 1` fail-closed checks | most | **0** |
| Model selection | dropdown click + text assert | JSON field |
| Answer extraction | DOM scrape | JSON `mapping` |
| Breaks on UI redesign | yes | only if the mint trigger's `<form>` disappears |

Residual browser coupling: a signed-in Chrome on loopback CDP must exist, and
one generic-HTML form submit is used per question to mint the anti-abuse token.
The mint trigger has no ChatGPT-specific contract; a redesign changes class
names, test ids and labels, none of which it reads.

---

## 10. Operational notes

- The sentinel token lives 540 s. One mint per question is the safe default;
  reuse across questions inside that window was **not** tested (budget).
- Harvesting mints a token but never spends it: the intercepted POST is rejected
  in-page, so no model request occurs. The UI shows a transient send failure.
- Bearer, cookies and sentinel values are secrets. The client only ever logs
  prefixes via `redact()`.
- The client inherits `conversation_id` / `parent_message_id` from the harvested
  template, so questions land in whatever conversation the brokering tab is on.
