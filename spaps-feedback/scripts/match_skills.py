#!/usr/bin/env python3
"""Match SPAPS issue reports to sibling skills via overlay registry.

Reads issues from stdin (JSON array, as emitted by fetch_issues.py --json)
and the `spaps_feedback.skill_registry` from the resolved client overlay.
Prints ranked candidates per issue.

Usage:
  fetch_issues.py --json | match_skills.py [--top 3] [--json] [--cwd PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def die(msg: str, code: int = 2) -> None:
    print(f"spaps-feedback match_skills: {msg}", file=sys.stderr)
    sys.exit(code)


def load_overlay(cwd: Path, client: str | None = None) -> dict[str, Any]:
    manage = Path.home() / ".claude/skills/skill-issue/scripts/manage_overlays.py"
    if not manage.exists():
        die(f"skill-issue manage_overlays.py not found at {manage}")
    try:
        out = subprocess.check_output(
            ["python3", str(manage), "match", "--cwd", str(cwd), "--json"],
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        die(f"no overlay matches {cwd}: {e.stderr.strip()}")
    payload = json.loads(out)
    matches = payload.get("matches") or []
    if client:
        picked = next((m for m in matches if m.get("client_id") == client), None)
        if not picked:
            ids = ", ".join(m.get("client_id") or "?" for m in matches) or "<none>"
            die(f"--client {client} did not match. Available: {ids}")
        overlay_path = picked.get("path")
    elif not matches:
        overlay_path = payload.get("overlay_path") or payload.get("path")
    elif len(matches) == 1:
        overlay_path = matches[0].get("path")
    else:
        ranked = sorted(
            matches,
            key=lambda m: (-len(m.get("matched_pattern") or ""), m.get("client_id") or ""),
        )
        top_len = len(ranked[0].get("matched_pattern") or "")
        tied = [m for m in ranked if len(m.get("matched_pattern") or "") == top_len]
        if len(tied) > 1:
            ids = ", ".join(m.get("client_id") or "?" for m in tied)
            die(f"multiple client overlays match {cwd}: {ids}. Pass --client <id>.")
        overlay_path = ranked[0].get("path")
    if not overlay_path:
        die(f"overlay match returned no path: {payload}")
    try:
        import yaml  # type: ignore
    except ImportError:
        die("PyYAML required: pip install pyyaml")
    with open(os.path.expanduser(overlay_path)) as fh:
        return yaml.safe_load(fh) or {}


def get_registry(overlay: dict[str, Any]) -> list[dict[str, Any]]:
    ctx = (overlay.get("client") or {}).get("context") or {}
    sf = ctx.get("spaps_feedback") or {}
    reg = sf.get("skill_registry") or []
    if not isinstance(reg, list):
        die("spaps_feedback.skill_registry must be a list")
    return reg


def haystack(issue: dict[str, Any], fields: list[str]) -> str:
    parts: list[str] = []
    for f in fields:
        v = issue.get(f)
        if isinstance(v, dict):
            parts.append(json.dumps(v))
        elif v is not None:
            parts.append(str(v))
    return " \n ".join(parts).lower()


def score_entry(issue: dict[str, Any], entry: dict[str, Any]) -> tuple[int, list[str]]:
    apps = entry.get("applications") or []
    if apps and issue.get("application_id") not in apps:
        return 0, []
    pages = entry.get("pages") or []
    if pages:
        url = (issue.get("page_url") or "").lower()
        if not any(url.startswith(p.lower()) for p in pages):
            return 0, []
    fields = entry.get("match_fields") or ["note", "component_label", "page_url"]
    hay = haystack(issue, fields)
    hits: list[str] = []
    for tag in entry.get("tags") or []:
        pattern = r"\b" + re.escape(str(tag).lower()) + r"\b"
        if re.search(pattern, hay):
            hits.append(str(tag))
    return len(hits), hits


def rank(issue: dict[str, Any], registry: list[dict[str, Any]], top: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for idx, entry in enumerate(registry):
        score, hits = score_entry(issue, entry)
        if score > 0:
            scored.append((score, -idx, entry, hits))  # idx negated for stable tie-break
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for score, _, entry, hits in scored[:top]:
        out.append(
            {
                "skill_id": entry.get("id"),
                "path": entry.get("path"),
                "score": score,
                "matched_tags": hits,
            }
        )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Match SPAPS issues to sibling skills.")
    p.add_argument("--cwd", default=os.getcwd())
    p.add_argument("--client", help="force a specific client overlay id")
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--json", action="store_true")
    if len(sys.argv) == 1 and sys.stdin.isatty():
        p.print_help(sys.stderr)
        print("\nPipe fetch_issues.py --json into this script.", file=sys.stderr)
        return 2
    args = p.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        die("no input on stdin")
    try:
        issues = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"stdin is not valid JSON: {e}")
    if isinstance(issues, dict):
        issues = [issues]

    overlay = load_overlay(Path(args.cwd), client=args.client)
    registry = get_registry(overlay)
    if not registry:
        die("spaps_feedback.skill_registry is empty in overlay")

    results = []
    for issue in issues:
        results.append(
            {
                "issue_id": issue.get("id"),
                "component_label": issue.get("component_label"),
                "page_url": issue.get("page_url"),
                "candidates": rank(issue, registry, args.top),
            }
        )

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in results:
            print(f"\nissue {r['issue_id'][:8] if r['issue_id'] else '?'}  {r['component_label']}")
            if not r["candidates"]:
                print("  (no skill candidates matched)")
            for c in r["candidates"]:
                tags = ",".join(c["matched_tags"])
                print(f"  [{c['score']}] {c['skill_id']}  matched: {tags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
