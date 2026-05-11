#!/usr/bin/env python3
"""Read-only scanner for skill registry, SBP, Skillbox, and MCP surfaces."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - scanner still works partially
    yaml = None


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}

RUNTIME_HINTS = (
    "default-skills",
    "skills.manifest",
    "skills.sources.yaml",
    "default-skills.manifest",
    "default-skills.sources.yaml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of skill registry and MCP visibility surfaces."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root to scan. Repeatable. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a compact text report.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compatibility flag: scanner is always read-only and never mutates files.",
    )
    return parser.parse_args()


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        base = Path(dirpath)
        for name in filenames:
            yield base / name


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def yaml_load(path: Path) -> Any:
    if yaml is None:
        return None
    try:
        return yaml.safe_load(read_text(path))
    except Exception:
        return None


def walk_values(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item)
    else:
        yield value


def path_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value.startswith(("http://", "https://", "git@", "${")):
        return False
    if "${" in value or "*" in value:
        return False
    return value.startswith(("/", "./", "../", "~"))


def resolve_path(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate


def static_skill_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        item
        for item in values
        if isinstance(item, str) and "*" not in item and "/" not in item
    ]


def frontmatter(path: Path) -> dict[str, Any]:
    text = read_text(path)
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    raw = match.group(1)
    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def collect_skill_names(root: Path) -> dict[str, list[Path]]:
    names: dict[str, list[Path]] = {}
    if not root.exists():
        return names
    for manifest in root.glob("*/SKILL.md"):
        meta = frontmatter(manifest)
        name = str(meta.get("name", "")).strip()
        if name:
            names.setdefault(name, []).append(manifest)
    return names


def merge_skill_names(target: dict[str, list[Path]], source: dict[str, list[Path]]) -> None:
    for name, paths in source.items():
        target.setdefault(name, []).extend(paths)


def codex_mcp_servers(path: Path) -> set[str]:
    text = read_text(path)
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
            servers = data.get("mcp_servers") or data.get("mcpServers") or {}
            if isinstance(servers, dict):
                return set(servers)
        except Exception:
            pass
    names = set(re.findall(r"^\[mcp_servers\.([A-Za-z0-9_.-]+)\]", text, re.MULTILINE))
    names.update(re.findall(r"^\[mcpServers\.([A-Za-z0-9_.-]+)\]", text, re.MULTILINE))
    return names


def claude_mcp_servers(path: Path) -> set[str]:
    try:
        data = json.loads(read_text(path))
    except Exception:
        return set()
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    return set(servers) if isinstance(servers, dict) else set()


def classify_skill_owner(path: Path) -> str:
    parts = set(path.parts)
    text_path = str(path)
    if "opensource" in parts and "skills" in parts:
        return "portable-skill-contract"
    if "skills-private" in parts:
        return "private-skill-contract"
    if "skillbox-config" in parts:
        return "client-overlay-or-config"
    if "skillbox" in parts:
        return "runtime-or-distribution"
    if "/skills/" in text_path:
        return "repo-local-skill"
    return "unknown"


def add_issue(issues: list[dict[str, str]], severity: str, code: str, path: Path, message: str):
    issues.append(
        {
            "severity": severity,
            "code": code,
            "path": str(path),
            "message": message,
        }
    )


def check_declared_paths(path: Path, value: Any, issues: list[dict[str, str]], *, code: str) -> None:
    for item in walk_values(value):
        if not path_like(item):
            continue
        candidate = resolve_path(path.parent, str(item))
        if not candidate.exists():
            add_issue(
                issues,
                "HIGH",
                code,
                path,
                f"Declared path does not exist: {item}",
            )


def check_skill_scope(path: Path, data: Any, skill_names: dict[str, list[Path]], issues: list[dict[str, str]]) -> None:
    if not isinstance(data, dict):
        add_issue(issues, "MEDIUM", "scope-drift", path, "skill-scope.yaml is not a YAML object.")
        return

    source_roots = data.get("skill_source_roots", [])
    if isinstance(source_roots, list):
        for source_root in source_roots:
            if not path_like(source_root):
                continue
            candidate = resolve_path(path.parent, str(source_root))
            if not candidate.exists():
                add_issue(
                    issues,
                    "HIGH",
                    "missing-registry-source",
                    path,
                    f"Skill source root does not exist: {source_root}",
                )
            else:
                merge_skill_names(skill_names, collect_skill_names(candidate))
    elif source_roots:
        add_issue(issues, "MEDIUM", "scope-drift", path, "skill_source_roots must be a list.")

    global_allowlist = data.get("global_allowlist", [])
    if global_allowlist and not isinstance(global_allowlist, list):
        add_issue(issues, "MEDIUM", "scope-drift", path, "global_allowlist must be a list.")
        global_allowlist = []
    allowed_global = set(static_skill_names(global_allowlist))

    seen: dict[str, str] = {}
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        add_issue(issues, "MEDIUM", "scope-drift", path, "rules must be a list.")
        return

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            add_issue(issues, "MEDIUM", "scope-drift", path, f"Rule {index} is not an object.")
            continue
        rule_id = str(rule.get("id", f"rule-{index}"))
        skills = rule.get("skills", [])
        if not isinstance(skills, list):
            add_issue(issues, "MEDIUM", "scope-drift", path, f"Rule `{rule_id}` skills must be a list.")
            continue
        for skill in static_skill_names(skills):
            if skill in seen:
                add_issue(
                    issues,
                    "LOW",
                    "scope-drift",
                    path,
                    f"Skill `{skill}` appears in both `{seen[skill]}` and `{rule_id}`.",
                )
            else:
                seen[skill] = rule_id
            if skill_names and skill not in skill_names:
                add_issue(
                    issues,
                    "MEDIUM",
                    "scope-drift",
                    path,
                    f"Policy references unknown skill `{skill}` in `{rule_id}`.",
                )
            if rule.get("allow_global") is True and skill not in allowed_global:
                add_issue(
                    issues,
                    "MEDIUM",
                    "scope-drift",
                    path,
                    f"Rule `{rule_id}` allows `{skill}` globally but it is absent from global_allowlist.",
                )

    for skill in allowed_global:
        if skill_names and skill not in skill_names:
            add_issue(
                issues,
                "MEDIUM",
                "scope-drift",
                path,
                f"global_allowlist references unknown skill `{skill}`.",
            )


def check_skill_repo_entry(
    path: Path,
    entry: Any,
    issues: list[dict[str, str]],
    *,
    code: str,
) -> None:
    if not isinstance(entry, dict):
        return
    source_path = entry.get("path") or entry.get("source_path")
    source_root: Path | None = None
    if isinstance(source_path, str) and path_like(source_path):
        source_root = resolve_path(path.parent, source_path)
        if not source_root.exists():
            add_issue(
                issues,
                "HIGH",
                "missing-registry-source",
                path,
                f"Skill source path does not exist: {source_path}",
            )

    picks = static_skill_names(entry.get("pick", []))
    if source_root and source_root.exists():
        for skill in picks:
            if not (source_root / skill / "SKILL.md").exists():
                add_issue(
                    issues,
                    "HIGH",
                    code,
                    path,
                    f"Picked skill `{skill}` is missing under {source_path}.",
                )


def check_skill_repos(path: Path, data: Any, issues: list[dict[str, str]]) -> None:
    if data is None:
        add_issue(
            issues,
            "LOW",
            "registry-parse-degraded",
            path,
            "Could not parse YAML; path existence checks were skipped.",
        )
        return
    if isinstance(data, dict) and isinstance(data.get("skill_repos"), list):
        for entry in data["skill_repos"]:
            check_skill_repo_entry(path, entry, issues, code="missing-registry-source")
    check_declared_paths(path, data, issues, code="missing-registry-source")


def check_runtime_manifest(path: Path, data: Any, issues: list[dict[str, str]]) -> None:
    if data is None:
        add_issue(
            issues,
            "LOW",
            "runtime-parse-degraded",
            path,
            "Could not parse runtime manifest; bundle checks were skipped.",
        )
        return

    entries: list[Any] = []
    if isinstance(data, dict):
        for key in ("skill_repos", "skills", "sources"):
            if isinstance(data.get(key), list):
                entries.extend(data[key])
    elif isinstance(data, list):
        entries = data

    names: dict[str, int] = {}
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("id")
            if isinstance(name, str):
                names[name] = names.get(name, 0) + 1
            check_skill_repo_entry(path, entry, issues, code="bundle-drift")

    for name, count in names.items():
        if count > 1:
            add_issue(
                issues,
                "MEDIUM",
                "bundle-drift",
                path,
                f"Runtime manifest lists `{name}` {count} times.",
            )


def check_overlay(path: Path, data: Any, issues: list[dict[str, str]]) -> None:
    if not isinstance(data, dict):
        add_issue(issues, "MEDIUM", "overlay-drift", path, "overlay.yaml is not a YAML object.")
        return
    for field in ("cwd_match", "default_cwd"):
        value = data.get(field)
        if isinstance(value, str) and path_like(value):
            candidate = resolve_path(path.parent, value)
            if not candidate.exists():
                add_issue(
                    issues,
                    "HIGH",
                    "overlay-drift",
                    path,
                    f"{field} points at a missing path: {value}",
                )
    scan_roots = data.get("scan_roots", [])
    if isinstance(scan_roots, list):
        for value in scan_roots:
            if isinstance(value, str) and path_like(value):
                candidate = resolve_path(path.parent, value)
                if not candidate.exists():
                    add_issue(
                        issues,
                        "HIGH",
                        "overlay-drift",
                        path,
                        f"scan_roots entry points at a missing path: {value}",
                    )

    repo_ownership = data.get("repo_ownership", {})
    if isinstance(repo_ownership, dict):
        for repo_id, repo_data in repo_ownership.items():
            if not isinstance(repo_data, dict):
                continue
            value = repo_data.get("path")
            if isinstance(value, str) and path_like(value):
                candidate = resolve_path(path.parent, value)
                if not candidate.exists():
                    add_issue(
                        issues,
                        "HIGH",
                        "overlay-drift",
                        path,
                        f"repo_ownership `{repo_id}` points at a missing path: {value}",
                    )


def scan_root(root: Path) -> dict[str, Any]:
    files = list(iter_files(root))
    skill_repos = [p for p in files if p.name == "skill-repos.yaml"]
    skill_manifests = [p for p in files if p.name == "SKILL.md"]
    scope_files = [p for p in files if p.name == "skill-scope.yaml"]
    runtime_files = [
        p
        for p in files
        if any(hint in str(p) for hint in RUNTIME_HINTS)
    ]
    overlays = [
        p
        for p in files
        if p.name == "overlay.yaml" and "skillbox-config" in p.parts
    ]
    claude_mcp = [p for p in files if p.name == ".mcp.json"]
    codex_mcp = [p for p in files if p.name == "config.toml" and ".codex" in p.parts]

    issues: list[dict[str, str]] = []
    skill_names: dict[str, list[Path]] = {}

    for manifest in skill_manifests:
        meta = frontmatter(manifest)
        name = str(meta.get("name", "")).strip()
        desc = str(meta.get("description", "")).strip()
        if not name:
            add_issue(issues, "HIGH", "manifest-drift", manifest, "SKILL.md is missing a name.")
        else:
            skill_names.setdefault(name, []).append(manifest)
        if not desc:
            add_issue(
                issues,
                "HIGH",
                "manifest-drift",
                manifest,
                "SKILL.md is missing a description.",
            )
        owner = classify_skill_owner(manifest)
        if owner == "portable-skill-contract":
            text = read_text(manifest)
            if re.search(r"/Users/[A-Za-z0-9_.-]+/", text):
                add_issue(
                    issues,
                    "HIGH",
                    "placement-drift",
                    manifest,
                    "Portable skill contract contains a machine-local user path.",
                )

    for name, paths in skill_names.items():
        if len(paths) > 1:
            path_list = ", ".join(str(p) for p in paths[:4])
            add_issue(
                issues,
                "MEDIUM",
                "manifest-drift",
                paths[0],
                f"Duplicate skill name `{name}` appears in {len(paths)} manifests: {path_list}",
            )

    for registry in skill_repos:
        check_skill_repos(registry, yaml_load(registry), issues)

    for scope_file in scope_files:
        check_skill_scope(scope_file, yaml_load(scope_file), skill_names, issues)

    for runtime_file in runtime_files:
        if runtime_file in skill_repos:
            continue
        suffix = runtime_file.suffix.lower()
        if suffix == ".json":
            try:
                data = json.loads(read_text(runtime_file))
            except Exception:
                data = None
        else:
            data = yaml_load(runtime_file)
        check_runtime_manifest(runtime_file, data, issues)

    for overlay in overlays:
        check_overlay(overlay, yaml_load(overlay), issues)

    mcp_by_repo: dict[Path, dict[str, Any]] = {}
    for path in claude_mcp:
        mcp_by_repo.setdefault(path.parent, {})["claude"] = path
    for path in codex_mcp:
        repo = path.parent.parent
        mcp_by_repo.setdefault(repo, {})["codex"] = path

    for repo, pair in mcp_by_repo.items():
        claude = pair.get("claude")
        codex = pair.get("codex")
        if claude and not codex:
            add_issue(issues, "MEDIUM", "mcp-parity-drift", claude, "Codex MCP config is missing.")
            continue
        if codex and not claude:
            add_issue(issues, "MEDIUM", "mcp-parity-drift", codex, "Claude MCP config is missing.")
            continue
        claude_servers = claude_mcp_servers(claude)
        codex_servers = codex_mcp_servers(codex)
        if claude_servers != codex_servers:
            diff = sorted(claude_servers.symmetric_difference(codex_servers))
            add_issue(
                issues,
                "MEDIUM",
                "mcp-parity-drift",
                claude,
                f"Claude/Codex MCP server sets differ: {', '.join(diff)}",
            )

    inventory = {
        "root": str(root),
        "skill_repos_yaml": len(skill_repos),
        "skill_manifests": len(skill_manifests),
        "unique_skill_names": len(skill_names),
        "skill_scope_yaml": len(scope_files),
        "runtime_manifest_files": len(runtime_files),
        "client_overlays": len(overlays),
        "claude_mcp_configs": len(claude_mcp),
        "codex_mcp_configs": len(codex_mcp),
    }
    return {"inventory": inventory, "issues": issues}


def text_report(results: list[dict[str, Any]]) -> str:
    lines = ["skill registry scan (read-only)"]
    for result in results:
        inv = result["inventory"]
        lines.append(f"\nroot: {inv['root']}")
        for key, value in inv.items():
            if key != "root":
                lines.append(f"  {key}: {value}")
        issues = result["issues"]
        if not issues:
            lines.append("  issues: none found by scanner")
        else:
            lines.append(f"  issues: {len(issues)}")
            for issue in issues[:40]:
                lines.append(
                    f"  - {issue['severity']} {issue['code']}: {issue['path']} - {issue['message']}"
                )
            if len(issues) > 40:
                lines.append(f"  ... {len(issues) - 40} more issues; rerun with --json")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    roots = [Path(p).expanduser() for p in (args.root or ["."])]
    results = [scan_root(root) for root in roots]
    if args.json:
        print(json.dumps({"dry_run": True, "results": results}, indent=2, sort_keys=True))
    else:
        print(text_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
