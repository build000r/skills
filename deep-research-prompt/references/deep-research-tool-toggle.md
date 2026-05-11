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

## How the skill wires this into an Oracle run

Oracle's browser mode launches its own Chrome and drives it to completion in
one shot, so there's no natural pause between "open tab" and "submit prompt"
where we can interleave a tool toggle. Remote Chrome only solves the
login/profile problem; it does not by itself prove same-tab submission. The
route guard above decides whether automatic execution is allowed.

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

2. **Wait for the intended tab to be ready.** Poll
   `http://127.0.0.1:9222/json` until the target with `url` matching the
   intended ChatGPT project/folder/conversation has loaded past `about:blank`.
   If multiple ChatGPT tabs are open, set `ORACLE_CHATGPT_TARGET_ID` or
   `ORACLE_CHATGPT_URL_MATCH` before toggling.

3. **Run the route guard.** Resolve the skill dir first, then:
   ```
   node "$SKILL_DIR/assets/scripts/check-oracle-tab-local-route.mjs"
   ```
   If this exits non-zero, stop. Report the prompt file and guard output. Do
   not launch a normal Oracle browser submission.

4. **Toggle Deep research on in that resolved submit tab.** Resolve the
   skill dir first — project-local activation puts the helper at
   `./.claude/skills/deep-research-prompt`, global activation at
   `$HOME/.claude/skills/deep-research-prompt`:
   ```
   SKILL_DIR=""
   for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
     [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
   done
   ORACLE_CHATGPT_URL_MATCH="<unique-project-or-conversation-path>" \
     node "$SKILL_DIR/assets/scripts/toggle-deep-research.mjs"
   ```
   If this exits non-zero, **do not silently proceed** — surface the reason to
   the user. The common failure modes are exit 4 (ChatGPT moved the menu item
   label), exit 3 (plus button moved), exit 7 (selector still matches multiple
   ChatGPT tabs), and exit 8 (selector matched no tab).

5. **Run Oracle against the prepared browser without reselecting the model,
   only after the route guard passes.**
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy ignore \
     --timeout 30m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-deep-research-<date>.md)"
   ```
   On Oracle builds like v0.9.0, this step is route-blocked because remote
   Chrome opens a fresh dedicated tab. Do not add `--chatgpt-url` to try to
   force reuse; that is the behavior that creates the extra non-Deep-Research
   submit tab.
   `--browser-model-strategy ignore` avoids an extra model-picker click that can
   move focus or fail when ChatGPT's selector DOM changes. The prepared tab's
   current model/tool state is the source of truth.

6. **Verify the submitted tab.** Immediately inspect the browser or reattach
   with `oracle session <slug>`. If Oracle opened or switched to a different
   target than the selected project/conversation, if the submitted
   composer/conversation lacks the Deep Research chip, or if the reply starts
   like a normal answer rather than a research run with external-source
   behavior, treat the run as failed. Do not report "Deep Research started."

7. **Surface the session slug** for reattach, do not re-print the prompt.

## Verification after the run starts

After Oracle submits the prompt, the user can reattach with
`oracle session <slug>`. If the resulting ChatGPT turn does not cite external
sources or uses a generic "I'll answer based on what I know" opener, Deep
research did not actually apply. The most common causes are: Oracle submitted
in a different tab than the toggled tab, the click landed on the wrong item
(exit code 6 catches the DOM case), or ChatGPT silently downgraded because quota
or tool state changed. Treat this as a real failure and tell the user.

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
