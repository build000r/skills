#!/usr/bin/env python3
"""Generate a skillbox client overlay.yaml from a scan report.

Usage:
    scan_environment.py --json | generate_overlay.py --client-id myproject [--output DIR]

Reads scan JSON from stdin. Produces:
  - overlay.yaml (client config)
  - recommendation.json (blueprint choice + --set args + human decisions needed)
"""

import argparse
import json
import sys
import yaml
from pathlib import Path


def pick_blueprint(scan: dict) -> dict:
    """Select the best blueprint and compute --set args from scan results."""
    repos = scan.get("repos", [])
    if not repos:
        return {
            "blueprint": "skill-builder-fwc",
            "set_args": {},
            "reason": "No repos found — defaulting to skill-builder for a clean workspace",
        }

    # Find the "primary" repo — prefer one with a dev server, else the first
    primary = None
    for r in repos:
        if r.get("service"):
            primary = r
            break
    if not primary:
        primary = repos[0]

    has_service = bool(primary.get("service"))
    has_docker = "docker" in primary.get("stacks", []) or "docker-compose" in primary.get("stacks", [])

    if has_service:
        svc = primary["service"]
        return {
            "blueprint": "git-repo-http-service",
            "set_args": {
                "PRIMARY_REPO_URL": primary["remote"] or f"file://{primary['path']}",
                "PRIMARY_REPO_BRANCH": primary.get("branch", "main"),
                "PRIMARY_REPO_ID": primary["name"],
                "SERVICE_COMMAND": svc["command"],
            },
            "reason": f"Repo '{primary['name']}' has a dev server ({svc['command']})",
            "primary_repo": primary,
        }
    elif primary.get("remote"):
        return {
            "blueprint": "git-repo",
            "set_args": {
                "PRIMARY_REPO_URL": primary["remote"],
                "PRIMARY_REPO_BRANCH": primary.get("branch", "main"),
                "PRIMARY_REPO_ID": primary["name"],
            },
            "reason": f"Repo '{primary['name']}' is a standard git repo",
            "primary_repo": primary,
        }
    else:
        return {
            "blueprint": "skill-builder-fwc",
            "set_args": {},
            "reason": f"Repo '{primary['name']}' has no remote — using skill-builder as base",
        }


def build_overlay(client_id: str, scan: dict, blueprint_rec: dict) -> dict:
    """Build a draft overlay.yaml from scan results.

    This is a starting point — the agent refines it with the user.
    """
    repos = scan.get("repos", [])
    primary = blueprint_rec.get("primary_repo")

    overlay = {
        "version": 1,
        "client": {
            "id": client_id,
            "label": client_id.replace("-", " ").replace("_", " ").title(),
            "default_cwd": "${SKILLBOX_MONOSERVER_ROOT}",
            "repos": [],
            "logs": [
                {
                    "id": client_id,
                    "path": f"${{SKILLBOX_LOG_ROOT}}/clients/{client_id}",
                    "required": False,
                    "profiles": ["core"],
                    "retention_days": 14,
                    "notes": f"Client-scoped logs for {client_id}.",
                }
            ],
            "context": {
                "cwd_match": ["${SKILLBOX_MONOSERVER_ROOT}"],
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

    # Add repos from scan
    for i, repo in enumerate(repos):
        if not repo.get("remote"):
            continue  # Skip local-only repos without remotes
        repo_id = repo["name"]
        repo_entry = {
            "id": repo_id,
            "kind": "repo",
            "path": f"${{CLIENT_ROOT}}/{repo_id}",
            "required": i == 0,  # First repo is required
            "profiles": ["core"],
            "source": {
                "kind": "git",
                "url": repo["remote"],
                "branch": repo.get("branch", "main"),
            },
            "sync": {"mode": "clone-if-missing"},
            "notes": f"{', '.join(repo['stacks']) if repo['stacks'] else 'unknown stack'}",
        }
        overlay["client"]["repos"].append(repo_entry)

    # Add services for repos with dev servers
    services = []
    for repo in repos:
        svc = repo.get("service")
        if svc and repo.get("remote"):
            services.append({
                "id": f"{repo['name']}-dev",
                "kind": "http",
                "command": svc["command"],
                "cwd": f"${{CLIENT_ROOT}}/{repo['name']}",
                "profiles": ["core"],
            })
    if services:
        overlay["client"]["services"] = services

    return overlay


def compute_decisions(scan: dict, blueprint_rec: dict) -> list[dict]:
    """Identify decisions the user needs to make."""
    decisions = []
    repos = scan.get("repos", [])

    if len(repos) > 1:
        repo_names = [r["name"] for r in repos]
        decisions.append({
            "question": "Which repos should be included in this client?",
            "options": repo_names,
            "default": repo_names,
            "type": "multi-select",
        })

    if len(repos) > 1:
        decisions.append({
            "question": "Which repo is the primary (default working directory)?",
            "options": [r["name"] for r in repos],
            "default": blueprint_rec.get("primary_repo", {}).get("name", repos[0]["name"]) if repos else None,
            "type": "single-select",
        })

    gaps = scan.get("gaps", [])
    recommended_gaps = [g for g in gaps if g["severity"] == "recommended"]
    if any(g["tool"] == "do_token" for g in recommended_gaps):
        decisions.append({
            "question": "Do you want to provision a DigitalOcean droplet, or run locally?",
            "options": ["remote (DO droplet)", "local (docker on this machine)"],
            "default": "local (docker on this machine)",
            "type": "single-select",
        })

    return decisions


def main():
    parser = argparse.ArgumentParser(description="Generate skillbox client overlay from scan")
    parser.add_argument("--client-id", required=True, help="Client identifier (snake_case)")
    parser.add_argument("--output", default=None, help="Output directory (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Output full recommendation as JSON")
    args = parser.parse_args()

    scan = json.load(sys.stdin)
    blueprint_rec = pick_blueprint(scan)
    overlay = build_overlay(args.client_id, scan, blueprint_rec)
    decisions = compute_decisions(scan, blueprint_rec)

    result = {
        "client_id": args.client_id,
        "blueprint": blueprint_rec,
        "overlay": overlay,
        "decisions": decisions,
        "first_box_command": build_first_box_cmd(args.client_id, blueprint_rec),
    }

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "overlay.yaml").write_text(yaml.dump(overlay, default_flow_style=False, sort_keys=False))
        (out / "recommendation.json").write_text(json.dumps(result, indent=2))
        print(f"Written to {out}/", file=sys.stderr)
    elif args.json:
        print(json.dumps(result, indent=2))
    else:
        print("# Generated overlay.yaml")
        print(yaml.dump(overlay, default_flow_style=False, sort_keys=False))
        print("---")
        print(f"# Blueprint: {blueprint_rec['blueprint']}")
        print(f"# Reason: {blueprint_rec['reason']}")
        if decisions:
            print(f"# Decisions needed: {len(decisions)}")
            for d in decisions:
                print(f"#   - {d['question']}")


def build_first_box_cmd(client_id: str, blueprint_rec: dict) -> str:
    """Build the manage.py first-box command."""
    parts = [f"python3 .env-manager/manage.py first-box {client_id}"]
    bp = blueprint_rec.get("blueprint")
    if bp:
        parts.append(f"--blueprint {bp}")
    for k, v in blueprint_rec.get("set_args", {}).items():
        parts.append(f"--set {k}={v}")
    parts.append("--format json")
    return " \\\n  ".join(parts)


if __name__ == "__main__":
    main()
