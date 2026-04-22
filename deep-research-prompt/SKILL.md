---
name: deep-research-prompt
description: Produce copy-pasteable mega-prompts for external deep research tools (ChatGPT Deep Research, Perplexity Deep Research, Claude Research) and Oracle-ready prompt handoffs when the current run should execute GPT-5 Pro / Deep Research directly. Use when the user asks for "a prompt for another agent to research X", "mega prompt for deep research", "draft a research prompt", "make a prompt to paste into ChatGPT deep research", "prompt for another agent to do all the Y", or when another skill needs a bounded external-reality pass before a strategic decision or document update. Not for inline research the current agent can do with WebFetch or WebSearch directly, and not for prompts that ask another agent to write code or edit files.
---

# Deep research prompt

Produce a single standalone deep-research prompt that survives copy/paste cleanly. Default output is for the user to send outside the current session. When the caller explicitly wants an Oracle handoff, also return the prompt file path and the run/verification commands needed for GPT-5 Pro + Deep Research. Do not execute Oracle unless the parent skill or user asked for execution.

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

## Do not use for

- Research the current agent can do inline with `WebFetch` or `WebSearch` in a handful of calls. Just do it.
- Short lookups (fewer than ~10 facts). The overhead of a deep research prompt is not worth it.
- Prompts for agents that will write code, edit files, or execute commands. Those belong to the `Agent` tool, not a deep research prompt.
- Interactive back-and-forth with a research agent. Deep research tools are one-shot report generators; multi-turn dialogue is a different contract.

## Two delivery modes

Pick one mode from context and say which one you are producing:

- **Paste mode** (default) — the user will paste the prompt into ChatGPT Deep Research, Perplexity, Claude Research, or a similar external tool.
- **Oracle handoff mode** — another skill or the current run will execute the prompt through `oracle` against ChatGPT/GPT-5 Pro. Use this when external reality is the blocking uncertainty for a strategic choice, a market/positioning document, or a repo/portfolio decision.

Oracle handoff mode still produces the same standalone prompt block. It additionally returns:

- a prompt file path like `/tmp/<slug>-deep-research-<date>.md`
- a sizing command: `oracle --dry-run summary --file <promptfile>`
- a run command using `oracle --engine browser --browser-manual-login --model gpt-5-pro --browser-timeout 30m -p "$(cat <promptfile>)"`
- a short verification reminder: confirm the Deep Research toggle is on, capture the Oracle session ID, and verify the resulting chat actually ran on a `gpt-5-pro`-ish model slug

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
- **Custom** — none of the above fits; construct from first principles using the contract above.

Generic skeleton at `assets/templates/n-entity-structured.md`. Start there for almost any N-entity task. Cross-jurisdiction legal specialization at `assets/templates/cross-jurisdiction-legal.md`.

### 3. Compose the prompt

Fill in the chosen skeleton with task-specific content. Required sections in order:

1. **Role + mission** (1 sentence) — "You are a [role]. Your sole task is to [action] for [subject]. You do NOT [non-goal]."
2. **Context** (2-4 short paragraphs) — why this research exists, who uses the output, what calibration examples look like. If an anchor example already exists in the user's project, reference it and tell the research agent to match its mechanical specificity without copying its prose.
3. **The research question** (numbered list) — the concrete fields the research agent must answer per entity.
4. **Output format** — exact markdown structure the research agent must produce. Show it with inline example headings and bullet labels, not just description. Prose description alone produces prose drift.
5. **Hard constraints** — the anti-hallucination stanza plus task-specific constraints.
6. **What to report back when done** — 3-5 concrete completion criteria.

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

### 5. Wrap with copy instructions outside the block

**Above** the fenced block, write a short framing paragraph and an explicit copy instruction:

> Copy only the contents of the code block below. Paste into [tool]. Do not include any of your terminal session or surrounding Claude Code output — let the prompt stand alone.

**Below** the block, write:

1. **Where to save the output** — a concrete file path if there is a project context.
2. **Time budget heads-up** — structured N-entity research takes 20-90 minutes of tool runtime. Warn the user so they do not panic at 15 minutes in.
3. **Reusability note** — if the prompt is parameterized on one variable (topic, entity class), tell the user how to rerun it for other values.
4. **Red flag to watch for** — name the one most-likely failure mode given the task. Examples: "confidence inflation if every row is high-confidence," "aggregator citations if source discipline slips," "prose drift if the agent ignores the schema."

### 5b. If Oracle handoff mode, add the execution wrapper outside the block

After the normal post-block notes, add:

1. **Prompt file** — where the caller should save the block contents
2. **Sizing command** — `oracle --dry-run summary --file <promptfile>`
3. **Run command** — GPT-5 Pro browser invocation
4. **Verification note** — Deep Research toggle, session ID capture, model-slug check

Do not put shell commands inside the prompt block. They are operator instructions, not research instructions.

## Output shape for the current agent

When invoked, produce exactly this structure in the current conversation:

1. **One or two lines of framing** — what this prompt does and what tool it is for.
2. **The copy instruction** — "Copy only the contents of the code block below..." placed immediately before the block.
3. **The fenced code block** — the prompt itself. Starts with "You are a [role]..."
4. **Post-block notes** — save path, time budget, reusability, red flag.
5. **Oracle wrapper** — only in Oracle handoff mode: prompt file, sizing command, run command, verification note.

Do not summarize the prompt content in prose after the block. The user will read the block themselves.

## Validation before handoff

Before finalizing the prompt, check:

- First line inside the block is "You are a ..." or equivalent self-announcing role statement
- Entire prompt is inside a single fenced code block
- Output format is shown with a concrete example structure, not just described
- Hard-constraint stanza is present
- "What to report back when done" section is present with 3-5 bullets
- No terminal chrome, shell prompts, or Claude Code banner text inside the block
- Copy instruction is outside the block and above it (users scan top-to-bottom)
- Post-block notes name the one most-likely failure mode
- If Oracle handoff mode was requested, the response includes prompt file, sizing command, run command, and verification note outside the block

If any item fails, fix before sending. Read `references/anti-patterns.md` for the fixes.

## Templates and references

- `references/hygiene-rules.md` — the four rules that defend against terminal leak, plus the failure history that justifies them
- `references/output-structures.md` — six structured output patterns with when-to-use notes
- `references/anti-patterns.md` — failure modes and their fixes
- `assets/templates/n-entity-structured.md` — generic skeleton for "research N things with same structure"
- `assets/templates/cross-jurisdiction-legal.md` — specialization for state-by-state or country-by-country legal research

## Verification / Closeout Contract

For skill-contract edits, rerun:

```bash
python3 skill-issue/scripts/quick_validate.py deep-research-prompt
```

Before returning, confirm all of the following:

1. Delivery mode is explicit: `Paste mode` or `Oracle handoff mode`.
2. The prompt is a single fenced code block with a self-announcing first line,
   output schema, hard constraints, and completion criteria.
3. The copy instruction sits above the block and no session chrome leaked into
   the prompt.
4. If Oracle handoff mode was requested, the response includes prompt file,
   sizing command, run command, and verification note outside the block.
5. If the caller expected execution rather than handoff, state plainly whether
   Oracle was actually run or only prepared.
