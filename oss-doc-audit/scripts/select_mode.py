#!/usr/bin/env python3
"""
Select an oss-doc-audit mode file based on cwd prefix matching.

Resolution order:
  1. Skillbox client overlay `oss_doc_audit` section (if present)
  2. Legacy {skill_dir}/modes/*.md with YAML frontmatter and cwd_match

Usage:
  python scripts/select_mode.py [cwd] [--format shell|json] [--skill-dir <path>]

Defaults:
  cwd: current working directory
  format: shell
  skill-dir: parent of this script
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


def _matches_prefix(cwd: str, prefix: str) -> bool:
    if prefix == "/":
        return True
    return cwd == prefix or cwd.startswith(prefix + os.sep)


def _extract_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML map")
    return data


def _flatten(prefix: str, data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            key_norm = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).upper().strip("_")
            child_prefix = f"{prefix}_{key_norm}" if prefix else key_norm
            out.update(_flatten(child_prefix, value))
        return out

    if isinstance(data, list):
        out[prefix] = ":".join(str(item) for item in data)
        return out

    if data is None:
        out[prefix] = ""
        return out

    out[prefix] = str(data)
    return out


def _to_shell_exports(values: dict[str, str]) -> str:
    lines: list[str] = []
    for key in sorted(values):
        val = values[key]
        lines.append(f"export {key}={shlex.quote(val)}")
    return "\n".join(lines)


def _try_overlay_context(cwd: str, fmt: str) -> int | None:
    """Check for skillbox client context.yaml; return exit code or None to fall through."""
    # Import the shared resolver if available
    shared_scripts = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
    if not shared_scripts.exists():
        return None
    sys.path.insert(0, str(shared_scripts))
    try:
        from resolve_context import resolve  # type: ignore[import-untyped]
    except ImportError:
        return None
    finally:
        sys.path.pop(0)

    data = resolve(cwd, section="oss_doc_audit")
    if data is None:
        return None

    flattened = _flatten("MODE", data)
    flattened.setdefault("MODE_NAME", "overlay")
    if fmt == "json":
        print(json.dumps(flattened, indent=2, sort_keys=True))
    else:
        print(_to_shell_exports(flattened))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    parser.add_argument("--skill-dir", default="")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    # Try skillbox overlay context first
    overlay_result = _try_overlay_context(cwd, args.format)
    if overlay_result is not None:
        return overlay_result

    # Fall back to legacy modes/ directory
    script_dir = Path(__file__).resolve().parent
    skill_dir = Path(args.skill_dir).resolve() if args.skill_dir else script_dir.parent
    modes_dir = skill_dir / "modes"

    if not modes_dir.exists():
        print(f"No modes directory found at: {modes_dir}", file=sys.stderr)
        return 2

    candidates: list[tuple[int, Path, str, dict[str, Any]]] = []
    for mode_file in sorted(modes_dir.glob("*.md")):
        try:
            data = _extract_frontmatter(mode_file)
        except Exception:
            continue

        raw_match = data.get("cwd_match")
        if isinstance(raw_match, str):
            prefixes = [raw_match]
        elif isinstance(raw_match, list):
            prefixes = [str(v) for v in raw_match]
        else:
            continue

        for raw_prefix in prefixes:
            prefix = _normalize_path(raw_prefix)
            if _matches_prefix(cwd, prefix):
                candidates.append((len(prefix), mode_file, prefix, data))

    if not candidates:
        print(f"No mode matched cwd: {cwd}", file=sys.stderr)
        return 2

    max_len = max(item[0] for item in candidates)
    top = [item for item in candidates if item[0] == max_len]

    if len(top) > 1:
        print(f"Ambiguous mode match for cwd: {cwd}", file=sys.stderr)
        for _, mode_file, prefix, _ in top:
            print(f"  - {mode_file.name} via {prefix}", file=sys.stderr)
        return 3

    _, mode_file, matched_prefix, data = top[0]
    mode_name = str(data.get("mode_name") or mode_file.stem)
    flattened = _flatten("MODE", data)
    flattened["MODE_FILE"] = str(mode_file)
    flattened["MODE_NAME"] = mode_name
    flattened["MODE_MATCH_PREFIX"] = matched_prefix

    if args.format == "json":
        print(json.dumps(flattened, indent=2, sort_keys=True))
    else:
        print(_to_shell_exports(flattened))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
