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
import json
import re
from pathlib import Path


DONE_STATES = {"done", "skipped"}
ACTIVE_STATES = {"in_progress"}
BLOCKED_STATES = {"blocked"}
PENDING_STATES = {"todo", "ready", "planned", "open", ""}


def extract_json_block(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError("No fenced ```json block found in WORKGRAPH.md")
    return json.loads(match.group(1))


def normalize_prefix(path_pattern: str) -> str:
    prefix = re.split(r"[*?\[]", path_pattern, maxsplit=1)[0]
    return prefix.rstrip("/")


def writes_overlap(left: list[str], right: list[str]) -> bool:
    for a in left:
        for b in right:
            if a == b:
                return True
            a_prefix = normalize_prefix(a)
            b_prefix = normalize_prefix(b)
            if not a_prefix or not b_prefix:
                continue
            if a_prefix.startswith(b_prefix) or b_prefix.startswith(a_prefix):
                return True
    return False


def classify_nodes(nodes: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    issues: list[str] = []
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
        deps = node.get("depends_on", [])
        missing = [dep for dep in deps if dep not in node_ids]
        if missing:
            issues.append(f"{node_id}: missing dependency IDs: {', '.join(missing)}")

        unresolved = [dep for dep in deps if dep not in done_ids]

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

        ready_nodes.append(node)

    return ready_nodes, waiting_nodes, issues


def group_waves(ready_nodes: list[dict]) -> list[dict]:
    waves: list[list[dict]] = []
    for node in sorted(ready_nodes, key=lambda item: item.get("id", "")):
        writes = node.get("writes", [])
        placed = False
        for wave in waves:
            if all(not writes_overlap(writes, existing.get("writes", [])) for existing in wave):
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
