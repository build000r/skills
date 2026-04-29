---
name: mmd
description: Choose, author, encode, and open Mermaid diagrams. Use when the user invokes /mmd or $mmd, asks for the best .mmd/diagram type for a context, wants a Mermaid diagram created from prose, needs a mermaid.live/edit pako URL, asks to preview a .mmd file, or wants to decode/check Mermaid Live URL fragments.
---

# Buildooor Diagrams Links

## Quick Start

Create the best Mermaid diagram from a prose brief:

```bash
# Read references/diagram-selection.md and references/visual-grammar.md,
# choose the diagram type and visual grammar, write a .mmd, then open it with:
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/generated.mmd --open
```

Open a Mermaid source file in the buildooor diagrams viewer:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/diagram.mmd --open
```

Open with a local tmux handoff channel so the viewer can send selected notes back to the pane that launched it:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/diagram.mmd --open --tmux
```

Open with the same handoff channel and automatically press Enter after Send pastes the edit packet:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/diagram.mmd --open --tmux --tmux-submit
```

Validate Mermaid syntax without opening a URL:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/diagram.mmd --preflight-only
```

Print the editable URL without opening it:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py path/to/diagram.mmd
```

Read Mermaid source from stdin:

```bash
pbpaste | python3 {{SKILL_DIR}}/scripts/mmd.py - --open
```

Decode an existing Mermaid Live/buildooor diagrams fragment or URL:

```bash
python3 {{SKILL_DIR}}/scripts/mmd.py --decode 'https://mermaid.live/edit#pako:...'
```

## Invocation Routing

- Existing file path or stdin: encode/open that source directly.
- Mermaid Live URL, buildooor diagrams URL, or `pako:`/`base64:` fragment: decode it.
- Natural-language brief: choose the diagram type, create a `.mmd`, then open it.
- Requests for "best", "what diagram", "matrix", "root cause", "timeline", "sequence", "schema", or "architecture": treat as a diagram-selection task, not a generic flowchart task.

## Diagram Selection

Use [references/diagram-selection.md](references/diagram-selection.md) before authoring from prose, then apply [references/visual-grammar.md](references/visual-grammar.md) before writing Mermaid.

Default rule: choose the diagram that answers the user's implied question. Do not default to `flowchart` unless the question is actually about order, branching, or control flow.

Say the decision in one sentence after creating the file:

```text
I chose an Ishikawa-style cause map because the prompt is about diagnosing why the workflow can fail.
```

Ask a clarifying question only when the user is asking for a deliverable where the wrong diagram would materially change the conclusion. Otherwise make the decision, write the `.mmd`, open it, and report the path plus URL.

## Decision-Grade Visuals

Default rule: visual encoding must serve the user's decision, not decorate the chart.

- Use position for structure, priority, sequence, or proximity to the outcome.
- Use color for status, severity, confidence, or recommendation.
- Do not use the same color channel for both category and severity.
- Never rely on color alone. Include short labels such as `HIGH`, `MED`, `OK`, `LOW`, `UNKNOWN`, or `BLOCKED`.
- Prefer muted category nodes and stronger color on the actionable leaf nodes.
- Put the most important conclusion, bottleneck, effect, or recommendation where the eye naturally lands for that chart type.

For an Ishikawa/fishbone chart, use native Mermaid `ishikawa-beta` syntax by default. Keep categories neutral and put severity in the cause labels:

- `HIGH`: likely root cause, severe, or blocking.
- `MED`: plausible, partial, or worth investigating.
- `OK`: healthy, mitigated, or working as intended.
- `UNKNOWN`: insufficient evidence.

Native `ishikawa-beta` has limited per-cause styling hooks. If colored stoplight styling is more important than the fishbone layout, use the documented `flowchart LR` fallback and explicitly say it is a fallback, not a native Ishikawa chart.

When the prompt asks for the "best" diagram, also choose the best visual grammar and state both decisions:

```text
I chose an Ishikawa cause map with stoplight severity because the prompt is about diagnosing what blocks useful decisions.
```

## Encoding Contract

Mermaid Live Editor serializes state as:

1. Build a state object with `code`, `grid`, `mermaid`, `panZoom`, `rough`, and `updateDiagram`.
2. `JSON.stringify` the state with no extra spaces.
3. UTF-8 encode the JSON.
4. Compress with zlib/DEFLATE level 9, matching `pako.deflate(data, { level: 9 })`.
5. URL-safe base64 encode the compressed bytes without padding.
6. Prefix the fragment with `pako:`.

The bundled script implements that path with Python standard-library `json`, `zlib`, and `base64`, then opens the `https://buildooor.com/diagrams#pako:...` URL through `osascript`.

When `--tmux` is passed, the script also starts an ephemeral localhost handoff server and adds a `buildooorHandoff` object to the compressed state, including the launcher command the browser should place in reopen instructions. For file inputs, it also adds `buildooorSource` with the resolved `.mmd` path. The browser reads that private hash metadata and shows `send to <tmux target>` instead of relying on clipboard copy. In handoff mode, the prompt panel previews the exact agent edit packet that will be sent. The server validates an unguessable token, expires by TTL, and pastes an edit packet into the target tmux pane without pressing Enter by default. If `--tmux-submit` is also passed, Send pastes the edit packet and then presses Enter in the target pane. If the localhost handoff is unavailable when the user presses Send, the app copies the same agent edit packet to the clipboard as a recovery path.

## Local Bridge Ownership

The localhost handoff server belongs to this skill, not to the buildooor app. `scripts/mmd.py --tmux` starts the ephemeral bridge and embeds its endpoint, token, target tmux pane, source path, launcher command, and capabilities into the private `buildooorHandoff`/`buildooorSource` state.

The buildooor `/diagrams` page is the browser client for that bridge. It may render selection UI, notes, packet previews, source-edit controls, and send/submit buttons, but it should discover local capabilities from the pako state and call the MMD bridge. Do not add buildooor Next API routes for local `.mmd` file reads, writes, preflight, file watching, or tmux submission.

Direct-edit behavior must extend the token-gated MMD bridge first, then add browser UI that consumes those endpoints. The bridge currently supports:

- `POST /source/read`: return the attached `.mmd` source file.
- `POST /source/preflight`: validate submitted code, or the attached file when no code is supplied.
- `POST /source/write`: validate submitted code with Mermaid preflight, then save it to the attached `.mmd` file only if validation succeeds.

The browser must not choose arbitrary filesystem paths. It can only operate on the source file attached by `scripts/mmd.py --tmux`. Future bridge additions should follow the same pattern for file status/watch and explicit submit.

## Parser Preflight

The script validates Mermaid syntax with Mermaid's own npm parser before encoding or opening.

- Default behavior: run parser preflight first, auto-installing the pinned parser dependency from `scripts/package.json` when missing.
- `--preflight-only`: validate syntax and print the detected diagram type without producing a URL.
- `--no-preflight`: bypass parser validation for drafts or unsupported edge cases.
- `--no-parser-install`: fail instead of auto-installing the parser dependency.
- `--setup-parser`: install the parser dependency explicitly.

If preflight fails, fix the `.mmd` before opening Mermaid Live unless the user explicitly asks to inspect a broken draft.

## Common Options

- `--open`: open the generated URL with the bundled AppleScript launcher.
- `--view`: accepted for compatibility; buildooor diagrams uses one URL.
- `--fragment-only`: print only `pako:...`.
- `--tmux` / `--tmux-handoff`: attach a local handoff channel for the diagrams viewer's Send button.
- `--tmux-target <target>`: override the tmux target pane; defaults to the current pane.
- `--tmux-submit`: after Send pastes into the target pane, press Enter automatically.
- `--handoff-ttl <seconds>`: lifetime for the local handoff channel, default 3600.
- `--preflight-only`: validate Mermaid syntax and exit.
- `--no-preflight`: skip parser validation.
- `--theme <name>`: set the Mermaid config theme, default `default`.
- `--config <json-or-path>`: use a custom Mermaid config JSON string or file.
- `--decode <url-or-fragment>`: decode a Mermaid Live URL or fragment into JSON state.

## Verification

After changes to the script, run:

```bash
python3 {{SKILL_DIR}}/scripts/test_mmd.py
python3 {{SKILL_DIR}}/scripts/mmd.py {{SKILL_DIR}}/examples/ishikawa-stoplight.mmd --preflight-only
```

For a numeric `/crap` score on the bridge, generate a temporary coverage artifact first:

```bash
cd {{SKILL_DIR}}/scripts
python3 -m coverage run --source=. test_mmd.py
python3 -m coverage xml -o coverage.xml
python3 {{SKILL_DIR}}/../crap/scripts/analyze_crap.py {{SKILL_DIR}}/scripts --languages python --top 10
```

For authoring changes, also round-trip the generated file:

```bash
frag=$(python3 {{SKILL_DIR}}/scripts/mmd.py path/to/generated.mmd --fragment-only)
python3 {{SKILL_DIR}}/scripts/mmd.py --decode "$frag" --code-only | diff -u path/to/generated.mmd -
```
