"""
Filesystem scanner for Claude configuration.

Discovers projects, MCP servers, skills, CLAUDE.md files, hooks,
and other Claude config across scan roots and ~/.claude/.
"""

import hashlib
import json
import os
from pathlib import Path


def expand_path(p):
    """Expand ~ and resolve path."""
    return Path(os.path.expanduser(str(p))).resolve()


def scan_global_config(claude_home=None):
    """Scan ~/.claude/ for global configuration.

    Returns dict with: settings, commands, skills, permissions.
    """
    home = expand_path(claude_home or "~/.claude")
    result = {
        "path": str(home),
        "settings": None,
        "commands": [],
        "skills": {"symlinked": [], "packaged": [], "local": [], "with_modes": {}},
        "permissions_mode": None,
        "model": None,
    }

    # Settings
    settings_path = home / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            result["settings"] = str(settings_path)
            perms = settings.get("permissions", {})
            result["permissions_mode"] = perms.get("defaultMode", "unknown")
            result["model"] = settings.get("model")
        except (json.JSONDecodeError, OSError):
            result["settings"] = str(settings_path)

    # Commands
    commands_dir = home / "commands"
    if commands_dir.is_dir():
        result["commands"] = sorted(
            f.stem for f in commands_dir.iterdir() if f.suffix == ".md"
        )

    # Skills
    skills_dir = home / "skills"
    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            name = entry.name
            if name.startswith("."):
                continue

            if entry.suffix == ".skill":
                result["skills"]["packaged"].append(name.removesuffix(".skill"))
            elif entry.is_symlink():
                target = str(entry.resolve()) if entry.exists() else None
                result["skills"]["symlinked"].append(
                    {"name": name, "target": target, "broken": not entry.exists()}
                )
            elif entry.is_dir():
                result["skills"]["local"].append(name)

            # Check for modes/ directory
            modes_dir = entry / "modes" if entry.is_dir() else None
            if modes_dir and modes_dir.is_dir():
                modes = []
                for mf in sorted(modes_dir.iterdir()):
                    if mf.suffix == ".md":
                        cwd_match = _extract_cwd_match(mf)
                        modes.append(
                            {"name": mf.stem, "cwd_match": cwd_match}
                        )
                if modes:
                    result["skills"]["with_modes"][name] = modes

    return result


def scan_projects(scan_roots):
    """Scan directories for projects with Claude configuration.

    Args:
        scan_roots: List of paths to scan (depth 1-2 for .claude/, CLAUDE.md, .mcp.json)

    Returns:
        List of project dicts.
    """
    projects = []
    seen_paths = set()

    for root in scan_roots:
        root = expand_path(root)
        if not root.is_dir():
            continue

        # Check the root itself and its immediate children
        candidates = [root] + sorted(
            d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

        for candidate in candidates:
            path = candidate.resolve()
            if path in seen_paths:
                continue

            project = _scan_single_project(path)
            if project:
                seen_paths.add(path)
                projects.append(project)

    return sorted(projects, key=lambda p: p["name"])


def _scan_single_project(path):
    """Scan a single directory for Claude configuration. Returns project dict or None."""
    claude_dir = path / ".claude"
    claude_md = path / "CLAUDE.md"
    mcp_json = path / ".mcp.json"

    has_config = claude_dir.is_dir() or claude_md.exists() or mcp_json.exists()
    if not has_config:
        return None

    project = {
        "name": path.name,
        "path": str(path),
        "claude_md": None,
        "claude_dir": None,
        "settings": None,
        "hooks": [],
        "skills": [],
        "mcp": None,
        "mcp_servers": [],
        "is_repo": (path / ".git").exists(),
    }

    # CLAUDE.md
    if claude_md.exists():
        project["claude_md"] = str(claude_md)

    # .claude/ directory
    if claude_dir.is_dir():
        project["claude_dir"] = str(claude_dir)

        # Settings
        settings_path = claude_dir / "settings.json"
        if settings_path.exists():
            project["settings"] = str(settings_path)
            try:
                settings = json.loads(settings_path.read_text())
                # Check for hooks
                hooks = settings.get("hooks", {})
                if hooks:
                    for event_type, hook_list in hooks.items():
                        if isinstance(hook_list, list):
                            for h in hook_list:
                                matcher = h.get("matcher", "*")
                                cmd = h.get("command", h.get("script", ""))
                                project["hooks"].append(
                                    {"type": event_type, "matcher": matcher, "command": cmd}
                                )
            except (json.JSONDecodeError, OSError):
                pass

        # Hooks directory (standalone scripts)
        hooks_dir = claude_dir / "hooks"
        if hooks_dir.is_dir():
            for hf in sorted(hooks_dir.iterdir()):
                if hf.is_file() and not hf.name.startswith("."):
                    project["hooks"].append(
                        {"type": "script", "matcher": "*", "command": hf.name}
                    )

        # Project-level skills
        skills_dir = claude_dir / "skills"
        if skills_dir.is_dir():
            for sf in sorted(skills_dir.iterdir()):
                if sf.is_dir() and not sf.name.startswith("."):
                    project["skills"].append(sf.name)

        # CLAUDE.md inside .claude/
        inner_md = claude_dir / "CLAUDE.md"
        if inner_md.exists() and not claude_md.exists():
            project["claude_md"] = str(inner_md)

    # .mcp.json
    if mcp_json.exists():
        project["mcp"] = str(mcp_json)
        try:
            mcp_data = json.loads(mcp_json.read_text())
            servers = mcp_data.get("mcpServers", {})
            for server_name, server_config in servers.items():
                env_vars = list((server_config.get("env", {}) or {}).keys())
                project["mcp_servers"].append({
                    "name": server_name,
                    "type": _detect_mcp_type(server_config),
                    "env_vars": env_vars,
                    "has_secrets": _has_secret_env_vars(server_config.get("env", {})),
                })
        except (json.JSONDecodeError, OSError):
            pass

    return project


def _extract_cwd_match(mode_file):
    """Extract cwd_match value from a mode markdown file."""
    try:
        text = mode_file.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("cwd_match:"):
                return stripped.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def _detect_mcp_type(config):
    """Detect MCP server type from config."""
    if "command" in config:
        cmd = config["command"]
        if "npx" in str(cmd):
            return "npx"
        return "stdio"
    if "url" in config:
        return "sse"
    return "unknown"


SECRET_PATTERNS = {"key", "secret", "token", "password", "credential", "private"}


def _has_secret_env_vars(env_dict):
    """Check if env dict likely contains secret values."""
    if not env_dict:
        return False
    for key in env_dict:
        lower = key.lower()
        if any(pat in lower for pat in SECRET_PATTERNS):
            return True
    return False


def file_hash(path):
    """Return SHA-256 hex digest of a file's contents, or None if unreadable."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def snapshot_project(project):
    """Create a hashable snapshot of a project's config state.

    Returns a dict of file paths to their content hashes.
    """
    snap = {}
    for key in ("claude_md", "settings", "mcp"):
        path = project.get(key)
        if path:
            snap[path] = file_hash(path)
    return snap
