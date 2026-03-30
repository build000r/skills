---
name: divide-and-conquer
description: Decompose complex work into independent parallel sub-agents with no write overlap, synthesize or consume a `WORKGRAPH.md` execution artifact, and launch describe-style worker briefs before review. Use before spawning multiple agents for multi-file, multi-domain, or naturally parallel tasks.
license: MIT
---

# Divide and Conquer

Decompose a task into sub-agents that run fully in parallel with zero conflicts.
Autonomous: analyze → load or synthesize `WORKGRAPH.md` → launch
describe-style node briefs → Codex review → commit → report. No approval
gates.

## Default Marker

Start with a stable first progress message such as:

`Using \`divide-and-conquer\` to map the ready frontier, write a temp \`WORKGRAPH.md\` when needed, and launch conflict-free workers.`

Shared cross-skill rules live in
[references/orchestration-contract.md](references/orchestration-contract.md).
Use that file for worker ownership, background-task collection, and detached
review handoff semantics.

Temp workgraph synthesis and describe-style worker briefs live in
[references/workgraph-synthesis.md](references/workgraph-synthesis.md).

## Modes

Modes customize decomposition for specific projects — split boundaries, agent preferences, repo structure, naming conventions, and validation commands. Stored in `modes/` (gitignored, never committed).

### How Modes Work

Each mode is a markdown file: `modes/{project-name}.md`. It contains project-specific configuration: where the natural split boundaries are, what agent types to prefer, what `gpt-5.4` reasoning strategy to prefer, what commands to run for validation, and how to label agents.

### Mode Selection (Step 0)

1. List `.md` files in `modes/` (if directory exists)
2. Each mode file has a `cwd_match` field — a path prefix to match against cwd
3. If cwd matches exactly one mode, use it automatically
4. If cwd matches multiple or none, ask the user which mode (or use generic defaults)
5. If `modes/` doesn't exist, use generic decomposition (no project-specific config)

### Creating a Mode

Copy `references/mode-template.md` to `modes/{project-name}.md` and fill in split boundaries, agent preferences, and validation commands for your project. When a user runs the skill with no matching mode, offer to create one.

Modes are gitignored — they contain project-specific paths and preferences that should not be committed to the skill repo.

## Agent Types

Know what each type can and cannot do:

| Type | Can Read | Can Write | Can Bash | Sees Conversation | Best For |
|------|----------|-----------|----------|-------------------|----------|
| **Explore** | Yes | **No** | No | No | Research, codebase exploration — inherently safe |
| **general-purpose** | Yes | Yes | Yes | **Yes** | Implementation, complex multi-step work |
| **Bash** | No | No | Yes | No | Running commands, builds, tests, git operations |
| **Plan** | Yes | **No** | No | No | Designing implementation approaches |

Key implications:
- **Explore agents are physically read-only** — they cannot Edit, Write, or NotebookEdit. Use them for research without worrying about file conflicts.
- **general-purpose agents see full conversation history** — prompts can reference earlier context concisely instead of repeating everything.
- **Bash agents only have Bash** — they can't use Read/Edit/Glob/Grep tools. They run shell commands only.

## Model Selection (`gpt-5.4` Only)

- **Use `gpt-5.4` for every explicit model selection in this skill.** Do not fall back to older `gpt-5.x-codex` variants or provider-specific tier names.
- **Tune depth with reasoning effort instead of swapping models.** Use `medium` only for clearly bounded work, default to `high`, and use `xhigh` for reviews, ambiguity, or high-risk changes.
- **When unsure, go one tier higher.** Choose `high` over `medium`, and `xhigh` over `high`, when the task is borderline.
- **Leaving the model unset is only fine if the runtime already resolves to `gpt-5.4`.** Otherwise set it explicitly.

## Process

### 1. Analyze the Task

Read the conversation to understand:
- What the user wants accomplished
- What files/areas of the codebase are involved
- What the dependencies between subtasks are

### 2. Decide Whether a Workgraph Is Relevant

Use a workgraph when any of these are true:
- The task has 2+ plausible concern-owned sub-agents
- Dependency edges matter to the launch order
- The user explicitly wants an orchestrated or parallel split
- You need a durable artifact to explain and reuse the split across workers

If the work collapses to one concern or a strict dependency chain, do **not**
force a graph just to satisfy the ritual.

If the split itself is unclear, use `ask-cascade` on the first blocking
strategic fork before inventing nodes or launching agents.

### 3. Load or Synthesize `WORKGRAPH.md`

Before inventing a split, check whether the repo or plan directory already has a
durable `WORKGRAPH.md` execution artifact.

If a durable `WORKGRAPH.md` exists:
- Run `python3 ~/.claude/skills/divide-and-conquer/scripts/workgraph_ready.py --file <path-to-WORKGRAPH.md>`
- Treat the reported `ready_nodes` and `waves` as the default split proposal
- Launch work only from the current ready frontier
- Do **not** pull blocked or dependency-pending nodes into the same batch
- Respect `writes` ownership from the workgraph even if the user asked broadly

If no durable `WORKGRAPH.md` exists and parallelism is still relevant:
- Create a temp directory, for example `mktemp -d "${TMPDIR:-/tmp}/dac-workgraph-XXXXXX"`
- Write `WORKGRAPH.md` inside that directory using the canonical node contract
  from [references/workgraph-synthesis.md](references/workgraph-synthesis.md)
- Keep the temp graph focused on this execution slice only, usually 2-8 nodes
- Do **not** commit the temp graph unless the user explicitly asks to preserve
  it
- Immediately run `workgraph_ready.py` against the temp file and treat the
  resulting ready frontier as the launch plan

The temp graph is a scratch execution artifact, not a second plan document.

### 4. Identify Node Boundaries

Find natural seams where work can be divided. Good boundaries:
- **Domain boundaries**: Frontend vs backend vs database vs tests
- **Concern boundaries**: Research vs implementation, different features
- **Goal boundaries**: Different outcomes that don't interact

Scope agents by **concern**, not by file list. "Handle authentication changes"
is better than "Modify src/auth.ts". The agent discovers which files are
relevant; you verify no overlap in the conflict check. When `WORKGRAPH.md`
exists, the node's `concern` and `writes` fields become the starting point for
that split.

If you cannot express a node with concrete `done_when` and `validate_cmds`, the
node is not ready to launch. Tighten it first instead of delegating vague work.

### 5. Verify Independence

For each proposed agent pair, confirm:
- No two agents write to the same file
- No agent needs another agent's output to start
- No shared mutable state between agents
- Dependency edges are represented in `depends_on`, not hidden in prompt prose
- Each agent's instructions are self-contained (or uses general-purpose type which sees conversation)

If any check fails, merge those agents or restructure the split.

See `references/decomposition-patterns.md` for safe/unsafe patterns and the full checklist.

### 6. Plan, Brief, Launch, and Report (Single Flow)

This is autonomous — **do NOT ask for approval** between planning and launching.
Output the plan for transparency, then launch immediately in the same response.

#### 6a. Resolve Fuzzy Nodes with `describe` Rules

Use `describe` only when a node is still fuzzy, not as mandatory ceremony for
every worker.

When a ready node still has fuzzy `done_when`, `validate_cmds`, or non-goals:
- Do **not** launch a write agent yet
- Run a node-local `describe` pass or fresh review to tighten the node contract
- If the review exposes a real strategic decision, route that single blocking
  question through `ask-cascade`
- Rewrite the node in `WORKGRAPH.md`
- Re-run `workgraph_ready.py` before launching workers

#### 6b. Build a Describe-Style Worker Brief

Every launched worker, especially write agents, gets the workgraph path and the
specific node it owns. Use a compact describe-style brief:

```text
Workgraph: <path-to-WORKGRAPH.md> (durable | temp)
Node: <WG-001> - <title>
Concern: <concern>
Depends on: <ids already satisfied, or None>
Writes: <expected paths/globs, or None>
Underlying ask: <plain-language user outcome for this node>
Done when:
- <binary completion check>
Validate:
- <command>
Risk gate:
- none | <what must be confirmed first>
Non-goals:
- <explicitly out of scope items>

If anything above is ambiguous enough that you would guess, stop and return the
single smallest ask-cascade question or a proposed WORKGRAPH edit instead of
coding past it.
```

This is the default launch contract even when you do **not** run the full
`describe` skill for that node.

#### 6c. Output the Decomposition (Transparent, Not a Gate)

Print the decomposition as a numbered list. For each agent:

```
## Agent [N]: [Short Label]

**Workgraph**: <path> (`durable` | `temp`)
**Node**: <WG-00N> | None
**Type**: Explore | general-purpose | Bash
**Model**: `gpt-5.4` + `medium|high|xhigh` (`high` default; round up when unsure)
**Background**: true if non-blocking, false if results needed before next step
**Concern**: [Domain/goal this agent owns — scope by concern, not file list]
**Task**: [Goal-focused instructions. Include the describe-style node brief in the launch prompt.]
**Writes**: [Expected files — verified for no overlap, but agent discovers actual files needed. "None" for Explore/Bash types.]
```

Then the **Conflict Check**:

```
## Conflict Check
- Write overlap: None | [list conflicts]
- Data dependencies: None | [list dependencies]
- Workgraph frontier: [ready nodes / waves used for this launch]
- Type safety: [Confirm write-agents are general-purpose, research-agents are Explore]
- Verdict: Ready to launch | Needs restructuring
```

If verdict is "Needs restructuring", fix the split before continuing. Otherwise, proceed immediately.

#### 6d. Launch (Same Message — No Approval Gate)

All parallel agents MUST be launched in the **same message** as the plan output above. Do not wait for user confirmation. The conflict check IS the safety gate.

All worker prompts must reference the same `WORKGRAPH.md` path plus the
specific node ID they own. Agents that depend on prior results must be launched
sequentially in a follow-up message.

#### 6e. Collect Agent Results

Once all agents complete, read each agent's output. Do NOT manually review, fix, or verify — that's the Codex reviewer's job (Step 7).

**Save the original task description and workgraph path** — the reviewer needs both.

### 7. Codex Review (via codex-tmux)

After all agents return, launch a Codex review via the `codex-tmux` utility skill. See `~/.claude/skills/codex-tmux/SKILL.md` for the full tmux protocol details.

#### 7a. Build the Review Prompt

```
You are the REVIEW AGENT for a divide-and-conquer parallel execution.
Multiple sub-agents just completed work in this repository. Your job:

1. Understand what was requested:
   Task: <original task description>
   Workgraph: <path-to-WORKGRAPH.md or null>

2. Review what was done:
   - If a workgraph exists, read it first to understand node intent and ownership
   - Run `git status` and `git diff` to see all changes
   - Read modified files to understand the changes
   - Assess whether the changes correctly and completely address the task

3. Fix issues:
   - If you find bugs, incomplete work, or inconsistencies, fix them
   - If tests exist and are relevant, run them: fix failures
   - If linting/type-checking is configured, run it: fix errors
   - Do NOT add unnecessary improvements beyond what the task requires

4. Commit:
   - If there are uncommitted changes (from agents or your fixes), stage and commit
   - Use a clear commit message summarizing what was accomplished
   - Format: "feat: <what was done>" or "fix: <what was fixed>"
   - If nothing was changed (no git modifications), skip the commit

5. Report:
   After committing (or determining no commit needed), print EXACTLY this
   block at the end of your output (the orchestrator parses it):

   ```json
   {
     "commit_hash": "<hash or null if no commit>",
     "summary": "<1-2 sentence summary of what was done and any fixes applied>",
     "files_changed": <number of files changed>,
     "status": "success"
   }
   ```

   If you encounter an unrecoverable error, use status "error" with a
   summary explaining what went wrong.

Guardrails:
- Work ONLY in <repo>
- Do NOT push to remote
- Do NOT modify files outside the repo
- Keep fixes minimal and targeted
```

#### 7b. Launch the Reviewer

```bash
python3 ~/.claude/skills/codex-tmux/scripts/run.py launch \
    --task "<review prompt from 7a>" \
    --cd "<repo working directory>" \
    --model gpt-5.4 \
    --reasoning-effort xhigh \
    --prefix dac-review
```

#### 7c. Start Background Waiter

Parse the `wait_command` from the launch output:

```bash
# run_in_background: true, timeout: 600000
tmux wait-for <signal_channel> && cat <result_file>
```

#### 7d. Tell User the Session Name

```
Agents completed. Codex review running in: dac-review-20260220-143022

  Watch live:  tmux a -t dac-review-20260220-143022
  Status:      python3 ~/.claude/skills/codex-tmux/scripts/run.py status --session dac-review-20260220-143022
```

The conversation can continue normally or end here — the background waiter handles both.

#### 7e. Collect Result

If the conversation is still alive, periodically check the runtime's background
task handle or the detached review session result:

- First check after ~60 seconds
- Subsequent checks every ~30 seconds
- If the background task timed out (max 10 min), check the result file directly:

```bash
python3 ~/.claude/skills/codex-tmux/scripts/run.py result \
    --session <session-name>
```

### 8. Report to User

When the result is available (via background task or manual check):

#### If commit was made (commit_hash is not null)

```bash
git -C <repo> show --stat <commit_hash>  # files changed summary
```

Report:
```
Codex reviewed and committed: <commit_hash_short>

<commit_message>

Files changed:
<git show --stat output>
```

#### If no commit (non-commitable work like DB writes, API calls)

```
Done. No files modified (work involved external operations).
Review session: <session_name>
```

#### If reviewer errored

```
Codex review failed. Agent work is in the repo but uncommitted.
Inspect: tmux a -t <session-name>
```

## Rules

- **2-5 agents** is the sweet spot. More than 5 signals over-decomposition.
- **Scope by concern, not files**. "Handle auth changes" > "Modify src/auth.ts". Agent discovers files; you verify no overlap.
- **If `WORKGRAPH.md` exists, start from its ready frontier**. Do not freelance a broader split unless the workgraph is obviously stale or wrong.
- **If no durable `WORKGRAPH.md` exists and parallelism is relevant, synthesize a temp one first**. Use the same node contract and parser flow.
- **Never split same-concern work** across agents. One domain = one owner.
- **Use Explore for research agents** — physically cannot write, so file conflicts are impossible.
- **Use general-purpose for write agents** — they see conversation history, so prompts can be concise.
- **Every launched agent gets the workgraph path and node ID**. Do not send workers into the repo with an unanchored task.
- **Use describe-style briefs for worker prompts**. Do not hand off vague work when you can state `done_when`, `validate_cmds`, and non-goals explicitly.
- **Use `describe` only for fuzzy nodes**. If the node contract is already concrete, launch directly.
- **Use `ask-cascade` only for the first blocking strategic ambiguity**. Do not spray the user with tactical questions before the branch is set.
- **Use `gpt-5.4` whenever you set a model explicitly** — do not drop back to older model families or provider-specific tiers inside this skill.
- **Default reasoning to `high`** — use `medium` only for clearly bounded work and `xhigh` for reviews/ambiguity; when in doubt, choose the next higher tier.
- **Use `run_in_background: true`** for agents whose results aren't needed before the next step.
- **Prefer fewer write-agents**. Read-only Explore agents are cheap to parallelize.
- **When in doubt, don't split**. A single well-prompted agent beats a bad decomposition.
- **Sequential is fine** when there are real dependencies. Don't force parallelism.
