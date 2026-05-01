# ChatGPT image tool toggle

## Why this file exists

Oracle v0.9.0 can pick a ChatGPT **model** (GPT-5.x Pro, Thinking, Instant) and
a **thinking-time level**. It cannot toggle ChatGPT's **Create image** tool —
the composer `+` menu entry that routes the turn through ChatGPT's image
generation stack (gpt-image-1 / DALL·E) instead of a text response. Oracle's
`--generate-image` flag is Gemini-only at the moment.

The owner of this skill wants a first-class path from "I said /image" to "a
generated image comes back" without asking the user to paste a block into a
browser tab. This file is the sibling of
`references/deep-research-tool-toggle.md` — same pattern, different menu item.

## The helper

`assets/scripts/toggle-chatgpt-image.mjs` connects to a running Chrome via the
Chrome DevTools Protocol, finds the first `chatgpt.com` tab, clicks the
composer tool button (`+`), and clicks the `Create image` (or `Image`) menu
item.

It exits `0` if Image mode is on (either newly toggled or already selected).
Non-zero codes by reason:

| Exit | Reason |
|------|--------|
| 2    | No `chatgpt.com` tab on the given DevTools port |
| 3    | Composer `+` button / menu did not render |
| 4    | `Create image` menu item not found (ChatGPT UI may have changed) |
| 5    | CDP connection failed |
| 6    | Click dispatched but the composer chip did not show image mode |

Environment knobs:
- `ORACLE_CDP_HOST` (default `127.0.0.1`)
- `ORACLE_CDP_PORT` (default `9222`)
- `CHATGPT_IMAGE_VERBOSE=1` for stderr tracing

The helper uses WebSockets over CDP. On current Node versions it uses the
built-in `WebSocket`; on older Node versions it falls back to the `ws` npm
module if available.

## How the skill wires this into an Oracle run

Same Chrome as Deep research. Don't spawn a second Chrome; attach Oracle to
the already-running port.

End-to-end flow for Image execute mode:

1. **Launch Chrome with a known DevTools port** (or reuse the one already open
   from a Deep research session):
   ```
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9222 \
     --user-data-dir="$HOME/.oracle/browser-profile" \
     --no-first-run --no-default-browser-check \
     https://chatgpt.com/
   ```

2. **Wait for the tab to be ready.** Poll `http://127.0.0.1:9222/json` until a
   target with `url` matching `chatgpt.com` has loaded past `about:blank`.

3. **Make sure Deep research is OFF** before toggling image mode. Deep
   research and Create image are mutually exclusive composer tools; if the
   user just came from a Deep research run, re-select a different tool or
   clear the composer tool first. The image helper handles "already on" but
   not "some other tool is on."

4. **Toggle Create image on.**
   ```
   node "${HOME}/.claude/skills/deep-research-prompt/assets/scripts/toggle-chatgpt-image.mjs"
   ```
   If this exits non-zero, **do not silently proceed** — surface the reason to
   the user. Common failures: exit 4 (ChatGPT moved or renamed the menu item),
   exit 3 (plus button moved).

5. **Run Oracle against the same Chrome.** Use a shorter browser timeout since
   image generation finishes in 1-3 minutes, not 30:
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy current \
     --browser-timeout 15m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-image-<date>.md)"
   ```
   Image mode is already on from step 4, so Oracle just submits the spec.

6. **Surface the session slug** for reattach, and save the generated image
   file alongside the prompt. Do not re-print the prompt block.

## Verification after the run starts

After Oracle submits the prompt, the user can reattach with
`oracle session <slug>`. Two specific failure shapes to watch for:

- **The response is text, not an image.** Image mode fell out (usually because
  the turn was routed to a model that cannot emit images, or because a policy
  filter downgraded the request). Re-run after confirming the toggle chip is
  still present in the composer.
- **An image came back but the verification caption is missing or doesn't
  name deviations from the spec.** The spec explicitly requires the caption
  so silent substitutions surface. If the caption is missing, the skill
  should ask the model for it before closing out.

## When to not use this

- When `oracle` is not on PATH — the skill falls back to paste mode, and this
  file is irrelevant.
- When the user explicitly asked for `paste-only`. Respect the opt-out.
- When the caller wants Gemini image generation — use Oracle's built-in
  `--generate-image` (Gemini web/cookie mode) instead.
- When the target is a non-ChatGPT image surface (Midjourney, Firefly, etc.).
  This helper only knows about ChatGPT's composer.

## Known fragility

The CDP selector logic in `toggle-chatgpt-image.mjs` targets DOM shapes
observed in ChatGPT as of the date this file was committed. ChatGPT renames
composer tools often (e.g., "Create an image" → "Create image" → "Image"),
so the helper matches multiple label variants. If new builds ship a menu label
the script misses, update the `IMAGE_LABELS` list and the `waitForMenu` /
`option-missing` matchers in `pageScript()` rather than patching Oracle.
