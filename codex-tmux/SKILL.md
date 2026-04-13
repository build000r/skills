---
name: codex-tmux
type: utility
description: Run Codex in a persistent tmux session with signal-based completion so long tasks survive conversation death. Use when work may take 5+ minutes, needs background execution, or must remain retrievable after the calling session ends.
license: MIT
---

# Codex Tmux

Run Codex non-interactively in a detached tmux session. The calling skill
launches it, starts a background waiter, and continues — or dies. Either
way the work completes and the result is retrievable.

This skill is a detached transport wrapper, not an NTM-style swarm
orchestrator. Use it only when detached single-session survivability is the
actual requirement.

Shared cross-skill rules live in
[references/orchestration-contract.md](references/orchestration-contract.md).
Use that file for detached review and background-result collection semantics.

## When to Use

| Use Claude Code subagents when | Use codex-tmux when |
|---|---|
| Task completes in < 2 minutes | Task may take 5+ minutes |
| Needs Claude Code tools (Edit, Read, Glob, Grep, Task) | Needs only filesystem + git |
| Multiple parallel fast tasks | Single slow quality gate / review |
| Context from conversation is useful | Fresh context is better (no orchestrator bias) |
| Must complete within this session | Must survive session death |

## Architecture

```
Calling skill or workflow
 ├── Builds prompt string
 ├── Calls: python3 codex-tmux/scripts/run.py launch --task "..." --cd <repo>
 ├── Starts background wait helper: python3 codex-tmux/scripts/run.py wait --session <name>
 │    └── BLOCKS until Codex signals, then prints result.json
 ├── Tells user the session name only when detached survivability matters
 └── Continues conversation (or session dies — both are fine)

Path A (conversation alive):
   Codex finishes → signals channel → background wait helper unblocks
   → runtime task/session handle returns result.json → calling skill reports to user

Path B (conversation died):
   Codex finishes → signals channel (no listener, fine)
   → macOS notification → tmux display-message
   → User checks: tmux a -t <session> OR cat <result_file>
```

No recursive agents. No `claude --resume`. The signal is a dumb tmux primitive.

## Model Policy

- Default to `gpt-5.4`. For bounded or budget-sensitive work, `gpt-5.4-mini` and `codex-mini-latest` are also allowed. Older `gpt-5.x-codex` variants remain out of scope for this skill.
- Default to `high` reasoning. Use `medium` only for clearly bounded work, and `xhigh` for reviews, ambiguity, or high-risk changes.
- When unsure between two reasoning tiers, choose the next higher one.

## Usage Protocol

### Step 1: Build your prompt

The calling skill builds the full prompt string. codex-tmux does NOT generate prompts — it's a transport layer.
The calling skill also owns most user messaging. Treat codex-tmux as infrastructure unless the user explicitly needs the detached-session handle.

### Step 2: Launch

```bash
python3 ~/.claude/skills/codex-tmux/scripts/run.py launch \
    --task "<your prompt string>" \
    --cd "<repo working directory>"
```

Defaults are `gpt-5.4` and `high` reasoning. For routine or budget-sensitive work, pass `--model gpt-5.4-mini` or `--model codex-mini-latest`. Raise to `xhigh` when the task is reviewer-grade or ambiguous.

The script outputs JSON to stdout:

```json
{
  "session": "codex-20260220-143022",
  "signal_channel": "codex-20260220-143022-done",
  "result_file": "/tmp/codex-tmux/codex-20260220-143022.json",
  "wait_command": "python3 ~/.claude/skills/codex-tmux/scripts/run.py wait --session codex-20260220-143022 --result-dir /tmp/codex-tmux"
}
```

And a human-friendly summary to stderr:

```
  Codex launched: codex-20260220-143022
  Watch live: tmux a -t codex-20260220-143022
  Result:     /tmp/codex-tmux/codex-20260220-143022.json
  Signal:     tmux wait-for codex-20260220-143022-done
  Kill:       tmux kill-session -t codex-20260220-143022
```

### Step 3: Start background waiter

Immediately after launching, start a **background wait helper**:

```bash
# run_in_background: true, timeout: 600000
python3 ~/.claude/skills/codex-tmux/scripts/run.py wait --session <session-name>
```

### Step 4: Tell user the session name

Only surface the session details when:

- the task is expected to outlive the current conversation
- the user explicitly asked for detached/background execution details
- you are handing off a long-running quality gate the user may want to inspect manually

Otherwise keep the detail minimal and continue with the calling workflow.

```
Codex running in: codex-20260220-143022

  Watch live:  tmux a -t codex-20260220-143022
  Status:      python3 ~/.claude/skills/codex-tmux/scripts/run.py status --session codex-20260220-143022
```

### Step 5: Collect result

If the conversation is still alive, prefer the background wait helper above.
Use the session `status` / `result` commands only for polling, timeout recovery, or manual inspection:

- First check after ~60 seconds
- Subsequent checks every ~30 seconds
- If the background task timed out, check the result file directly:

```bash
python3 ~/.claude/skills/codex-tmux/scripts/run.py result --session <session-name>
```

## CLI Reference

### launch

```
python3 scripts/run.py launch \
    --task "prompt string" \
    --cd ~/repos/myapp \
    [--prefix codex]              # session name prefix (default: codex)
    [--result-dir /tmp/codex-tmux] # where to write results (default: /tmp/codex-tmux)
    [--model gpt-5.4]             # default model; also allows gpt-5.4-mini and codex-mini-latest
    [--reasoning-effort high]     # medium|high|xhigh (default: high; round up when unsure)
    [--codex-bin codex]            # path to codex binary (default: codex)
```

### status

```
python3 scripts/run.py status --session <session-name>
```

Returns JSON with `status` (running | completed | completed_no_result), `has_result`, and optional `tail` (last 30 lines of tmux pane output if still running).

### wait

```
python3 scripts/run.py wait --session <session-name>
```

Blocks on the session completion signal, then prints the same JSON as `result`.
Use this for background-task handles instead of spelling raw `tmux wait-for ... && cat ...` in calling skills.

### result

```
python3 scripts/run.py result --session <session-name>
```

Returns the result JSON written by the wrapper script. Shape:

```json
{
  "session": "codex-20260220-143022",
  "exit_code": 0,
  "commit_hash": "abc1234..." | null,
  "commit_message": "feat: ...",
  "completed_at": "2026-02-20T14:35:25Z"
}
```

## Result File

The wrapper script always writes a result JSON, even on failure. It detects new commits by comparing HEAD before and after the Codex run. On error, the tmux session stays alive for `tmux a -t <session>` inspection.

## Completion Signals

Three channels fire on completion (any may be dead, all are best-effort):

1. **tmux wait-for -S** — unblocks the orchestrator's background Bash task
2. **macOS notification** — reaches user even if conversation died
3. **tmux display-message** — visible if user is in another tmux window
