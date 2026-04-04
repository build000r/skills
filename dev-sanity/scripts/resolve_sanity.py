#!/usr/bin/env python3
"""
Resolve dev-sanity config from skillbox client overlay.

Fallback chain:
  1. SKILLBOX_CLIENT_CONTEXT env var → path to context/overlay YAML
  2. resolve_context.py shared resolver (scan /workspace/clients/)
  3. Local overlay scan: walk up from cwd for skillbox-config/clients/*/overlay.yaml

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
from glob import glob
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None  # type: ignore[assignment]


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


def _matches_prefix(cwd: str, prefix: str) -> bool:
    if prefix == "/":
        return True
    return cwd == prefix or cwd.startswith(prefix + os.sep)


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required but not installed")
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    body_lines = [l for l in lines if not l.startswith("#") or l.strip() == ""]
    data = yaml.safe_load("\n".join(body_lines))
    return data if isinstance(data, dict) else {}


def _try_shared_resolver(cwd: str) -> dict[str, Any] | None:
    """Use the shared resolve_context.py if available."""
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


def _find_config_roots(cwd: str) -> list[Path]:
    """Walk up from cwd and check ~/.claude/skills/ for skillbox-config/clients/."""
    roots: list[Path] = []
    p = Path(cwd)
    for d in [p, *p.parents]:
        candidate = d / "skillbox-config" / "clients"
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)

    # Also check the skills directory (common on local Mac)
    skills_config = Path.home() / ".claude" / "skills" / "skillbox-config" / "clients"
    if skills_config.is_dir() and skills_config not in roots:
        roots.append(skills_config)

    return roots


def _try_local_overlay_scan(cwd: str) -> dict[str, Any] | None:
    """Scan local skillbox-config directories for overlay.yaml with cwd_match."""
    if yaml is None:
        return None

    config_roots = _find_config_roots(cwd)
    if not config_roots:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []

    for config_root in config_roots:
        for overlay_file in config_root.glob("*/overlay.yaml"):
            try:
                data = _load_yaml_file(overlay_file)
            except Exception:
                continue

            # Extract cwd_match from nested client.context.cwd_match or top-level
            client = data.get("client", {})
            ctx = client.get("context", {})
            raw_match = ctx.get("cwd_match") or data.get("cwd_match")

            if isinstance(raw_match, str):
                prefixes = [raw_match]
            elif isinstance(raw_match, list):
                prefixes = [str(v) for v in raw_match]
            else:
                continue

            for raw_prefix in prefixes:
                prefix = _normalize_path(raw_prefix)
                if _matches_prefix(cwd, prefix):
                    # Extract dev_sanity section
                    dev_sanity = (
                        client.get("dev_sanity")
                        or data.get("dev_sanity")
                    )
                    if dev_sanity:
                        candidates.append((len(prefix), dev_sanity))

    if not candidates:
        return None

    # Longest prefix match wins
    max_len = max(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == max_len]
    return top[0][1]


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


def _overlay_to_json(data: dict[str, Any]) -> str:
    """Convert overlay dev_sanity section to JSON."""
    return json.dumps(data, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve dev-sanity config")
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    # 1. Try shared resolver (env var, /workspace scan, legacy modes)
    data = _try_shared_resolver(cwd)
    if data is not None:
        if args.format == "json":
            print(_overlay_to_json(data))
        else:
            print(_overlay_to_shell(data))
        return 0

    # 2. Try local overlay scan (walk up from cwd + ~/.claude/skills/)
    data = _try_local_overlay_scan(cwd)
    if data is not None:
        if args.format == "json":
            print(_overlay_to_json(data))
        else:
            print(_overlay_to_shell(data))
        return 0

    # No config found
    print(f"No dev_sanity config matched cwd: {cwd}", file=sys.stderr)
    print("Create a client overlay with a dev_sanity section, or set SKILLBOX_CLIENT_CONTEXT.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
