#!/usr/bin/env python3
"""
Delete session files for a specific week after they've been reviewed.

Usage:
  purge_sessions.py --provider codex --week 2025-W36 [--dry-run]

Options:
  --provider NAME   Provider to purge (claude, codex, opencode)
  --week YYYY-WNN   Week to purge (e.g., 2025-W36)
  --dry-run         Show what would be deleted without deleting

ALWAYS use --dry-run first to preview what will be deleted.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def week_to_date_range(week_str: str) -> tuple[datetime, datetime]:
    """Convert ISO week string to start/end datetimes."""
    year, week_num = week_str.split("-W")
    year = int(year)
    week_num = int(week_num)
    # ISO week 1 contains Jan 4
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    start_date = start_of_week1 + timedelta(weeks=week_num - 1)
    end_date = start_date + timedelta(days=7)  # exclusive
    return start_date, end_date


def find_claude_sessions(claude_dir: Path, start: datetime, end: datetime) -> list[Path]:
    """Find Claude Code sessions in date range."""
    sessions = []
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return sessions

    for session_file in projects_dir.rglob("*.jsonl"):
        if session_file.name.startswith("agent-"):
            continue
        try:
            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            if start <= mtime < end:
                sessions.append(session_file)
        except Exception:
            continue
    return sessions


def find_codex_sessions(codex_dir: Path, start: datetime, end: datetime) -> list[Path]:
    """Find Codex sessions in date range."""
    sessions = []
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return sessions

    for session_file in sessions_dir.rglob("rollout-*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            if start <= mtime < end:
                sessions.append(session_file)
        except Exception:
            continue
    return sessions


def find_opencode_sessions(start: datetime, end: datetime) -> list[Path]:
    """Find OpenCode prompt history if modified in date range.

    OpenCode stores prompts in ~/.local/state/opencode/prompt-history.jsonl
    This is a single file with all prompts (no timestamps per-prompt).
    We use file mtime to determine if it falls in the date range.
    """
    sessions = []
    home = Path.home()

    # Primary location: ~/.local/state/opencode/prompt-history.jsonl
    history_file = home / ".local" / "state" / "opencode" / "prompt-history.jsonl"
    if history_file.exists():
        try:
            mtime = datetime.fromtimestamp(history_file.stat().st_mtime)
            if start <= mtime < end:
                sessions.append(history_file)
        except Exception:
            pass

    # Also check session storage in ~/.local/share/opencode/storage/session/
    storage_dir = home / ".local" / "share" / "opencode" / "storage" / "session"
    if storage_dir.exists():
        for session_file in storage_dir.rglob("*.json"):
            try:
                with open(session_file) as f:
                    data = json.load(f)
                created = data.get("time", {}).get("created")
                if created:
                    dt = datetime.fromtimestamp(created / 1000)
                    if start <= dt < end:
                        sessions.append(session_file)
            except Exception:
                continue

    return sessions


def human_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Purge reviewed session files")
    parser.add_argument("--provider", required=True,
                        choices=["claude", "codex", "opencode"],
                        help="Provider to purge")
    parser.add_argument("--week", required=True,
                        help="Week to purge (e.g., 2025-W36)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without deleting")
    args = parser.parse_args()

    home = Path.home()
    start, end = week_to_date_range(args.week)

    # Find sessions
    if args.provider == "claude":
        sessions = find_claude_sessions(home / ".claude", start, end)
    elif args.provider == "codex":
        sessions = find_codex_sessions(home / ".codex", start, end)
    elif args.provider == "opencode":
        sessions = find_opencode_sessions(home / ".local" / "share" / "opencode", start, end)
    else:
        sessions = []

    if not sessions:
        print(f"No {args.provider} sessions found for {args.week}")
        return

    # Calculate total size
    total_size = sum(f.stat().st_size for f in sessions)

    print(f"## {args.provider.capitalize()} Sessions for {args.week}\n")
    print(f"Files: {len(sessions)}")
    print(f"Size: {human_size(total_size)}")
    print("")

    if args.dry_run:
        print("### Files (dry run - nothing deleted)\n")
        for f in sorted(sessions)[:20]:
            print(f"  {f}")
        if len(sessions) > 20:
            print(f"  ... and {len(sessions) - 20} more")
        print("")
        print(f"Run without --dry-run to delete these {len(sessions)} files.")
    else:
        print("### Deleting...\n")
        deleted = 0
        for f in sessions:
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                print(f"  Error deleting {f}: {e}")

        print(f"Deleted {deleted}/{len(sessions)} files")
        print(f"Freed {human_size(total_size)}")


if __name__ == "__main__":
    main()
