#!/usr/bin/env python3
"""Scan the local environment and produce a structured assessment.

Usage:
    scan_environment.py [--scan-root DIR]... [--json] [--quiet]

Outputs a JSON report with:
  - repos: git repos found, with detected stack and remote info
  - tools: which prerequisites are installed
  - claude: existing Claude config, skills, MCP servers
  - gaps: missing prerequisites for skillbox
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def detect_stack(repo_path: Path) -> list[str]:
    """Detect programming languages/frameworks in a repo."""
    markers = {
        "Cargo.toml": "rust",
        "pyproject.toml": "python",
        "setup.py": "python",
        "requirements.txt": "python",
        "package.json": "node",
        "tsconfig.json": "typescript",
        "go.mod": "go",
        "Gemfile": "ruby",
        "mix.exs": "elixir",
        "pom.xml": "java",
        "build.gradle": "java",
        "Dockerfile": "docker",
        "docker-compose.yml": "docker-compose",
        "docker-compose.yaml": "docker-compose",
    }
    found = []
    for marker, stack in markers.items():
        if (repo_path / marker).exists() and stack not in found:
            found.append(stack)
    return found


def detect_service_command(repo_path: Path, stacks: list[str]) -> dict | None:
    """Try to detect a dev server command from package.json or common patterns."""
    if "node" in stacks or "typescript" in stacks:
        pkg = repo_path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                scripts = data.get("scripts", {})
                for key in ("dev", "start", "serve"):
                    if key in scripts:
                        return {"command": f"npm run {key}", "source": f"package.json scripts.{key}"}
            except (json.JSONDecodeError, OSError):
                pass
    if "python" in stacks:
        for pattern in ["manage.py", "app.py", "main.py"]:
            if (repo_path / pattern).exists():
                return {"command": f"python3 {pattern}", "source": pattern}
    return None


def is_git_repo_root(path: Path) -> bool:
    """Return true for regular repos, submodules, and worktrees."""
    if not (path / ".git").exists():
        return False
    top_level = run(["git", "rev-parse", "--show-toplevel"], cwd=str(path))
    if not top_level:
        return False
    return Path(top_level).resolve() == path.resolve()


def scan_repos(roots: list[Path], max_depth: int = 3) -> list[dict]:
    """Find git repos under scan roots."""
    repos = []
    seen = set()

    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth > max_depth:
                dirnames.clear()
                continue
            # Skip hidden dirs and common non-project dirs
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in ("node_modules", "venv", ".venv", "target", "__pycache__", "vendor")
            ]
            p = Path(dirpath)
            if is_git_repo_root(p):
                real = p.resolve()
                if real in seen:
                    continue
                seen.add(real)
                remote = run(["git", "remote", "get-url", "origin"], cwd=str(p))
                branch = run(["git", "branch", "--show-current"], cwd=str(p))
                stacks = detect_stack(p)
                service = detect_service_command(p, stacks)
                repo = {
                    "path": str(p),
                    "name": p.name,
                    "remote": remote or None,
                    "branch": branch or "main",
                    "stacks": stacks,
                }
                if service:
                    repo["service"] = service
                repos.append(repo)
                dirnames.clear()  # Don't descend into git repos
    return repos


def scan_tools() -> dict:
    """Check which prerequisite tools are installed."""
    tools = {}
    checks = {
        "docker": ["docker", "--version"],
        "docker_compose": ["docker", "compose", "version"],
        "git": ["git", "--version"],
        "tailscale": ["tailscale", "version"],
        "claude": ["claude", "--version"],
        "python3": ["python3", "--version"],
        "node": ["node", "--version"],
        "make": ["make", "--version"],
    }
    for name, cmd in checks.items():
        result = run(cmd)
        tools[name] = {"installed": bool(result), "version": result or None}

    # Check DO token
    tools["do_token"] = {"installed": bool(os.environ.get("SKILLBOX_DO_TOKEN") or os.environ.get("DO_API_TOKEN")), "version": None}
    tools["ts_authkey"] = {"installed": bool(os.environ.get("SKILLBOX_TS_AUTHKEY") or os.environ.get("TS_AUTHKEY")), "version": None}

    return tools


def scan_claude_config() -> dict:
    """Scan existing Claude Code configuration."""
    claude_dir = Path.home() / ".claude"
    result = {"exists": claude_dir.is_dir(), "skills": [], "mcp_servers": [], "settings": {}}

    if not claude_dir.is_dir():
        return result

    # Skills
    skills_dir = claude_dir / "skills"
    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir() or entry.is_symlink():
                skill_md = entry / "SKILL.md" if entry.is_dir() else (entry.resolve() / "SKILL.md" if entry.is_symlink() else None)
                has_skill_md = skill_md.exists() if skill_md else False
                result["skills"].append({
                    "name": entry.name,
                    "path": str(entry),
                    "symlink": entry.is_symlink(),
                    "has_skill_md": has_skill_md,
                })

    # Settings
    settings_path = claude_dir / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
            result["settings"] = {
                "has_hooks": bool(data.get("hooks")),
                "has_mcp": bool(data.get("mcpServers")),
                "mcp_server_names": list(data.get("mcpServers", {}).keys()),
            }
            result["mcp_servers"] = result["settings"]["mcp_server_names"]
        except (json.JSONDecodeError, OSError):
            pass

    return result


def compute_gaps(tools: dict) -> list[dict]:
    """Identify missing prerequisites."""
    gaps = []
    required = {
        "docker": "Docker is required to run the skillbox container",
        "docker_compose": "Docker Compose v2 is required (docker compose)",
        "git": "Git is required for repo management",
    }
    recommended = {
        "tailscale": "Tailscale enables secure remote access to your box",
        "do_token": "SKILLBOX_DO_TOKEN env var needed for DO provisioning (set in ~/.zshrc)",
        "ts_authkey": "SKILLBOX_TS_AUTHKEY env var needed for Tailscale enrollment (set in ~/.zshrc)",
    }

    for name, reason in required.items():
        if not tools.get(name, {}).get("installed"):
            gaps.append({"tool": name, "severity": "required", "reason": reason})

    for name, reason in recommended.items():
        if not tools.get(name, {}).get("installed"):
            gaps.append({"tool": name, "severity": "recommended", "reason": reason})

    return gaps


def main():
    parser = argparse.ArgumentParser(description="Scan local environment for skillbox quickstart")
    parser.add_argument("--scan-root", action="append", dest="scan_roots", help="Directory roots to scan for repos (default: ~/repos, ~/projects)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    args = parser.parse_args()

    roots = [Path(r).expanduser() for r in (args.scan_roots or ["~/repos", "~/projects", "~/dev", "~/src"])]

    if not args.quiet:
        print("Scanning environment...", file=sys.stderr)

    tools = scan_tools()
    repos = scan_repos(roots)
    claude = scan_claude_config()
    gaps = compute_gaps(tools)

    report = {
        "scan_roots": [str(r) for r in roots],
        "repos": repos,
        "repo_count": len(repos),
        "tools": tools,
        "claude": claude,
        "gaps": gaps,
        "has_blocking_gaps": any(g["severity"] == "required" for g in gaps),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        # Human-readable summary
        print(f"\n{'='*60}")
        print(f"  SKILLBOX QUICKSTART — Environment Scan")
        print(f"{'='*60}\n")

        print(f"📦 Repos found: {len(repos)}")
        for r in repos:
            stacks = ", ".join(r["stacks"]) if r["stacks"] else "unknown"
            svc = f" [has dev server]" if r.get("service") else ""
            print(f"   {r['name']:30s} ({stacks}){svc}")
            if r.get("remote"):
                print(f"   {'':30s} └─ {r['remote']}")

        print(f"\n🔧 Tools:")
        for name, info in tools.items():
            status = "✓" if info["installed"] else "✗"
            ver = f" ({info['version'][:40]})" if info.get("version") else ""
            print(f"   {status} {name}{ver}")

        if claude["exists"]:
            print(f"\n🤖 Claude Config:")
            print(f"   Skills: {len(claude['skills'])}")
            for s in claude["skills"][:10]:
                sym = " (symlink)" if s["symlink"] else ""
                print(f"     - {s['name']}{sym}")
            if claude["mcp_servers"]:
                print(f"   MCP Servers: {', '.join(claude['mcp_servers'])}")

        if gaps:
            print(f"\n⚠️  Gaps:")
            for g in gaps:
                icon = "🚫" if g["severity"] == "required" else "⚡"
                print(f"   {icon} {g['tool']}: {g['reason']}")

        if report["has_blocking_gaps"]:
            print(f"\n❌ Blocking gaps found — fix required items before proceeding.")
        else:
            print(f"\n✅ Ready to generate client overlay.")

    return 0 if not report["has_blocking_gaps"] else 1


if __name__ == "__main__":
    sys.exit(main())
