#!/usr/bin/env python3
"""
Extract a recent user prompt profile from Claude Code and Codex transcript history.

Usage:
  extract_prompt_profile.py [--source both] [--since week] [--limit 8]
  extract_prompt_profile.py [--project /path/to/repo] [--json]

Outputs recent user prompts plus lightweight style cues that another agent can reuse.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.skill_review import collect_session_data, list_session_files, parse_date, truncate

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "an",
    "and",
    "any",
    "are",
    "around",
    "as",
    "at",
    "be",
    "based",
    "before",
    "below",
    "both",
    "but",
    "by",
    "can",
    "check",
    "claude",
    "codex",
    "code",
    "could",
    "default",
    "draw",
    "for",
    "from",
    "get",
    "give",
    "have",
    "help",
    "how",
    "i",
    "if",
    "in",
    "into",
    "it",
    "its",
    "just",
    "keep",
    "last",
    "let",
    "look",
    "logs",
    "me",
    "my",
    "need",
    "of",
    "on",
    "or",
    "our",
    "out",
    "please",
    "prompt",
    "prompting",
    "prompts",
    "repo",
    "say",
    "should",
    "show",
    "so",
    "tell",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "through",
    "to",
    "transcript",
    "transcripts",
    "use",
    "using",
    "want",
    "week",
    "what",
    "when",
    "with",
    "work",
    "would",
    "you",
    "your",
}

ACTION_WORDS = {
    "add",
    "adjust",
    "analyze",
    "audit",
    "build",
    "change",
    "check",
    "create",
    "debug",
    "design",
    "draw",
    "edit",
    "explain",
    "find",
    "fix",
    "implement",
    "improve",
    "inspect",
    "list",
    "make",
    "move",
    "patch",
    "plan",
    "refactor",
    "rename",
    "review",
    "rewrite",
    "run",
    "scaffold",
    "show",
    "summarize",
    "test",
    "trace",
    "tweak",
    "update",
    "verify",
    "wire",
    "write",
}

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")
CODE_ANCHOR_PATTERN = re.compile(
    r"`[^`]+`|(?:^|[\s(])(?:\.{0,2}/|/)[^\s)]+|\b(?:make|python3|pytest|rg|sed|git|npm|pnpm|uv|xcodebuild)\b|\.[a-z]{2,5}\b",
    re.IGNORECASE,
)
VERIFICATION_PATTERN = re.compile(
    r"\b(test|tests|verify|verification|validate|validation|replay|proof|prove|check)\b",
    re.IGNORECASE,
)
PLANNING_PATTERN = re.compile(
    r"\b(plan|design|architecture|flow|slice|scaffold|strategy|approach|system)\b",
    re.IGNORECASE,
)
REVISION_PATTERN = re.compile(
    r"\b(fix|edit|tweak|patch|change|adjust|rename|move|update|refactor|rewrite)\b",
    re.IGNORECASE,
)
CONSTRAINT_PATTERN = re.compile(
    r"\b(only|avoid|exact|precise|strict|must|should|prefer|keep|never|do not|don't|without)\b",
    re.IGNORECASE,
)
IGNORED_PREFIXES = ("<turn_aborted>",)


def prompt_opener(text: str) -> str | None:
    """Return the first meaningful token in a user message."""
    for token in re.findall(r"[a-z][a-z0-9_-]*", text.lower()):
        if token in {"please", "can", "could", "would", "you", "the", "a", "an"}:
            continue
        return token
    return None


def top_terms(messages: list[str], limit: int = 10) -> list[str]:
    """Return high-signal tokens across the selected user prompts."""
    counts: Counter[str] = Counter()
    for message in messages:
        for token in TOKEN_PATTERN.findall(message.lower()):
            if token in STOPWORDS or token in ACTION_WORDS:
                continue
            if token.isdigit():
                continue
            counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def ratio(messages: list[str], predicate) -> float:
    """Return the fraction of messages matching a predicate."""
    if not messages:
        return 0.0
    return sum(1 for message in messages if predicate(message)) / len(messages)


def build_style_cues(messages: list[str]) -> list[str]:
    """Infer lightweight prompting-style cues from recent user messages."""
    if not messages:
        return ["no recent prompts were available"]

    avg_len = sum(len(" ".join(message.split())) for message in messages) / len(messages)
    cues: list[str] = []

    if avg_len < 120:
        cues.append("brief, directive asks")
    elif avg_len > 260:
        cues.append("dense, spec-heavy asks")
    else:
        cues.append("moderately detailed asks")

    opener_ratio = ratio(messages, lambda message: (prompt_opener(message) or "") in ACTION_WORDS)
    candidate_cues: list[tuple[float, str]] = []
    if opener_ratio >= 0.35:
        candidate_cues.append((opener_ratio, "starts from clear action verbs instead of long scene-setting"))

    code_anchor_ratio = ratio(messages, lambda message: bool(CODE_ANCHOR_PATTERN.search(message)))
    if code_anchor_ratio >= 0.2:
        candidate_cues.append((code_anchor_ratio, "anchors requests in concrete files, commands, and repo paths"))

    verification_ratio = ratio(messages, lambda message: bool(VERIFICATION_PATTERN.search(message)))
    if verification_ratio >= 0.2:
        candidate_cues.append((verification_ratio, "cares about verification, replay, and proof of behavior"))

    planning_ratio = ratio(messages, lambda message: bool(PLANNING_PATTERN.search(message)))
    if planning_ratio >= 0.2:
        candidate_cues.append((planning_ratio, "thinks in plans, slices, and system structure"))

    revision_ratio = ratio(messages, lambda message: bool(REVISION_PATTERN.search(message)))
    if revision_ratio >= 0.2:
        candidate_cues.append((revision_ratio, "iterates through fixes, renames, and tight local edits"))

    constraint_ratio = ratio(messages, lambda message: bool(CONSTRAINT_PATTERN.search(message)))
    if constraint_ratio >= 0.2:
        candidate_cues.append((constraint_ratio, "adds tight constraints and preference edges"))

    question_ratio = ratio(messages, lambda message: "?" in message)
    if question_ratio >= 0.25:
        candidate_cues.append((question_ratio, "uses question-shaped exploration when the problem is still fuzzy"))

    for _, cue in sorted(candidate_cues, key=lambda item: item[0], reverse=True):
        if cue not in cues:
            cues.append(cue)

    if len(cues) == 1:
        cues.append("mixes execution asks with occasional exploratory follow-up")

    return cues[:5]


def common_openers(messages: list[str], limit: int = 8) -> list[dict[str, int | str]]:
    """Return the most common opener tokens across messages."""
    counts: Counter[str] = Counter()
    for message in messages:
        opener = prompt_opener(message)
        if opener:
            counts[opener] += 1
    return [{"token": token, "count": count} for token, count in counts.most_common(limit)]


def matches_project(session: dict, project_filter: str | None) -> bool:
    """Filter sessions by a project substring when requested."""
    if not project_filter:
        return True
    needle = project_filter.lower()
    project = str(session.get("project") or "").lower()
    file_path = str(session.get("file") or "").lower()
    return needle in project or needle in file_path


def usable_messages(messages: list[str]) -> list[str]:
    """Drop transcript wrapper noise that is not meaningful prompt content."""
    cleaned = []
    for message in messages:
        stripped = message.strip()
        if not stripped:
            continue
        if stripped.startswith(IGNORED_PREFIXES):
            continue
        cleaned.append(stripped)
    return cleaned


def build_report(
    *,
    source: str,
    since: datetime,
    until: datetime,
    limit: int,
    project_filter: str | None = None,
    messages_per_session: int = 4,
    max_message_chars: int = 280,
) -> dict:
    """Build a recent prompt profile from transcript history."""
    selected_sessions = []
    provider_counts: Counter[str] = Counter()
    all_messages: list[str] = []

    for provider, path, mtime in list_session_files(source, since, until):
        session = collect_session_data(provider, path, mtime)
        messages = usable_messages(session["user_messages"])
        if not messages:
            continue
        if not matches_project(session, project_filter):
            continue

        provider_counts[provider] += 1
        all_messages.extend(messages)
        selected_sessions.append(
            {
                "provider": provider,
                "project": session["project"],
                "file": session["file"],
                "timestamp": session["timestamp"].isoformat(),
                "message_count": len(messages),
                "messages": [
                    truncate(message, max_message_chars)
                    for message in messages[: max(1, messages_per_session)]
                ],
            }
        )
        if len(selected_sessions) >= limit:
            break

    avg_prompt_length = 0.0
    if all_messages:
        avg_prompt_length = sum(len(" ".join(message.split())) for message in all_messages) / len(all_messages)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "limit": limit,
        "project_filter": project_filter,
        "messages_per_session": messages_per_session,
        "summary": {
            "sessions": len(selected_sessions),
            "prompts": len(all_messages),
            "providers": dict(provider_counts),
            "avg_prompt_length": round(avg_prompt_length, 1),
            "style_cues": build_style_cues(all_messages),
            "top_terms": top_terms(all_messages),
            "common_openers": common_openers(all_messages),
        },
        "sessions": selected_sessions,
    }
    return report


def render_markdown(report: dict) -> str:
    """Render a prompt profile as compact markdown."""
    summary = report["summary"]
    lines = ["## Recent Prompt Profile", ""]
    lines.append(f"Window: `{report['since']}` to `{report['until']}`")
    lines.append(f"Source: `{report['source']}`")
    if report.get("project_filter"):
        lines.append(f"Project filter: `{report['project_filter']}`")
    lines.append(f"Sessions: `{summary['sessions']}`")
    lines.append(f"Prompts: `{summary['prompts']}`")
    lines.append(f"Average prompt length: `{summary['avg_prompt_length']}` characters")
    lines.append("")

    lines.append("### Style Cues")
    lines.append("")
    for cue in summary["style_cues"]:
        lines.append(f"- {cue}")

    if summary["common_openers"]:
        lines.append("")
        lines.append("### Common Openers")
        lines.append("")
        for row in summary["common_openers"]:
            lines.append(f"- `{row['token']}` x{row['count']}")

    if summary["top_terms"]:
        lines.append("")
        lines.append("### Top Terms")
        lines.append("")
        lines.append(", ".join(f"`{term}`" for term in summary["top_terms"]))

    lines.append("")
    lines.append("### Recent Sessions")
    lines.append("")
    if not report["sessions"]:
        lines.append("- No matching sessions found in the selected window.")
    else:
        for session in report["sessions"]:
            lines.append(
                f"#### `{session['timestamp']}` `{session['provider']}` `{session['project']}`"
            )
            lines.append("")
            for message in session["messages"]:
                lines.append(f"- {message}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a recent Claude/Codex prompt profile")
    parser.add_argument(
        "--source",
        choices=("claude", "codex", "both", "all"),
        default="both",
        help="Which transcript source(s) to scan",
    )
    parser.add_argument(
        "--since",
        default="week",
        help="Start date (YYYY-MM-DD or today/yesterday/week/month)",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="End date (YYYY-MM-DD), defaults to now",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum recent sessions to include",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Optional project substring filter",
    )
    parser.add_argument(
        "--messages-per-session",
        type=int,
        default=4,
        help="Maximum prompt excerpts to keep per session",
    )
    parser.add_argument(
        "--max-message-chars",
        type=int,
        default=280,
        help="Maximum characters per emitted prompt excerpt",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args()

    since = parse_date(args.since)
    until = parse_date(args.until) if args.until else datetime.now(timezone.utc)
    report = build_report(
        source=args.source,
        since=since,
        until=until,
        limit=max(1, args.limit),
        project_filter=args.project,
        messages_per_session=max(1, args.messages_per_session),
        max_message_chars=max(80, args.max_message_chars),
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report), end="")


if __name__ == "__main__":
    main()
