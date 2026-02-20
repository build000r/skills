#!/usr/bin/env python3
"""
Run Codex in a persistent tmux session with signal-based completion.

Two-path completion model:
  Path A (conversation alive): Background Bash blocks on `tmux wait-for`,
    unblocks when Codex signals, returns result.json via TaskOutput.
  Path B (conversation died): Wrapper writes result.json, sends macOS
    notification + tmux display-message. User resumes manually.

The tmux session stays alive on error for inspection.

Usage:
    # Launch
    python3 scripts/run.py launch \
        --task "Review and fix all uncommitted changes" \
        --cd ~/repos/myapp

    # Check status
    python3 scripts/run.py status --session codex-20260220-143022

    # Read result file directly
    python3 scripts/run.py result --session codex-20260220-143022

    # Override model/effort/prefix
    python3 scripts/run.py launch \
        --task "..." --cd ~/repos/myapp \
        --prefix dac-review --model gpt-5.2-codex --reasoning-effort high
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent

DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_RESULT_DIR = Path("/tmp/codex-tmux")
DEFAULT_PREFIX = "codex"


def _session_name(prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{ts}"


def _result_file(result_dir: Path, session: str) -> Path:
    return result_dir / f"{session}.json"


def _signal_channel(session: str) -> str:
    """tmux wait-for channel name for this session."""
    return f"{session}-done"


def _build_codex_command(
    prompt: str,
    repo: str,
    model: str,
    reasoning_effort: str,
    codex_bin: str,
) -> list[str]:
    return [
        codex_bin, "exec",
        "-m", model,
        "-c", f'model_reasoning_effort="{reasoning_effort}"',
        "--cd", repo,
        prompt,
    ]


def _build_tmux_wrapper(
    codex_cmd: list[str],
    result_file: Path,
    prompt_file: Path,
    repo: str,
    session_name: str,
    prefix: str,
) -> str:
    """Build a shell script that runs codex, writes results, and signals completion.

    Completion signaling:
      1. Writes result.json (always)
      2. tmux wait-for -S <channel> (unblocks the orchestrator's background Bash)
      3. macOS notification (fallback if conversation died)
      4. tmux display-message (fallback if user is in tmux but conversation died)

    On error: stays alive for `tmux a -t <session>` inspection.
    """
    # Build codex command — prompt comes from file to avoid escaping issues
    cmd_parts = [shlex.quote(arg) for arg in codex_cmd[:-1]]
    escaped_cmd = " ".join(cmd_parts) + f" \"$(cat {shlex.quote(str(prompt_file))})\""

    signal_channel = _signal_channel(session_name)

    return dedent(f"""\
        #!/bin/bash
        # codex-tmux wrapper
        # Session: {session_name}
        # Repo: {repo}
        # Signal channel: {signal_channel}
        # DO NOT set -e — we want the tmux session to stay alive on error

        RESULT_FILE={shlex.quote(str(result_file))}
        REPO_DIR={shlex.quote(repo)}
        SESSION="{session_name}"
        SIGNAL_CHANNEL="{signal_channel}"
        PREFIX="{prefix}"
        mkdir -p "$(dirname "$RESULT_FILE")"

        echo "=== $PREFIX: $SESSION ==="
        echo "Repo: $REPO_DIR"
        echo "Started: $(date)"
        echo ""

        # Snapshot HEAD before so we can detect new commits
        HEAD_BEFORE=$(cd "$REPO_DIR" && git rev-parse HEAD 2>/dev/null || echo "none")

        # Run codex — capture exit code but do NOT exit on failure
        EXIT_CODE=0
        {escaped_cmd} || EXIT_CODE=$?

        echo ""
        echo "Codex exited with code: $EXIT_CODE"

        # Check if a new commit was made
        HEAD_AFTER=$(cd "$REPO_DIR" && git rev-parse HEAD 2>/dev/null || echo "none")
        if [ "$HEAD_BEFORE" = "$HEAD_AFTER" ]; then
          COMMIT_HASH="null"
          COMMIT_MSG=""
        else
          COMMIT_HASH="$HEAD_AFTER"
          COMMIT_MSG=$(cd "$REPO_DIR" && git log -1 --format="%s" 2>/dev/null || echo "")
        fi

        # Write result file (env vars avoid injection from commit messages)
        DAC_SESSION="$SESSION" \\
        DAC_EXIT_CODE="$EXIT_CODE" \\
        DAC_COMMIT_HASH="$COMMIT_HASH" \\
        DAC_COMMIT_MSG="$COMMIT_MSG" \\
        DAC_RESULT_FILE="$RESULT_FILE" \\
        python3 -c "
import json, os
data = {{
    'session': os.environ['DAC_SESSION'],
    'exit_code': int(os.environ['DAC_EXIT_CODE']),
    'commit_hash': os.environ['DAC_COMMIT_HASH'] if os.environ['DAC_COMMIT_HASH'] != 'null' else None,
    'commit_message': os.environ['DAC_COMMIT_MSG'],
    'completed_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
}}
with open(os.environ['DAC_RESULT_FILE'], 'w') as f:
    json.dump(data, f, indent=2)
"

        echo ""
        echo "Result written to: $RESULT_FILE"

        # === SIGNAL COMPLETION (3 channels, any may be dead) ===

        # 1. tmux wait-for signal — unblocks orchestrator's background Bash task
        #    (no-op if nobody is waiting, which is fine)
        tmux wait-for -S "$SIGNAL_CHANNEL" 2>/dev/null || true

        # 2. macOS notification — reaches user even if conversation died
        if command -v osascript &>/dev/null; then
          NOTIFY_MSG="$PREFIX done"
          if [ "$COMMIT_HASH" != "null" ]; then
            SHORT_HASH=$(echo "$COMMIT_HASH" | cut -c1-8)
            NOTIFY_MSG="$PREFIX committed: $SHORT_HASH"
          fi
          if [ "$EXIT_CODE" -ne 0 ]; then
            NOTIFY_MSG="$PREFIX FAILED (exit $EXIT_CODE)"
          fi
          osascript -e "display notification \\"$NOTIFY_MSG\\" with title \\"codex-tmux\\"" 2>/dev/null || true
        fi

        # 3. tmux display-message — visible if user is in another tmux window
        tmux display-message "$PREFIX $SESSION: $([ $EXIT_CODE -eq 0 ] && echo 'done' || echo 'FAILED')" 2>/dev/null || true

        # === POST-COMPLETION ===

        if [ "$EXIT_CODE" -ne 0 ]; then
          # Keep tmux session alive so user can attach and inspect
          echo ""
          echo "\\033[1;31mFailed. Session stays alive for inspection.\\033[0m"
          echo "Attach: tmux a -t $SESSION"
          echo ""
          echo "Press enter to close, or Ctrl-C to keep session."
          read -r
        fi
        # On success, tmux session exits naturally — it's done its job
    """).strip()


def cmd_launch(args: argparse.Namespace) -> int:
    result_dir = Path(args.result_dir)
    session = _session_name(args.prefix)
    result_file = _result_file(result_dir, session)
    signal_channel = _signal_channel(session)
    result_dir.mkdir(parents=True, exist_ok=True)

    repo = str(Path(args.cd).expanduser().resolve())

    codex_cmd = _build_codex_command(
        prompt=args.task,
        repo=repo,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        codex_bin=args.codex_bin,
    )

    # Write prompt to a file (avoids shell escaping nightmares)
    prompt_file = result_dir / f"{session}.prompt"
    prompt_file.write_text(args.task, encoding="utf-8")

    # Write wrapper script
    wrapper_path = result_dir / f"{session}.sh"
    wrapper_path.write_text(
        _build_tmux_wrapper(codex_cmd, result_file, prompt_file, repo, session, args.prefix)
    )
    wrapper_path.chmod(0o755)

    # Always use new-session — gives a proper named session with full TTY,
    # and has-session can find it reliably for status checks.
    tmux_cmd = [
        "tmux", "new-session",
        "-d",                       # detached
        "-s", session,              # session name
        "-c", repo,                 # working directory
        f"bash {wrapper_path}",
    ]

    result = subprocess.run(tmux_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to create tmux session: {result.stderr}", file=sys.stderr)
        return 1

    # Output structured info for the orchestrator
    output = {
        "session": session,
        "signal_channel": signal_channel,
        "result_file": str(result_file),
        "wrapper_script": str(wrapper_path),
        "prompt_file": str(prompt_file),
        "repo": repo,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "prefix": args.prefix,
        "wait_command": f"tmux wait-for {signal_channel} && cat {result_file}",
    }
    print(json.dumps(output, indent=2))

    # Human-friendly summary to stderr
    print(f"\n  Codex launched: {session}", file=sys.stderr)
    print(f"  Watch live: tmux a -t {session}", file=sys.stderr)
    print(f"  Result:     {result_file}", file=sys.stderr)
    print(f"  Signal:     tmux wait-for {signal_channel}", file=sys.stderr)
    print(f"  Kill:       tmux kill-session -t {session}\n", file=sys.stderr)

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session = args.session

    # Check if tmux session still exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    )

    alive = result.returncode == 0

    # Infer result_dir from session prefix or use default
    result_dir = Path(args.result_dir) if args.result_dir else DEFAULT_RESULT_DIR
    result_file = result_dir / f"{session}.json"
    has_result = result_file.exists()

    if alive:
        status = "running"
        tail = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", session, "-S", "-30"],
            capture_output=True, text=True,
        )
        pane_output = tail.stdout.rstrip() if tail.returncode == 0 else ""
    elif has_result:
        status = "completed"
        pane_output = ""
    else:
        status = "completed_no_result"
        pane_output = ""

    output = {"status": status, "session": session, "has_result": has_result}
    if pane_output:
        output["tail"] = pane_output

    print(json.dumps(output, indent=2))

    # Human-friendly to stderr
    if alive:
        print(f"\n  {session}: RUNNING", file=sys.stderr)
        print(f"  Attach: tmux a -t {session}", file=sys.stderr)
        if pane_output:
            print(f"\n  Last output:", file=sys.stderr)
            for line in pane_output.split("\n")[-10:]:
                print(f"    {line}", file=sys.stderr)
    elif has_result:
        data = json.loads(result_file.read_text())
        print(f"\n  {session}: COMPLETED", file=sys.stderr)
        if data.get("commit_hash"):
            print(f"  Commit: {data['commit_hash'][:12]}", file=sys.stderr)
        print(f"  Result: {result_file}", file=sys.stderr)
    else:
        print(f"\n  {session}: ended with no result file", file=sys.stderr)

    return 0


def cmd_result(args: argparse.Namespace) -> int:
    result_dir = Path(args.result_dir) if args.result_dir else DEFAULT_RESULT_DIR
    result_file = result_dir / f"{args.session}.json"

    if not result_file.exists():
        print(json.dumps({
            "error": f"No result file found at {result_file}",
            "session": args.session,
        }))
        return 1

    data = json.loads(result_file.read_text())
    print(json.dumps(data, indent=2))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Codex in a persistent tmux session with signal-based completion."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # launch
    p_launch = sub.add_parser("launch", help="Launch Codex in tmux")
    p_launch.add_argument("--task", required=True, help="Prompt string for Codex")
    p_launch.add_argument("--cd", required=True, help="Repository directory")
    p_launch.add_argument("--prefix", default=DEFAULT_PREFIX,
                          help=f"Session name prefix (default: {DEFAULT_PREFIX})")
    p_launch.add_argument("--result-dir", default=str(DEFAULT_RESULT_DIR),
                          help=f"Directory for result files (default: {DEFAULT_RESULT_DIR})")
    p_launch.add_argument("--model", default=DEFAULT_MODEL)
    p_launch.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT,
                          choices=["minimal", "low", "medium", "high", "xhigh"])
    p_launch.add_argument("--codex-bin", default="codex")

    # status
    p_status = sub.add_parser("status", help="Check session status + show tail output")
    p_status.add_argument("--session", required=True, help="tmux session name")
    p_status.add_argument("--result-dir", default=None,
                          help=f"Result directory (default: {DEFAULT_RESULT_DIR})")

    # result
    p_result = sub.add_parser("result", help="Read result file")
    p_result.add_argument("--session", required=True, help="tmux session name")
    p_result.add_argument("--result-dir", default=None,
                          help=f"Result directory (default: {DEFAULT_RESULT_DIR})")

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.command == "launch":
        return cmd_launch(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "result":
        return cmd_result(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
