---
name: deep-research-prompt
description: Produce copy-pasteable mega-prompts for external deep research tools (ChatGPT Deep Research, Perplexity Deep Research, Claude Research), Oracle-ready prompt handoffs when the current run should execute GPT-5 Pro / Deep Research directly, and high-detail image-creation prompts for ChatGPT image creation via Oracle. Use when the user asks for "a prompt for another agent to research X", "mega prompt for deep research", "draft a research prompt", "make a prompt to paste into ChatGPT deep research", "prompt for another agent to do all the Y", "image prompt", "make an image prompt", "use this image/style/contact sheet as visual inspiration", "describe these references for an image generator", "get this off the page", "better vibes", "image to the left/right", or when another skill needs a bounded external-reality pass before a strategic decision or document update. Not for inline research the current agent can do with WebFetch/WebSearch, and not for prompts asking another agent to write code or edit files.
---

# Deep research prompt

Produce a single standalone deep-research prompt and, by default, **execute it through `oracle` headlessly** when `oracle` is on PATH and the installed Oracle can prove same-tab routing for ChatGPT tab-local tools. The prompt must still survive copy/paste cleanly, because paste mode is the documented fallback — but paste mode is no longer the default.

**Hard rule — never ask the user to copy and paste when `oracle` is on PATH and the route guard passes.** If `oracle` is available and `assets/scripts/check-oracle-tab-local-route.mjs` reports same-tab routing support, run it. Do not hand back a code block with "paste this into ChatGPT" and stop there. The owner of this skill flagged that exact behavior as the thing to stop doing. Paste mode is only correct when (1) `oracle` is genuinely missing from PATH, (2) the user explicitly asked for `paste-only` / a Perplexity / Claude Research target, (3) the caller skill explicitly asked for paste output, or (4) the route guard blocks automatic execution because Oracle would submit in a different ChatGPT tab than the one holding the Deep Research/Create image tool state.

**Fail-closed rule for tab-local ChatGPT tools.** Deep Research and Create image are composer/tab-local. If the route guard says the installed Oracle opens a fresh remote ChatGPT tab, stop before toggling or submitting. Report the prompt/spec file path and the exact blocker. Do not "try anyway", do not rely on `--chatgpt-url` as a pin, and do not silently downgrade to a normal non-Deep-Research Oracle turn.

**Execution-effort rule.** A route-blocked result is a blocked ChatGPT tab-local submission, not a completed launch. When the user asked to "launch", "run", "generate", or otherwise expected execution, do not stop at prompt/spec preparation if another route-independent execution lane exists. After the guarded ChatGPT path blocks, make one clearly labeled fallback attempt or control probe that cannot accidentally submit to the wrong ChatGPT tab, such as an available first-party image tool, Oracle/Gemini image generation, or a repo-local render/export path. Label it as a fallback, attach/source the same assets when the lane supports files, and report the exact success or failure evidence. Do not call the original ChatGPT Image/Deep Research request "launched" unless that exact tool actually received the job.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using deep-research-prompt`.

Preferred format: `Using deep-research-prompt to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

## When to use this

Invoked when the user wants a structured research task delegated to an external deep research tool. Strong trigger phrases:

- "make a prompt for another agent to research ..."
- "mega prompt for deep research"
- "prompt for another agent to go do all the X"
- "draft a research prompt I can paste into ChatGPT Deep Research / Perplexity / Claude Research"
- "I want to send this to a deep research tool"
- "/deep-research-prompt"
- "image" / "image prompt" / "make an image prompt" / "image creator prompt" — selects Image execute mode below
- "use this image/style/contact sheet as visual inspiration"
- "describe these references for an image generator"
- "get this off the page", "better vibes", "put the image to the left/right" when the request is really asking for an image-generation/spec handoff

## Do not use for

- Research the current agent can do inline with `WebFetch` or `WebSearch` in a handful of calls. Just do it.
- Short lookups (fewer than ~10 facts). The overhead of a deep research prompt is not worth it.
- Prompts for agents that will write code, edit files, or execute commands. Those belong to the `Agent` tool, not a deep research prompt.
- Interactive back-and-forth with a research agent. Deep research tools are one-shot report generators; multi-turn dialogue is a different contract.

## Three delivery modes

Pick one mode from context and say which one you are producing:

- **Oracle execute mode** (default when `oracle` is on PATH and the route guard passes) — the current run writes the prompt to `/tmp/<slug>-deep-research-<date>.md` and invokes `oracle` headlessly. User does not paste anything. This is the new default; see "Oracle execute mode contract" below.
- **Route-blocked execute attempt** (automatic safety stop when `oracle` is on PATH but cannot prove same-tab routing) — the current run writes and sizes the prompt/spec, runs the guard, and stops before opening Chrome or submitting to the unsafe tab-local tool. User gets the file path and blocker, not a fake Oracle session. If execution was requested, also attempt one clearly labeled route-independent fallback/control probe when available and report that evidence separately.
- **Paste mode** (fallback) — used only when `oracle` is not on PATH, the user explicitly asked for `paste-only`, or the target is Perplexity / Claude Research rather than ChatGPT. The user will paste the prompt into the external tool themselves.
- **Image execute mode** (default when `oracle` is on PATH, the user asked for an image, and the route guard passes) — the prompt is an image-generation spec, not a research task spec. The skill writes it to `/tmp/<slug>-image-<date>.md`, toggles ChatGPT's Create image tool via the CDP helper, then runs Oracle headlessly against the same Chrome. Sibling of Oracle execute mode; see "Image execute mode contract" below. Falls back to Image paste mode only if Oracle is missing, the user asked for paste-only, or the route guard blocks and the user explicitly chooses manual fallback.

### Oracle execute mode contract (default)

This is what the skill does when `oracle` is on PATH and neither `paste-only` nor an explicit Perplexity/Claude Research target was requested:

1. Compose the standalone prompt block (same content rules as paste mode — self-announcing first line, hard constraints, completion criteria).
2. Write it to `/tmp/<slug>-deep-research-<date>.md`.
3. Run a sizing check: `oracle --dry-run summary --file /tmp/<slug>-deep-research-<date>.md`. If it reports oversized input, fix the prompt (usually by tightening scope or dropping attached files) and retry before the real run.
4. Resolve the skill directory and run the route guard:
   ```
   SKILL_DIR=""
   for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
     [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
   done
   [ -n "$SKILL_DIR" ] || { echo "deep-research-prompt skill not activated" >&2; exit 1; }
   node "$SKILL_DIR/assets/scripts/check-oracle-tab-local-route.mjs"
   ```
   If it exits non-zero, **do not launch Chrome, toggle Deep Research, or run
   Oracle**. Return a route-blocked execute attempt: mode, slug, prompt file,
   guard output, and the choices "manual Deep Research paste" or "normal
   non-Deep-Research Oracle run if the user explicitly accepts the downgrade."
5. Prepare an explicit submit target on a known Chrome DevTools port. The Deep
   Research toggle is **tab/composer-local**, not Chrome-global. "Same Chrome"
   is not enough: Oracle may create or switch to another ChatGPT tab, and that
   new tab will not inherit the Deep Research tool. Use the flow in
   `references/deep-research-tool-toggle.md`:
   - launch or reuse Chrome on `127.0.0.1:9222`
   - when a ChatGPT Project/folder URL exists, open it only as the target that
     will be toggled; do not treat `--chatgpt-url` as proof of tab reuse
   - make the toggle helper resolve exactly one tab using a dedicated DevTools
     port, `ORACLE_CHATGPT_TARGET_ID`, or `ORACLE_CHATGPT_URL_MATCH`
   - multiple ChatGPT tabs are fine for subagents only when the intended submit
     tab is explicit; if the helper reports ambiguous or missing selectors, stop
     and surface the issue instead of submitting
6. Invoke Oracle headlessly against that same prepared browser only when the
   route guard has passed and the command includes whatever same-tab target
   option or pre-submit hook the guard found. On Oracle v0.9.0, `--chatgpt-url`
   opens a fresh dedicated remote tab; that is unsafe for Deep Research and
   must be treated as route-blocked, not as a pin.
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy ignore \
     --timeout 30m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-deep-research-<date>.md)"
   ```
   If using a URL selector for the toggle helper, set
   `ORACLE_CHATGPT_URL_MATCH` to a unique substring from the same URL before
   running `assets/scripts/toggle-deep-research.mjs`.
   Add `--file <path>` for any supporting files the prompt references.
7. Immediately verify the submitted conversation is the prepared Deep Research
   tab. If Oracle opened or switched to a different project/conversation than
   the resolved target, submitted in a tab without the Deep Research chip, or
   the response begins like a normal non-research answer, treat the run as
   failed. Do not claim Deep Research ran.
8. Return to the user a short "Oracle session started" line with the slug and the `oracle session <slug>` reattach command. Do **not** also print the prompt block — that is what the user explicitly said not to do.

If any of steps 3–7 fail, report the failure plainly and **do not** silently fall back to paste mode; ask the user whether to retry, patch, or fall back.

### Paste-mode fallback contract

Only reached when `oracle` is missing, the user said `paste-only`, or the target is Perplexity / Claude Research. In that case the skill still produces the standalone prompt block, plus:

- a prompt file path like `/tmp/<slug>-deep-research-<date>.md`
- a sizing command: `oracle --dry-run summary --file <promptfile>` (still useful — flags oversized prompts before the user pastes)
- a run command using `oracle --engine browser --browser-manual-login --model gpt-5-pro --browser-timeout 30m -p "$(cat <promptfile>)"` — kept here so the user can copy it if Oracle reappears
- a short verification reminder: confirm the Deep Research toggle is on, capture the Oracle session ID, and verify the resulting chat actually ran on a `gpt-5-pro`-ish model slug

### Image execute mode contract (default when `oracle` is on PATH and the user asked for an image)

Sibling of Oracle execute mode. Same shape, different composer tool, different Oracle timeout.

**Run storage.** When the caller supplies a per-run directory (for example,
ui-fresh-eyes routes its `oracle-image` delivery under
`<repo>/.fresh-eyes/runs/<slug>/`), write the spec, copied source images,
and Oracle log there instead of `/tmp` so the run is project-traceable and
parallel runs do not collide. Honor `DEEP_RESEARCH_RUN_ROOT` when set —
treat it as the parent for `<run-root>/spec.md`, `<run-root>/source/`,
`<run-root>/oracle.log`, and `<run-root>/result/`. Fall back to
`/tmp/<slug>-image-<date>.md` and `/tmp/<slug>-source/` only when no run
root is supplied.

**Shared runner.** If a caller has already staged a run directory with
`spec.md`, `source/`, and `result/`, do not retype the Oracle command in the
caller. Invoke the canonical helper:

```bash
assets/scripts/run-image-execute.sh --run-dir <run-root>
```

The helper owns sizing, same-tab route guard, Create image pre-submit hook,
source-file attachment, command logging, Oracle log path, and route-blocked
failure reporting. Callers such as `ui-fresh-eyes` and
`visual-inspiration-demo` own only their domain-specific prompt/spec and source
material staging.

1. Compose the standalone image-spec block using `assets/templates/image-creation.md` (self-announcing first line, layered fields, image-drift hard constraints, verification-caption requirement).
2. If the image request depends on visual source material, materialize and attach
   the source images. URLs, Midjourney `/styles/...` links, and `--sref` values
   are metadata only; they are not a substitute for pasted/attached source
   pixels. Copy local images or downloaded/cached reference images under
   `/tmp/<slug>-source/`, list them in the spec under `# Source visual assets`,
   and pass each file with `--file`. If the actual source images are not
   available, stop and ask for an upload/export instead of launching with only
   links.
3. Write it to `/tmp/<slug>-image-<date>.md`.
4. Run a sizing check: `oracle --dry-run summary --file /tmp/<slug>-image-<date>.md`. If oversized, tighten the spec and retry.
5. Resolve the skill directory once. The skill may be activated globally
   (`~/.claude/skills/deep-research-prompt`) or project-local
   (`./.claude/skills/deep-research-prompt`, when installed via
   `sbp skill activate ... --cwd $PWD`). The guard and toggle helpers must be invoked
   from whichever path actually exists:
   ```
   SKILL_DIR=""
   for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
     [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
   done
   [ -n "$SKILL_DIR" ] || { echo "deep-research-prompt skill not activated" >&2; exit 1; }
   ```
   Run the route guard before opening Chrome or toggling tools:
   ```
   node "$SKILL_DIR/assets/scripts/check-oracle-tab-local-route.mjs"
   ```
   If it exits non-zero, stop and report a route-blocked Image execute attempt
   with the spec file path and guard output. Do not submit a text-only ChatGPT
   turn by accident.
6. Make sure a Chrome instance is running on the DevTools port (default `127.0.0.1:9222`) using the user's logged-in ChatGPT profile, with a `chatgpt.com` tab open. If a Chrome was launched earlier in the session for Deep research, reuse it — but first ensure the Deep research toggle is **off** (Image and Deep research are mutually exclusive composer tools).
7. Decide how Create image will be toggled based on what made the route guard pass:
   - If Oracle exposes `--pre-submit-hook`, do **not** pre-toggle a different tab. Pass the image toggle helper as the pre-submit hook so Oracle toggles Create image inside the exact tab it opened and will submit from.
   - If Oracle exposes an explicit target-id/reuse-tab option instead, prepare that exact tab first and toggle Create image on that tab:
   ```
   node "$SKILL_DIR/assets/scripts/toggle-chatgpt-image.mjs"
   ```
   Non-zero exit from the helper or hook means stop and surface the reason — **do not** silently fall back to paste mode. See `references/chatgpt-image-toggle.md` for exit codes and DOM-fragility notes.
8. Invoke Oracle against the same Chrome only when the route guard has passed
   and the command includes whatever same-tab target option or pre-submit hook
   the guard found. On Oracle v0.9.0, `--chatgpt-url` opens a fresh dedicated
   remote tab; that is unsafe for Image mode and must be treated as
   route-blocked, not as a pin.
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy ignore \
     --browser-attachments always \
     --pre-submit-hook "node $SKILL_DIR/assets/scripts/toggle-chatgpt-image.mjs" \
     --browser-timeout 15m \
     --slug <slug> \
     --file /tmp/<slug>-source/<reference-image>.<ext> \
     -p "$(cat /tmp/<slug>-image-<date>.md)"
   ```
   Use `--browser-model-strategy ignore`, **not** `current`. Image mode hides
   the ChatGPT model selector, so `current` exits early with
   `Unable to locate the ChatGPT model selector button` before the prompt is
   submitted. The model is fixed to ChatGPT's image-tool model in this
   composer mode anyway, so verifying the selector is moot. Omit `--file`
   only when the request has no visual source material. Image mode is
   already on from step 7, or it is turned on by the pre-submit hook immediately
   before upload/send, so Oracle submits the spec in Image mode.

   The Image toggle is **tab-local** (same hazard as the Deep research
   toggle): if Oracle navigates to a brand-new `chatgpt.com` tab to submit,
   the new tab will not inherit the toggle from step 7. Do not rely on
   `--chatgpt-url` as a same-tab guarantee; the route guard must pass first.
   Set `ORACLE_CHATGPT_URL_MATCH` to a unique substring before running the
   toggle helper only to make the helper choose the right tab. See
   `references/chatgpt-image-toggle.md` for details and recovery.

   **Parallel image runs.** Image generation can run concurrently across
   multiple `chatgpt.com` tabs in the same Chrome. Open one tab per run with
   a unique URL marker (a `?run=<slug>` query string is enough), then for
   each run set `ORACLE_CHATGPT_URL_MATCH=<slug>` before invoking
   `toggle-chatgpt-image.mjs`. Run the route guard before any Oracle
   submission; do not rely on `--chatgpt-url` matching the same URL as a
   same-tab guarantee. The helper now refuses to silently pick one of N matching
   tabs (exit `7` when ambiguous, exit `8` when a selector was given but did
   not match), so the routing must be explicit per run. Same env-var
   contract as the deep-research toggle. Full parallel-runs flow lives in
   `references/chatgpt-image-toggle.md`.
9. Surface the session slug for reattach (`oracle session <slug>`), and tell the user where the generated image file will be saved. Do **not** print the image-spec block back into chat.

If any of steps 4–8 fail, report the failure plainly and ask the user whether to retry, patch the toggle helper, or fall back to Image paste mode.

### Image paste-mode fallback contract

Reached when `oracle` is missing, the user said `paste-only`, or steps 3–6 above failed and the user opted to fall back. The skill produces the standalone image-spec block plus:

- a prompt file path like `/tmp/<slug>-image-<date>.md`
- a sizing command: `oracle --dry-run summary --file <promptfile>` (still useful — flags accidental token bloat in the spec)
- a manual instruction: open ChatGPT in a browser tab, switch the composer to Create image, and paste the block
- a verification reminder: confirm the resulting message actually attached a generated image (not just a written description), save the image file alongside the prompt. If the run produced text only, the model fell out of image mode — re-run after re-toggling.

## The core contract

A deep research prompt is a **one-shot research task spec that survives being pasted alongside unrelated noise**. It must:

1. **Stand alone** — no reliance on surrounding context, prior conversation, or hidden framing.
2. **Self-announce** — first line states the role and task unambiguously.
3. **Live in one fenced code block** — so the user can copy it cleanly.
4. **Carry a structured output format** — not "write an essay about X" but "fill this schema, one row per entity."
5. **Explicitly constrain sources and uncertainty** — authoritative sources, no fabrication, honest flags.
6. **Tell the agent what to report back** — concrete completion criteria.

Read `references/hygiene-rules.md` for the full failure-mode history and the four hard rules that defend against it.

## Workflow

### 1. Clarify the research task shape

Before writing the prompt, pin down:

- **Subject** — what is being researched?
- **Entity set** — how many discrete things get researched? (50 states, 8 competitors, 30 papers, 1 topic)
- **Output consumer** — who uses the research afterwards? The user directly, or a downstream writing step?
- **Depth per entity** — shallow fact-gather or deep synthesis per entity?
- **Authority level** — academic, legal, commercial, journalistic?

Ask at most one clarifying question — only the one thing you cannot infer from the conversation. Do not gather requirements in a long cascade. Produce a first draft fast and let the user correct it in one round.

### 2. Pick an output structure

Map the task to a known structure from `references/output-structures.md`:

- **N-entity structured report** — same fields repeated for each of N entities, plus cross-entity synthesis. Used for states, competitors, products, regulations.
- **Cross-jurisdiction legal research** — specialization of N-entity with statute citations and applicability scopes.
- **Academic literature map** — paper-by-paper with methodology, findings, and citation graph.
- **Competitive intelligence sweep** — company-by-company with pricing, positioning, and go-to-market.
- **Decision-support research** — options-by-criteria matrix with a recommendation.
- **Image creation prompt** — single image, layered specification (composition, lighting, style, palette, atmosphere, constraints). Use when the delivery mode is Image execute mode (or Image paste-mode fallback). Template at `assets/templates/image-creation.md`.
- **Custom** — none of the above fits; construct from first principles using the contract above.

Generic skeleton at `assets/templates/n-entity-structured.md`. Start there for almost any N-entity task. Cross-jurisdiction legal specialization at `assets/templates/cross-jurisdiction-legal.md`. Image generation specialization at `assets/templates/image-creation.md`.

### 3. Compose the prompt

Fill in the chosen skeleton with task-specific content.

**For research-style prompts (Oracle execute mode and paste-mode fallback):** required sections in order:

1. **Role + mission** (1 sentence) — "You are a [role]. Your sole task is to [action] for [subject]. You do NOT [non-goal]."
2. **Context** (2-4 short paragraphs) — why this research exists, who uses the output, what calibration examples look like. If an anchor example already exists in the user's project, reference it and tell the research agent to match its mechanical specificity without copying its prose.
3. **The research question** (numbered list) — the concrete fields the research agent must answer per entity.
4. **Output format** — exact markdown structure the research agent must produce. Show it with inline example headings and bullet labels, not just description. Prose description alone produces prose drift.
5. **Hard constraints** — the anti-hallucination stanza plus task-specific constraints.
6. **What to report back when done** — 3-5 concrete completion criteria.

**For image creation prompts (Image execute mode and Image paste-mode fallback):** the contract is the same — self-announcing first line, single fenced code block, hard constraints, completion criteria — but the section list differs because the deliverable is an image, not a report. Required sections in order:

1. **Role + mission** (1 sentence) — "You are an image generation tool. Produce one image matching the specification below. Generate the image — do not produce a written description in lieu of the image."
2. **Subject** — concrete, visualizable, mid-action description.
3. **Composition and framing** — shot type, camera angle, focal length character, depth of field, subject placement, layered foreground/midground/background contents.
4. **Setting and environment.**
5. **Lighting** — source, direction, quality, color temperature, shadow behavior, mood of light.
6. **Style and medium** — pick one and commit (photographic with named film stock; illustration with named tradition; 3D render aesthetic; painting medium).
7. **Color palette** — dominant, accent, harmony, saturation, contrast.
8. **Mood and atmosphere.**
9. **Detail and texture.**
10. **Aspect ratio and orientation.**
11. **Text in image** — explicit "no text" or exact text in quotes.
12. **Source visual assets** — only when the request uses visual references; list attached/copied source images first and put URLs or Midjourney references under metadata. Do not rely on links alone.
13. **Hard constraints** — drift items to avoid, style boundary, behavior for unspecified regions, anatomy/physics expectations.
14. **What to return** — the image plus a 3-5 sentence verification caption naming any deviation from spec.

The image template at `assets/templates/image-creation.md` already lays this out — start there.

### 4. Add the hard-constraint stanza

Every deep research prompt carries a version of this block, tuned for the subject:

- Topic scope only. Do not drift into adjacent topics. Enumerate the adjacent topics by name.
- Authoritative sources only. Every citation must resolve to an official domain class that you name explicitly. Enumerate disallowed aggregators by name — LexisNexis, Westlaw, Justia, FindLaw, Crunchbase, Wikipedia, law-firm marketing pages, etc., depending on the domain.
- Every factual claim must be traceable to a cited source. If you cannot find a direct citation, say "not found" or "inferred from [X]" — do not make it up.
- Do not invent citations, identifiers, or dates. If you cite something, the URL must actually open to that thing.
- Do not write finished prose for the end audience. The output is facts and citations, not marketing copy or plain-language pages.
- Do not pad. If multiple entities have substantively identical findings, say so in the executive summary and let the reader decide whether all deserve downstream work.
- Be honest about complexity — name the specific framework / transition / methodology nuance the research agent must not flatten.
- Be honest about uncertainty. A row marked "confidence: low, needs human review" is more valuable than a confident-sounding fabrication.

The exact wording changes per task; the shape stays constant.

**For Image execute mode (and its paste-mode fallback)**, the hard-constraint stanza is reshaped — there are no citations, but image generators have their own drift modes. Use a stanza like:

- Do NOT include watermarks, signatures, logos, captions, borders, or stock-photo overlays unless explicitly specified.
- Do NOT default to: enumerate the generic drift modes for this subject by name (e.g., "smiling stock-pose models," "lens flares as a substitute for atmosphere," "extra fingers or malformed hands," "AI-uncanny symmetric faces").
- Stay within the named style. Do not blend with [ADJACENT STYLE THAT WOULD DILUTE IT].
- For unspecified regions, default to clean negative space or natural background extension. Do not invent additional subjects, props, or focal points.
- Anatomy and physics must be plausible unless the named style explicitly permits stylization (and even then, name the stylization).
- Generate the image; do not substitute a written description. If a spec element is genuinely impossible, generate the closest faithful version and name the deviation in the verification caption.

### 5. Wrap the prompt for the chosen delivery mode

**Oracle execute mode (default):**
- Do **not** print the prompt as a fenced code block in chat. Write it to `/tmp/<slug>-deep-research-<date>.md` and run Oracle on it per the "Oracle execute mode contract" above.
- In chat, print only: the one-line mode declaration, the slug, the prompt file path, the Oracle session slug once launched, and the `oracle session <slug>` reattach command. That's it. No copy instruction. No pasted block. The prompt's contents are for Oracle's eyes, not the user's clipboard.

**Paste-mode fallback (and Perplexity / Claude Research targets):**

**Above** the fenced block, write a short framing paragraph and an explicit copy instruction:

> Copy only the contents of the code block below. Paste into [tool]. Do not include any of your terminal session or surrounding Claude Code output — let the prompt stand alone.

**Below** the block, write:

1. **Where to save the output** — a concrete file path if there is a project context.
2. **Time budget heads-up** — structured N-entity research takes 20-90 minutes of tool runtime. Warn the user so they do not panic at 15 minutes in.
3. **Reusability note** — if the prompt is parameterized on one variable (topic, entity class), tell the user how to rerun it for other values.
4. **Red flag to watch for** — name the one most-likely failure mode given the task. Examples: "confidence inflation if every row is high-confidence," "aggregator citations if source discipline slips," "prose drift if the agent ignores the schema."

### 5b. If the fallback path is Oracle-ready (paste mode with Oracle present), add the execution wrapper outside the block

After the normal post-block notes, add:

1. **Prompt file** — where the caller should save the block contents
2. **Sizing command** — `oracle --dry-run summary --file <promptfile>`
3. **Run command** — GPT-5 Pro browser invocation
4. **Verification note** — Deep Research toggle, session ID capture, model-slug check

Do not put shell commands inside the prompt block. They are operator instructions, not research instructions.

### 5c. Image execute mode (default for image requests when Oracle is on PATH)

Do **not** print the spec as a fenced code block in chat. Write it to `/tmp/<slug>-image-<date>.md` and run the Image execute mode contract above (source-image materialization when applicable → sizing check → toggle Create image via the CDP helper → invoke Oracle with `--remote-chrome` and `--file` attachments).

In chat, print only: the one-line mode declaration, the slug, the spec file path, the toggle helper's status (e.g. "Create image: turned on" or the exit-code reason), the Oracle session slug once launched, and the `oracle session <slug>` reattach command. No spec block. No copy instruction.

### 5d. Image paste-mode fallback (only when Oracle is missing or the user opted into paste-only)

Only reached when `oracle` is missing, the user said `paste-only`, or steps 3–6 of the Image execute contract failed and the user opted to fall back. Write the spec block + paste-mode wrapper:

1. **Prompt file** — `/tmp/<slug>-image-<date>.md`
2. **Sizing command** — `oracle --dry-run summary --file <promptfile>` (still useful — flags accidental token bloat in the spec)
3. **Manual instruction** — open ChatGPT in a browser tab, switch the composer to Create image, and paste the block contents
4. **Verification note** — confirm an actual image was attached (not a written description), save the image file alongside the prompt, and re-run after re-toggling if the model fell out of image mode.

Same rule: do not put any shell commands inside the prompt block.

## Output shape for the current agent

Pick the shape based on the mode you chose:

**Oracle execute mode (default):**
1. One line: `Mode: Oracle execute. Slug: <slug>. Prompt file: /tmp/<slug>-deep-research-<date>.md.`
2. Oracle invocation line actually run (not a code block — the one real command).
3. Deep-research tool toggle status: whether the helper at `assets/scripts/toggle-deep-research.mjs` fired cleanly, and what it reported.
4. One line: `Oracle session started — reattach with: oracle session <slug>`.
5. One-sentence red flag / verification reminder (e.g. "Deep research toggle must be on; verify in the reattached session").

Do not print the prompt text. Do not print a fenced block. Do not print a copy instruction.

**Long-running Oracle supervision:** Deep Research can sit silently for a long
time after a valid submission. Treat silence as normal unless there is concrete
error evidence from Oracle, the browser, or the target conversation. If the
research result is not the immediate blocker for the next local action, hand
the waiting to a monitor subagent or background watcher and continue the
caller/orchestration workflow. Do not start polling until roughly 30 minutes
after launch; after that, poll sparingly, about every 15 minutes. Do not
diagnose a stall before roughly 2 hours just because the terminal has no new
output. The monitor owns only status, output-file existence/size, reattach
command, and completion notice unless the caller explicitly gives it a repo
write scope.

**Route-blocked execute attempt (Oracle present but unsafe for tab-local tool):** one line naming mode, slug, prompt/spec file, guard command/result, and that no Oracle browser submission was made because the installed Oracle would open a fresh ChatGPT tab without the tool state. If the user expected execution, include the route-independent fallback/control probe that was actually attempted, the command/session/output path, and whether it produced the requested artifact. Offer only explicit next choices: manual Deep Research/Image paste, upgrade/patch Oracle for target-id or pre-submit-hook support, a supported fallback image/research lane, or normal non-Deep-Research Oracle if the user accepts that downgrade. Do not print the prompt/spec block unless the user explicitly chooses paste-mode fallback.

**Paste-mode fallback / Perplexity / Claude Research:**
1. **One or two lines of framing** — what this prompt does and what tool it is for, and why Oracle was skipped.
2. **The copy instruction** — "Copy only the contents of the code block below..." placed immediately before the block.
3. **The fenced code block** — the prompt itself. Starts with "You are a [role]..."
4. **Post-block notes** — save path, time budget, reusability, red flag.
5. **Oracle wrapper** — include prompt file, sizing command, run command, verification note so the user can switch to Oracle later.

**Image execute mode (default for image requests):** same shape as Oracle execute mode, but mention the Create image toggle helper status explicitly. One line: `Mode: Image execute. Slug: <slug>. Spec file: /tmp/<slug>-image-<date>.md.` Then the toggle status (e.g. "Create image: turned on"), then the Oracle invocation that was actually run, then `Oracle session started — reattach with: oracle session <slug>`, then the one-sentence image verification reminder ("confirm an image — not text — came back; re-run after re-toggling if it didn't"). Do not print the spec block.

**Image paste-mode fallback:** spec block + manual "switch composer to Create image and paste" instruction + verification reminder. Used only when Oracle is missing or the user opted into paste-only.

Do not summarize the prompt content in prose after the block. The user will read the block themselves.

## Validation before handoff

**Oracle execute mode checks:**

- Prompt file was written to disk under `/tmp/` with an unambiguous slug
- `oracle --dry-run summary` was run and the prompt is within the token budget
- `assets/scripts/check-oracle-tab-local-route.mjs` was run before opening Chrome
  or toggling Deep Research; if it failed, no browser submission was made
- When the guard passed, the Deep Research toggle was applied to the exact tab/composer Oracle submitted in; if multiple `chatgpt.com` tabs existed, the run stopped before submission or the ambiguity was explicitly resolved
- When Oracle was invoked, the real command includes `--engine browser` with `--remote-chrome`, a concrete `--browser-model-strategy`, a slug, and the prompt file
- When the guard passed, the Deep Research tool toggle helper was invoked after the submit tab existed and before Oracle submitted (or an explicit reason why it was skipped is logged)
- The chat reply contains no prompt code block, no "paste this" instruction, and no "copy the block below" phrasing
- Oracle session slug is surfaced for reattach
- Long-running waits were either bounded by the current task's critical path or
  delegated to a monitor while the caller continued useful non-overlapping work

**Image execute mode checks:**

- Spec file was written to disk under `/tmp/` with an unambiguous slug
- `oracle --dry-run summary` was run on the spec file
- `assets/scripts/check-oracle-tab-local-route.mjs` was run before opening Chrome
  or toggling Create image; if it failed, no browser submission was made
- If the user asked to launch/generate and the route guard failed, at least one
  route-independent fallback/control probe was attempted when a plausible lane
  existed, and the closeout states whether that attempt produced an artifact
- When the guard passed, a Chrome on the DevTools port has a `chatgpt.com` tab open
- When the guard passed, `assets/scripts/toggle-chatgpt-image.mjs` was invoked either directly against the selected target or through Oracle's `--pre-submit-hook`, and the exit status is logged in the chat reply (e.g. "Create image: turned on" or the failure reason)
- When Oracle was invoked, the real command includes `--remote-chrome`, `--browser-model-strategy ignore` (not `current` — Image mode hides the model selector), the slug, and the spec file
- If visual source material was part of the request, the source images were
  copied/downloaded/cached under `/tmp/<slug>-source/` and attached with
  `--file`; URLs, Midjourney `/styles/...` links, and `--sref` values were
  treated as metadata only
- The chat reply contains no spec code block and no "paste this" instruction
- Oracle session slug is surfaced for reattach
- The verification reminder explicitly tells the user to confirm an image (not text) came back

**Paste-mode / fallback checks (only when Oracle is not on PATH or the user asked for paste-only — applies to both research and image variants):**

- First line inside the block is "You are a ..." or equivalent self-announcing role statement
- Entire prompt is inside a single fenced code block
- Output format is shown with a concrete example structure, not just described
- Hard-constraint stanza is present (research stanza for research modes, image-drift stanza for image mode)
- "What to report back when done" / "What to return" section is present with 3-5 bullets (image mode requires the verification caption that names any deviation from spec)
- No terminal chrome, shell prompts, or Claude Code banner text inside the block
- Copy instruction is outside the block and above it (users scan top-to-bottom)
- Post-block notes name the one most-likely failure mode
- For research paste-mode, an Oracle-ready wrapper is present so the user can switch to Oracle later
- For Image paste-mode fallback, the manual "switch composer to Create image and paste" instruction is present and the verification reminder requires confirming an actual image came back

If any item fails, fix before sending. Read `references/anti-patterns.md` for the fixes.

## Templates and references

- `references/hygiene-rules.md` — the four rules that defend against terminal leak, plus the failure history that justifies them
- `references/output-structures.md` — structured output patterns (N-entity, cross-jurisdiction legal, academic literature, competitive intel, decision-support, image creation, custom) with when-to-use notes
- `references/anti-patterns.md` — failure modes and their fixes
- `references/deep-research-tool-toggle.md` — why the Deep research tool toggle is external to Oracle, and the CDP helper + orchestration flow the skill uses in Oracle execute mode
- `references/chatgpt-image-toggle.md` — sibling of the Deep research toggle doc, for the Create image composer tool
- `assets/templates/n-entity-structured.md` — generic skeleton for "research N things with same structure"
- `assets/templates/cross-jurisdiction-legal.md` — specialization for state-by-state or country-by-country legal research
- `assets/templates/image-creation.md` — high-detail image generation prompt for Image execute mode (and its paste-mode fallback)
- `assets/scripts/run-image-execute.sh` — shared runner for staged Create image / Oracle run directories (`spec.md`, `source/`, `result/`)
- `assets/scripts/check-oracle-tab-local-route.mjs` — guard that blocks automatic Oracle submission when the installed Oracle cannot prove same-tab routing for ChatGPT tab-local tools
- `assets/scripts/toggle-deep-research.mjs` — CDP helper that clicks ChatGPT's composer Deep research toggle on a running Chrome
- `assets/scripts/toggle-chatgpt-image.mjs` — CDP helper that clicks ChatGPT's composer Create image toggle on a running Chrome

## Verification / Closeout Contract

For skill-contract edits, rerun:

```bash
python3 skill-issue/scripts/quick_validate.py deep-research-prompt
```

Before returning, confirm all of the following:

1. Delivery mode is explicit: `Oracle execute mode` (default for research when
   `oracle` is on PATH), `Image execute mode` (default for image when
   `oracle` is on PATH), `Route-blocked execute attempt`, `Paste-mode fallback`,
   or `Image paste-mode fallback`.
1a. If `oracle` was on PATH and neither `paste-only` nor a Perplexity / Claude
    Research target was requested, the corresponding execute mode was used or
    the route guard blocked it before browser submission, and **no** "copy this
    / paste this" instruction appeared in the response unless the user chose
    paste fallback.
2. For paste-mode shapes only: the prompt is a single fenced code block with a
   self-announcing first line, output schema (or layered image spec), hard
   constraints, and completion criteria (or image verification caption
   requirement). For execute-mode shapes, the prompt block was written to disk
   and **not** printed back to the user.
3. The copy instruction sits above the block and no session chrome leaked into
   the prompt (paste shapes only; not applicable to execute shapes).
4. If Oracle execute mode was used, the chat reply names the spec file path,
   the slug, the toggle helper status, and the `oracle session <slug>`
   reattach command — and contains no spec block.
4a. If the route guard blocked execution, the chat reply says no Oracle browser
    submission was made and names the guard result instead of implying a
    session exists.
5. If Image execute mode was used, the chat reply additionally names which
   ChatGPT composer tool was toggled (Create image), whether it was toggled by
   direct helper call or `--pre-submit-hook`, the helper exit status, and the
   image verification reminder. If the toggle helper failed, the response says
   so plainly and does not silently fall back.
5a. If a caller supplied a staged run directory, the run went through
    `assets/scripts/run-image-execute.sh` (or the response names the exact
    blocker), and the run directory contains `oracle.command.sh`,
    `oracle.dry-run.log`, and `oracle.route-guard.log` when the helper reached
    those phases.
6. If the caller expected execution rather than handoff, state plainly whether
   Oracle was actually run or only prepared.

## Related

- [[skill-issue]]
