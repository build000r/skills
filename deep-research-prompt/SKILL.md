---
name: deep-research-prompt
description: Produce copy-pasteable mega-prompts for external deep research tools (ChatGPT Deep Research, Perplexity Deep Research, Claude Research), Oracle-ready prompt handoffs when the current run should execute GPT-5 Pro / Deep Research directly, and high-detail image-creation prompts for ChatGPT image creation via Oracle. Use when the user asks for "a prompt for another agent to research X", "mega prompt for deep research", "draft a research prompt", "make a prompt to paste into ChatGPT deep research", "prompt for another agent to do all the Y", "image", "image prompt", "make an image prompt", or when another skill needs a bounded external-reality pass before a strategic decision or document update. Not for inline research the current agent can do with WebFetch or WebSearch directly, and not for prompts that ask another agent to write code or edit files.
---

# Deep research prompt

Produce a single standalone deep-research prompt and, by default, **execute it through `oracle` headlessly** when `oracle` is on PATH. The prompt must still survive copy/paste cleanly, because paste mode is the documented fallback — but paste mode is no longer the default.

**Hard rule — never ask the user to copy and paste when `oracle` is on PATH.** If `oracle` is available, run it. Do not hand back a code block with "paste this into ChatGPT" and stop there. The owner of this skill flagged that exact behavior as the thing to stop doing. Paste mode is only correct when (1) `oracle` is genuinely missing from PATH, (2) the user explicitly asked for `paste-only` / a Perplexity / Claude Research target, or (3) the caller skill explicitly asked for paste output.

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

## Do not use for

- Research the current agent can do inline with `WebFetch` or `WebSearch` in a handful of calls. Just do it.
- Short lookups (fewer than ~10 facts). The overhead of a deep research prompt is not worth it.
- Prompts for agents that will write code, edit files, or execute commands. Those belong to the `Agent` tool, not a deep research prompt.
- Interactive back-and-forth with a research agent. Deep research tools are one-shot report generators; multi-turn dialogue is a different contract.

## Three delivery modes

Pick one mode from context and say which one you are producing:

- **Oracle execute mode** (default when `oracle` is on PATH) — the current run writes the prompt to `/tmp/<slug>-deep-research-<date>.md` and invokes `oracle` headlessly. User does not paste anything. This is the new default; see "Oracle execute mode contract" below.
- **Paste mode** (fallback) — used only when `oracle` is not on PATH, the user explicitly asked for `paste-only`, or the target is Perplexity / Claude Research rather than ChatGPT. The user will paste the prompt into the external tool themselves.
- **Image execute mode** (default when `oracle` is on PATH and the user asked for an image) — the prompt is an image-generation spec, not a research task spec. The skill writes it to `/tmp/<slug>-image-<date>.md`, toggles ChatGPT's Create image tool via the CDP helper, then runs Oracle headlessly against the same Chrome. Sibling of Oracle execute mode; see "Image execute mode contract" below. Falls back to Image paste mode only if Oracle is missing or the user asked for paste-only.

### Oracle execute mode contract (default)

This is what the skill does when `oracle` is on PATH and neither `paste-only` nor an explicit Perplexity/Claude Research target was requested:

1. Compose the standalone prompt block (same content rules as paste mode — self-announcing first line, hard constraints, completion criteria).
2. Write it to `/tmp/<slug>-deep-research-<date>.md`.
3. Run a sizing check: `oracle --dry-run summary --file /tmp/<slug>-deep-research-<date>.md`. If it reports oversized input, fix the prompt (usually by tightening scope or dropping attached files) and retry before the real run.
4. Prepare an explicit submit target on a known Chrome DevTools port. The Deep
   Research toggle is **tab/composer-local**, not Chrome-global. "Same Chrome"
   is not enough: Oracle may create or switch to another ChatGPT tab, and that
   new tab will not inherit the Deep Research tool. Use the flow in
   `references/deep-research-tool-toggle.md`:
   - launch or reuse Chrome on `127.0.0.1:9222`
   - when a ChatGPT Project/folder URL exists, open it and pass it to Oracle with
     `--chatgpt-url`
   - make the toggle helper resolve exactly one tab using a dedicated DevTools
     port, `ORACLE_CHATGPT_TARGET_ID`, or `ORACLE_CHATGPT_URL_MATCH`
   - multiple ChatGPT tabs are fine for subagents only when the intended submit
     tab is explicit; if the helper reports ambiguous or missing selectors, stop
     and surface the issue instead of submitting
5. Invoke Oracle headlessly against that same prepared browser:
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --chatgpt-url "$CHATGPT_PROJECT_URL" \
     --browser-model-strategy ignore \
     --timeout 30m \
     --slug <slug> \
     -p "$(cat /tmp/<slug>-deep-research-<date>.md)"
   ```
   Omit `--chatgpt-url` only when no ChatGPT Project/folder URL is configured
   and the submit target is otherwise unambiguous. If using a URL selector, set
   `ORACLE_CHATGPT_URL_MATCH` to a unique substring from the same URL before
   running `assets/scripts/toggle-deep-research.mjs`.
   Add `--file <path>` for any supporting files the prompt references.
6. Immediately verify the submitted conversation is the prepared Deep Research
   tab. If Oracle opened or switched to a different project/conversation than
   the resolved target, submitted in a tab without the Deep Research chip, or
   the response begins like a normal non-research answer, treat the run as
   failed. Do not claim Deep Research ran.
7. Return to the user a short "Oracle session started" line with the slug and the `oracle session <slug>` reattach command. Do **not** also print the prompt block — that is what the user explicitly said not to do.

If any of steps 3–6 fail, report the failure plainly and **do not** silently fall back to paste mode; ask the user whether to retry, patch, or fall back.

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
5. Make sure a Chrome instance is running on the DevTools port (default `127.0.0.1:9222`) using the user's logged-in ChatGPT profile, with a `chatgpt.com` tab open. If a Chrome was launched earlier in the session for Deep research, reuse it — but first ensure the Deep research toggle is **off** (Image and Deep research are mutually exclusive composer tools).
6. Resolve the skill directory once. The skill may be activated globally
   (`~/.claude/skills/deep-research-prompt`) or project-local
   (`./.claude/skills/deep-research-prompt`, when installed via
   `sbp skill activate ... --cwd $PWD`). The toggle helper must be invoked
   from whichever path actually exists:
   ```
   SKILL_DIR=""
   for d in "./.claude/skills/deep-research-prompt" "$HOME/.claude/skills/deep-research-prompt"; do
     [ -f "$d/SKILL.md" ] && { SKILL_DIR="$d"; break; }
   done
   [ -n "$SKILL_DIR" ] || { echo "deep-research-prompt skill not activated" >&2; exit 1; }
   ```
   Then toggle Create image on:
   ```
   node "$SKILL_DIR/assets/scripts/toggle-chatgpt-image.mjs"
   ```
   Non-zero exit means stop and surface the reason — **do not** silently fall back to paste mode. See `references/chatgpt-image-toggle.md` for exit codes and DOM-fragility notes.
7. Invoke Oracle against the same Chrome:
   ```
   oracle \
     --engine browser \
     --remote-chrome 127.0.0.1:9222 \
     --browser-model-strategy ignore \
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
   already on from step 6, so Oracle just submits the spec.

   The Image toggle is **tab-local** (same hazard as the Deep research
   toggle): if Oracle navigates to a brand-new `chatgpt.com` tab to submit,
   the new tab will not inherit the toggle from step 6. Pass
   `--chatgpt-url "$CHATGPT_PROJECT_URL"` so Oracle reuses the toggled tab,
   set `ORACLE_CHATGPT_URL_MATCH` to a unique substring before running the
   toggle helper, or re-toggle on the new submit tab before dispatch. See
   `references/chatgpt-image-toggle.md` for details and recovery.

   **Parallel image runs.** Image generation can run concurrently across
   multiple `chatgpt.com` tabs in the same Chrome. Open one tab per run with
   a unique URL marker (a `?run=<slug>` query string is enough), then for
   each run set `ORACLE_CHATGPT_URL_MATCH=<slug>` before invoking
   `toggle-chatgpt-image.mjs` and pass `--chatgpt-url` matching the same
   URL to Oracle. The helper now refuses to silently pick one of N matching
   tabs (exit `7` when ambiguous, exit `8` when a selector was given but did
   not match), so the routing must be explicit per run. Same env-var
   contract as the deep-research toggle. Full parallel-runs flow lives in
   `references/chatgpt-image-toggle.md`.
8. Surface the session slug for reattach (`oracle session <slug>`), and tell the user where the generated image file will be saved. Do **not** print the image-spec block back into chat.

If any of steps 4–7 fail, report the failure plainly and ask the user whether to retry, patch the toggle helper, or fall back to Image paste mode.

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
- The Deep Research toggle was applied to the exact tab/composer Oracle submitted in; if multiple `chatgpt.com` tabs existed, the run stopped before submission or the ambiguity was explicitly resolved
- The real Oracle invocation includes `--engine browser` with `--remote-chrome`, a concrete `--browser-model-strategy`, a slug, and the prompt file
- The Deep Research tool toggle helper was invoked after the submit tab existed and before Oracle submitted (or an explicit reason why it was skipped is logged)
- The chat reply contains no prompt code block, no "paste this" instruction, and no "copy the block below" phrasing
- Oracle session slug is surfaced for reattach

**Image execute mode checks:**

- Spec file was written to disk under `/tmp/` with an unambiguous slug
- `oracle --dry-run summary` was run on the spec file
- A Chrome on the DevTools port has a `chatgpt.com` tab open
- `assets/scripts/toggle-chatgpt-image.mjs` was invoked and the exit status is logged in the chat reply (e.g. "Create image: turned on" or the failure reason)
- The real Oracle invocation includes `--remote-chrome`, `--browser-model-strategy ignore` (not `current` — Image mode hides the model selector), the slug, and the spec file
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
   `oracle` is on PATH), `Paste-mode fallback`, or `Image paste-mode fallback`.
1a. If `oracle` was on PATH and neither `paste-only` nor a Perplexity / Claude
    Research target was requested, the corresponding execute mode was used
    and **no** "copy this / paste this" instruction appeared in the response.
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
5. If Image execute mode was used, the chat reply additionally names which
   ChatGPT composer tool was toggled (Create image), the helper exit status,
   and the image verification reminder. If the toggle helper failed, the
   response says so plainly and does not silently fall back.
6. If the caller expected execution rather than handoff, state plainly whether
   Oracle was actually run or only prepared.

## Related

- [[skill-issue]]
