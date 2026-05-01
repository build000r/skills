# Deep research tool toggle

## Why this file exists

Oracle v0.9.0 can pick a ChatGPT **model** (GPT-5.x Pro, Thinking, Instant) and a
**thinking-time level** (light / standard / extended / heavy). It cannot toggle
ChatGPT's separate **Deep research** *tool* — the one you enable from the
composer `+` menu that turns a normal ChatGPT turn into a multi-source research
run with citations.

The owner of this skill wants Deep research on by default for the research
prompts this skill produces. Oracle doesn't support that natively yet, so the
skill ships a small CDP helper that does the click.

## The helper

`assets/scripts/toggle-deep-research.mjs` connects to a running Chrome via the
Chrome DevTools Protocol, finds the first `chatgpt.com` tab, clicks the
composer tool button (`+`), and clicks the `Deep research` menu item.

It exits `0` if Deep research is on (either newly toggled or already selected).
Non-zero codes by reason:

| Exit | Reason |
|------|--------|
| 2    | No `chatgpt.com` tab on the given DevTools port |
| 3    | Composer `+` button / menu did not render |
| 4    | `Deep research` menu item not found (ChatGPT UI may have changed) |
| 5    | CDP connection failed |
| 6    | Click dispatched but the composer chip did not show Deep research |

Environment knobs:
- `ORACLE_CDP_HOST` (default `127.0.0.1`)
- `ORACLE_CDP_PORT` (default `9222`)
- `DEEP_RESEARCH_VERBOSE=1` for stderr tracing

The helper uses WebSockets over CDP. On current Node versions it uses the
built-in `WebSocket`; on older Node versions it falls back to the `ws` npm
module if available.

## How the skill wires this into an Oracle run

Oracle's browser mode launches its own Chrome and drives it to completion in
one shot, so there's no natural pause between "open tab" and "submit prompt"
where we can interleave a tool toggle. The clean way around this is Oracle's
`--remote-chrome host:port` flag, which makes Oracle attach to an *already
running* Chrome instead of launching its own. That gives the skill full
control over the pre-submit setup.

End-to-end flow for Oracle execute mode:

1. **Launch Chrome with a known DevTools port.** Use the user's existing Chrome
   profile so they stay logged into ChatGPT, but open a fresh Chrome instance
   on port `9222` (or any free port). Example:
   ```
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9222 \
     --user-data-dir="$HOME/.oracle/browser-profile" \
     --no-first-run --no-default-browser-check \
     https://chatgpt.com/
   ```
   (If Oracle's own persistent profile at `~/.oracle/browser-profile` is in
   use, reuse it — logged-in cookies are already there.)

2. **Wait for the tab to be ready.** Poll `http://127.0.0.1:9222/json` until a
   target with `url` matching `chatgpt.com` has loaded past `about:blank`.

3. **Toggle Deep research on.**
   ```
   node "${HOME}/.claude/skills/deep-research-prompt/assets/scripts/toggle-deep-research.mjs"
   ```
   If this exits non-zero, **do not silently proceed** — surface the reason to
   the user. The common failure modes are exit 4 (ChatGPT moved the menu item
   label) and exit 3 (plus button moved).

4. **Run Oracle against the same Chrome.**
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy current \
     --model gpt-5-pro \
     --browser-timeout 30m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-deep-research-<date>.md)"
   ```
   `--browser-model-strategy current` tells Oracle to keep the active model.
   Deep research is already on from step 3, so Oracle just types the prompt
   and submits.

5. **Surface the session slug** for reattach, do not re-print the prompt.

## Verification after the run starts

After Oracle submits the prompt, the user can reattach with
`oracle session <slug>`. If the resulting ChatGPT turn does not cite external
sources or uses a generic "I'll answer based on what I know" opener, Deep
research did not actually apply — most likely the click landed on the wrong
item (exit code 6's verification catches the DOM case, but ChatGPT can also
silently downgrade a Deep research request if quota is exhausted). Treat this
as a real failure and tell the user.

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

The CDP selector logic in `toggle-deep-research.mjs` targets DOM shapes
observed in ChatGPT as of the date this file was committed. ChatGPT ships UI
changes frequently. Verification mode (`--verbose`) exists so failures come
back with the actual DOM state; if the helper starts exiting 3 or 4 after a
ChatGPT release, update the selector lists in `pageScript()` rather than
patching Oracle.
