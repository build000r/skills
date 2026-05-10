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
| 7    | Multiple matching `chatgpt.com` tabs; submit tab is ambiguous |
| 8    | Requested ChatGPT target selector matched no tab |

The helper does **not** silently grab the first `chatgpt.com` tab when more
than one is open. When more than one matches and no selector was provided it
exits `7` and prints the candidate list; provide a selector via the env
vars below to disambiguate.

Environment knobs:
- `ORACLE_CDP_HOST` (default `127.0.0.1`)
- `ORACLE_CDP_PORT` (default `9222`)
- `ORACLE_CHATGPT_TARGET_ID` — exact CDP target id of the intended tab
- `ORACLE_CHATGPT_URL_MATCH` — substring of the intended tab's URL (also
  honored as `CHATGPT_IMAGE_URL_MATCH` for image-only callers; the deep
  research toggle reads the same `ORACLE_CHATGPT_URL_MATCH` env var so the
  routing contract is uniform across the two helpers)
- `CHATGPT_IMAGE_VERBOSE=1` for stderr tracing

The helper uses WebSockets over CDP. On current Node versions it uses the
built-in `WebSocket`; on older Node versions it falls back to the `ws` npm
module if available.

## Parallel image runs

The image toggle is **per composer tab**, so concurrent image generations
must each own their own `chatgpt.com` tab. Recommended shape:

1. One Chrome instance, one DevTools port (`127.0.0.1:9222`). Do not spawn a
   second Chrome — share the same logged-in profile across runs.
2. For each parallel run, open a new ChatGPT tab with a unique URL — easiest
   is the per-run slug as a query string or hash, e.g.
   `https://chatgpt.com/?run=<slug>` or a fresh project URL with a unique
   path. The hash and query are arbitrary to ChatGPT but observable to CDP.
3. For each run, set `ORACLE_CHATGPT_URL_MATCH=<slug>` (or
   `ORACLE_CHATGPT_TARGET_ID=<cdp-id>`) **before** invoking
   `toggle-chatgpt-image.mjs`. The helper now refuses to pick one of N
   matching tabs without a selector; ambiguous and missing-selector paths
   exit `7` and `8` respectively.
4. For each run, pass `--chatgpt-url <same-url>` to `oracle` so it submits
   into the same tab the toggle activated. Without this, Oracle may open a
   fresh tab whose composer is not in image mode.
5. Capture the per-run Oracle slug for reattach. The runs proceed
   independently from there; image generation finishes in 1-3 minutes per
   tab.

If two runs accidentally share a tab, the toggle for run B will succeed (it
sees image mode is "already on") but Oracle for run A and run B will
contend for the same composer. Always disambiguate up front rather than
recovering after a collision.

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

4. **Toggle Create image on.** Resolve the skill dir first (project-local
   activation puts it at `./.claude/skills/deep-research-prompt`, global
   activation puts it at `$HOME/.claude/skills/deep-research-prompt`):
   ```
   SKILL_DIR=""
   for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
     [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
   done
   node "$SKILL_DIR/assets/scripts/toggle-chatgpt-image.mjs"
   ```
   If this exits non-zero, **do not silently proceed** — surface the reason to
   the user. Common failures: exit 4 (ChatGPT moved or renamed the menu item),
   exit 3 (plus button moved), exit 7 (multiple chatgpt.com tabs and no
   selector), exit 8 (selector matched no tab).

5. **Run Oracle against the same Chrome.** Use a shorter browser timeout since
   image generation finishes in 1-3 minutes, not 30. Use
   `--browser-model-strategy ignore`, **not** `current` — Image mode hides the
   ChatGPT model selector and `current` will exit early with
   `Unable to locate the ChatGPT model selector button` before submission. The
   model is fixed to ChatGPT's image-tool model anyway, so verifying the
   selector is moot in this mode.
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy ignore \
     --browser-timeout 15m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-image-<date>.md)"
   ```
   Image mode is already on from step 4, so Oracle just submits the spec.

   **Tab-local hazard.** Image mode is a per-composer-tab toggle, just like
   Deep research. If Oracle navigates to a brand-new `chatgpt.com` tab to
   submit (it sometimes does — same caveat as the Deep research flow), the
   new tab will not inherit the toggle from step 4. Mitigations, in
   preference order:
   - Pass `--chatgpt-url "$CHATGPT_PROJECT_URL"` so Oracle reuses the
     toggled tab instead of opening a new one.
   - Set `ORACLE_CHATGPT_URL_MATCH` to a unique substring of that URL before
     running `assets/scripts/toggle-chatgpt-image.mjs` so the helper targets
     the same tab Oracle will land on.
   - After Oracle opens its submit tab but before the prompt is dispatched,
     re-run `toggle-chatgpt-image.mjs` against the new tab.

   If the response comes back as text instead of an image, the toggle was
   not on the submit tab. Re-toggle and rerun rather than retrying with the
   same configuration.

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
