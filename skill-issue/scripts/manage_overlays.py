#!/usr/bin/env python3
"""Manage skillbox client overlays: list, validate, create, migrate.

Usage:
    manage_overlays.py list   [--config-root DIR]
    manage_overlays.py validate [--config-root DIR]
    manage_overlays.py create --client-id ID [--cwd DIR] [--config-root DIR]
    manage_overlays.py migrate --from-version N --to-version N [--config-root DIR]
    manage_overlays.py match  [--cwd DIR] [--config-root DIR]

All commands output JSON when --json is passed.
By default, new overlays are created under .buildooor/skillbox-config/clients
inside the target git repo; legacy/shared skillbox-config/clients roots are
still discovered for matching and explicit --config-root use.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml


CONFIG_ROOT_SUFFIXES = (
    (".buildooor", "skillbox-config", "clients"),
    ("skillbox-config", "clients"),
)


def _candidate_config_roots(base: Path) -> list[Path]:
    return [base.joinpath(*suffix) for suffix in CONFIG_ROOT_SUFFIXES]


def _find_git_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return None


def _start_path(start: str | Path | None = None) -> Path:
    if start is None:
        return Path.cwd()
    return Path(os.path.abspath(os.path.expanduser(os.path.expandvars(str(start)))))


def find_config_root(start: str | Path | None = None) -> Path | None:
    """Walk up from cwd looking for a known clients/ root."""
    cwd = _start_path(start)
    for p in [cwd, *cwd.parents]:
        for candidate in _candidate_config_roots(p):
            if candidate.is_dir():
                return candidate
    return None


def find_config_roots(start: str | Path | None = None) -> list[Path]:
    """Walk up from cwd and return every known clients/ root."""
    cwd = _start_path(start)
    roots = []
    for p in [cwd, *cwd.parents]:
        for candidate in _candidate_config_roots(p):
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
    return roots


def default_create_config_root(cwd: str) -> Path:
    """Create new overlays inside the current git repo's tracked .buildooor tree."""
    cwd_path = Path(os.path.abspath(os.path.expanduser(os.path.expandvars(cwd))))
    git_root = _find_git_root(cwd_path)
    base = git_root if git_root is not None else cwd_path
    return base / ".buildooor" / "skillbox-config" / "clients"


def load_overlays(config_root: Path) -> list[dict]:
    """Load all overlay.yaml files under config_root."""
    overlays = []
    if not config_root.is_dir():
        return overlays
    for client_dir in sorted(config_root.iterdir()):
        overlay_file = client_dir / "overlay.yaml"
        if overlay_file.is_file():
            try:
                data = yaml.safe_load(overlay_file.read_text())
                if not isinstance(data, dict):
                    raise ValueError(
                        f"overlay.yaml must contain a YAML mapping, got {type(data).__name__}"
                    )
                overlays.append({
                    "client_id": client_dir.name,
                    "path": str(overlay_file),
                    "data": data,
                })
            except Exception as e:
                overlays.append({
                    "client_id": client_dir.name,
                    "path": str(overlay_file),
                    "error": str(e),
                })
    return overlays


def _matches_prefix(cwd: str, prefix: str) -> bool:
    """Return true when cwd is exactly prefix or below it as a path segment."""
    if prefix == os.sep:
        return True
    return cwd == prefix or cwd.startswith(prefix + os.sep)


def _expanded_match(pattern: str) -> str | None:
    expanded = os.path.abspath(os.path.expanduser(os.path.expandvars(pattern)))
    if "$" in expanded:
        return None
    return expanded


def _cwd_match_patterns(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def cmd_list(config_root: Path, as_json: bool) -> int:
    """List all client overlays."""
    overlays = load_overlays(config_root)
    if not overlays:
        if as_json:
            print(json.dumps({"overlays": [], "config_root": str(config_root)}))
        else:
            print(f"No client overlays found in {config_root}")
        return 0

    if as_json:
        summary = []
        for o in overlays:
            entry = {"client_id": o["client_id"], "path": o["path"]}
            if "error" in o:
                entry["error"] = o["error"]
            else:
                client = o["data"].get("client", {})
                ctx = client.get("context", {})
                entry["label"] = client.get("label", "")
                entry["cwd_match"] = ctx.get("cwd_match", [])
                entry["repos"] = len(client.get("repos", []))
                entry["version"] = o["data"].get("version", "unknown")
            summary.append(entry)
        print(json.dumps({"overlays": summary, "config_root": str(config_root)}, indent=2))
    else:
        print(f"Client overlays in {config_root}:\n")
        for o in overlays:
            if "error" in o:
                print(f"  {o['client_id']}  ERROR: {o['error']}")
                continue
            client = o["data"].get("client", {})
            ctx = client.get("context", {})
            cwd_match = ctx.get("cwd_match", [])
            repos = len(client.get("repos", []))
            label = client.get("label", o["client_id"])
            print(f"  {o['client_id']}  ({label})")
            print(f"    cwd_match: {', '.join(cwd_match) if cwd_match else '(none)'}")
            print(f"    repos: {repos}")
    return 0


def cmd_validate(config_root: Path, as_json: bool) -> int:
    """Validate all overlays: check structure, path existence, required fields."""
    overlays = load_overlays(config_root)
    results = []
    has_errors = False

    for o in overlays:
        issues = []
        if "error" in o:
            issues.append({"severity": "error", "message": f"YAML parse error: {o['error']}"})
        else:
            data = o["data"]
            # Check version
            if "version" not in data:
                issues.append({"severity": "warn", "message": "Missing 'version' field"})

            client = data.get("client", {})
            if not client:
                issues.append({"severity": "error", "message": "Missing 'client' block"})
            else:
                # Required fields
                if not client.get("id"):
                    issues.append({"severity": "error", "message": "Missing client.id"})
                ctx = client.get("context", {})
                if not ctx.get("cwd_match"):
                    issues.append({"severity": "warn", "message": "No cwd_match — this overlay will never auto-select"})

                # Check repo paths (expand env vars)
                for repo in client.get("repos", []):
                    repo_path = repo.get("path", "")
                    expanded = os.path.expanduser(os.path.expandvars(repo_path))
                    # Only validate paths that don't contain unexpanded vars
                    if "${" not in expanded and expanded and not Path(expanded).exists():
                        issues.append({
                            "severity": "warn",
                            "message": f"Repo path does not exist: {expanded} (id: {repo.get('id', '?')})",
                        })

        errors = [i for i in issues if i["severity"] == "error"]
        if errors:
            has_errors = True

        results.append({
            "client_id": o["client_id"],
            "path": o["path"],
            "issues": issues,
            "ok": len(errors) == 0,
        })

    if as_json:
        print(json.dumps({"results": results, "all_ok": not has_errors}, indent=2))
    else:
        if not results:
            print(f"No overlays to validate in {config_root}")
            return 0
        for r in results:
            status = "OK" if r["ok"] else "FAIL"
            print(f"  {r['client_id']}  [{status}]")
            for issue in r["issues"]:
                marker = "ERROR" if issue["severity"] == "error" else "WARN"
                print(f"    {marker}: {issue['message']}")
        if has_errors:
            print(f"\n{sum(1 for r in results if not r['ok'])} overlay(s) with errors")

    return 1 if has_errors else 0


def find_matches(cwd: str, config_root: Path) -> list[dict]:
    """Find overlay matches for a cwd in one config root."""
    cwd_path = os.path.abspath(os.path.expanduser(os.path.expandvars(cwd)))
    candidates = []

    for client_dir in sorted(config_root.iterdir()) if config_root.is_dir() else []:
        ctx_file = client_dir / "context.yaml"
        if not ctx_file.is_file():
            continue
        try:
            data = yaml.safe_load(ctx_file.read_text()) or {}
        except Exception:
            continue
        patterns = _cwd_match_patterns(data.get("cwd_match", []))
        overlay_file = client_dir / "overlay.yaml"
        match_path = overlay_file if overlay_file.is_file() else ctx_file
        for pattern in patterns:
            expanded = _expanded_match(str(pattern))
            if expanded is None or not _matches_prefix(cwd_path, expanded):
                continue
            candidates.append({
                "client_id": client_dir.name,
                "path": str(match_path),
                "source_path": str(ctx_file),
                "source_kind": "context",
                "config_root": str(config_root),
                "matched_pattern": str(pattern),
                "expanded": expanded,
                "_match_len": len(expanded),
                "_priority": 1,
            })

    overlays = load_overlays(config_root)
    for o in overlays:
        if "error" in o:
            continue
        client = o["data"].get("client", {})
        ctx = client.get("context", {})
        for pattern in _cwd_match_patterns(ctx.get("cwd_match", [])):
            expanded = _expanded_match(str(pattern))
            if expanded is None or not _matches_prefix(cwd_path, expanded):
                continue
            candidates.append({
                "client_id": o["client_id"],
                "path": o["path"],
                "source_path": o["path"],
                "source_kind": "overlay",
                "config_root": str(config_root),
                "matched_pattern": pattern,
                "expanded": expanded,
                "_match_len": len(expanded),
                "_priority": 0,
            })

    if not candidates:
        return []

    best_len = max(match["_match_len"] for match in candidates)
    top = [match for match in candidates if match["_match_len"] == best_len]
    best_priority = max(match["_priority"] for match in top)
    top = [match for match in top if match["_priority"] == best_priority]

    cleaned = []
    seen = set()
    for match in top:
        key = (match["client_id"], match["path"], match["expanded"])
        if key in seen:
            continue
        seen.add(key)
        match = dict(match)
        del match["_match_len"]
        del match["_priority"]
        cleaned.append(match)
    return cleaned


def cmd_match(cwd: str, config_root: Path, as_json: bool) -> int:
    """Find which overlay matches a given cwd."""
    cwd_path = os.path.abspath(os.path.expanduser(os.path.expandvars(cwd)))
    matches = find_matches(cwd, config_root)

    if as_json:
        print(json.dumps({"cwd": cwd_path, "matches": matches}, indent=2))
    else:
        if not matches:
            print(f"No overlay matches cwd: {cwd_path}")
            return 1
        for m in matches:
            print(f"  {m['client_id']}  (pattern: {m['matched_pattern']})")

    return 0 if matches else 1


def cmd_match_roots(cwd: str, config_roots: list[Path], as_json: bool) -> int:
    """Find overlay matches across multiple local config roots."""
    cwd_path = os.path.abspath(os.path.expanduser(os.path.expandvars(cwd)))
    matches = []
    for root_index, config_root in enumerate(config_roots):
        for match in find_matches(cwd, config_root):
            match["_root_index"] = root_index
            match["_match_len"] = len(match["expanded"])
            matches.append(match)

    if matches:
        best_len = max(match["_match_len"] for match in matches)
        matches = [match for match in matches if match["_match_len"] == best_len]
        best_root = min(match["_root_index"] for match in matches)
        matches = [match for match in matches if match["_root_index"] == best_root]
        for match in matches:
            del match["_root_index"]
            del match["_match_len"]

    if as_json:
        print(json.dumps({
            "cwd": cwd_path,
            "config_roots": [str(root) for root in config_roots],
            "matches": matches,
        }, indent=2))
    else:
        if not matches:
            print(f"No overlay matches cwd: {cwd_path}")
            return 1
        for m in matches:
            print(f"  {m['client_id']}  (pattern: {m['matched_pattern']})")

    return 0 if matches else 1


def cmd_create(client_id: str, cwd: str, config_root: Path, as_json: bool) -> int:
    """Create a minimal overlay for a new client."""
    target_dir = config_root / client_id
    target_file = target_dir / "overlay.yaml"

    if target_file.exists():
        msg = f"Overlay already exists: {target_file}"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return 1

    cwd_abs = str(_start_path(cwd))

    overlay = {
        "version": 1,
        "client": {
            "id": client_id,
            "label": client_id.replace("-", " ").replace("_", " ").title(),
            "default_cwd": cwd_abs,
            "repos": [],
            "logs": [],
            "context": {
                "cwd_match": [cwd_abs],
                "plans": {
                    "plan_root": "plans/released",
                    "plan_draft": "plans/draft",
                    "plan_index": "plans/INDEX.md",
                    "session_plans": "plans/sessions",
                },
            },
            "checks": [],
        },
    }

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(yaml.dump(overlay, default_flow_style=False, sort_keys=False))

    if as_json:
        print(json.dumps({
            "created": str(target_file),
            "client_id": client_id,
            "cwd_match": [cwd_abs],
            "note": "Minimal overlay — enrich with scan data or edit manually",
        }, indent=2))
    else:
        print(f"Created {target_file}")
        print(f"  cwd_match: {cwd_abs}")
        print("  Minimal overlay — enrich with scan data or edit manually")

    return 0


def cmd_migrate(from_ver: int, to_ver: int, config_root: Path, as_json: bool) -> int:
    """Report which overlays need migration between versions."""
    overlays = load_overlays(config_root)
    needs_migration = []

    for o in overlays:
        if "error" in o:
            needs_migration.append({
                "client_id": o["client_id"],
                "current_version": "parse_error",
                "action": "fix YAML first",
            })
            continue
        ver = o["data"].get("version", 0)
        if ver < to_ver:
            needs_migration.append({
                "client_id": o["client_id"],
                "current_version": ver,
                "action": f"migrate {ver} → {to_ver}",
            })

    if as_json:
        print(json.dumps({
            "from_version": from_ver,
            "to_version": to_ver,
            "needs_migration": needs_migration,
        }, indent=2))
    else:
        if not needs_migration:
            print(f"All overlays are at version {to_ver} or newer")
        else:
            print(f"Overlays needing migration to v{to_ver}:")
            for m in needs_migration:
                print(f"  {m['client_id']}  v{m['current_version']} → {m['action']}")

    return 0 if not needs_migration else 1


def main():
    parser = argparse.ArgumentParser(description="Manage skillbox client overlays")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--config-root", default=None, help="Path to clients/ directory")
    sub = parser.add_subparsers(dest="command")

    list_p = sub.add_parser("list", help="List all client overlays")
    list_p.add_argument("--json", action="store_true", dest="sub_json")

    validate_p = sub.add_parser("validate", help="Validate overlay structure and paths")
    validate_p.add_argument("--json", action="store_true", dest="sub_json")

    match_p = sub.add_parser("match", help="Find overlay matching a cwd")
    match_p.add_argument("--cwd", default=os.getcwd(), help="Working directory to match")
    match_p.add_argument("--json", action="store_true", dest="sub_json")

    create_p = sub.add_parser("create", help="Create a minimal overlay")
    create_p.add_argument("--client-id", required=True, help="Client identifier")
    create_p.add_argument("--cwd", default=os.getcwd(), help="Working directory for cwd_match")
    create_p.add_argument("--json", action="store_true", dest="sub_json")

    migrate_p = sub.add_parser("migrate", help="Check/run overlay migrations")
    migrate_p.add_argument("--from-version", type=int, default=0)
    migrate_p.add_argument("--to-version", type=int, required=True)
    migrate_p.add_argument("--json", action="store_true", dest="sub_json")

    args = parser.parse_args()
    # Merge --json from either position
    if hasattr(args, "sub_json") and args.sub_json:
        args.json = True

    if not args.command:
        parser.print_help()
        return 1

    config_root_explicit = args.config_root is not None
    if config_root_explicit:
        config_root = Path(args.config_root)
    elif args.command == "create":
        config_root = default_create_config_root(args.cwd)
    else:
        config_root = find_config_root(args.cwd if args.command == "match" else None)
        if config_root is None:
            fallback_base = _start_path(args.cwd) if args.command == "match" else Path.cwd()
            config_root = fallback_base / ".buildooor" / "skillbox-config" / "clients"

    if args.command == "list":
        return cmd_list(config_root, args.json)
    elif args.command == "validate":
        return cmd_validate(config_root, args.json)
    elif args.command == "match":
        if not config_root_explicit:
            config_roots = find_config_roots(args.cwd)
            if not config_roots:
                config_roots = [config_root]
            return cmd_match_roots(args.cwd, config_roots, args.json)
        return cmd_match(args.cwd, config_root, args.json)
    elif args.command == "create":
        return cmd_create(args.client_id, args.cwd, config_root, args.json)
    elif args.command == "migrate":
        return cmd_migrate(args.from_version, args.to_version, config_root, args.json)


if __name__ == "__main__":
    sys.exit(main() or 0)
