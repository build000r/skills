---
name: deep-research-prompt
description: Ask GPT-5 Pro a question directly, produce copy-pasteable mega-prompts for external deep research tools (ChatGPT Deep Research, Perplexity, Claude Research), execute Deep Research runs, and write high-detail image-creation prompts for ChatGPT image creation. Use when the user says "ask GPT-5 Pro", "ask the oracle", "what would Pro say", "a prompt for another agent to research X", "mega prompt for deep research", "draft a research prompt", "prompt for another agent to do all the Y", "image prompt", "make an image prompt", "use this image/style/contact sheet as visual inspiration", "get this off the page", "better vibes", "image to the left/right", or when another skill needs a bounded external-reality pass before a strategic decision or document update. Not for inline research the current agent can do with WebFetch/WebSearch, and not for prompts asking another agent to write code or edit files.
depends_on:
  - skill-issue   # optional: scripts/resolve_overlay_config.py supplies per-project ORACLE_* env for the DOM fallback lane only
---

# Deep research prompt

Two jobs, one skill:

1. **Ask the oracle a question.** One command in, the answer out. GPT-5 Pro
   answers over HTTPS in roughly 10–30 s. This is the default for anything
   shaped like a question. See "Ask mode" below — it is the whole procedure.
2. **Compose a deep-research mega-prompt** for a long-running Deep Research or
   image run, then either execute it or hand it over for pasting. The prompt
   craft rules start at "The core contract".

**Hard rule — asking is one command, not a project.** When the user wants the
oracle's opinion, run `oracle-ask`. Do not resolve `SKILL_DIR` in a loop, do not
`eval` an overlay config, do not launch a browser, do not render an Oracle
bundle, and do not drive the DOM composer. Those steps exist only in the
fallback lane, for the things Ask mode genuinely cannot do (file attachments,
Deep Research review cards, image generation).

**Hard rule — never ask the user to copy and paste** when Ask mode or the
fallback lane is available. Paste mode is only correct when (1) the user
explicitly asked for `paste-only`, (2) the target is Perplexity or Claude
Research rather than ChatGPT, (3) the caller skill explicitly asked for paste
output, or (4) every execution lane is blocked and the user chose manual
fallback.

**Hard rule — fail loudly, never silently.** A blocked lane is a blocked run,
not a completed one. Report the exact blocker and the file path. Never downgrade
to a weaker model, a different tool, or paste mode without saying so.

## First Progress Marker (Required)

Start the first progress update with the exact prefix `Using deep-research-prompt`.

Preferred format: `Using deep-research-prompt to <goal>. First I will <next concrete step>.`

Do not change or omit that prefix.

---

## Ask mode (default for questions)

```bash
ASK=$(ls -d ./.claude/skills/deep-research-prompt/assets/scripts/oracle-ask.mjs \
             "$HOME"/.claude/skills/deep-research-prompt/assets/scripts/oracle-ask.mjs 2>/dev/null | head -1)
node "${ASK:?deep-research-prompt is not activated here}" \
  "Why would a p99 go bimodal while p50 stays flat?"
```

That is the complete procedure. The answer is on stdout; progress lines go to
stderr; a non-zero exit means nothing was submitted and the reason is printed
with the command that fixes it.

Optional one-time convenience — after this the command is literally one word:

```bash
node "$ASK" --install     # writes a shim to ~/.local/bin/oracle-ask
oracle-ask "your question"
```

### Projects and cheap iteration

Answers land in root chat unless a Project is named. Set
`ORACLE_CHATGPT_PROJECT_URL` (the overlay already supplies it) or pass
`--project`, and the turn is filed into that Project so the work is trackable:

```bash
oracle-ask --project https://chatgpt.com/g/g-p-<id>/project "your question"
```

`--project` accepts a full Project URL or a bare `g-p-…` id. Verify placement
against the Project itself, not the progress line:
`GET /backend-api/gizmos/<g-p-id>/conversations`.

**While testing, do not burn Pro usage.** `--model instant` answers the same
question on `gpt-5-5-instant` — measured 7s versus 27s for Pro, and it does not
consume the Pro allowance. Use `pro` only when the answer quality is the point.

### What you get by default

| | |
|---|---|
| Model | GPT-5 Pro (`gpt-5-6-pro`) |
| Deadline | 900 s |
| Transport | HTTPS to the ChatGPT backend; zero CSS selectors |
| Browser role | credential + one anti-abuse token per question, over loopback CDP |
| Output | answer text on stdout |

### The flags that actually matter

```bash
node "$ASK" --prompt-file /tmp/question.md --out /tmp/answer.md   # long prompt, saved answer
node "$ASK" --model thinking "quick sanity check"                  # pro | thinking | instant | research | raw slug
node "$ASK" --timeout 3600 "<a genuinely hard question>"           # longer deadline
node "$ASK" --json "..."                                           # result object incl. conversationId
node "$ASK" --doctor                                               # readiness only; submits nothing
```

`--models` lists what the account can select. Anything unrecognised passed to
`--model` is forwarded verbatim, so a new slug never needs a code change.

### When Ask mode is not ready

`--doctor` and every failure path print the remediation. The usual one is that
no signed-in Chrome is exposing loopback CDP, and the fix is the launcher —
which needs the enrolled subprofile and target, not its defaults:

```bash
ORACLE_PROFILE_DIRECTORY="<subprofile holding the signed-in session>" \
ORACLE_CHATGPT_PROJECT_URL="<project or conversation URL>" \
  assets/scripts/launch-chatgpt-cdp.sh
```

The launcher defaults to profile `Default` and root `chatgpt.com`; the enrolled
session usually lives in a subprofile such as `Profile 1`. Set both variables.

Exit codes: `0` answered · `2` usage · `3` lane not ready · `4` upstream refused
(auth or anti-abuse) · `5` deadline · `1` other.

### What Ask mode cannot do

**File attachments** (the prompt is text only — inline what matters),
**Deep Research runs** with the review card and 20–90 minute dossier (the
`research` slug is selectable but has never been exercised on this lane), and
**image generation**. For all three, use the DOM fallback lane below — it is
plan B, not a downgrade.

Background: `references/chatgpt-backend-api.md` (reconstructed contract, what is
observed vs inferred vs unknown) and `references/oracle-credential-portability.md`
(running the credential off this Mac, via `assets/scripts/oracle-credential.mjs`).

---

## DOM fallback lane (plan B)

Use only when Ask mode is blocked or the run needs attachments, a Deep Research
review card, or a long-running dossier. This lane drives the real ChatGPT UI
over CDP and is correspondingly fragile — it carries ~35 CSS selectors that a
redesign can break. **The full canonical sequence, with every UI gotcha, lives
in `references/deep-research-tool-toggle.md` → "Verified composer flow". Follow
it there rather than reconstructing it here.** The shape:

1. Write the prompt to `/tmp/<slug>-deep-research-<date>.md` and size it:
   `oracle --dry-run summary --file <promptfile>`.
2. Optionally source per-project ChatGPT config (soft dependency on
   `skill-issue`; no-op when absent):
   `eval "$(python3 <skill-issue>/scripts/resolve_overlay_config.py --section oracle --format env)"`.
3. Launch the dedicated CDP Chrome (`assets/scripts/launch-chatgpt-cdp.sh`) and
   confirm the tab list shows the signed-in account.
4. Render the bundle — **render only, Oracle never submits a Deep Research run**:
   `oracle --render --render-plain --engine browser --model "${ORACLE_DEFAULT_MODEL:-gpt-5-pro}" ...`
5. Drive `assets/scripts/chatgpt-composer.mjs`: `clear` → `select-pro` →
   `toggle-deep-research.mjs` → `verify-ready` → `paste-file` → `verify-ready`
   again → `send` → `start-research` → `verify-started` → `screenshot`.
6. Capture the dossier with `assets/scripts/await-deep-research.mjs`.

Non-negotiables for this lane:

- `verify-ready` is a **hard gate**. Pro and Deep research must be proven in the
  DOM before `send`, and again after paste. Never send unverified.
- A user-turn-only conversation is submission evidence, not generation evidence.
  `verify-started` (or the watcher) must see researching UI, a stop button, or an
  assistant turn before calling the run launched.
- **Oracle renders; CDP submits.** Observed on Oracle v0.9.0: its model-selector
  click fails against the current UI, `--browser-model-strategy ignore` submits
  on Instant with Deep research off (a garbage run that looks launched), and
  `--pre-submit-hook` fires only after the send click.
- **Fail-closed on tab-local tools.** Deep research and Create image are
  composer/tab-local. If `assets/scripts/check-oracle-tab-local-route.mjs` says
  the installed Oracle opens a fresh remote tab, stop before toggling or
  submitting. Do not "try anyway"; `--chatgpt-url` is not a pin.

### Stable oracle-subagent controller

For long-running Deep Research work that must survive the caller, use the
bundled controller instead of hand-driving the sequence. It owns private run
artifacts, exact-target preflight, dedupe/reattach, a hidden worker, truthful
status, bounded waiting, and verified result publication:

```bash
ORACLE_SUBAGENT="$SKILL_DIR/assets/scripts/oracle-subagent.mjs"

node "$ORACLE_SUBAGENT" run --slug <slug> \
  --prompt-file /tmp/<slug>-deep-research-<date>.md \
  --file <context-file> --mode deep-research \
  --wait started --timeout-seconds 7200 --json

node "$ORACLE_SUBAGENT" status --run-id <run-id> --json
node "$ORACLE_SUBAGENT" wait --run-id <run-id> --for completed --result /tmp/<slug>-result.md --json
node "$ORACLE_SUBAGENT" run --reattach <run-id> --wait completed --json
```

Prompt text is never accepted on argv. `--wait none` detaches, `started`
requires generation evidence, `completed` blocks for terminal truth.
`--timeout-seconds` bounds the caller's wait, not the detached run: the worker
has its own 12-hour deadline inside a 24-hour queue lease.

`run --reattach` may return `resume_directive`. `execute` and `restart_worker`
start exactly one worker; `wait` means the run is still queued; `monitor` and
`reconcile_submission` deliberately never resend at or after the browser send
boundary. Keep waiting on the same run ID or report the bounded timeout — never
turn a directive into a fresh submission.

The controller honors the normalized `ORACLE_CHATGPT_PROJECT_URL` from the
active overlay, binds that exact root or Project path into its private browser
pool, and re-proves access before every worker start. Changing the configured
target invalidates the old pool instead of silently navigating elsewhere.

### Paste-mode fallback contract

Reached when the user said `paste-only`, the target is Perplexity / Claude
Research, or every execution lane is blocked and the user chose manual fallback.
Produce the standalone prompt block plus:

- a prompt file path like `/tmp/<slug>-deep-research-<date>.md`
- a sizing command: `oracle --dry-run summary --file <promptfile>`
- a verification reminder: confirm the Deep Research toggle is on, capture the
  session ID, and verify the chat actually ran on a `gpt-5-pro`-ish model slug

## Image execute mode

Sibling lane for image generation. Ask mode cannot do this; the composer's
Create image tool is tab-local, so this stays on the guarded Oracle+CDP path.

**Run storage.** When the caller supplies a per-run directory (for example
ui-fresh-eyes routing `oracle-image` under `<repo>/.fresh-eyes/runs/<slug>/`),
write the spec, copied source images, and Oracle log there instead of `/tmp` so
the run is project-traceable and parallel runs do not collide. Honor
`DEEP_RESEARCH_RUN_ROOT` when set — `<run-root>/spec.md`, `<run-root>/source/`,
`<run-root>/oracle.log`, `<run-root>/result/`. Fall back to
`/tmp/<slug>-image-<date>.md` and `/tmp/<slug>-source/` only when no run root is
supplied.

**Shared runner.** If a caller has already staged a run directory with
`spec.md`, `source/`, and `result/`, do not retype the Oracle command:

```bash
assets/scripts/run-image-execute.sh --run-dir <run-root>
```

The helper owns sizing, the same-tab route guard, the Create image pre-submit
hook, source-file attachment, command logging, the Oracle log path, and
route-blocked failure reporting. Callers such as `ui-fresh-eyes` and
`visual-inspiration-demo` own only their spec and source material.

When no run directory was staged, follow
`references/chatgpt-image-toggle.md` → "How the skill wires this into an Oracle
run" (and "Parallel image runs" for concurrent tabs). The shape: compose the
spec from `assets/templates/image-creation.md` → write it to
`/tmp/<slug>-image-<date>.md` and size it → run the route guard **before**
opening Chrome or toggling → ensure a `chatgpt.com` tab on the DevTools port →
toggle Create image (via `--pre-submit-hook` when Oracle supports it, otherwise
directly on the exact target tab) → invoke Oracle with `--remote-chrome`.

Non-negotiables for this lane:

- **Attach the pixels.** URLs, Midjourney `/styles/...` links and `--sref`
  values are metadata only. Copy the real images under `/tmp/<slug>-source/`,
  list them under `# Source visual assets`, and pass each with `--file`. If they
  are unavailable, stop and ask for an upload rather than launching with links.
- **Guard first.** Non-zero exit from `check-oracle-tab-local-route.mjs` is a
  route-blocked attempt: report the spec path and guard output, submit nothing.
- Deep research must be **off** if that Chrome was used for it — Create image
  and Deep research are mutually exclusive composer tools.
- Use `--browser-model-strategy ignore`, **not** `current`: Image mode hides the
  model selector, so `current` exits with `Unable to locate the ChatGPT model
  selector button` before anything is submitted.
- Surface the session slug for reattach (`oracle session <slug>`) and where the
  image will be saved. Do **not** print the spec block into chat.

**Image paste-mode fallback** (Oracle missing, `paste-only`, or the guard
blocked and the user opted to fall back): the spec block, the spec file path,
the sizing command, a manual "switch the composer to Create image and paste"
instruction, and a reminder to confirm an actual image came back — if the run
produced text only, the model fell out of image mode.

## The core contract

A deep research prompt is a **one-shot research task spec that survives being
pasted alongside unrelated noise**. It must:

1. **Stand alone** — no reliance on surrounding context or prior conversation.
2. **Self-announce** — first line states the role and task unambiguously.
3. **Live in one fenced code block** — so it can be copied cleanly.
4. **Carry a structured output format** — not "write an essay about X" but
   "fill this schema, one row per entity."
5. **Explicitly constrain sources and uncertainty** — authoritative sources, no
   fabrication, honest flags.
6. **Tell the agent what to report back** — concrete completion criteria.

Read `references/hygiene-rules.md` for the failure-mode history behind these.

Ask mode is exempt from the fenced-block rule — its prompt goes over the wire,
not through a clipboard. The content rules still apply.

## Do not use this skill for

Research the current agent can do inline with `WebFetch` / `WebSearch` in a
handful of calls — just do it. Short lookups when a full research prompt is the
ask (Ask mode is fine for a single hard question; that is what it is for).
Prompts for agents that will write code, edit files, or run commands — those
belong to the `Agent` tool. Interactive back-and-forth — deep research tools are
one-shot report generators.

## Workflow (for composed research prompts)

### 1. Clarify the research task shape

Pin down the **subject**, the **entity set** (how many discrete things — 50
states, 8 competitors, 30 papers), the **output consumer** (the user directly or
a downstream writing step), the **depth per entity**, and the **authority level**
(academic, legal, commercial, journalistic).

Ask at most one clarifying question — only the thing you cannot infer. Produce a
first draft fast and let the user correct it in one round.

### 2. Pick an output structure

Map the task to a structure from `references/output-structures.md`:
N-entity structured report · cross-jurisdiction legal · academic literature map
· competitive intelligence sweep · decision-support matrix · image creation ·
custom.

Skeletons: `assets/templates/n-entity-structured.md` (start here for almost any
N-entity task), `assets/templates/cross-jurisdiction-legal.md`,
`assets/templates/image-creation.md`.

### 3. Compose the prompt

**Research-style prompts** — required sections in order:

1. **Role + mission** (1 sentence) — "You are a [role]. Your sole task is to
   [action] for [subject]. You do NOT [non-goal]."
2. **Context** (2–4 short paragraphs) — why this research exists, who consumes
   it, what calibration looks like. Reference an existing anchor example and
   tell the agent to match its mechanical specificity without copying its prose.
3. **The research question** (numbered list) — the concrete fields per entity.
4. **Output format** — exact markdown structure, shown with inline example
   headings and bullet labels. Prose description alone produces prose drift.
5. **Hard constraints** — the anti-hallucination stanza plus task-specific ones.
6. **No clarifying-question directive** — "Do not ask clarifying questions
   before starting. Begin the research and report immediately unless a hard
   constraint makes the task impossible; if a constraint is impossible, state
   the blocker and proceed with the closest valid scoped report."
7. **What to report back when done** — 3–5 concrete completion criteria.

**Image creation prompts** — same contract, layered sections instead (subject,
composition, lighting, style, palette, mood, texture, aspect ratio, text-in-image,
source assets, drift constraints, verification caption). Start from
`assets/templates/image-creation.md`, which lays all of them out.

### 4. Add the hard-constraint stanza

Every composed research prompt carries one, tuned to the task: topic scope,
authoritative sources with disallowed aggregators named, traceable claims, no
invented citations, no finished prose, no clarifying questions, no padding,
honest complexity, honest uncertainty. Image prompts use the drift-mode variant
instead. **Both stanzas, verbatim and ready to adapt, are in
`references/hygiene-rules.md` → "The hard-constraint stanza".**

### 5. Wrap for the chosen delivery mode

**Ask mode** — no wrapper. The prompt goes to `oracle-ask` and the answer comes
back. Do not print the prompt block into chat.

**Execute modes (Deep Research / Image)** — write the prompt to disk and run the
lane. In chat print only: the mode line, the slug, the prompt file path, the
lane's evidence, and the reattach command. No copy instruction, no pasted block.

**Paste mode / Perplexity / Claude Research** — above the fenced block write a
short framing paragraph and an explicit copy instruction:

> Copy only the contents of the code block below. Paste into [tool]. Do not
> include any of your terminal session or surrounding Claude Code output — let
> the prompt stand alone.

Below the block write: where to save the output, a time-budget heads-up
(structured N-entity research takes 20–90 minutes — warn so the user does not
panic at 15), a reusability note if the prompt is parameterized, and the one
most-likely failure mode for this task ("confidence inflation if every row is
high-confidence", "aggregator citations if source discipline slips", "prose
drift if the agent ignores the schema"). Never put shell commands inside the
prompt block — they are operator instructions, not research instructions.

**Long-running supervision.** Deep Research can sit silently for a long time
after a valid submission. Treat silence as normal unless there is concrete error
evidence. If the result is not the immediate blocker, hand the waiting to a
monitor subagent or `assets/scripts/await-deep-research.mjs` and continue. Do
not poll before ~30 minutes, then poll ~every 15. Do not diagnose a stall before
~2 hours just because the terminal is quiet.

## Output shape for the current agent

**Ask mode (default for questions):**
1. One line: `Asked GPT-5 Pro (<Ns>).`
2. The answer, or the relevant part of it.
3. If the lane was not ready: the exact blocker, and that nothing was submitted.

**Execute modes:**
1. One line: `Mode: <Oracle|Image> execute. Slug: <slug>. Prompt file: <path>.`
2. The lane's evidence — `verify-ready` / `verify-started` and the screenshot
   path for Deep Research; the Create image toggle status for Image mode.
3. The submitted conversation URL; the watcher output path when started.
4. One-sentence red flag / verification reminder.

Do not print the prompt text, a fenced block, or a copy instruction.

**Route-blocked execute attempt:** one line naming the mode, slug, prompt/spec
file, guard command and result, and that **no** submission was made. If the user
expected execution, include the one clearly labeled route-independent fallback
or control probe that was attempted, and whether it produced the artifact. Offer
explicit next choices only. Never imply a run exists.

**Paste mode:** framing lines → copy instruction → the fenced block → post-block
notes (save path, time budget, reusability, red flag).

## Validation before handoff

**Ask mode:**
- The question actually went through `assets/scripts/oracle-ask.mjs`; no browser
  launch, overlay `eval`, or composer choreography was performed for it
- The answer text is reported, not paraphrased into a claim the model did not make
- A non-zero exit was reported as a blocked run with its remediation, never as
  an answer and never as a silent fallback to a different model or lane

**Execute modes:**
- Prompt/spec file written to disk with an unambiguous slug, and sized with
  `oracle --dry-run summary`
- For Deep Research: the CDP Chrome came from `launch-chatgpt-cdp.sh` (or a
  verified endpoint) with the signed-in account confirmed; the bundle came from
  `oracle --render` and Oracle itself made no submission; `verify-ready` passed
  after selection **and** after paste; `start-research` was handled and
  `verify-started` saw generation evidence
- For Image: `check-oracle-tab-local-route.mjs` ran before opening Chrome or
  toggling; the toggle helper's exit status is stated in the reply; the Oracle
  command included `--remote-chrome` and `--browser-model-strategy ignore`;
  source images were attached with `--file` rather than cited as links
- If the dossier is the deliverable, completion capture is delegated to
  `await-deep-research.mjs` with an output path or explicitly left as a blocker
- The reply contains no prompt block and no "paste this" instruction

**Paste mode:** all four hygiene rules hold (self-announcing first line, one
self-contained fenced block, no terminal chrome inside it, copy instruction
above it); the output format is shown as a concrete example structure rather
than described; the hard-constraint stanza and completion criteria are present;
and the post-block notes name the one most-likely failure mode.

If any item fails, fix before sending. `references/anti-patterns.md` has the fixes.

## Bundled files

**Ask mode**
- `assets/scripts/oracle-ask.mjs` — **the entrypoint.** Prompt in, answer out.
- `assets/scripts/oracle-http-client.mjs` — HTTPS transport it delegates to;
  zero CSS selectors, model selection as a JSON field
- `assets/scripts/oracle-credential.mjs` — portable credential lane
  (`acquire` / `refresh` / `doctor` / `print-access-token` / `export` /
  `import`); browserless refresh, so d3 and d3c can run this without a Mac
- `references/chatgpt-backend-api.md` — reconstructed backend contract, with
  every claim labeled observed / inferred / replayed / implemented / blocked
- `references/oracle-credential-portability.md` — how the credential travels

**Fallback lane**
- `references/deep-research-tool-toggle.md` — **the canonical verified composer
  flow** plus UI gotchas and project oracle config
- `references/chatgpt-image-toggle.md` — the Create image sibling
- `assets/scripts/oracle-subagent.mjs` — durable controller for detached Deep
  Research runs (queue, idempotency, state, resume)
- `assets/scripts/launch-chatgpt-cdp.sh` — dedicated CDP Chrome on a clone of
  the signed-in profile · `chatgpt-composer.mjs` — DOM-verified composer control
  · `check-oracle-tab-local-route.mjs` — route guard for tab-local tools
- `assets/scripts/toggle-deep-research.mjs` · `toggle-chatgpt-image.mjs` ·
  `await-deep-research.mjs` (dossier watcher) · `run-image-execute.sh` (shared
  runner for staged image runs)

**Prompt craft**
- `references/hygiene-rules.md`, `references/output-structures.md`,
  `references/anti-patterns.md`
- `assets/templates/n-entity-structured.md`,
  `assets/templates/cross-jurisdiction-legal.md`,
  `assets/templates/image-creation.md`

## Verification / Closeout Contract

For skill-contract edits, rerun:

```bash
python3 skill-issue/scripts/quick_validate.py deep-research-prompt
node --test tests/*.test.mjs   # from the parent skills directory
```

Before returning, confirm:

1. Delivery mode is explicit: `Ask mode`, `Oracle execute mode`,
   `Image execute mode`, `Route-blocked execute attempt`, or `Paste-mode
   fallback`.
2. If the user asked a question, Ask mode was used — not the fallback lane, and
   not a paste handoff.
3. For paste shapes only: single fenced block, self-announcing first line,
   output schema, hard constraints, completion criteria, copy instruction above
   the block, no session chrome inside it. For execute shapes the prompt was
   written to disk and **not** printed back.
4. If an execute lane was used, the reply names the prompt file, the slug, the
   lane's evidence, and the conversation URL — and contains no prompt block.
5. If any lane blocked, the reply says no submission was made and names the
   exact blocker instead of implying a run exists.
6. If the caller expected execution rather than handoff, state plainly whether
   the run actually happened or was only prepared.

## Related

- [[skill-issue]]
