#!/usr/bin/env python3
"""
Extract the current ready frontier from a WORKGRAPH.md file.

WORKGRAPH.md is expected to contain a fenced ```json block with:

{
  "nodes": [
    {
      "id": "WG-001",
      "title": "Backend API",
      "concern": "backend-api",
      "repo": "backend",
      "depends_on": [],
      "writes": ["src/domain/**"],
      "done_when": ["Contract implemented"],
      "validate_cmds": ["npm test -- backend-api"],
      "risk_gate": "none",
      "status": "todo"
    }
  ]
}
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path


DONE_STATES = {"done", "skipped"}
ACTIVE_STATES = {"in_progress"}
BLOCKED_STATES = {"blocked"}
PENDING_STATES = {"todo", "ready", "planned", "open", ""}
PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:todo|tbd|fill me in|placeholder|later)\b", re.IGNORECASE),
    re.compile(r"\b(?:n/?a|none)\b", re.IGNORECASE),
    re.compile(r"\bBinary completion check\b", re.IGNORECASE),
    re.compile(r"\bConcrete validation command\b", re.IGNORECASE),
)


def extract_json_block(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError("No fenced ```json block found in WORKGRAPH.md")
    return json.loads(match.group(1))


def _prefix_info(path_pattern: str) -> tuple[str, bool]:
    match = re.search(r"[*?\[]", path_pattern)
    raw_prefix = path_pattern[: match.start()] if match else path_pattern
    prefix = raw_prefix.rstrip("/")
    partial_segment_glob = bool(match and raw_prefix and not raw_prefix.endswith("/"))
    return prefix, partial_segment_glob


def normalize_prefix(path_pattern: str) -> str:
    prefix, _ = _prefix_info(path_pattern)
    return prefix


def prefix_contains(parent: str, child: str) -> bool:
    return child == parent or child.startswith(parent + "/")


def writes_overlap(left: list[str], right: list[str]) -> bool:
    for a in left:
        for b in right:
            if a == b:
                return True
            a_prefix, a_partial_segment_glob = _prefix_info(a)
            b_prefix, b_partial_segment_glob = _prefix_info(b)
            if not a_prefix or not b_prefix:
                continue
            if prefix_contains(a_prefix, b_prefix) or prefix_contains(b_prefix, a_prefix):
                return True
            if (
                a_partial_segment_glob
                and b_prefix.startswith(a_prefix)
                or b_partial_segment_glob
                and a_prefix.startswith(b_prefix)
            ):
                return True
    return False


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            stripped = item.strip()
            if stripped:
                items.append(stripped)
        return items
    return []


def _has_placeholder(items: list[str]) -> bool:
    for item in items:
        if any(pattern.search(item) for pattern in PLACEHOLDER_PATTERNS):
            return True
    return False


def _node_contract_issues(node: dict) -> list[str]:
    issues: list[str] = []
    node_id = node.get("id") or "<unknown>"

    done_when = _normalize_string_list(node.get("done_when"))
    validate_cmds = _normalize_string_list(node.get("validate_cmds"))

    if not done_when:
        issues.append(f"{node_id}: missing done_when contract")
    elif _has_placeholder(done_when):
        issues.append(f"{node_id}: done_when contains placeholder text")

    if not validate_cmds:
        issues.append(f"{node_id}: missing validate_cmds contract")
    elif _has_placeholder(validate_cmds):
        issues.append(f"{node_id}: validate_cmds contains placeholder text")

    writes = node.get("writes", [])
    if writes is not None and not isinstance(writes, list):
        issues.append(f"{node_id}: writes must be a list or null")

    depends_on = node.get("depends_on", [])
    if depends_on is not None and not isinstance(depends_on, list):
        issues.append(f"{node_id}: depends_on must be a list")

    return issues


def classify_nodes(nodes: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    issues: list[str] = []
    node_id_counts = Counter(node.get("id") for node in nodes if node.get("id"))
    duplicate_ids = {node_id for node_id, count in node_id_counts.items() if count > 1}
    for node_id in sorted(duplicate_ids):
        issues.append(f"{node_id}: duplicate node ID")

    done_ids = {
        node.get("id")
        for node in nodes
        if str(node.get("status", "")).strip().lower() in DONE_STATES
    }
    node_ids = {node.get("id") for node in nodes}

    ready_nodes: list[dict] = []
    waiting_nodes: list[dict] = []

    for node in nodes:
        node_id = node.get("id")
        status = str(node.get("status", "")).strip().lower()
        if node_id in duplicate_ids:
            waiting_nodes.append(node)
            continue

        deps = node.get("depends_on", [])
        if not isinstance(deps, list):
            issues.append(f"{node_id}: depends_on must be a list")
            waiting_nodes.append(node)
            continue
        missing = [dep for dep in deps if dep not in node_ids]
        if missing:
            issues.append(f"{node_id}: missing dependency IDs: {', '.join(missing)}")
        ambiguous = [dep for dep in deps if dep in duplicate_ids]
        if ambiguous:
            issues.append(f"{node_id}: ambiguous duplicate dependency IDs: {', '.join(ambiguous)}")

        unresolved = [dep for dep in deps if dep not in done_ids]
        unresolved.extend(dep for dep in ambiguous if dep not in unresolved)

        if status in DONE_STATES or status in ACTIVE_STATES or status in BLOCKED_STATES:
            waiting_nodes.append(node)
            continue

        if status not in PENDING_STATES:
            issues.append(f"{node_id}: unknown status '{node.get('status')}'")
            waiting_nodes.append(node)
            continue

        if unresolved:
            waiting_nodes.append(node)
            continue

        node_issues = _node_contract_issues(node)
        if node_issues:
            issues.extend(node_issues)
            waiting_nodes.append(node)
            continue

        ready_nodes.append(node)

    return ready_nodes, waiting_nodes, issues


def group_waves(ready_nodes: list[dict]) -> list[dict]:
    waves: list[list[dict]] = []
    for node in sorted(ready_nodes, key=lambda item: item.get("id", "")):
        writes = _normalize_string_list(node.get("writes"))
        placed = False
        for wave in waves:
            if all(
                not writes_overlap(writes, _normalize_string_list(existing.get("writes")))
                for existing in wave
            ):
                wave.append(node)
                placed = True
                break
        if not placed:
            waves.append([node])

    return [
        {
            "wave": idx + 1,
            "nodes": wave,
        }
        for idx, wave in enumerate(waves)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Report ready WORKGRAPH nodes")
    parser.add_argument("--file", required=True, help="Path to WORKGRAPH.md")
    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()
    data = extract_json_block(path.read_text())
    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        raise SystemExit("WORKGRAPH JSON must contain a top-level 'nodes' array")

    ready_nodes, waiting_nodes, issues = classify_nodes(nodes)
    waves = group_waves(ready_nodes)

    result = {
        "file": str(path),
        "node_count": len(nodes),
        "ready_count": len(ready_nodes),
        "ready_nodes": ready_nodes,
        "waves": waves,
        "waiting_nodes": waiting_nodes,
        "issues": issues,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
