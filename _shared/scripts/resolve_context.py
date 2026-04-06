#!/usr/bin/env python3
"""
Resolve skill context from skillbox client overlays or legacy mode files.

Fallback chain:
  1. SKILLBOX_CLIENT_CONTEXT env var → path to generated context.yaml
  2. Scan /workspace/clients/*/context.yaml using cwd_match prefix matching
  3. Fall back to {skill_dir}/modes/*.md (legacy)

Usage:
  python resolve_context.py [cwd] [--section deploy|plans|backend|frontend|auth]
                            [--format shell|json] [--skill-dir <path>]
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

try:
    import yaml
except ModuleNotFoundError:
    yaml = None  # type: ignore[assignment]


WORKSPACE_CLIENTS_GLOB = "/workspace/clients/*/context.yaml"
LOCAL_SKILLBOX_CLIENTS = Path.home() / ".claude" / "skills" / "skillbox-config" / "clients"
FOCUS_STATE_PATHS = (
    Path("/workspace/.focus.json"),
    Path.home() / ".focus.json",
)


def _normalize_path(value: str) -> str:
    return os.path.realpath(os.path.expanduser(value))


def _matches_prefix(cwd: str, prefix: str) -> bool:
    if prefix == "/":
        return True
    return cwd == prefix or cwd.startswith(prefix + os.sep)


def _flatten(prefix: str, data: Any) -> dict[str, str]:
    """Flatten nested dict into MODE_* style shell exports."""
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


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required but not installed")
    text = path.read_text(encoding="utf-8")
    # Strip comment header lines before YAML content
    lines = text.split("\n")
    body_lines = [l for l in lines if not l.startswith("#") or l.strip() == ""]
    data = yaml.safe_load("\n".join(body_lines))
    return data if isinstance(data, dict) else {}


def _extract_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    if yaml is None:
        raise RuntimeError("PyYAML required but not installed")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML map")
    return data


# --- Resolution strategies ---------------------------------------------------


def _resolve_from_env(section: str | None) -> dict[str, Any] | None:
    """Strategy 1: SKILLBOX_CLIENT_CONTEXT env var."""
    env_path = os.environ.get("SKILLBOX_CLIENT_CONTEXT")
    if not env_path:
        # Try reading from .focus.json
        for fp in FOCUS_STATE_PATHS:
            if fp.is_file():
                try:
                    focus = json.loads(fp.read_text(encoding="utf-8"))
                    env_path = focus.get("skill_context_path")
                    if env_path:
                        break
                except (json.JSONDecodeError, OSError):
                    continue
    if not env_path:
        return None
    ctx_path = Path(env_path)
    if not ctx_path.is_file():
        return None
    data = _load_yaml_file(ctx_path)
    if section:
        return data.get(section)  # type: ignore[return-value]
    return data


def _resolve_from_scan(cwd: str, section: str | None) -> dict[str, Any] | None:
    """Strategy 2: Scan workspace clients for matching cwd_match."""
    from glob import glob

    candidates: list[tuple[int, Path, dict[str, Any]]] = []
    for ctx_file in glob(WORKSPACE_CLIENTS_GLOB):
        ctx_path = Path(ctx_file)
        try:
            data = _load_yaml_file(ctx_path)
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
                candidates.append((len(prefix), ctx_path, data))

    if not candidates:
        return None

    max_len = max(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == max_len]
    if len(top) > 1:
        print(f"Ambiguous context match for cwd: {cwd}", file=sys.stderr)
        return None

    _, _, data = top[0]
    if section:
        return data.get(section)  # type: ignore[return-value]
    return data


def _resolve_from_local_overlays(
    cwd: str, section: str | None,
) -> dict[str, Any] | None:
    """Strategy 3: Scan ~/.claude/skills/skillbox-config/clients/ and walk-up from cwd."""
    if yaml is None:
        return None

    roots: list[Path] = []

    # Walk up from cwd looking for skillbox-config/clients/
    p = Path(cwd)
    for d in [p, *p.parents]:
        candidate = d / "skillbox-config" / "clients"
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)

    # Also check the standard local install path
    if LOCAL_SKILLBOX_CLIENTS.is_dir() and LOCAL_SKILLBOX_CLIENTS not in roots:
        roots.append(LOCAL_SKILLBOX_CLIENTS)

    if not roots:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []
    for config_root in roots:
        for overlay_file in config_root.glob("*/overlay.yaml"):
            try:
                data = _load_yaml_file(overlay_file)
            except Exception:
                continue

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
                    # Extract section or full client block
                    source = client if client else data
                    payload = source.get(section) if section else source
                    if payload is not None:
                        candidates.append((len(prefix), payload))

    if not candidates:
        return None

    max_len = max(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == max_len]
    return top[0][1]


def _resolve_from_modes(
    cwd: str, skill_dir: Path, section: str | None,
) -> dict[str, Any] | None:
    """Strategy 4: Legacy modes/ directory scan."""
    modes_dir = skill_dir / "modes"
    if not modes_dir.exists():
        return None

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
        return None

    max_len = max(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == max_len]
    if len(top) > 1:
        print(f"Ambiguous mode match for cwd: {cwd}", file=sys.stderr)
        return None

    _, mode_file, _, data = top[0]
    data["_source"] = "modes"
    data["_mode_file"] = str(mode_file)
    # In legacy mode, the whole file IS the section (no sub-sections)
    return data


# --- Main --------------------------------------------------------------------


def resolve(
    cwd: str, *, section: str | None = None, skill_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Resolve context using the 3-step fallback chain."""
    result = _resolve_from_env(section)
    if result is not None:
        return result

    result = _resolve_from_scan(cwd, section)
    if result is not None:
        return result

    result = _resolve_from_local_overlays(cwd, section)
    if result is not None:
        return result

    if skill_dir:
        result = _resolve_from_modes(cwd, skill_dir, section)
        if result is not None:
            return result

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve skill context")
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--section", default=None,
                        help="Extract a specific section (deploy, plans, backend, etc.)")
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    parser.add_argument("--skill-dir", default="",
                        help="Skill directory for legacy modes/ fallback")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)
    skill_dir = Path(args.skill_dir).resolve() if args.skill_dir else None

    data = resolve(cwd, section=args.section, skill_dir=skill_dir)
    if data is None:
        print(f"No context matched cwd: {cwd}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        flattened = _flatten("MODE", data)
        print(_to_shell_exports(flattened))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
