#!/usr/bin/env python3
"""
Context Init - Bootstrap ~/.claude/context/ for a new machine or project.

Usage:
    init_context.py                          # Full interactive machine init
    init_context.py --project <path>         # Add a single project to existing registry
    init_context.py --non-interactive        # Accept all defaults, no prompts
    init_context.py --scan-root <path>       # Override default scan root

Examples:
    init_context.py                          # Walk through setup
    init_context.py --project ~/repos/my-app # Add one project
    init_context.py --non-interactive --scan-root ~/projects
"""

import sys
import os
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.scanner import scan_global_config, scan_projects, _scan_single_project, expand_path
from lib.reporter import format_audit_report, detect_issues
from lib.registry import write_registry


def prompt_input(question, default=None):
    """Prompt user for input with optional default."""
    if default:
        answer = input(f"  {question} [{default}] > ").strip()
        return answer or default
    else:
        return input(f"  {question} > ").strip()


def full_init(scan_roots=None, non_interactive=False):
    """Full machine init — scan everything, write registry."""
    context_dir = expand_path("~/.claude/context")

    if context_dir.exists() and not non_interactive:
        print(f"Registry already exists at {context_dir}/")
        answer = prompt_input("Overwrite? (y/n)", "y")
        if answer.lower() != "y":
            print("Aborted.")
            return

    # Step 1: Machine identity
    default_name = _default_machine_name()
    if non_interactive:
        machine_name = default_name
        print(f"Step 1: Machine name: {machine_name}")
    else:
        print("\nStep 1: Machine Identity")
        machine_name = prompt_input("What should this machine be called?", default_name)

    # Step 2: Scan roots
    default_root = os.path.expanduser("~/repos")
    if scan_roots:
        roots = scan_roots
    elif non_interactive:
        roots = [default_root]
    else:
        print("\nStep 2: Scan Roots")
        root_input = prompt_input("Where do you keep your repos?", default_root)
        roots = [r.strip() for r in root_input.split(",")]

    print(f"  Scanning: {', '.join(roots)}")

    # Step 3: Scan
    print("\nStep 3: Scanning...")
    global_config = scan_global_config()
    projects = scan_projects(roots)

    skills = global_config.get("skills", {})
    total_skills = (
        len(skills.get("symlinked", []))
        + len(skills.get("packaged", []))
        + len(skills.get("local", []))
    )
    mcp_count = sum(len(p.get("mcp_servers", [])) for p in projects)

    print(f"  Found {len(projects)} projects with Claude config.")
    print(f"  Found {mcp_count} MCP servers.")
    print(f"  Found {total_skills} skills.")

    # Step 4: Review (interactive only)
    if not non_interactive and projects:
        print("\nStep 4: Review")
        print("  Projects found:")
        for i, p in enumerate(projects, 1):
            parts = []
            if p.get("settings"):
                parts.append("settings")
            if p.get("hooks"):
                parts.append(f"hooks({len(p['hooks'])})")
            if p.get("skills"):
                parts.append(f"skills({len(p['skills'])})")
            if p.get("mcp_servers"):
                mcps = ", ".join(m["name"] for m in p["mcp_servers"])
                parts.append(f"mcp: {mcps}")
            if p.get("claude_md"):
                parts.append("CLAUDE.md")
            detail = f" ({', '.join(parts)})" if parts else ""
            print(f"    {i}. {p['name']}{detail}")

    # Step 5: Write registry
    step = "Step 5" if not non_interactive else "Step 4"
    print(f"\n{step}: Writing Registry")
    write_registry(str(context_dir), global_config, projects, machine_name=machine_name)

    # Count files written
    file_count = 1  # manifest
    file_count += len(list((context_dir / "projects").glob("*.yaml")))
    file_count += len(list((context_dir / "mcps").glob("*.yaml")))
    file_count += len(list((context_dir / "machines").glob("*.yaml")))

    print(f"  Created {file_count} registry files in {context_dir}/")

    # Show issues
    issues = detect_issues(global_config, projects)
    if issues:
        print(f"\n  Issues detected: {len(issues)}")
        for issue in issues[:5]:
            icon = {"warn": "\u26a0", "info": "\u2139", "error": "\u274c"}.get(issue["severity"], "\u26a0")
            print(f"    {icon} {issue['message']}")
        if len(issues) > 5:
            print(f"    ... and {len(issues) - 5} more (run audit for full report)")

    print(f"\nDone. Run `audit_context.py` anytime to refresh.")


def project_init(project_path):
    """Add a single project to an existing registry."""
    context_dir = expand_path("~/.claude/context")
    project_path = expand_path(project_path)

    if not project_path.is_dir():
        print(f"Error: {project_path} is not a directory")
        sys.exit(1)

    if not context_dir.exists():
        print(f"No registry found at {context_dir}/")
        print("Run init_context.py first (without --project) to create the registry.")
        sys.exit(1)

    # Scan the project
    from lib.scanner import _scan_single_project
    project = _scan_single_project(project_path)

    if not project:
        print(f"No Claude config found in {project_path}")
        print("Expected: .claude/ directory, CLAUDE.md, or .mcp.json")
        sys.exit(1)

    # Read existing registry and merge
    global_config = scan_global_config()

    # Load existing projects from manifest
    manifest_path = context_dir / "manifest.yaml"
    existing_projects = []
    if manifest_path.exists():
        try:
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text())
            # Re-scan existing projects to get full data
            existing_paths = [v.get("path", "") for v in (manifest.get("projects") or {}).values()]
            for ep in existing_paths:
                if ep and Path(ep).is_dir() and Path(ep).resolve() != project_path:
                    scanned = _scan_single_project(Path(ep))
                    if scanned:
                        existing_projects.append(scanned)
        except Exception:
            pass

    # Add the new project
    all_projects = existing_projects + [project]
    all_projects = sorted(all_projects, key=lambda p: p["name"])

    # Re-read machine name from existing manifest
    machine_name = None
    if manifest_path.exists():
        try:
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text())
            machine_name = manifest.get("machine")
        except Exception:
            pass

    write_registry(str(context_dir), global_config, all_projects, machine_name=machine_name)

    parts = []
    if project.get("settings"):
        parts.append("settings")
    if project.get("hooks"):
        parts.append(f"hooks({len(project['hooks'])})")
    if project.get("skills"):
        parts.append(f"skills({len(project['skills'])})")
    if project.get("mcp_servers"):
        parts.append(f"mcp({len(project['mcp_servers'])})")
    if project.get("claude_md"):
        parts.append("CLAUDE.md")

    detail = f" ({', '.join(parts)})" if parts else ""
    print(f"Added {project['name']}{detail} to registry.")
    print(f"Registry updated at {context_dir}/")


def _default_machine_name():
    """Generate a default machine name from hostname."""
    hostname = socket.gethostname().lower()
    for suffix in [".local", ".lan", ".home"]:
        if hostname.endswith(suffix):
            hostname = hostname[: -len(suffix)]
    return hostname


def main():
    args = sys.argv[1:]

    scan_roots = []
    project_path = None
    non_interactive = False

    i = 0
    while i < len(args):
        if args[i] == "--project" and i + 1 < len(args):
            project_path = args[i + 1]
            i += 2
        elif args[i] == "--scan-root" and i + 1 < len(args):
            scan_roots.append(args[i + 1])
            i += 2
        elif args[i] == "--non-interactive":
            non_interactive = True
            i += 1
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown argument: {args[i]}")
            print(__doc__)
            sys.exit(1)

    if project_path:
        project_init(project_path)
    else:
        full_init(scan_roots=scan_roots or None, non_interactive=non_interactive)


if __name__ == "__main__":
    main()
