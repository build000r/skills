#!/usr/bin/env python3
"""
Resolve dev-sanity config from skillbox client overlay.

Delegates to the shared resolve_context.py resolver with section="dev_sanity".

Output: shell arrays in DEV_SANITY_* format, ready to eval.

Usage:
  eval "$(python3 scripts/resolve_sanity.py "$PWD")"
  python3 scripts/resolve_sanity.py "$PWD" --format json
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


def _resolve(cwd: str) -> dict[str, Any] | None:
    """Use the shared resolve_context.py resolver."""
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

    return resolve(cwd, section="dev_sanity")


def _overlay_to_shell(data: dict[str, Any]) -> str:
    """Convert overlay dev_sanity section to DEV_SANITY_* shell arrays."""
    lines: list[str] = []

    for key, var_name in [
        ("repos", "DEV_SANITY_REPOS"),
        ("env_files", "DEV_SANITY_ENV_FILES"),
        ("containers", "DEV_SANITY_CONTAINERS"),
        ("health_urls", "DEV_SANITY_HEALTH_URLS"),
    ]:
        items = data.get(key, [])
        if not isinstance(items, list):
            continue
        entries: list[str] = []
        for item in items:
            if isinstance(item, dict):
                label = item.get("label", item.get("id", "unknown"))
                value = item.get("path") or item.get("name") or item.get("url", "")
                value = os.path.expanduser(str(value))
                entries.append(f"{label}|{value}")
            elif isinstance(item, str):
                entries.append(item)
        quoted = " ".join(shlex.quote(e) for e in entries)
        lines.append(f"{var_name}=({quoted})")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve dev-sanity config")
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    data = _resolve(cwd)
    if data is None:
        print(f"No dev_sanity config matched cwd: {cwd}", file=sys.stderr)
        print("Create a client overlay with a dev_sanity section, or set SKILLBOX_CLIENT_CONTEXT.", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(_overlay_to_shell(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
