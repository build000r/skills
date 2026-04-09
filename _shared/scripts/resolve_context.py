#!/usr/bin/env python3
"""
Resolve skill context from skillbox client overlays.

Fallback chain:
  1. SKILLBOX_CLIENT_CONTEXT env var → path to generated context.yaml
  2. Scan /workspace/clients/*/context.yaml using cwd_match prefix matching
  3. Scan local skillbox-config overlays using cwd_match prefix matching

Usage:
  python resolve_context.py [cwd] [--section deploy|plans|backend|frontend|auth]
                            [--format shell|json]
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

from legacy_probe import format_legacy_transition_error

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


def _extract_overlay_payload(data: dict[str, Any], section: str | None) -> dict[str, Any] | None:
    client = data.get("client")
    if not isinstance(client, dict):
        client = {}

    context = client.get("context")
    if not isinstance(context, dict):
        context = {}

    if section is None:
        return client if client else data

    for source in (context, client, data):
        if isinstance(source, dict) and section in source:
            payload = source.get(section)
            if isinstance(payload, dict):
                return payload
            if payload is None:
                return None
            return {"value": payload}

    return None


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
                    payload = _extract_overlay_payload(data, section)
                    if payload is not None:
                        candidates.append((len(prefix), payload))

    if not candidates:
        return None

    max_len = max(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == max_len]
    return top[0][1]


# --- Main --------------------------------------------------------------------


def resolve(cwd: str, *, section: str | None = None) -> dict[str, Any] | None:
    """Resolve context using the overlay-backed fallback chain."""
    result = _resolve_from_env(section)
    if result is not None:
        return result

    result = _resolve_from_scan(cwd, section)
    if result is not None:
        return result

    result = _resolve_from_local_overlays(cwd, section)
    if result is not None:
        return result

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve skill context")
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--section", default=None,
                        help="Extract a specific section (deploy, plans, backend, etc.)")
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    data = resolve(cwd, section=args.section)
    if data is None:
        print(format_legacy_transition_error(cwd), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        flattened = _flatten("MODE", data)
        print(_to_shell_exports(flattened))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
