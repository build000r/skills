---
name: codex-tmux
type: utility
description: >
  Run Codex in a persistent tmux session with signal-based completion.
  Two-path model: if the calling conversation is alive, a background
  `tmux wait-for` unblocks and returns the result. If the conversation
  died, a macOS notification fires and the result file persists on disk.
  Use when a task may take 5+ minutes, must survive session death, or
  needs a fresh context without orchestrator bias.
license: MIT
---

# Codex Tmux

Run Codex non-interactively in a detached tmux session. The calling skill
launches it, starts a background waiter, and continues — or dies. Either
way the work completes and the result is retrievable.

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
Calling skill (e.g. divide-and-conquer)
 ├── Builds prompt string
 ├── Calls: python3 codex-tmux/scripts/run.py launch --task "..." --cd <repo>
 ├── Starts background Bash: tmux wait-for <channel> && cat <result_file>
 │    └── BLOCKS (zero CPU) until Codex signals
 ├── Tells user the session name
 └── Continues conversation (or session dies — both are fine)

Path A (conversation alive):
   Codex finishes → signals channel → background Bash unblocks
   → TaskOutput returns result.json → calling skill reports to user

Path B (conversation died):
   Codex finishes → signals channel (no listener, fine)
   → macOS notification → tmux display-message
   → User checks: tmux a -t <session> OR cat <result_file>
```

No recursive agents. No `claude --resume`. The signal is a dumb tmux primitive.

## Usage Protocol

### Step 1: Build your prompt

The calling skill builds the full prompt string. codex-tmux does NOT generate prompts — it's a transport layer.

### Step 2: Launch

```bash
python3 ~/.claude/skills/codex-tmux/scripts/run.py launch \
    --task "<your prompt string>" \
    --cd "<repo working directory>"
```

The script outputs JSON to stdout:

```json
{
  "session": "codex-20260220-143022",
  "signal_channel": "codex-20260220-143022-done",
  "result_file": "/tmp/codex-tmux/codex-20260220-143022.json",
  "wait_command": "tmux wait-for codex-20260220-143022-done && cat /tmp/codex-tmux/codex-20260220-143022.json"
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

Immediately after launching, start a **background Bash task** that blocks on the tmux signal channel:

```bash
# run_in_background: true, timeout: 600000
tmux wait-for <signal_channel> && cat <result_file>
```

### Step 4: Tell user the session name

```
Codex running in: codex-20260220-143022

  Watch live:  tmux a -t codex-20260220-143022
  Status:      python3 ~/.claude/skills/codex-tmux/scripts/run.py status --session codex-20260220-143022
```

### Step 5: Collect result

If the conversation is still alive, check the background task via `TaskOutput`:

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
    [--model gpt-5.3-codex]       # codex model (default: gpt-5.3-codex)
    [--reasoning-effort xhigh]    # minimal|low|medium|high|xhigh (default: xhigh)
    [--codex-bin codex]            # path to codex binary (default: codex)
```

### status

```
python3 scripts/run.py status --session <session-name>
```

Returns JSON with `status` (running | completed | completed_no_result), `has_result`, and optional `tail` (last 30 lines of tmux pane output if still running).

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
