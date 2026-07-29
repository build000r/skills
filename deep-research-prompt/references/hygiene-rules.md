# Deep research prompt hygiene rules

Four rules that defend against the most common failure mode: the research tool treating leaked session context as part of the task.

## Rule 1 — Self-announcing opening line

The prompt's first line must state the role and task unambiguously. Not a blank line, not a `## Context:` header, not a markdown preamble. Something like:

- "You are a legal-research agent. Your task is to produce one structured report on..."
- "You are a market-intelligence analyst. Your sole assignment is to survey..."
- "You are a literature-review agent. You will produce a bibliographic map of..."

This gives the research tool an explicit anchor even if other text leaks in around the block. Without it, the first sentence of leaked content becomes the de facto role statement.

## Rule 2 — Single fenced code block, fully self-contained

The prompt lives in one fenced code block. No reliance on framing outside the block. The research agent should be able to do its job from the block content alone, as if no other text existed.

This means:

- No "(see context above)" or "(per earlier discussion)" references
- No conversation history assumed
- No placeholders for the user to fill in — if variables exist, write them inline with clear labels or pick concrete values and name them

## Rule 3 — No incidental terminal chrome inside the block

If the user pastes a prompt that contains a zsh prompt character, a recent error message, or a Claude Code permissions banner, the research tool will treat those as part of the task. Do not include inside the block:

- Shell prompt characters (`%`, `$`, `>`)
- Error messages from the current session
- Tool banners, mode labels, or permission hints
- File paths from the current agent environment unless they are load-bearing for the research task
- Any meta-commentary about which tool is running or who is invoking

## Rule 4 — Tell the user what to copy, outside the block

The current agent writes copy instructions **outside** the fenced block, **above** it. Not below (users scan top-to-bottom and may paste before reading further). Not inside (defeats the purpose — the research tool would read the copy instructions too).

Canonical form:

> Copy only the contents of the code block below. Paste into [tool]. Do not include any of your terminal session or surrounding Claude Code output — let the prompt stand alone.

## The failure these rules prevent

A taxonomy-research prompt was produced inside a fenced block with proper framing. The user copied the full Claude Code session — the prompt plus surrounding terminal output including zsh `compdef` errors and a "bypass permissions on" banner. The research tool's output was roughly 60% noise: long sections analyzing shell initialization and permission-mode governance, because those strings appeared in the paste and the research tool treated them as part of the question.

Any single rule above is defeatable. Running all four together produces a prompt that is robust against realistic paste behavior — including the paste behaviors users do not warn you about.

## Rule of thumb

Imagine the prompt pasted into a new browser tab, preceded by a random paragraph of unrelated text, and followed by a stack trace from something else. If it still works, it passes.

## The hard-constraint stanza

Every composed research prompt carries a tuned version of this block. The exact
wording changes per task; the shape stays constant.

- Topic scope only. Do not drift into adjacent topics — enumerate the adjacent
  topics by name.
- Authoritative sources only. Every citation must resolve to an official domain
  class that you name explicitly. Enumerate disallowed aggregators by name —
  LexisNexis, Westlaw, Justia, FindLaw, Crunchbase, Wikipedia, law-firm
  marketing pages, whatever fits the domain.
- Every factual claim must be traceable to a cited source. If you cannot find a
  direct citation, say "not found" or "inferred from [X]" — do not make it up.
- Do not invent citations, identifiers, or dates. If you cite something, the URL
  must actually open to that thing.
- Do not write finished prose for the end audience. The output is facts and
  citations, not marketing copy or plain-language pages.
- Do not ask clarifying questions before starting. Begin immediately unless a
  hard constraint makes the task impossible; if so, state the blocker and
  produce the closest valid scoped report.
- Do not pad. If multiple entities have substantively identical findings, say so
  in the executive summary and let the reader decide.
- Be honest about complexity — name the specific framework, transition, or
  methodology nuance that must not be flattened.
- Be honest about uncertainty. A row marked "confidence: low, needs human
  review" is more valuable than a confident-sounding fabrication.

### Image variant

No citations, but image generators have their own drift modes:

- No watermarks, signatures, logos, captions, borders, or stock-photo overlays
  unless explicitly specified.
- Do NOT default to — enumerate the generic drift modes for this subject by
  name, e.g. "smiling stock-pose models", "lens flares as a substitute for
  atmosphere", "extra fingers or malformed hands", "AI-uncanny symmetric faces".
- Stay within the named style. Do not blend with [adjacent style that would
  dilute it].
- For unspecified regions, default to clean negative space or natural background
  extension. Do not invent additional subjects, props, or focal points.
- Anatomy and physics must be plausible unless the named style explicitly
  permits stylization — and even then, name the stylization.
- Generate the image; do not substitute a written description. If a spec element
  is genuinely impossible, generate the closest faithful version and name the
  deviation in the verification caption.
