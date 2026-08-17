# Deep research tool toggle

## Why this file exists

Oracle v0.9.0 can pick a ChatGPT **model** (GPT-5.x Pro, Thinking, Instant) and a
**thinking-time level** (light / standard / extended / heavy). It cannot toggle
ChatGPT's separate **Deep research** *tool* — the one you enable from the
composer `+` menu that turns a normal ChatGPT turn into a multi-source research
run with citations.

The owner of this skill wants Deep research on by default for the research
prompts this skill produces. Oracle doesn't support that natively yet, so the
skill ships small CDP helpers: one to toggle the tool and one to watch for the
eventual dossier after submission.

## Project oracle config (overlay-sourced)

The per-project oracle settings — which ChatGPT account (Chrome profile), which
ChatGPT Project/folder, CDP host/port, and default engine/model — should come
from the matched client overlay's `oracle:` block, not from env vars an agent
hand-sets each run. This is what prevents the wrong-account / wrong-tab footgun:
the right target becomes the default for the repo.

Source it once at the start of any oracle run, before launching Chrome or
running the helpers below. It is a soft dependency on the `skill-issue`
resolver and a no-op when the resolver or overlay is absent, so the existing
manual env-var path still works:

```bash
for d in "./.claude/skills/skill-issue" "$HOME/.claude/skills/skill-issue"; do
  [ -f "$d/scripts/overlay_env.sh" ] && { . "$d/scripts/overlay_env.sh"; break; }
done
# No-op if skill-issue is absent; non-zero if it is present and the resolver fails.
command -v overlay_env_load >/dev/null && { overlay_env_load oracle || exit 1; }
```

Do **not** substitute a bare `eval "$(python3 "$RESOLVER" ... )"` here. That form
discards the resolver's exit status, so a crashed resolver sets nothing and
returns 0 — the run then proceeds against default CDP port and model instead of
the project's, which looks like success and targets the wrong account. See
[skill-issue references/overlay-config.md](../../skill-issue/references/overlay-config.md#why-not-eval).

After sourcing, these are set from the project overlay when defined (otherwise
unset, and the agent may still set them by hand):

- `ORACLE_CDP_HOST`, `ORACLE_CDP_PORT` — the DevTools endpoint the helpers use
- `ORACLE_CHATGPT_URL_MATCH` — the unique project-URL substring that selects
  the submit tab (the same knob the toggle/await helpers read), so you no
  longer pass `ORACLE_CHATGPT_URL_MATCH="<unique-path>"` inline
- `ORACLE_CHATGPT_TARGET_ID` — exact CDP target id when the overlay pins one
- `ORACLE_BROWSER_PROFILE_DIR` — the Chrome `--user-data-dir` = which
  logged-in ChatGPT account; use it for the Chrome launch below
- `ORACLE_DEFAULT_ENGINE`, `ORACLE_DEFAULT_MODEL`, `ORACLE_SLUG_PREFIX`,
  `ORACLE_DEEP_RESEARCH_DEFAULT` — project defaults for the run command

See `skill-issue/references/overlay-config.md` for the full key→env mapping and
the multi-profile/multi-account pattern (one profile dir per ChatGPT account,
each with its own project URL).

## The helper

`assets/scripts/toggle-deep-research.mjs` connects to a running Chrome via the
Chrome DevTools Protocol, resolves the intended `chatgpt.com` submit tab,
clicks the composer tool button (`+`), and clicks the `Deep research` menu
item.

It exits `0` if Deep research is on (either newly toggled or already selected).
Non-zero codes by reason:

| Exit | Reason |
|------|--------|
| 2    | No `chatgpt.com` tab on the given DevTools port |
| 3    | Composer `+` button / menu did not render |
| 4    | `Deep research` menu item not found (ChatGPT UI may have changed) |
| 5    | CDP connection failed |
| 6    | Click dispatched but the composer chip did not show Deep research |
| 7    | Multiple matching `chatgpt.com` tabs found; the submit tab is ambiguous |
| 8    | Requested ChatGPT target selector matched no tab |

Environment knobs:
- `ORACLE_CDP_HOST` (default `127.0.0.1`)
- `ORACLE_CDP_PORT` (default `9222`)
- `ORACLE_CHATGPT_TARGET_ID` for an exact Chrome DevTools target id
- `ORACLE_CHATGPT_URL_MATCH` for a URL substring that must match exactly one
  `chatgpt.com` tab; `DEEP_RESEARCH_CHATGPT_URL_MATCH` is accepted as an alias
- `DEEP_RESEARCH_VERBOSE=1` for stderr tracing

The helper uses WebSockets over CDP. On current Node versions it uses the
built-in `WebSocket`; on older Node versions it falls back to the `ws` npm
module if available.

## Completion capture helper

`assets/scripts/await-deep-research.mjs` connects to the same Chrome DevTools
endpoint and resolves the same ChatGPT target contract:

- `ORACLE_CDP_HOST` (default `127.0.0.1`)
- `ORACLE_CDP_PORT` (default `9222`)
- `ORACLE_CHATGPT_TARGET_ID`
- `ORACLE_CHATGPT_URL_MATCH` or `DEEP_RESEARCH_CHATGPT_URL_MATCH`

By default, it waits about 30 minutes before the first poll, polls every 15
minutes, and stops at about 2 hours unless it sees concrete browser/ChatGPT
error evidence first. When it detects assistant/research output with no obvious
active "researching/searching/stop generating" UI and that output is unchanged
across the configured stable polls, it prints the final text to stdout. Set
`DEEP_RESEARCH_OUTPUT=/path/to/result.md` or pass `--output /path/to/result.md`
to also write the capture to disk.

Example after Oracle submission:

```bash
DEEP_RESEARCH_OUTPUT=/tmp/<slug>-deep-research-result.md \
ORACLE_CHATGPT_URL_MATCH="<unique-project-or-conversation-path>" \
  node "$SKILL_DIR/assets/scripts/await-deep-research.mjs"
```

If the operator or monitor did not start the helper until roughly 30 minutes
after launch, use `--no-initial-delay` so it polls immediately and then follows
the 15 minute cadence:

```bash
DEEP_RESEARCH_OUTPUT=/tmp/<slug>-deep-research-result.md \
ORACLE_CHATGPT_URL_MATCH="<unique-project-or-conversation-path>" \
  node "$SKILL_DIR/assets/scripts/await-deep-research.mjs" --no-initial-delay
```

Exit codes:

| Exit | Reason |
|------|--------|
| 0    | Assistant/research output captured |
| 2    | No `chatgpt.com` tab on the given DevTools port |
| 5    | CDP connection or eval failed |
| 7    | Multiple matching `chatgpt.com` tabs found; completion target is ambiguous |
| 8    | Requested ChatGPT target selector matched no tab |
| 9    | Timed out before active signals cleared or output stabilized |
| 10   | Timed out with no assistant output visible |
| 11   | Concrete ChatGPT/browser error text was visible |
| 12   | Failed to write `DEEP_RESEARCH_OUTPUT` / `--output` |
| 64   | Invalid helper arguments |

The watcher is intentionally conservative. It is not a guarantee that ChatGPT's
Deep Research UI is stable; it is a best-effort DOM poller that fails with a
specific reason instead of pretending Oracle's immediate capture is the final
dossier.

## Oracle routing guard

Before any automatic Deep Research submission, run:

```bash
node "$SKILL_DIR/assets/scripts/check-oracle-tab-local-route.mjs"
```

This is a hard preflight, not a warning. If it exits non-zero, stop before
opening Chrome, toggling the tool, or invoking Oracle. The installed Oracle
must prove it can submit in the exact CDP target where this helper verified
the Deep Research chip.

Observed failure, May 2026: Oracle v0.9.0 remote browser mode opens a fresh
dedicated ChatGPT tab for its URL before submitting. That means this sequence
is unsafe:

1. open `https://chatgpt.com/?run=<slug>` manually
2. toggle Deep Research in that tab
3. run `oracle --remote-chrome ... --chatgpt-url https://chatgpt.com/?run=<slug>`

The `--chatgpt-url` value is used by Oracle as the URL for a new dedicated tab;
it is not a same-tab pin. The result is exactly the bad shape: one tab has
Deep Research selected, another receives the pasted prompt and submits a normal
text turn.

Until Oracle exposes a target-id, tab-reuse, or pre-submit-hook contract for
ChatGPT browser runs, the skill must fail closed and report a route-blocked
execute attempt. Do not "race" Oracle by trying to toggle the new tab after it
appears; the submit timing is not a stable contract.

## Verified composer flow (canonical execution path)

**Oracle renders; CDP submits.** For ChatGPT Deep Research browser runs, never
let Oracle click the model picker or the send button. Use `oracle` only to
size and render the prompt+files bundle, then drive the composer over CDP with
a DOM verification after every step. This sidesteps the route-guard problem
entirely: submission happens in the exact tab where Pro and Deep research were
verified, by construction.

Why Oracle's own browser submission is banned for Deep Research (all observed
against Oracle v0.9.0 + ChatGPT, June 2026):

- `--browser-manual-login` reused `~/.oracle/browser-profile` but landed on a
  logged-out ChatGPT — the live session lived in a **subprofile**
  (`Profile 1`), not `Default`.
- Cookie-copy from `Default/Cookies` applied no usable ChatGPT cookies for the
  same reason. Check subprofiles before blaming auth:
  `sqlite3 "<root>/<profile>/Cookies" "select host_key, count(*) from cookies
  where host_key like '%chatgpt%' group by host_key;"` — the subprofile with
  the most `chatgpt.com` rows (and the right `Preferences` profile name) is
  the logged-in one.
- `--browser-model-strategy select` aborted with
  `Unable to locate the ChatGPT model selector button` (UI drift).
- `--browser-model-strategy ignore` "succeeded" — by submitting on **Instant
  with Deep research off**. That run looked launched and was garbage.
- `--pre-submit-hook` executed only **after** the send click, so it cannot
  prove composer state before submission.

The canonical sequence (after sourcing the per-project oracle config above):

```bash
SKILL_DIR=""
for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
  [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
done

# 1. Dedicated CDP Chrome on a CLONE of the logged-in profile. Cloning avoids
#    the profile lock (a root attached to a running Chrome silently forwards
#    and never binds CDP); `open -na` avoids the macOS app-singleton handoff.
"$SKILL_DIR/assets/scripts/launch-chatgpt-cdp.sh"   # honors ORACLE_* env
# Inspect the printed tab list: it must be the logged-in account, not "Log in".

# 2. Render the prompt+files bundle (render only — no submission).
oracle --render --render-plain --engine browser \
  --model "${ORACLE_DEFAULT_MODEL:-gpt-5-pro}" --slug "<slug>" \
  -p "$(cat /tmp/<slug>-deep-research-<date>.md)" \
  --file <context-files...> > "/tmp/<slug>.oracle-rendered.md"

# 3. Drive the composer; every step prints JSON and exits 1 on failure.
C() { node "$SKILL_DIR/assets/scripts/chatgpt-composer.mjs" "$@"; }
C clear
C select-pro
node "$SKILL_DIR/assets/scripts/toggle-deep-research.mjs"
C verify-ready                                  # HARD GATE: Pro + Deep research
C paste-file "/tmp/<slug>.oracle-rendered.md"
C verify-ready                                  # paste must not reset the state
C send
C start-research                                # review card's Start (see below)
C verify-started                                # researching UI / stop button
C screenshot "/tmp/<slug>-submitted.png"        # evidence for the closeout

# 4. Capture the dossier (same watcher as before).
DEEP_RESEARCH_OUTPUT="/tmp/<slug>-deep-research-result.md" \
  node "$SKILL_DIR/assets/scripts/await-deep-research.mjs"
```

If `verify-ready` fails, stop and fix selection — do not send. If any DOM step
fails twice, take a `screenshot`, read it, and adjust; the JSON `state` field
carries the composer pills and menus the helper actually saw.

### ChatGPT UI gotchas (encoded in chatgpt-composer.mjs, June 2026)

- **Model picker:** the menu lists Instant / Thinking / Pro / Configure. The
  Pro row's trailing sliders icon opens an **effort submenu**
  (Standard / Extended) instead of switching the model — click the row's
  visible "Pro" text. The **account menu** also contains "Pro", and the
  sidebar's "Projects" matches a sloppy `/pro/` regex. `select-pro` handles
  all three traps; `verify-ready` proves the pill actually changed.
- **Mic trap:** the dictation button's aria-label is "Start dictation". Any
  Start-button matching must use visible text only, never aria-labels.
- **Deep Research review card:** after `send`, ChatGPT may insert a review
  card (title, plan bullets, Edit / Cancel / Start). The Start button shows a
  countdown and **auto-starts when it expires**. `start-research` clicks it,
  and treats already-visible research progress as success
  (`alreadyStarted: true`).
- **Long pastes** fold into a "Pasted text" attachment chip; the visible
  composer text being short is normal and `paste-file` accounts for it.
- **Subprofiles:** the logged-in session may live in `Profile 1` (or higher),
  not `Default`. Pin it per project with the overlay key `profile_directory`
  (→ `ORACLE_PROFILE_DIRECTORY`).

The route guard section above still governs the **legacy lane** where Oracle
itself submits (and Image execute mode, where the pre-submit hook works for
the Create image toggle). For Deep Research, prefer this verified flow
unconditionally.

## Submit-tab invariant

Deep Research is **tab/composer-local**. It is not a Chrome-wide setting. A run
is valid only if Oracle submits the prompt in the exact tab where the helper
verified the Deep Research chip. Toggling Deep Research in one ChatGPT tab and
then letting Oracle open or switch to another ChatGPT tab produces a normal
non-Deep-Research submission.

This is the critical invariant:

> Same Chrome is not enough. Same submit tab is required.

Multiple ChatGPT tabs are allowed for concurrent subagents or manual work. What
is not allowed is an ambiguous submit target. Resolve the target by one of these
routes, in order of preference:

1. Use a dedicated Chrome DevTools port/profile for the run.
2. Use a ChatGPT Project/folder URL only as a selector for the toggle helper,
   not as proof that Oracle will reuse the tab.
3. Set `ORACLE_CHATGPT_TARGET_ID=<cdp-target-id>` when the exact tab is known.
4. Set `ORACLE_CHATGPT_URL_MATCH=<unique-url-substring>` when the intended
   project/conversation path is unique.
5. Fall back to exactly one `chatgpt.com` tab only for simple, single-run
   workflows.

If the selector matches zero tabs or multiple tabs, stop before submitting. Do
not guess.

## ChatGPT Project/folder organization

Oracle supports `--chatgpt-url <url>` for ChatGPT workspace/folder/project
targets. Prefer using one ChatGPT Project/folder per client, domain, or research
wave (for example, a Buildooor research-validation project) so browser runs are
organized and the URL itself becomes a stable selector for the toggle helper.

When a project/folder URL is available and the route guard has already passed:

1. Open that URL in the Chrome instance attached to the DevTools port.
2. Set `ORACLE_CHATGPT_URL_MATCH` to a unique substring from that URL.
3. Run the toggle helper and confirm it selects exactly one tab.
4. Run Oracle with the same-tab target option or pre-submit hook reported by
   the guard. Do not rely on `--chatgpt-url` alone.

End-to-end flow for Oracle execute mode: use the **Verified composer flow**
above — launch via `launch-chatgpt-cdp.sh`, render the bundle with
`oracle --render`, then `chatgpt-composer.mjs` for select/verify/paste/send,
`toggle-deep-research.mjs` for the tool, and `await-deep-research.mjs` for the
dossier. Do not maintain a second runbook here; the canonical sequence lives in
that section. When a project URL exists, open it via
`ORACLE_CHATGPT_PROJECT_URL` so the dedicated Chrome starts on the project page
and `ORACLE_CHATGPT_URL_MATCH` resolves the tab unambiguously.

## Verification after the run starts

After Oracle submits the prompt, the user can reattach with
`oracle session <slug>`. If the resulting ChatGPT turn does not cite external
sources or uses a generic "I'll answer based on what I know" opener, Deep
research did not actually apply. The most common causes are: Oracle submitted
in a different tab than the toggled tab, the click landed on the wrong item
(exit code 6 catches the DOM case), ChatGPT asked a clarifying question instead
of starting, or ChatGPT silently downgraded because quota or tool state changed.
Treat this as a real failure and tell the user.

Do not confuse long silence with failure. Deep Research runs can take tens of
minutes with little or no terminal output after the prompt is visible in the
conversation and the composer is empty. If the run is not blocking the next
local action, delegate sparse monitoring to a subagent or background watcher,
wait about 30 minutes before the first poll, then poll around every 15 minutes,
and keep working on non-overlapping tasks. A reasonable monitor report is:
Oracle status, reattach command, output-file existence and size, and first/last
headings once the file appears. Do not call the run stalled before about 2
hours without concrete Oracle/browser error evidence. The bundled watcher
implements this cadence; use manual polling only when CDP access is unavailable
or ChatGPT's DOM has drifted beyond the helper's selectors.

## When to not use this

- When `oracle` is not on PATH at all — the skill falls back to paste mode and
  this file is irrelevant.
- When the target is Perplexity or Claude Research — they have their own
  research modes, and this helper only knows about ChatGPT.
- When the user explicitly asked for `paste-only`. Respect the opt-out.
- When the prompt is short enough that Deep research is overkill (the skill
  should already route those to regular GPT-5 Pro via Oracle without any
  toggle).

## Known fragility

The CDP selector logic in `toggle-deep-research.mjs` and
`await-deep-research.mjs` targets DOM shapes observed in ChatGPT as of the date
the helpers were committed. ChatGPT ships UI changes frequently. Verification
mode (`--verbose`) exists so failures come back with the actual DOM state; if
the toggle helper starts exiting 3 or 4 after a ChatGPT release, update the
selector lists in its `pageScript()` rather than patching Oracle. If the watcher
starts timing out with no assistant output despite visible completed reports,
update its assistant-message and active-state selectors before trusting its
status.
