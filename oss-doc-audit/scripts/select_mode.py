#!/usr/bin/env python3
"""
Resolve oss-doc-audit context from skillbox-config overlays and emit MODE_* vars.

Usage:
  python scripts/select_mode.py [cwd] [--format shell|json]

Defaults:
  cwd: current working directory
  format: shell
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


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


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
        lines.append(f"export {key}={shlex.quote(values[key])}")
    return "\n".join(lines)


def _mode_exports(payload: dict[str, Any]) -> dict[str, str]:
    flattened = _flatten("MODE", payload)
    mode_name = flattened.pop("MODE_MODE_NAME", None)
    if mode_name is not None:
        flattened["MODE_NAME"] = mode_name
    else:
        flattened.setdefault("MODE_NAME", "overlay")
    return flattened


def _load_shared_helpers() -> tuple[Any, Any]:
    shared_scripts = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
    if not shared_scripts.exists():
        raise RuntimeError(f"Missing shared helper directory: {shared_scripts}")

    sys.path.insert(0, str(shared_scripts))
    try:
        from legacy_probe import format_legacy_transition_error  # type: ignore[import-untyped]
        from resolve_context import resolve  # type: ignore[import-untyped]
    finally:
        sys.path.pop(0)

    return resolve, format_legacy_transition_error


def _missing_section_message(cwd: str) -> str:
    return (
        f"No oss_doc_audit section found in the matching skillbox-config overlay for {cwd}.\n"
        "Add client.context.oss_doc_audit to that overlay or continue the audit with explicit repo-native inference."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    try:
        resolve, format_legacy_transition_error = _load_shared_helpers()
        payload = resolve(cwd, section="oss_doc_audit")
        matched_overlay = resolve(cwd)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if payload is None:
        if matched_overlay is not None:
            print(_missing_section_message(cwd), file=sys.stderr)
        else:
            print(format_legacy_transition_error(cwd), file=sys.stderr)
        return 2

    flattened = _mode_exports(payload)
    if args.format == "json":
        print(json.dumps(flattened, indent=2, sort_keys=True))
    else:
        print(_to_shell_exports(flattened))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
