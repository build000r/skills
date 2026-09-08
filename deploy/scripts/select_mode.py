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


class ReleaseContextError(ValueError):
    def __init__(self, message: str, missing_fields: list[str]):
        super().__init__(message)
        self.missing_fields = missing_fields


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


def _select_deploy_payload(cwd: str, deploy: dict[str, Any], *, expand_release: bool = True) -> dict[str, Any]:
    def expand(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value if key == "release" and not expand_release else _expand_strings(value)
                for key, value in payload.items()}

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
        return expand(payload)

    payload = dict(shared if shared else deploy)
    if "surface" not in payload:
        if isinstance(deploy.get("services"), dict) and deploy["services"]:
            payload["surface"] = "docker_compose"
        elif isinstance(deploy.get("packages"), dict) and deploy["packages"]:
            payload["surface"] = "package_publish"

    payload.setdefault("mode_name", Path(cwd).name or "overlay")
    return expand(payload)


def _resolve_overlay_payload(cwd: str) -> dict[str, Any] | None:
    resolve, _format_legacy_transition_error = _load_shared_helpers()
    deploy = resolve(cwd, section="deploy")
    if deploy is None:
        return None
    return _select_deploy_payload(cwd, deploy)


def resolve_release_context(cwd: str, *, context_path: str | None = None) -> tuple[dict[str, Any], str]:
    """Resolve trusted context data with provenance; never run embedded commands."""
    _load_shared_helpers()
    import resolve_context as shared

    def read(path: Path) -> tuple[dict[str, Any], Any]:
        try:
            data = shared._load_yaml_file(path)
        except OSError:
            raise ValueError(f"Release context is unreadable: {path}") from None
        except Exception:
            raise ValueError(f"Release context is invalid: {path}") from None
        if path.name == "overlay.yaml" or "client" in data:
            client = data.get("client", {})
            if not isinstance(client, dict) or not isinstance(client.get("context", {}), dict):
                raise ValueError(f"Release context requires client/context mappings: {path}")
            payload = shared._extract_overlay_payload(data, "deploy")
            context = client.get("context", {})
        else:
            payload = shared._extract_context_payload(data, "deploy")
            context = data
        return payload or {}, context.get("cwd_match", [])

    def match(prefixes: Any) -> int:
        prefixes = [prefixes] if isinstance(prefixes, str) else prefixes
        matches = []
        for raw in prefixes if isinstance(prefixes, list) else []:
            expanded = shared._expand_match_prefix(str(raw))
            if expanded is not None:
                prefix = _normalize_path(expanded)
                if _matches_prefix(cwd, prefix):
                    matches.append(len(prefix))
        return max(matches, default=-1)

    selected = context_path or os.environ.get("SKILLBOX_CLIENT_CONTEXT")
    if not selected:
        for focus_path in shared.FOCUS_STATE_PATHS:
            if focus_path.is_file():
                focus = json.loads(focus_path.read_text(encoding="utf-8"))
                if not isinstance(focus, dict):
                    raise ValueError("Invalid focus context mapping")
                selected = focus.get("skill_context_path")
                if selected is not None and not isinstance(selected, str):
                    raise ValueError("Invalid focus context path")
                if selected:
                    break
    if selected:
        source = Path(_normalize_path(selected))
    else:
        from glob import glob
        workspace = [Path(p) for p in glob(shared.WORKSPACE_CLIENTS_GLOB)]
        roots = [d / "skillbox-config" / "clients" for d in [Path(cwd), *Path(cwd).parents]]
        roots.append(shared.LOCAL_SKILLBOX_CLIENTS)
        local = [p for root in roots for pattern in ("*/context.yaml", "*/overlay.yaml")
                 for p in root.glob(pattern)]
        source = None
        for paths in (workspace, local):
            candidates = []
            for path in sorted(set(p.resolve() for p in paths)):
                payload, prefixes = read(path)
                specificity = match(prefixes)
                if payload and specificity >= 0:
                    candidates.append((specificity, int(path.name == "context.yaml"), path))
            if candidates:
                specificity = max(a for a, _, _ in candidates)
                owners = {p.parent for a, _, p in candidates if a == specificity}
                if len(owners) != 1:
                    raise ValueError("Ambiguous release context owners: " + ", ".join(map(str, sorted(owners))))
                priority = max((a, b) for a, b, _ in candidates)
                top = [p for a, b, p in candidates if (a, b) == priority]
                if len(top) != 1:
                    raise ValueError("Ambiguous release context: " + ", ".join(map(str, top)))
                source = top[0]
                break
        if source is None:
            raise ValueError("Release context unavailable; configure a matching skillbox-config client overlay")
    deploy, prefixes = read(source)
    if match(prefixes) < 0:
        raise ValueError(f"Release context cwd_match does not contain cwd: {source}")
    paired = source.with_name("overlay.yaml" if source.name == "context.yaml" else "context.yaml")
    if source.name in {"overlay.yaml", "context.yaml"} and paired.is_file():
        other, other_prefixes = read(paired)
        if _expand_strings(other) != _expand_strings(deploy) or match(other_prefixes) < 0:
            raise ValueError(f"Stale or conflicting deploy context: {source} and {paired}; regenerate context from its owning overlay")
    if any(key in deploy for key in ("services", "packages")) and not _target_candidates(cwd, deploy):
        raise ValueError(f"No matching deploy target in release context: {source}")
    # References remain opaque. Expanding a proof command can reveal an ordinary
    # password that no token-pattern screen could recognize.
    payload = _select_deploy_payload(cwd, deploy, expand_release=False)
    payload["context_source"] = str(source)
    return payload, str(source)


def validate_release_payload(cwd: str, payload: dict[str, Any]) -> None:
    """Validate references only; never execute release commands or proof probes."""
    missing = []
    for field in ("repo_root", "target_id"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            missing.append(field)
    release = payload.get("release")
    release = release if isinstance(release, dict) else {}
    for field in ("command", "gate", "behavior_proof", "state_proof", "rollback"):
        if not isinstance(release.get(field), str) or not release[field].strip():
            missing.append(f"release.{field}")
    repo_root = payload.get("repo_root")
    if isinstance(repo_root, str) and repo_root.strip():
        if not _matches_prefix(cwd, _normalize_path(repo_root)):
            missing.append("repo_root (must contain cwd)")
    if "services" in payload or "packages" in payload:
        missing.append("matching deploy target")
    if missing:
        raise ReleaseContextError(
            "Release context incomplete: " + ", ".join(missing)
            + ". Repair the owning skillbox-config client overlay, regenerate its "
            "context if applicable, and reselect before release.", missing
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cwd", nargs="?", default=os.getcwd())
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    parser.add_argument("--context", help="Explicit owning overlay.yaml or generated context.yaml")
    parser.add_argument("--errors-json", action="store_true", help="Emit sanitized structured failures on stderr")
    parser.add_argument("--require-release", action="store_true",
                        help="Require matching target, native command/gate, proof and rollback references")
    args = parser.parse_args()

    cwd = _normalize_path(args.cwd)
    _source = args.context

    try:
        if args.require_release or args.context:
            payload, _source = resolve_release_context(cwd, context_path=args.context)
        else:
            payload = _resolve_overlay_payload(cwd)
        if args.require_release and payload is not None:
            validate_release_payload(cwd, payload)
        _resolve, format_legacy_transition_error = _load_shared_helpers()
    except ValueError as exc:
        if args.errors_json:
            print(json.dumps({"ok": False, "code": "deploy_context_invalid",
                              "missing_fields": getattr(exc, "missing_fields", []),
                              "context_source": _source}), file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 3
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if payload is None:
        if args.require_release:
            print("Release context unavailable or ambiguous. Repair the owning "
                  "skillbox-config client overlay and reselect before release.", file=sys.stderr)
            return 2
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
