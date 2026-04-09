#!/usr/bin/env python3
"""
Resolve deploy context from skillbox-config overlays and emit MODE_* exports.

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


def _matches_prefix(cwd: str, prefix: str) -> bool:
    if prefix == "/":
        return True
    return cwd == prefix or cwd.startswith(prefix + os.sep)


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
    return flattened


def _expand_strings(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: _expand_strings(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_expand_strings(item) for item in data]
    if isinstance(data, str):
        return os.path.expanduser(os.path.expandvars(data))
    return data


def _shared_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"


def _load_shared_helpers() -> tuple[Any, Any]:
    shared_scripts = _shared_scripts_dir()
    if not shared_scripts.exists():
        raise RuntimeError(f"Missing shared helper directory: {shared_scripts}")

    sys.path.insert(0, str(shared_scripts))
    try:
        from legacy_probe import format_legacy_transition_error  # type: ignore[import-untyped]
        from resolve_context import resolve  # type: ignore[import-untyped]
    finally:
        sys.path.pop(0)

    return resolve, format_legacy_transition_error


def _direct_deploy_fields(deploy: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in deploy.items()
        if key not in {"services", "packages"}
    }


def _target_candidates(
    cwd: str, deploy: dict[str, Any],
) -> list[tuple[int, str, str, dict[str, Any]]]:
    candidates: list[tuple[int, str, str, dict[str, Any]]] = []

    for collection_name, default_surface in (("services", "docker_compose"), ("packages", "package_publish")):
        raw_collection = deploy.get(collection_name)
        if not isinstance(raw_collection, dict):
            continue

        for target_id, raw_target in raw_collection.items():
            if not isinstance(raw_target, dict):
                continue

            repo_root = raw_target.get("repo_root")
            if not isinstance(repo_root, str):
                continue

            prefix = _normalize_path(repo_root)
            if _matches_prefix(cwd, prefix):
                target = dict(raw_target)
                target.setdefault("surface", default_surface)
                candidates.append((len(prefix), collection_name, str(target_id), target))

    return candidates


def _derive_mode_name(cwd: str, target_id: str, target: dict[str, Any]) -> str:
    repo_root = target.get("repo_root")
    if isinstance(repo_root, str):
        repo_name = Path(_normalize_path(repo_root)).name
        if repo_name:
            return repo_name
    return Path(cwd).name or target_id or "overlay"


def _select_deploy_payload(cwd: str, deploy: dict[str, Any]) -> dict[str, Any]:
    shared = _direct_deploy_fields(deploy)
    candidates = _target_candidates(cwd, deploy)

    if candidates:
        max_len = max(item[0] for item in candidates)
        top = [item for item in candidates if item[0] == max_len]
        if len(top) > 1:
            target_ids = ", ".join(sorted(item[2] for item in top))
            raise ValueError(f"Ambiguous deploy target for {cwd}: {target_ids}")

        _prefix_len, collection_name, target_id, target = top[0]
        payload = dict(shared)
        payload.update(target)
        payload.setdefault("surface", "docker_compose" if collection_name == "services" else "package_publish")
        payload.setdefault("mode_name", _derive_mode_name(cwd, target_id, target))
        payload.setdefault("target_id", target_id)
        return _expand_strings(payload)

    payload = dict(shared if shared else deploy)
    if "surface" not in payload:
        if isinstance(deploy.get("services"), dict) and deploy["services"]:
            payload["surface"] = "docker_compose"
        elif isinstance(deploy.get("packages"), dict) and deploy["packages"]:
            payload["surface"] = "package_publish"

    payload.setdefault("mode_name", Path(cwd).name or "overlay")
    return _expand_strings(payload)


def _resolve_overlay_payload(cwd: str) -> dict[str, Any] | None:
    resolve, _format_legacy_transition_error = _load_shared_helpers()
    deploy = resolve(cwd, section="deploy")
    if deploy is None:
        return None
    return _select_deploy_payload(cwd, deploy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)

    try:
        payload = _resolve_overlay_payload(cwd)
        _resolve, format_legacy_transition_error = _load_shared_helpers()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if payload is None:
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
