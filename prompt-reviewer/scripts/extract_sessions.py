#!/usr/bin/env python3
"""
Extract Claude Code and/or Codex sessions for prompt review analysis.

Usage:
  extract_sessions.py [--source SOURCE] [--project PATH] [--since DATE] [--until DATE] [--limit N]

Options:
  --source SOURCE  Which tool: 'claude', 'codex', or 'both' (default: both)
  --project PATH   Filter to sessions from this project path (Claude Code only)
  --since DATE     Start date (YYYY-MM-DD or 'today', 'yesterday', 'week', 'month')
  --until DATE     End date (YYYY-MM-DD), defaults to now
  --limit N        Max sessions to return (default: 50)

Output: JSON with session metadata and user prompts.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def parse_date(date_str: str) -> datetime:
    """Parse date string into datetime."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if date_str == "today":
        return today
    elif date_str == "yesterday":
        return today - timedelta(days=1)
    elif date_str == "week":
        return today - timedelta(days=7)
    elif date_str == "month":
        return today - timedelta(days=30)
    else:
        return datetime.strptime(date_str, "%Y-%m-%d")


def project_path_to_dir_name(project_path: str) -> str:
    """Convert project path to Claude's directory naming convention."""
    return project_path.replace("/", "-")


def extract_claude_messages(jsonl_path: Path) -> list[dict]:
    """Extract user messages from a Claude Code session file."""
    messages = []
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    # User messages have type="user" and contain the actual user content
                    if entry.get("type") == "user" and not entry.get("isMeta"):
                        msg = entry.get("message", {})
                        content = msg.get("content", "")

                        # Handle both string and list content formats
                        if isinstance(content, list):
                            text_parts = []
                            for block in content:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        text_parts.append(block.get("text", ""))
                                elif isinstance(block, str):
                                    text_parts.append(block)
                            content = "\n".join(text_parts)

                        if content and not content.startswith("<command-"):
                            messages.append({
                                "timestamp": entry.get("timestamp"),
                                "content": content[:2000],
                            })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {jsonl_path}: {e}", file=sys.stderr)
    return messages


def extract_codex_messages(jsonl_path: Path) -> list[dict]:
    """Extract user messages from a Codex session file."""
    messages = []
    seen_content = set()  # Deduplicate messages
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    content = None
                    timestamp = entry.get("timestamp")

                    # Codex format: response_item with role=user
                    if entry.get("type") == "response_item":
                        payload = entry.get("payload", {})
                        if payload.get("role") == "user":
                            content_list = payload.get("content", [])
                            text_parts = []
                            for item in content_list:
                                if isinstance(item, dict) and item.get("type") == "input_text":
                                    text = item.get("text", "")
                                    # Skip environment context blocks
                                    if not text.startswith("<environment_context>"):
                                        text_parts.append(text)
                            content = "\n".join(text_parts)

                    # Also check event_msg type for user messages
                    elif entry.get("type") == "event_msg":
                        payload = entry.get("payload", {})
                        if payload.get("type") == "user_message":
                            content = payload.get("message", "")

                    # Add message if content exists and not a duplicate
                    if content and content not in seen_content:
                        seen_content.add(content)
                        messages.append({
                            "timestamp": timestamp,
                            "content": content[:2000],
                        })

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {jsonl_path}: {e}", file=sys.stderr)
    return messages


def find_claude_sessions(
    claude_dir: Path,
    project_filter: str | None,
    since: datetime,
    until: datetime,
) -> list[dict]:
    """Find Claude Code sessions."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return []

    sessions = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Apply project filter
        if project_filter:
            filter_name = project_path_to_dir_name(project_filter)
            if filter_name not in project_dir.name:
                continue

        # Find session files (UUID.jsonl)
        for session_file in project_dir.glob("*.jsonl"):
            if session_file.name.startswith("agent-"):
                continue

            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            if mtime < since or mtime > until:
                continue

            user_messages = extract_claude_messages(session_file)
            if not user_messages:
                continue

            session_timestamp = user_messages[0].get("timestamp", mtime.isoformat())

            sessions.append({
                "source": "claude",
                "file": str(session_file),
                "project": project_dir.name.replace("-", "/")[1:],
                "timestamp": session_timestamp,
                "message_count": len(user_messages),
                "user_prompts": user_messages,
            })

    return sessions


def find_codex_sessions(
    codex_dir: Path,
    since: datetime,
    until: datetime,
) -> list[dict]:
    """Find Codex sessions."""
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return []

    sessions = []

    # Codex stores by year/month/day
    for session_file in sessions_dir.rglob("*.jsonl"):
        # Skip non-rollout files
        if not session_file.name.startswith("rollout-"):
            continue

        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
        if mtime < since or mtime > until:
            continue

        user_messages = extract_codex_messages(session_file)
        if not user_messages:
            continue

        # Extract project from session metadata
        project = "unknown"
        try:
            with open(session_file, "r") as f:
                first_line = f.readline()
                if first_line:
                    meta = json.loads(first_line)
                    if meta.get("type") == "session_meta":
                        project = meta.get("payload", {}).get("cwd", "unknown")
        except Exception:
            pass

        session_timestamp = user_messages[0].get("timestamp", mtime.isoformat())

        sessions.append({
            "source": "codex",
            "file": str(session_file),
            "project": project,
            "timestamp": session_timestamp,
            "message_count": len(user_messages),
            "user_prompts": user_messages,
        })

    return sessions


def main():
    parser = argparse.ArgumentParser(description="Extract sessions for prompt review analysis")
    parser.add_argument("--source", choices=["claude", "codex", "both"], default="both",
                        help="Which tool to analyze")
    parser.add_argument("--project", help="Filter to sessions from this project path (Claude only)")
    parser.add_argument("--since", default="today",
                        help="Start date (YYYY-MM-DD or today/yesterday/week/month)")
    parser.add_argument("--until", help="End date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=50, help="Max sessions to return")
    args = parser.parse_args()

    home = Path.home()
    claude_dir = home / ".claude"
    codex_dir = home / ".codex"

    since = parse_date(args.since)
    until = datetime.now() if not args.until else parse_date(args.until) + timedelta(days=1)

    sessions = []

    if args.source in ("claude", "both"):
        sessions.extend(find_claude_sessions(claude_dir, args.project, since, until))

    if args.source in ("codex", "both"):
        sessions.extend(find_codex_sessions(codex_dir, since, until))

    # Sort by timestamp (newest first) and limit
    sessions.sort(key=lambda s: s["timestamp"], reverse=True)
    sessions = sessions[:args.limit]

    result = {
        "query": {
            "source": args.source,
            "project": args.project,
            "since": since.isoformat(),
            "until": until.isoformat(),
            "limit": args.limit,
        },
        "session_count": len(sessions),
        "total_prompts": sum(s["message_count"] for s in sessions),
        "claude_sessions": len([s for s in sessions if s["source"] == "claude"]),
        "codex_sessions": len([s for s in sessions if s["source"] == "codex"]),
        "sessions": sessions,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
