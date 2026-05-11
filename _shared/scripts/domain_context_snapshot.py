#!/usr/bin/env python3
"""Print a compact domain-skill context snapshot from the active overlay."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    from resolve_context import resolve  # type: ignore[import-not-found]
finally:
    sys.path.pop(0)


PLAN_FILES = ("plan.md", "shared.md", "backend.md", "frontend.md", "flows.md", "schema.mmd")
CHECK_SECTIONS = ("plans", "backend", "frontend", "auth")


def _expand(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return None
    return os.path.realpath(os.path.expanduser(str(value)))


def _exists(value: Any) -> dict[str, Any] | None:
    path = _expand(value)
    if not path:
        return None
    return {"path": path, "exists": Path(path).exists()}


def _existing_paths(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in sorted(section.items()):
        if key.endswith(("_path", "_root", "_repo", "_index", "_reference")) or key in {
            "repo",
            "domain_path",
            "features_path",
            "types_path",
            "migration_path",
            "packages_root",
            "patterns_reference",
        }:
            checked = _exists(value)
            if checked is not None:
                out[key] = checked
    return out


def _slice_snapshot(plans: dict[str, Any], slice_name: str | None) -> dict[str, Any] | None:
    if not slice_name:
        return None
    root = _expand(plans.get("plan_root") or plans.get("plan_draft"))
    if not root:
        return {"slice": slice_name, "error": "no plan_root or plan_draft in active overlay"}

    plan_dir = Path(root) / slice_name
    files = {name: (plan_dir / name).exists() for name in PLAN_FILES}
    extras = {
        "review.mmdx": (plan_dir / "review.mmdx").exists(),
        "br_epic_pointer": (plan_dir / "EPIC_ID.txt").exists(),
        "optional_workgraph_view": (plan_dir / "WORKGRAPH.md").exists(),
        "REVIEW.md": (plan_dir / "REVIEW.md").exists(),
        "AUDIT_REPORT.md": (plan_dir / "AUDIT_REPORT.md").exists(),
        "COMPLETED.md": (plan_dir / "COMPLETED.md").exists(),
    }
    return {
        "slice": slice_name,
        "plan_dir": str(plan_dir),
        "plan_dir_exists": plan_dir.exists(),
        "required_plan_files": files,
        "workflow_artifacts": extras,
    }


def build_snapshot(cwd: str, slice_name: str | None) -> dict[str, Any]:
    cwd_real = os.path.realpath(os.path.expanduser(cwd))
    snapshot: dict[str, Any] = {"cwd": cwd_real, "sections": {}, "missing_sections": []}

    for section_name in CHECK_SECTIONS:
        section = resolve(cwd_real, section=section_name)
        if not section:
            snapshot["missing_sections"].append(section_name)
            continue
        snapshot["sections"][section_name] = {
            "values": section,
            "paths": _existing_paths(section),
        }

    plans = snapshot["sections"].get("plans", {}).get("values", {})
    if isinstance(plans, dict):
        snapshot["slice"] = _slice_snapshot(plans, slice_name)

    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print active domain-family overlay, path, and slice-plan context as JSON."
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory used for overlay matching")
    parser.add_argument("--slice", dest="slice_name", default=None, help="Optional slice name to inspect")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    snapshot = build_snapshot(args.cwd, args.slice_name)
    print(json.dumps(snapshot, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if snapshot["sections"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
