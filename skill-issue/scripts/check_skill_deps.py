#!/usr/bin/env python3
"""Cross-skill dependency checker.

Reads `depends_on: [skill_id, ...]` from SKILL.md frontmatter across all skills
under the given roots. Given a changed skill, lists its dependents and compares
the interface surfaces (bash/python code blocks, referenced file paths, phase
headers) between an old and new SKILL.md to flag drift.

Usage:
  check_skill_deps.py --changed-skill <id> \
                      [--old path/to/old/SKILL.md --new path/to/new/SKILL.md] \
                      [--roots ~/.claude/skills ~/.codex/skills] \
                      [--json]

Output contract (--json):
  {
    "skill": "<id>",
    "dependents": ["<id>", ...],
    "interface_drift": [{"kind": "phase|command|path", "removed": [...], "added": [...]}, ...]
  }

Exit code: 0 = no dependents; 1 = dependents exist but no drift; 2 = drift.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

CODE_BLOCK = re.compile(r"```(?:bash|sh|zsh|python|py)\s*\n(.*?)```", re.DOTALL)
PHASE_HDR = re.compile(r"^#{2,4}\s+(Phase\s+\d|Step\s+\d|\d+\.)", re.IGNORECASE | re.MULTILINE)
FILE_PATH = re.compile(r"[\w./-]+\.(md|py|sh|yaml|yml|json|toml|jsonl)\b")
DEFAULT_ROOTS = ["~/.claude/skills", "~/.codex/skills"]
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---(?:\n|$)", re.DOTALL)
SKILL_ID_RE = re.compile(r"^[a-z0-9-]+$")


def _is_skill_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(SKILL_ID_RE.match(value))
        and not value.startswith("-")
        and not value.endswith("-")
        and "--" not in value
    )


def _load_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _scan_skills(roots: list[str]) -> dict[str, dict]:
    skills: dict[str, dict] = {}
    for root in roots:
        root_p = Path(os.path.expanduser(root))
        if not root_p.exists():
            continue
        for entry in sorted(root_p.iterdir()):
            md = entry / "SKILL.md"
            if not md.is_file():
                continue
            try:
                fm = _load_frontmatter(md.read_text())
            except OSError:
                continue
            raw_name = fm.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else entry.name
            deps = fm.get("depends_on")
            if deps is None:
                deps = []
            elif not isinstance(deps, list) or not all(_is_skill_id(dep) for dep in deps):
                deps = []
            skills.setdefault(name, {"path": str(md), "depends_on": deps or []})
    return skills


def _interface_surfaces(text: str) -> dict[str, set[str]]:
    match = FRONTMATTER_RE.match(text) if text.startswith("---\n") else None
    body = text[match.end():] if match else text
    commands: set[str] = set()
    for block in CODE_BLOCK.findall(body):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                tokens = line.split()
                if not tokens:
                    continue
                first = tokens[0].lstrip("$")
                if first:
                    commands.add(first)
                # subcommand-level interface: first two tokens, if the second looks like a subcommand
                if len(tokens) >= 2 and re.fullmatch(r"[a-z][a-z0-9_-]*", tokens[1] or ""):
                    commands.add(f"{first} {tokens[1]}")
    return {
        "phase": {m.group(1).strip() for m in PHASE_HDR.finditer(body)},
        "command": commands,
        "path": set(FILE_PATH.findall(body)) if False else set(m.group(0) for m in FILE_PATH.finditer(body)),
    }


def compute_drift(old_text: str, new_text: str) -> list[dict]:
    old_s = _interface_surfaces(old_text)
    new_s = _interface_surfaces(new_text)
    drift: list[dict] = []
    for kind in ("phase", "command", "path"):
        removed = sorted(old_s[kind] - new_s[kind])
        added = sorted(new_s[kind] - old_s[kind])
        if removed or added:
            drift.append({"kind": kind, "removed": removed, "added": added})
    return drift


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed-skill", required=True)
    ap.add_argument("--old", help="current SKILL.md path (for drift check)")
    ap.add_argument("--new", help="proposed SKILL.md path (for drift check)")
    ap.add_argument("--roots", nargs="+", default=DEFAULT_ROOTS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    skills = _scan_skills(args.roots)
    dependents = sorted(
        name for name, info in skills.items() if args.changed_skill in info["depends_on"]
    )
    drift: list[dict] = []
    if args.old and args.new:
        drift = compute_drift(Path(args.old).read_text(), Path(args.new).read_text())

    payload = {
        "skill": args.changed_skill,
        "dependents": dependents,
        "interface_drift": drift,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"skill: {args.changed_skill}")
        print(f"dependents: {', '.join(dependents) or '(none)'}")
        if drift:
            for d in drift:
                print(f"drift/{d['kind']}: -{len(d['removed'])} +{len(d['added'])}")
                if d["removed"]:
                    print(f"  removed: {d['removed']}")
                if d["added"]:
                    print(f"  added:   {d['added']}")

    if dependents and drift:
        sys.exit(2)
    if dependents:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
