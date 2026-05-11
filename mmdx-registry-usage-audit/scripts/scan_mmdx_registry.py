#!/usr/bin/env python3
"""Read-only scanner for MMDX index freshness, links, and placement."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


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

ARCHIVE_PARTS = {"archive", "archived", "_archive", "old", "generated"}
TEMPLATE_PARTS = {"assets", "templates", "examples"}
TRACKER_HINTS = ("goal", "gantt", "plan", "tracker", "roadmap", "release", "audit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of MMDX registry freshness and link health."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root to scan. Repeatable. Defaults to the current directory.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compatibility flag: scanner is always read-only unless --run-preflight is supplied.",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=45,
        help="Age threshold for active tracker freshness warnings.",
    )
    parser.add_argument(
        "--run-preflight",
        action="store_true",
        help="Run mmd.py --preflight-only for active .mmdx files.",
    )
    parser.add_argument(
        "--mmd-script",
        default="~/repos/opensource/skills/mmdx/scripts/mmd.py",
        help="Path to mmd.py for optional preflight.",
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


def add_issue(issues: list[dict[str, str]], severity: str, code: str, path: Path, message: str):
    issues.append(
        {
            "severity": severity,
            "code": code,
            "path": str(path),
            "message": message,
        }
    )


def is_archived(path: Path) -> bool:
    return any(part.lower() in ARCHIVE_PARTS for part in path.parts)


def is_template(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts.intersection(TEMPLATE_PARTS))


def is_tracker(path: Path) -> bool:
    text = str(path).lower()
    return any(hint in text for hint in TRACKER_HINTS)


def parse_mmdx(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    text = read_text(path)
    metadata: dict[str, Any] = {}
    match = re.search(r"<!--\s*mmdx\s*(\{.*?\})\s*-->", text, re.DOTALL)
    if match:
        try:
            metadata = json.loads(match.group(1))
        except json.JSONDecodeError:
            metadata = {"_parse_error": "invalid mmdx metadata json"}

    charts: dict[str, str] = {}
    chart_matches = list(
        re.finditer(r"^## chart\s+([A-Za-z0-9_-]+)\s+.*$", text, re.MULTILINE)
    )
    for index, chart_match in enumerate(chart_matches):
        chart_id = chart_match.group(1)
        start = chart_match.end()
        end = chart_matches[index + 1].start() if index + 1 < len(chart_matches) else len(text)
        charts[chart_id] = text[start:end]
    return metadata, charts


def markdown_links(text: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def local_diagram_link(value: str) -> bool:
    if value.startswith(("http://", "https://", "#", "mailto:")):
        return False
    clean = value.split("#", 1)[0]
    return clean.endswith((".mmd", ".mmdx"))


def run_preflight(mmd_script: Path, path: Path) -> tuple[bool, str]:
    if not mmd_script.exists():
        return False, f"mmd.py not found at {mmd_script}"
    result = subprocess.run(
        [sys.executable, str(mmd_script), str(path), "--preflight-only"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    return result.returncode == 0, result.stdout.strip().splitlines()[-1:] and result.stdout.strip().splitlines()[-1] or ""


def scan_root(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    files = list(iter_files(root))
    mmdx_files = [p for p in files if p.suffix == ".mmdx"]
    mmd_files = [p for p in files if p.suffix == ".mmd"]
    indexes = [p for p in mmdx_files if p.name == "INDEX.mmdx"]
    active_mmdx = [
        p
        for p in mmdx_files
        if p.name != "INDEX.mmdx" and not is_archived(p) and not is_template(p)
    ]
    checkable_mmdx = [p for p in mmdx_files if p.name != "INDEX.mmdx" and not is_archived(p)]
    issues: list[dict[str, str]] = []
    preflight: list[dict[str, str]] = []

    if active_mmdx and not indexes:
        add_issue(
            issues,
            "MEDIUM",
            "index-stale",
            root,
            "Active MMDX files exist, but no INDEX.mmdx was found under this root.",
        )

    newest_active = max((p.stat().st_mtime for p in active_mmdx), default=0)
    newest_active_path = max(active_mmdx, key=lambda p: p.stat().st_mtime, default=None)
    for index in indexes:
        if newest_active and index.stat().st_mtime < newest_active:
            add_issue(
                issues,
                "HIGH",
                "index-stale",
                index,
                f"Index is older than active MMDX file {newest_active_path}.",
            )

    now = time.time()
    stale_seconds = args.stale_days * 24 * 60 * 60
    for path in checkable_mmdx:
        metadata, charts = parse_mmdx(path)
        if metadata.get("_parse_error"):
            add_issue(issues, "HIGH", "preflight-invalid", path, "MMDX metadata JSON is invalid.")
        entry = metadata.get("entry")
        if metadata and entry and entry not in charts:
            add_issue(
                issues,
                "HIGH",
                "chart-link-drift",
                path,
                f"Entry chart `{entry}` is not declared in the file.",
            )
        for link in metadata.get("links", []) if isinstance(metadata.get("links"), list) else []:
            if not isinstance(link, dict):
                continue
            source = link.get("from")
            target = link.get("to")
            label = link.get("label")
            if source and source not in charts:
                add_issue(
                    issues,
                    "HIGH",
                    "chart-link-drift",
                    path,
                    f"Link source chart `{source}` is missing.",
                )
            if target and target not in charts:
                add_issue(
                    issues,
                    "HIGH",
                    "chart-link-drift",
                    path,
                    f"Link target chart `{target}` is missing.",
                )
            if source in charts and label and label not in charts[source]:
                add_issue(
                    issues,
                    "MEDIUM",
                    "chart-link-drift",
                    path,
                    f"Link label `{label}` is not visible in source chart `{source}`.",
                )

        text = read_text(path)
        for link in markdown_links(text):
            if not local_diagram_link(link):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.exists():
                add_issue(
                    issues,
                    "MEDIUM",
                    "file-link-drift",
                    path,
                    f"Local diagram link is missing: {link}",
                )

        if (
            is_tracker(path)
            and not is_template(path)
            and now - path.stat().st_mtime > stale_seconds
        ):
            add_issue(
                issues,
                "LOW",
                "stale-plan-evidence",
                path,
                f"Tracker-like MMDX is older than {args.stale_days} days; confirm if still active.",
            )

        if args.run_preflight:
            ok, detail = run_preflight(Path(args.mmd_script).expanduser(), path)
            preflight.append(
                {
                    "path": str(path),
                    "status": "ok" if ok else "failed",
                    "detail": detail,
                }
            )
            if not ok:
                add_issue(issues, "HIGH", "preflight-invalid", path, detail)

    inventory = {
        "root": str(root),
        "mmdx_files": len(mmdx_files),
        "mmd_files": len(mmd_files),
        "indexes": len(indexes),
        "active_mmdx_files": len(active_mmdx),
        "template_mmdx_files": len([p for p in checkable_mmdx if is_template(p)]),
        "newest_active_mmdx": str(newest_active_path) if newest_active_path else "",
    }
    commands = [
        f"python3 {args.mmd_script} {path} --preflight-only"
        for path in checkable_mmdx[:20]
    ]
    return {
        "inventory": inventory,
        "issues": issues,
        "preflight": preflight,
        "suggested_preflight_commands": commands,
    }


def text_report(results: list[dict[str, Any]]) -> str:
    lines = ["mmdx registry scan (read-only)"]
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
        if result["suggested_preflight_commands"]:
            lines.append("  suggested preflight:")
            for command in result["suggested_preflight_commands"][:5]:
                lines.append(f"  - {command}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    roots = [Path(p).expanduser() for p in (args.root or ["."])]
    results = [scan_root(root, args) for root in roots]
    if args.json:
        print(json.dumps({"dry_run": not args.run_preflight, "results": results}, indent=2, sort_keys=True))
    else:
        print(text_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
