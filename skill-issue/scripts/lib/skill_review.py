"""
Helpers for reviewing skill usage across Claude Code and Codex session logs.
"""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REVIEW_HISTORY_FILE = Path.home() / ".claude" / "skill-review-history.jsonl"
MARKERS_DIR = Path.home() / ".claude" / "skill-markers"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

INSTRUCTION_END_MARKERS = (
    "</environment_context>",
    "</INSTRUCTIONS>",
    "</instructions>",
)

VALIDATION_PATTERNS = [
    re.compile(
        pattern,
        re.IGNORECASE,
    )
    for pattern in (
        r"\bquick_validate\.py\b",
        r"\bpackage_skill\.py\b",
        r"\blink-skills\.sh\b",
        r"\bpytest\b",
        r"\bcargo test\b",
        r"\bnpm test\b",
        r"\bpnpm test\b",
        r"\bbun test\b",
        r"\buv run pytest\b",
        r"\bmake (test|check)\b",
        r"\bscripts/check\.sh\b",
    )
]

CHECKPOINT_PATTERN = re.compile(
    r"\b(do you want|want me to|should i|would you like|okay to|confirm|is that okay|should we|do we need to|does this look good)\b",
    re.IGNORECASE,
)

CORRECTION_PATTERN = re.compile(
    r"\b(actually|instead|don't|do not|wrong|missed|why did|you need to|should have|not what i meant|rather than)\b",
    re.IGNORECASE,
)

RISK_GATING_PATTERN = re.compile(
    r"\b("
    r"wait until|hold on|not yet|should have asked|needed to ask|"
    r"ask further questions|ask first|clarify first|clarify if required|"
    r"confirm first|check first|"
    r"before (?:diving in|proceeding|upload(?:ing)?|email(?:ing)?|"
    r"send(?:ing)?|ship(?:ping)?|publish(?:ing)?|post(?:ing)?|deploy(?:ing)?)|"
    r"human in the loop|lawyer in the loop"
    r")\b",
    re.IGNORECASE,
)

RISK_GATING_ACTION_PATTERN = re.compile(
    r"\b(ask|clarify|confirm|check(?: with)?|approval|approve|sign[- ]?off|reach out to)\b",
    re.IGNORECASE,
)

RISK_GATING_BOUNDARY_PATTERN = re.compile(
    r"\b(before|first|until|prior to|if required|in the loop)\b",
    re.IGNORECASE,
)

COMMAND_STEM_EXCLUDE = {"python", "python3", "bash", "sh", "zsh", "env"}


def parse_date(date_str: str | None) -> datetime:
    """Parse date strings like today/week/month or YYYY-MM-DD."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_str or date_str == "today":
        return today
    if date_str == "yesterday":
        return today - timedelta(days=1)
    if date_str == "week":
        return today - timedelta(days=7)
    if date_str == "month":
        return today - timedelta(days=30)
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def load_marker(skill: str) -> dict[str, Any] | None:
    """Load the last review marker for a skill when present."""
    marker_path = MARKERS_DIR / f"{skill}.json"
    if not marker_path.exists():
        return None
    try:
        return json.loads(marker_path.read_text())
    except json.JSONDecodeError:
        return None


def iso_week(dt: datetime) -> str:
    """Return ISO week string like 2026-W11."""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def parse_timestamp(value: str | None, fallback: datetime) -> datetime:
    """Parse an ISO timestamp with a safe fallback."""
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback


def strip_instruction_preamble(text: str) -> str:
    """Drop embedded AGENTS/environment blocks from user prompts when present."""
    cleaned = text.strip()
    cleaned = re.sub(r"<environment_context>.*?</environment_context>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<collaboration_mode>.*?</collaboration_mode>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<permissions instructions>.*?</permissions instructions>", "", cleaned, flags=re.DOTALL)
    for marker in INSTRUCTION_END_MARKERS:
        idx = cleaned.rfind(marker)
        if idx != -1:
            tail = cleaned[idx + len(marker):].strip()
            if tail:
                cleaned = tail
                break
    return cleaned


def normalize_user_message(text: str) -> str | None:
    """Return meaningful user text or None for wrapper/system injection blocks."""
    cleaned = strip_instruction_preamble(text).strip()
    if not cleaned:
        return None

    wrapper_starts = (
        "# AGENTS.md instructions",
        "<INSTRUCTIONS>",
        "<environment_context>",
        "<skill>",
        "<permissions instructions>",
        "<collaboration_mode>",
    )
    if cleaned.startswith(wrapper_starts):
        return None
    return cleaned


def truncate(text: str, max_chars: int = 240) -> str:
    """Truncate text for compact JSON output."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def skill_token_regex(skill: str) -> re.Pattern[str]:
    """Match a skill token in prose or paths."""
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(skill)}(?=$|[^A-Za-z0-9-])", re.IGNORECASE)


def is_assistant_ack(message: str, skill: str) -> bool:
    """Detect the conventional skill acknowledgement line."""
    return bool(
        re.search(
            rf"\busing\s+`?{re.escape(skill)}`?\b",
            message,
            re.IGNORECASE,
        )
    )


def has_user_trigger(message: str, skill: str) -> bool:
    """Detect an explicit user request for a skill after stripping prompt boilerplate."""
    cleaned = normalize_user_message(message)
    if not cleaned:
        return False

    if re.search(rf"\${re.escape(skill)}\b", cleaned, re.IGNORECASE):
        return True

    if not skill_token_regex(skill).search(cleaned):
        return False

    return bool(
        re.search(
            r"\b(use|update|improve|fix|build|create|design|review|audit|mode|skill)\b",
            cleaned,
            re.IGNORECASE,
        )
    )


def command_stem(command: str) -> str | None:
    """Return a compact command stem from a shell command string."""
    command = command.strip()
    if not command:
        return None

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    if not parts:
        return None

    stem = Path(parts[0]).name
    if stem in COMMAND_STEM_EXCLUDE and len(parts) > 1:
        return Path(parts[1]).name
    return stem


def normalize_tool_name(name: Any) -> str | None:
    """Return a normalized tool/function name when present."""
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    return normalized or None


def find_skill_path_hits(value: Any, skill: str) -> list[str]:
    """Collect strings from nested JSON-like data that mention a skill path."""
    hits: list[str] = []
    token = skill_token_regex(skill)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for child in node.values():
                _walk(child)
            return
        if isinstance(node, list):
            for child in node:
                _walk(child)
            return
        if not isinstance(node, str):
            return

        if token.search(node) and ("/" in node or ".md" in node or ".py" in node or ".skill" in node):
            hits.append(truncate(node, 220))

    _walk(value)
    return hits


def is_checkpoint_message(message: str) -> bool:
    """Detect user-facing checkpoint prompts rather than normal progress updates."""
    return "?" in message and bool(CHECKPOINT_PATTERN.search(message))


def is_risk_gating_message(message: str) -> bool:
    """Detect user cues that the run should have paused before a risky boundary."""
    if RISK_GATING_PATTERN.search(message):
        return True
    return bool(
        RISK_GATING_ACTION_PATTERN.search(message)
        and RISK_GATING_BOUNDARY_PATTERN.search(message)
    )


def extract_codex_user_text(entry: dict[str, Any]) -> str | None:
    """Extract user text from a Codex session line."""
    entry_type = entry.get("type")
    payload = entry.get("payload", {})

    if entry_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
        parts = []
        for item in payload.get("content", []):
            if item.get("type") == "input_text":
                text = item.get("text", "")
                if text and not text.startswith("<environment_context>"):
                    parts.append(text)
        return "\n".join(parts).strip() or None

    if entry_type == "event_msg" and payload.get("type") == "user_message":
        text = payload.get("message", "")
        return text.strip() or None

    return None


def extract_codex_assistant_text(entry: dict[str, Any]) -> str | None:
    """Extract assistant text from a Codex session line."""
    entry_type = entry.get("type")
    payload = entry.get("payload", {})

    if entry_type == "event_msg" and payload.get("type") == "agent_message":
        text = payload.get("message", "")
        return text.strip() or None

    if entry_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "assistant":
        parts = []
        for item in payload.get("content", []):
            if item.get("type") == "output_text":
                text = item.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip() or None

    if entry_type == "event_msg" and payload.get("type") == "task_complete":
        text = payload.get("last_agent_message")
        if isinstance(text, str):
            return text.strip() or None
        return None

    return None


def extract_claude_user_text(entry: dict[str, Any]) -> str | None:
    """Extract user text from a Claude Code session line."""
    if entry.get("type") != "user":
        return None

    message = entry.get("message", {})
    if message.get("role") != "user":
        return None

    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip() or None

    return None


def extract_claude_assistant_text(entry: dict[str, Any]) -> list[str]:
    """Extract assistant text blocks from a Claude Code session line."""
    if entry.get("type") != "assistant":
        return []

    message = entry.get("message", {})
    if message.get("role") != "assistant":
        return []

    texts = []
    for block in message.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                texts.append(text.strip())
    return texts


def extract_codex_function_call(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a Codex function call payload."""
    if entry.get("type") != "response_item":
        return None

    payload = entry.get("payload", {})
    if payload.get("type") != "function_call":
        return None

    arguments = payload.get("arguments")
    parsed_arguments: Any = arguments
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_arguments = arguments

    command = None
    if isinstance(parsed_arguments, dict):
        command = parsed_arguments.get("cmd") or parsed_arguments.get("command")

    return {
        "name": payload.get("name"),
        "arguments": parsed_arguments,
        "command": command,
    }


def extract_claude_tool_uses(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract Claude tool_use blocks in a Codex-like shape."""
    if entry.get("type") != "assistant":
        return []

    message = entry.get("message", {})
    if message.get("role") != "assistant":
        return []

    tool_uses = []
    for block in message.get("content", []):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            input_value = block.get("input")
            command = None
            if isinstance(input_value, dict):
                command = input_value.get("command") or input_value.get("cmd")
            tool_uses.append(
                {
                    "name": block.get("name"),
                    "arguments": input_value,
                    "command": command,
                }
            )
    return tool_uses


def list_session_files(source: str, since: datetime, until: datetime) -> list[tuple[str, Path, datetime]]:
    """List Claude/Codex session files in descending modified-time order."""
    items: list[tuple[str, Path, datetime]] = []

    include_codex = source in {"codex", "both", "all"}
    include_claude = source in {"claude", "both", "all"}

    if include_codex and CODEX_SESSIONS_DIR.exists():
        for path in CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"):
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if since <= mtime <= until:
                items.append(("codex", path, mtime))

    if include_claude and CLAUDE_PROJECTS_DIR.exists():
        for path in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
            if path.name.startswith("agent-"):
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if since <= mtime <= until:
                items.append(("claude", path, mtime))

    items.sort(key=lambda item: item[2], reverse=True)
    return items


def collect_session_data(provider: str, path: Path, mtime: datetime) -> dict[str, Any]:
    """Collect normalized messages and tool calls from one transcript file."""
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    function_calls: list[dict[str, Any]] = []
    task_complete = False
    project = None
    timestamp = mtime

    seen_user = set()
    seen_assistant = set()

    with open(path, "r") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if provider == "codex":
                if entry.get("type") == "session_meta":
                    project = entry.get("payload", {}).get("cwd") or project
                    timestamp = parse_timestamp(entry.get("timestamp"), timestamp)

                text = extract_codex_user_text(entry)
                if text:
                    cleaned = normalize_user_message(text)
                    if cleaned and cleaned not in seen_user:
                        seen_user.add(cleaned)
                        user_messages.append(cleaned)

                text = extract_codex_assistant_text(entry)
                if text and text not in seen_assistant:
                    seen_assistant.add(text)
                    assistant_messages.append(text)

                call = extract_codex_function_call(entry)
                if call:
                    function_calls.append(call)

                if entry.get("type") == "event_msg" and entry.get("payload", {}).get("type") == "task_complete":
                    task_complete = True

            else:
                text = extract_claude_user_text(entry)
                if text:
                    cleaned = normalize_user_message(text)
                    if cleaned and cleaned not in seen_user:
                        seen_user.add(cleaned)
                        user_messages.append(cleaned)

                for text in extract_claude_assistant_text(entry):
                    if text and text not in seen_assistant:
                        seen_assistant.add(text)
                        assistant_messages.append(text)

                function_calls.extend(extract_claude_tool_uses(entry))

    return {
        "provider": provider,
        "file": str(path),
        "project": project or infer_project_from_path(provider, path),
        "timestamp": timestamp,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "function_calls": function_calls,
        "task_complete": task_complete,
    }


def parse_session(provider: str, path: Path, mtime: datetime, skill: str) -> dict[str, Any]:
    """Parse a Claude/Codex transcript into a skill-invocation summary."""
    validation_commands: list[str] = []
    checkpoint_messages: list[str] = []
    correction_messages: list[str] = []
    risk_gating_messages: list[str] = []
    command_stems: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    touched_paths: list[str] = []
    matched_on: set[str] = set()
    seen_paths = set()
    session = collect_session_data(provider, path, mtime)
    user_messages = session["user_messages"]
    assistant_messages = session["assistant_messages"]
    function_calls = session["function_calls"]
    task_complete = session["task_complete"]

    for text in user_messages:
        if has_user_trigger(text, skill):
            matched_on.add("user_trigger")
        if CORRECTION_PATTERN.search(text):
            correction_messages.append(truncate(text))
        if is_risk_gating_message(text):
            risk_gating_messages.append(truncate(text))

    for text in assistant_messages:
        if is_assistant_ack(text, skill):
            matched_on.add("assistant_ack")
        if is_checkpoint_message(text):
            checkpoint_messages.append(truncate(text))

    for call in function_calls:
        tool_name = normalize_tool_name(call.get("name"))
        if tool_name:
            tool_counts[tool_name] += 1

        command = call.get("command")
        if command:
            for pattern in VALIDATION_PATTERNS:
                if pattern.search(command):
                    validation_commands.append(truncate(command))
                    break
            stem = command_stem(command)
            if stem:
                command_stems[stem] += 1

        for hit in find_skill_path_hits(call.get("arguments"), skill):
            if hit not in seen_paths:
                seen_paths.add(hit)
                touched_paths.append(hit)
                matched_on.add("skill_path")

    match_score = 0
    if "assistant_ack" in matched_on:
        match_score += 3
    if "skill_path" in matched_on:
        match_score += 2
    if "user_trigger" in matched_on:
        match_score += 1

    return {
        "provider": provider,
        "file": session["file"],
        "project": session["project"],
        "timestamp": session["timestamp"].isoformat(),
        "matched_on": sorted(matched_on),
        "match_score": match_score,
        "user_request": truncate(user_messages[0], 500) if user_messages else None,
        "assistant_ack": next(
            (truncate(msg, 500) for msg in assistant_messages if is_assistant_ack(msg, skill)),
            None,
        ),
        "validation_commands": validation_commands,
        "checkpoint_messages": checkpoint_messages[:5],
        "user_corrections": correction_messages[:5],
        "risk_gating_messages": risk_gating_messages[:5],
        "touched_paths": touched_paths[:10],
        "tool_calls": sum(tool_counts.values()),
        "tool_counts": dict(tool_counts),
        "command_stems": dict(command_stems),
        "task_complete": task_complete,
    }


def infer_project_from_path(provider: str, path: Path) -> str:
    """Infer a project label from a transcript path when metadata is absent."""
    if provider == "claude":
        return path.parent.name.replace("-", "/")[1:] if path.parent.name.startswith("-") else path.parent.name
    return "unknown"


def build_tool_count_rows(
    tool_counts: Counter[str],
    provider_tool_counts: dict[str, Counter[str]] | None = None,
) -> list[dict[str, Any]]:
    """Render tool counters as stable JSON rows."""
    provider_tool_counts = provider_tool_counts or {}
    rows = []
    for tool, count in sorted(tool_counts.items(), key=lambda item: (-item[1], item[0])):
        providers = {}
        for provider in sorted(provider_tool_counts):
            provider_count = provider_tool_counts[provider].get(tool, 0)
            if provider_count:
                providers[provider] = provider_count
        row = {
            "tool": tool,
            "count": count,
        }
        if providers:
            row["providers"] = providers
        rows.append(row)
    return rows


def build_opportunities(
    skill: str,
    source: str,
    invocations: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate improvement opportunities from review heuristics."""
    opportunities: list[dict[str, Any]] = []

    marker_gaps = [
        inv for inv in invocations
        if "skill_path" in inv["matched_on"] and "assistant_ack" not in inv["matched_on"]
    ]
    if marker_gaps:
        opportunities.append(
            {
                "id": "ack-marker",
                "priority": "high",
                "summary": (
                    f"Some {skill} runs touched skill files without an explicit `Using {skill}` "
                    "commentary marker. Make the first progress update mandatory and stable so last-use "
                    "detection does not depend on path heuristics."
                ),
                "evidence": [
                    {
                        "timestamp": inv["timestamp"],
                        "file": inv["file"],
                    }
                    for inv in marker_gaps[:3]
                ],
            }
        )

    missing_validation = [inv for inv in invocations if not inv["validation_commands"]]
    if missing_validation and summary["metrics"]["validation_rate"] < 0.75:
        opportunities.append(
            {
                "id": "verification-gap",
                "priority": "high",
                "summary": (
                    "Validation coverage is low relative to the number of detected invocations. "
                    "Add a required verification block with concrete commands and a 'do not hand back "
                    "untested changes' rule."
                ),
                "evidence": [
                    {
                        "timestamp": inv["timestamp"],
                        "file": inv["file"],
                    }
                    for inv in missing_validation[:3]
                ],
            }
        )

    checkpoint_examples = [inv for inv in invocations if inv["checkpoint_messages"]]
    if checkpoint_examples and summary["metrics"]["checkpoint_rate"] >= 0.25:
        opportunities.append(
            {
                "id": "checkpoint-defaults",
                "priority": "medium",
                "summary": (
                    "Checkpoint prompts are still common. Move repeated preferences into mode files or "
                    "default decision rules so human checkpoints are reserved for missing information or "
                    "high-risk operations."
                ),
                "evidence": [
                    {
                        "timestamp": inv["timestamp"],
                        "message": inv["checkpoint_messages"][0],
                    }
                    for inv in checkpoint_examples[:3]
                ],
            }
        )

    risk_gating_examples = [inv for inv in invocations if inv["risk_gating_messages"]]
    if risk_gating_examples and summary["metrics"]["risk_gating_rate"] >= 0.1:
        opportunities.append(
            {
                "id": "risk-gating-gap",
                "priority": "high",
                "summary": (
                    "Users are explicitly flagging steps that should have paused for confirmation, "
                    "clarification, or outside review before proceeding. Add risk-gating rules so "
                    "irreversible or high-risk branches are not treated as defaults."
                ),
                "evidence": [
                    {
                        "timestamp": inv["timestamp"],
                        "message": inv["risk_gating_messages"][0],
                    }
                    for inv in risk_gating_examples[:3]
                ],
            }
        )

    correction_examples = [inv for inv in invocations if inv["user_corrections"]]
    if correction_examples and summary["metrics"]["correction_rate"] >= 0.15:
        opportunities.append(
            {
                "id": "contract-clarity",
                "priority": "medium",
                "summary": (
                    "Users are redirecting the run after it starts. Tighten trigger language, non-goals, "
                    "and ask-cascade guidance so the skill picks the right path earlier."
                ),
                "evidence": [
                    {
                        "timestamp": inv["timestamp"],
                        "message": inv["user_corrections"][0],
                    }
                    for inv in correction_examples[:3]
                ],
            }
        )

    top_stems = summary.get("top_command_stems", [])
    raw_shell_stems = [item for item in top_stems if item["stem"] in {"rg", "sed", "find", "git", "ls"}]
    if raw_shell_stems and raw_shell_stems[0]["count"] >= 4:
        stems = ", ".join(item["stem"] for item in raw_shell_stems[:3])
        opportunities.append(
            {
                "id": "automation-gap",
                "priority": "medium",
                "summary": (
                    f"Repeated ad-hoc shell work ({stems}) shows up across invocations. Bundle the recurring "
                    "analysis path into helper scripts or references so reliability is not gated on freehand shell usage."
                ),
                "evidence": raw_shell_stems[:3],
            }
        )

    if source in {"claude", "both", "all"} and summary["providers"].get("claude", 0) == 0:
        opportunities.append(
            {
                "id": "provider-coverage",
                "priority": "low",
                "summary": (
                    "No Claude Code invocations were matched in the selected range. Detection and markers are "
                    "currently validated on Codex logs only."
                ),
                "evidence": [],
            }
        )

    return opportunities


def scan_skill_invocations(
    skill: str,
    source: str = "both",
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Scan Claude/Codex logs for past invocations of a skill."""
    since = since or parse_date("month")
    until = until or datetime.now(timezone.utc)

    invocations: list[dict[str, Any]] = []
    sessions_scanned = 0
    providers = Counter()
    stems = Counter()
    tools = Counter()
    provider_tools: dict[str, Counter[str]] = defaultdict(Counter)

    for provider, path, mtime in list_session_files(source, since, until):
        sessions_scanned += 1
        parsed = parse_session(provider, path, mtime, skill)
        if parsed["match_score"] < 2:
            continue
        invocations.append(parsed)
        providers[provider] += 1
        stems.update(parsed["command_stems"])
        tools.update(parsed["tool_counts"])
        provider_tools[provider].update(parsed["tool_counts"])
        if len(invocations) >= limit:
            break

    invocations.sort(key=lambda item: item["timestamp"], reverse=True)
    last_invoked_at = invocations[0]["timestamp"] if invocations else None
    total = len(invocations)

    def rate(predicate: Any) -> float:
        if total == 0:
            return 0.0
        return round(sum(1 for item in invocations if predicate(item)) / total, 3)

    summary = {
        "providers": dict(providers),
        "metrics": {
            "ack_rate": rate(lambda item: "assistant_ack" in item["matched_on"]),
            "validation_rate": rate(lambda item: bool(item["validation_commands"])),
            "checkpoint_rate": rate(lambda item: bool(item["checkpoint_messages"])),
            "risk_gating_rate": rate(lambda item: bool(item["risk_gating_messages"])),
            "correction_rate": rate(lambda item: bool(item["user_corrections"])),
            "completion_rate": rate(lambda item: item["task_complete"]),
        },
        "top_command_stems": [
            {"stem": stem, "count": count}
            for stem, count in stems.most_common(8)
        ],
        "total_tool_calls": sum(tools.values()),
        "unique_tools": len(tools),
        "top_tools": build_tool_count_rows(tools, provider_tools)[:8],
    }

    report = {
        "skill": skill,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "sessions_scanned": sessions_scanned,
        "invocations_found": total,
        "last_invoked_at": last_invoked_at,
        "summary": summary,
        "tool_counts": build_tool_count_rows(tools, provider_tools),
        "invocations": invocations,
    }
    report["opportunities"] = build_opportunities(skill, source, invocations, summary)
    return report


def scan_tool_invocations(
    source: str = "both",
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
    skill: str | None = None,
) -> dict[str, Any]:
    """Count raw tool/function invocations across transcript files."""
    since = since or parse_date("month")
    until = until or datetime.now(timezone.utc)

    sessions_scanned = 0
    sessions_matched = 0
    sessions_with_tool_calls = 0
    providers = Counter()
    tool_counts = Counter()
    provider_tools: dict[str, Counter[str]] = defaultdict(Counter)

    for provider, path, mtime in list_session_files(source, since, until):
        sessions_scanned += 1

        if skill:
            session = parse_session(provider, path, mtime, skill)
            if session["match_score"] < 2:
                continue
            session_tool_counts = Counter(session["tool_counts"])
        else:
            session_data = collect_session_data(provider, path, mtime)
            session_tool_counts = Counter()
            for call in session_data["function_calls"]:
                tool_name = normalize_tool_name(call.get("name"))
                if tool_name:
                    session_tool_counts[tool_name] += 1

        sessions_matched += 1
        providers[provider] += 1

        if session_tool_counts:
            sessions_with_tool_calls += 1
            tool_counts.update(session_tool_counts)
            provider_tools[provider].update(session_tool_counts)

        if limit is not None and sessions_matched >= limit:
            break

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "skill": skill,
        "limit": limit,
        "sessions_scanned": sessions_scanned,
        "sessions_matched": sessions_matched,
        "sessions_with_tool_calls": sessions_with_tool_calls,
        "providers": dict(providers),
        "summary": {
            "total_tool_calls": sum(tool_counts.values()),
            "unique_tools": len(tool_counts),
            "top_tools": build_tool_count_rows(tool_counts, provider_tools)[:12],
        },
        "tool_counts": build_tool_count_rows(tool_counts, provider_tools),
    }


def write_marker(report: dict[str, Any]) -> Path:
    """Write the lightweight last-seen marker for a skill review run."""
    MARKERS_DIR.mkdir(parents=True, exist_ok=True)
    marker_path = MARKERS_DIR / f"{report['skill']}.json"
    marker = {
        "skill": report["skill"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_invoked_at": report.get("last_invoked_at"),
        "reviewed_since": report.get("since"),
        "reviewed_until": report.get("until"),
        "since_source": report.get("since_source"),
        "invocations_found": report.get("invocations_found", 0),
        "providers": report.get("summary", {}).get("providers", {}),
        "history_file": str(REVIEW_HISTORY_FILE),
    }
    marker_path.write_text(json.dumps(marker, indent=2) + "\n")
    return marker_path


def load_history(skill: str | None = None) -> list[dict[str, Any]]:
    """Load persisted skill review history."""
    if not REVIEW_HISTORY_FILE.exists():
        return []

    records = []
    with open(REVIEW_HISTORY_FILE, "r") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skill and record.get("skill") != skill:
                continue
            records.append(record)
    return records


def aggregate_history_by_week(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate saved review history by ISO week."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record.get("week", "unknown")].append(record)

    aggregated: dict[str, dict[str, Any]] = {}
    for week, items in sorted(grouped.items()):
        count = len(items)
        invocations = sum(item.get("invocations", 0) for item in items)
        metrics = {}
        for key in (
            "ack_rate",
            "validation_rate",
            "checkpoint_rate",
            "risk_gating_rate",
            "correction_rate",
            "completion_rate",
        ):
            values = [item.get("metrics", {}).get(key, 0.0) for item in items]
            metrics[key] = round(sum(values) / len(values), 3) if values else 0.0
        aggregated[week] = {
            "reviews": count,
            "invocations": invocations,
            "metrics": metrics,
        }
    return aggregated
