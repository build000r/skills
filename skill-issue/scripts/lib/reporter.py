"""
Report formatting for context audit output.

Produces styled text reports for terminal display.
"""

import os
from datetime import datetime, timezone


def format_audit_report(global_config, projects, issues):
    """Format a full audit report as styled text.

    Args:
        global_config: Dict from scanner.scan_global_config()
        projects: List of dicts from scanner.scan_projects()
        issues: List of issue dicts from detect_issues()

    Returns:
        Formatted string for terminal output.
    """
    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    import platform
    import socket

    hostname = socket.gethostname()
    plat = platform.system()

    # Header
    lines.append("=" * 55)
    lines.append("  CLAUDE ENVIRONMENT AUDIT")
    lines.append(f"  Machine: {hostname} ({plat.lower()})")
    lines.append(f"  Scanned: {now}")
    lines.append("=" * 55)
    lines.append("")

    # Summary
    skills = global_config.get("skills", {})
    symlinked = skills.get("symlinked", [])
    packaged = skills.get("packaged", [])
    local = skills.get("local", [])
    total_skills = len(symlinked) + len(packaged) + len(local)

    projects_with_config = [p for p in projects if p.get("claude_dir")]
    claude_mds = [p for p in projects if p.get("claude_md")]
    all_mcps = set()
    total_hooks = 0
    projects_with_hooks = set()
    for p in projects:
        for mcp in p.get("mcp_servers", []):
            all_mcps.add(mcp["name"])
        if p.get("hooks"):
            total_hooks += len(p["hooks"])
            projects_with_hooks.add(p["name"])

    lines.append("SUMMARY")
    lines.append(f"  Projects:     {len(projects)} discovered, {len(projects_with_config)} with .claude/ config")
    lines.append(f"  CLAUDE.md:    {len(claude_mds)} files")
    lines.append(f"  MCP servers:  {len(all_mcps)} across {sum(1 for p in projects if p.get('mcp_servers'))} projects")
    lines.append(f"  Skills:       {total_skills} installed ({len(symlinked)} symlinked, {len(packaged)} packaged)")
    lines.append(f"  Commands:     {len(global_config.get('commands', []))} global")
    lines.append(f"  Hooks:        {total_hooks} across {len(projects_with_hooks)} project(s)")
    lines.append("")

    # Issues
    if issues:
        lines.append(f"ISSUES ({len(issues)} found)")
        for issue in issues:
            severity = issue.get("severity", "warn")
            icon = {"warn": "\u26a0", "info": "\u2139", "error": "\u274c"}.get(severity, "\u26a0")
            category = issue.get("category", "").upper().ljust(10)
            lines.append(f"  {icon} {category} {issue['message']}")
        lines.append("")
    else:
        lines.append("ISSUES: None found")
        lines.append("")

    # Projects with richest config
    ranked = sorted(projects, key=lambda p: _project_richness(p), reverse=True)
    top = [p for p in ranked if _project_richness(p) > 0][:5]
    if top:
        lines.append("PROJECTS WITH RICHEST CONFIG")
        for p in top:
            parts = []
            if p.get("settings"):
                parts.append("settings")
            if p.get("hooks"):
                parts.append(f"hooks({len(p['hooks'])})")
            if p.get("skills"):
                parts.append(f"skills({len(p['skills'])})")
            if p.get("mcp_servers"):
                parts.append(f"mcp({len(p['mcp_servers'])})")
            if p.get("claude_md"):
                parts.append("CLAUDE.md")
            lines.append(f"  {p['name'].ljust(20)} {' + '.join(parts)}")
        lines.append("")

    # MCP Servers
    mcp_rows = []
    for p in projects:
        for mcp in p.get("mcp_servers", []):
            mcp_rows.append({
                "name": mcp["name"],
                "type": mcp.get("type", "?"),
                "project": p["name"],
                "has_secrets": mcp.get("has_secrets", False),
            })
    if mcp_rows:
        lines.append("MCP SERVERS")
        for row in mcp_rows:
            flag = " \u26a0 has secrets" if row["has_secrets"] else ""
            lines.append(f"  {row['name'].ljust(30)} {row['type'].ljust(8)} {row['project']}{flag}")
        lines.append("")

    # Skills by type
    lines.append("SKILLS BY TYPE")
    if symlinked:
        names = [s["name"] for s in symlinked]
        lines.append(f"  Symlinked ({len(symlinked)}):  {', '.join(names)}")
    modes = skills.get("with_modes", {})
    if modes:
        mode_parts = []
        for skill_name, mode_list in modes.items():
            mode_names = [m["name"] for m in mode_list]
            mode_parts.append(f"{skill_name} (modes: {', '.join(mode_names)})")
        lines.append(f"  With modes ({len(modes)}): {', '.join(mode_parts)}")
    if packaged:
        lines.append(f"  Packaged ({len(packaged)}):  {', '.join(packaged)}")
    if local:
        display = local[:10]
        suffix = f", ... (+{len(local) - 10} more)" if len(local) > 10 else ""
        lines.append(f"  Local ({len(local)}):     {', '.join(display)}{suffix}")
    lines.append("")

    return "\n".join(lines)


def _project_richness(p):
    """Score a project by how much Claude config it has."""
    score = 0
    if p.get("settings"):
        score += 2
    if p.get("hooks"):
        score += len(p["hooks"])
    if p.get("skills"):
        score += len(p["skills"])
    if p.get("mcp_servers"):
        score += len(p["mcp_servers"])
    if p.get("claude_md"):
        score += 1
    return score


def detect_issues(global_config, projects):
    """Detect issues across the Claude environment.

    Returns list of issue dicts with: severity, category, message.
    """
    issues = []

    # Check for secrets in MCP configs
    for p in projects:
        for mcp in p.get("mcp_servers", []):
            if mcp.get("has_secrets"):
                n_vars = len(mcp.get("env_vars", []))
                issues.append({
                    "severity": "warn",
                    "category": "secrets",
                    "message": f"{p['name']}/.mcp.json — {mcp['name']} has {n_vars} env vars with potential credentials",
                })

    # Check for broken symlinks in skills
    skills = global_config.get("skills", {})
    for s in skills.get("symlinked", []):
        if s.get("broken"):
            issues.append({
                "severity": "error",
                "category": "broken",
                "message": f"Skill symlink '{s['name']}' target does not exist",
            })

    # Check for stale projects (no settings, no hooks, no skills, no MCP)
    for p in projects:
        if (p.get("claude_dir")
                and not p.get("settings")
                and not p.get("hooks")
                and not p.get("skills")
                and not p.get("mcp_servers")
                and not p.get("claude_md")):
            issues.append({
                "severity": "info",
                "category": "stale",
                "message": f"{p['name']}/.claude/ — empty config directory (no settings, hooks, or skills)",
            })

    # Check for duplicate MCP server names with different configs
    mcp_by_name = {}
    for p in projects:
        for mcp in p.get("mcp_servers", []):
            mcp_by_name.setdefault(mcp["name"], []).append(p["name"])
    for name, project_list in mcp_by_name.items():
        if len(project_list) > 1:
            issues.append({
                "severity": "info",
                "category": "duplicate",
                "message": f"MCP '{name}' defined in {len(project_list)} projects: {', '.join(project_list)}",
            })

    # Check for mode files referencing nonexistent cwd_match paths
    for skill_name, modes in skills.get("with_modes", {}).items():
        for mode in modes:
            cwd = mode.get("cwd_match")
            if cwd:
                expanded = os.path.expanduser(cwd)
                if not os.path.isdir(expanded):
                    issues.append({
                        "severity": "warn",
                        "category": "mode-drift",
                        "message": f"Skill '{skill_name}' mode '{mode['name']}' targets nonexistent path: {cwd}",
                    })

    # Check parent-level CLAUDE.md that could affect many projects
    parent_mds = []
    for p in projects:
        md = p.get("claude_md")
        if md:
            md_path = os.path.dirname(md)
            # If CLAUDE.md is at a parent level (e.g., ~/repos/.claude/CLAUDE.md)
            child_projects = [
                other["name"] for other in projects
                if other["path"] != p["path"] and other["path"].startswith(p["path"])
            ]
            if child_projects:
                parent_mds.append((p["name"], md, len(child_projects)))

    for name, md, count in parent_mds:
        issues.append({
            "severity": "info",
            "category": "parent",
            "message": f"{name} has CLAUDE.md that inherits to {count} child project(s)",
        })

    return issues
