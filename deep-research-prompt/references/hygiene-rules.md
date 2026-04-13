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
