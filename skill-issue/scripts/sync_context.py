#!/usr/bin/env python3
"""
Context Sync - Detect drift between registry and filesystem.

Usage:
    sync_context.py                        # Check for drift (default)
    sync_context.py --check                # Same as above
    sync_context.py --update               # Re-scan and update registry
    sync_context.py --context-dir <path>   # Custom registry location

Examples:
    sync_context.py                        # Show what changed since last audit
    sync_context.py --update               # Refresh registry to match filesystem
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

from lib.scanner import (
    scan_global_config,
    scan_projects,
    expand_path,
    file_hash,
    snapshot_project,
)
from lib.reporter import format_audit_report, detect_issues
from lib.registry import write_registry

try:
    import yaml
except ImportError:
    yaml = None


def load_manifest(context_dir):
    """Load manifest.yaml from registry. Returns dict or None."""
    manifest_path = context_dir / "manifest.yaml"
    if not manifest_path.exists():
        return None
    try:
        if yaml:
            return yaml.safe_load(manifest_path.read_text())
        else:
            import json
            return json.loads(manifest_path.read_text())
    except Exception:
        return None


def load_project_record(context_dir, name):
    """Load a project YAML record. Returns dict or None."""
    slug = name.replace("/", "-").replace(" ", "-").lower()
    path = context_dir / "projects" / f"{slug}.yaml"
    if not path.exists():
        return None
    try:
        if yaml:
            return yaml.safe_load(path.read_text())
        else:
            import json
            return json.loads(path.read_text())
    except Exception:
        return None


def check_drift(context_dir):
    """Compare registry against filesystem. Returns list of drift entries."""
    manifest = load_manifest(context_dir)
    if not manifest:
        print(f"No registry found at {context_dir}/")
        print("Run init_context.py first to create the registry.")
        return None

    last_updated = manifest.get("last_updated", "unknown")
    drifts = []

    # Get current filesystem state
    registered_projects = manifest.get("projects", {})

    # Determine scan roots from registered project paths.
    # Use the most common parent directory (the actual scan root),
    # not every project's parent — that would scan too broadly.
    parent_counts = {}
    for name, info in registered_projects.items():
        proj_path = info.get("path", "")
        if proj_path:
            parent = str(Path(proj_path).parent)
            parent_counts[parent] = parent_counts.get(parent, 0) + 1

    # Use parents that contain multiple projects, or all if each is unique.
    # Filter out home dir — it's never a scan root.
    home = os.path.expanduser("~")
    scan_roots = set()
    for parent, count in parent_counts.items():
        if parent != home:
            scan_roots.add(parent)

    # Scan filesystem for current state
    current_projects = scan_projects(list(scan_roots)) if scan_roots else []
    current_by_name = {p["name"]: p for p in current_projects}
    registered_names = set(registered_projects.keys())
    current_names = set(current_by_name.keys())

    # Projects added on filesystem but not in registry
    for name in sorted(current_names - registered_names):
        p = current_by_name[name]
        drifts.append({
            "status": "ADDED",
            "path": p["path"],
            "detail": "not in registry",
        })

    # Projects in registry but gone from filesystem
    for name in sorted(registered_names - current_names):
        info = registered_projects[name]
        path = info.get("path", name)
        if not Path(path).exists():
            drifts.append({
                "status": "REMOVED",
                "path": path,
                "detail": "path gone, still in registry",
            })
        else:
            # Path exists but no longer has Claude config
            drifts.append({
                "status": "REMOVED",
                "path": path,
                "detail": "Claude config removed, still in registry",
            })

    # Projects in both — check for content changes
    for name in sorted(registered_names & current_names):
        info = registered_projects[name]
        current = current_by_name[name]
        record = load_project_record(context_dir, name)

        changes = []

        # Compare config files by hash
        current_snap = snapshot_project(current)
        if record:
            for key in ("claude_md", "settings", "mcp"):
                reg_path = record.get(key)
                cur_path = current.get(key)

                if reg_path and not cur_path:
                    changes.append(f"{key} removed")
                elif not reg_path and cur_path:
                    changes.append(f"{key} added")
                elif reg_path and cur_path:
                    reg_hash = file_hash(reg_path)
                    cur_hash = file_hash(cur_path)
                    if reg_hash != cur_hash:
                        changes.append(f"{key} content changed")

            # Compare skills list
            reg_skills = set(record.get("skills") or [])
            cur_skills = set(current.get("skills") or [])
            added_skills = cur_skills - reg_skills
            removed_skills = reg_skills - cur_skills
            if added_skills:
                changes.append(f"skills added: {', '.join(sorted(added_skills))}")
            if removed_skills:
                changes.append(f"skills removed: {', '.join(sorted(removed_skills))}")

            # Compare hooks count
            reg_hooks = len(record.get("hooks") or [])
            cur_hooks = len(current.get("hooks") or [])
            if reg_hooks != cur_hooks:
                changes.append(f"hooks changed ({reg_hooks} -> {cur_hooks})")

            # Compare MCP servers
            reg_mcps = set(record.get("mcp_servers") or [])
            cur_mcps = set(m["name"] for m in (current.get("mcp_servers") or []))
            if reg_mcps != cur_mcps:
                changes.append(f"MCP servers changed")

        if changes:
            drifts.append({
                "status": "CHANGED",
                "path": info.get("path", name),
                "detail": "; ".join(changes),
            })
        else:
            drifts.append({
                "status": "OK",
                "path": info.get("path", name),
                "detail": "matches",
            })

    # Check global skills drift
    current_global = scan_global_config()
    reg_skills = manifest.get("skills", {})
    cur_symlinked = set(s["name"] for s in current_global["skills"].get("symlinked", []))
    reg_symlinked = set(reg_skills.get("symlinked", []))
    if cur_symlinked != reg_symlinked:
        added = cur_symlinked - reg_symlinked
        removed = reg_symlinked - cur_symlinked
        parts = []
        if added:
            parts.append(f"added: {', '.join(sorted(added))}")
        if removed:
            parts.append(f"removed: {', '.join(sorted(removed))}")
        drifts.append({
            "status": "CHANGED",
            "path": "~/.claude/skills/ (symlinked)",
            "detail": "; ".join(parts),
        })

    cur_count = (
        len(current_global["skills"].get("symlinked", []))
        + len(current_global["skills"].get("packaged", []))
        + len(current_global["skills"].get("local", []))
    )
    reg_count = reg_skills.get("count", 0)
    if cur_count != reg_count:
        drifts.append({
            "status": "CHANGED",
            "path": "~/.claude/skills/ (total)",
            "detail": f"count changed ({reg_count} -> {cur_count})",
        })

    return drifts, last_updated


def format_drift_report(drifts, last_updated):
    """Format drift entries as a text report."""
    lines = []
    lines.append(f"DRIFT REPORT (vs registry from {last_updated})")
    lines.append("")

    changed = [d for d in drifts if d["status"] not in ("OK",)]
    ok = [d for d in drifts if d["status"] == "OK"]

    if not changed:
        lines.append("  No drift detected. Registry matches filesystem.")
        lines.append(f"  ({len(ok)} entries checked, all OK)")
    else:
        for d in drifts:
            icon = {
                "ADDED": "+",
                "REMOVED": "-",
                "CHANGED": "~",
                "OK": " ",
            }.get(d["status"], "?")

            # Shorten path for display
            path = d["path"].replace(os.path.expanduser("~"), "~")
            status = d["status"].ljust(8)

            lines.append(f"  {icon} {status} {path.ljust(40)} {d['detail']}")

        lines.append("")
        summary_parts = []
        for status in ("ADDED", "REMOVED", "CHANGED", "OK"):
            count = len([d for d in drifts if d["status"] == status])
            if count:
                summary_parts.append(f"{count} {status.lower()}")
        lines.append(f"  Summary: {', '.join(summary_parts)}")

    lines.append("")
    return "\n".join(lines)


def update_registry(context_dir):
    """Re-scan filesystem and update the registry. Print what changed."""
    manifest = load_manifest(context_dir)

    # Determine scan roots (same filtering as check_drift)
    home = os.path.expanduser("~")
    scan_roots = set()
    if manifest:
        for name, info in (manifest.get("projects") or {}).items():
            path = info.get("path", "")
            if path:
                parent = str(Path(path).parent)
                if parent != home:
                    scan_roots.add(parent)

    if not scan_roots:
        scan_roots = {os.path.expanduser("~/repos")}

    # Get machine name from existing manifest
    machine_name = manifest.get("machine") if manifest else None

    # Re-scan
    global_config = scan_global_config()
    projects = scan_projects(list(scan_roots))

    # Compare counts for summary
    old_count = len(manifest.get("projects", {})) if manifest else 0
    new_count = len(projects)

    # Write updated registry
    write_registry(str(context_dir), global_config, projects, machine_name=machine_name)

    print(f"Registry updated at {context_dir}/")
    print(f"  Projects: {old_count} -> {new_count}")

    issues = detect_issues(global_config, projects)
    if issues:
        print(f"  Issues: {len(issues)}")


def main():
    args = sys.argv[1:]

    context_dir = expand_path("~/.claude/context")
    mode = "check"

    i = 0
    while i < len(args):
        if args[i] == "--check":
            mode = "check"
            i += 1
        elif args[i] == "--update":
            mode = "update"
            i += 1
        elif args[i] == "--context-dir" and i + 1 < len(args):
            context_dir = expand_path(args[i + 1])
            i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown argument: {args[i]}")
            print(__doc__)
            sys.exit(1)

    if mode == "check":
        result = check_drift(context_dir)
        if result is None:
            sys.exit(1)
        drifts, last_updated = result
        report = format_drift_report(drifts, last_updated)
        print(report)

        # Exit code: 0 if no drift, 1 if drift detected
        has_drift = any(d["status"] != "OK" for d in drifts)
        sys.exit(1 if has_drift else 0)

    elif mode == "update":
        update_registry(context_dir)


if __name__ == "__main__":
    main()
