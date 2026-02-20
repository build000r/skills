#!/usr/bin/env python3
"""
Check status of background Codex workers.

The agent calls this instead of polling. Each worker writes a
JSON status marker when it starts (RUNNING) and updates it when
it finishes (DONE/FAILED). This script reads those markers and
prints a summary.

Default output shows only: status, exit code, and artifact paths.
Worker logs (raw Codex output) are hidden to protect orchestrator
context budget. Use --verbose to include log paths for debugging.

Usage:
    python3 check_workers.py              # show all (artifacts only)
    python3 check_workers.py --wait       # block until all RUNNING workers finish
    python3 check_workers.py --label X    # filter to one worker
    python3 check_workers.py --verbose    # include log file paths
    python3 check_workers.py --clear      # remove completed status files
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


DEFAULT_STATUS_DIR = Path("/tmp/domain-reviewer-logs/status")


def _read_statuses(status_dir: Path, label_filter: str | None = None) -> list[dict]:
    if not status_dir.exists():
        return []
    results = []
    for p in sorted(status_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if label_filter and data.get("label") != label_filter:
            continue
        results.append(data)
    return results


def _is_process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _print_summary(statuses: list[dict], verbose: bool = False) -> None:
    if not statuses:
        print("No workers found.")
        return

    running = 0
    done = 0
    failed = 0

    for s in statuses:
        status = s.get("status", "UNKNOWN")
        label = s.get("label", "?")
        pid = s.get("pid")
        exit_code = s.get("exit_code")
        artifacts = s.get("artifacts", [])

        # Detect zombie: marked RUNNING but process is dead
        if status == "RUNNING" and not _is_process_alive(pid):
            status = "ZOMBIE (process gone)"
            failed += 1
        elif status == "RUNNING":
            running += 1
        elif status == "DONE":
            done += 1
        elif status == "FAILED":
            failed += 1

        icon = {"RUNNING": "...", "DONE": "OK", "FAILED": "XX"}.get(status, "??")
        exit_str = f"exit {exit_code}" if exit_code is not None else ""
        print(f"  [{icon}] {label}: {status} {exit_str}")

        # Show artifacts (this is what the agent should read)
        if artifacts:
            for a in artifacts:
                print(f"       artifact: {a}")
        elif status == "DONE":
            print(f"       (no artifacts detected)")

        # Log path only with --verbose (for human debugging, not agent consumption)
        if verbose:
            log_file = s.get("_log_file") or s.get("log_file", "")
            if log_file:
                print(f"       log: {log_file}")

    print(f"\nTotal: {len(statuses)} workers — {running} running, {done} done, {failed} failed")

    if running == 0:
        print("All workers finished.")


def _wait_all(status_dir: Path, label_filter: str | None, poll_interval: float = 2.0) -> list[dict]:
    """Poll until no RUNNING workers remain."""
    while True:
        statuses = _read_statuses(status_dir, label_filter)
        still_running = [
            s for s in statuses
            if s.get("status") == "RUNNING" and _is_process_alive(s.get("pid"))
        ]
        if not still_running:
            return statuses
        labels = ", ".join(s["label"] for s in still_running)
        print(f"Waiting on {len(still_running)} workers: {labels}")
        time.sleep(poll_interval)


def _clear_done(status_dir: Path) -> int:
    """Remove status files for completed workers."""
    removed = 0
    for p in status_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") in ("DONE", "FAILED"):
            p.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Check status of background Codex workers.")
    parser.add_argument("--status-dir", default=str(DEFAULT_STATUS_DIR), help="Status directory")
    parser.add_argument("--label", default=None, help="Filter to a specific worker label")
    parser.add_argument("--wait", action="store_true", help="Block until all workers finish")
    parser.add_argument("--clear", action="store_true", help="Remove completed status files")
    parser.add_argument("--verbose", action="store_true", help="Include log file paths (for debugging)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    args = parser.parse_args()

    status_dir = Path(args.status_dir)

    if args.clear:
        removed = _clear_done(status_dir)
        print(f"Cleared {removed} completed status files.")
        return 0

    if args.wait:
        statuses = _wait_all(status_dir, args.label)
    else:
        statuses = _read_statuses(status_dir, args.label)

    if args.json_output:
        # JSON mode: strip _log_file unless verbose
        output = statuses
        if not args.verbose:
            output = [
                {k: v for k, v in s.items() if k != "_log_file"}
                for s in statuses
            ]
        print(json.dumps(output, indent=2))
    else:
        _print_summary(statuses, verbose=args.verbose)

    # Exit code: 0 if all done/ok, 1 if any failed, 2 if still running
    has_failed = any(s.get("status") == "FAILED" or (s.get("exit_code") or 0) != 0 for s in statuses)
    has_running = any(s.get("status") == "RUNNING" for s in statuses)
    if has_failed:
        return 1
    if has_running:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
