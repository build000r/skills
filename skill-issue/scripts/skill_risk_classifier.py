#!/usr/bin/env python3
"""Classify a SKILL.md edit into a risk tier.

Tiers (from the dueling-wizards MVP, consensus score 850):

  low    prose, examples, reference prose; auto-validate via quick_validate.py
  medium description field, phase/step ordering, script logic changes;
         requires LLM self-review + one human confirm
  high   allowed-tools frontmatter, destructive shell commands,
         safety rules, hooks config; mandatory human flip, no auto-apply

Usage:
  skill_risk_classifier.py --old path/to/current/SKILL.md --new path/to/proposed/SKILL.md [--json]

Exit code mirrors the tier for shell chaining: 0=low, 1=medium, 2=high.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

DESTRUCTIVE = re.compile(
    r"\b(rm\s+-rf|rm\s+-f|docker\s+(rm|kill|prune)|sudo\b|kill\s+-9|pkill\b|git\s+push(?!-)|git\s+reset\s+--hard|drop\s+database|truncate\s+table|shutdown\b|reboot\b)",
    re.IGNORECASE,
)
SAFETY_MARKERS = re.compile(
    r"\b(safety|guardrail|destructive|irreversible|risk.?gate|permission|allowed.?tools?|dangerous)\b",
    re.IGNORECASE,
)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _headers(body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith("#")]


def classify(old_text: str, new_text: str, *, deps_drift: bool = False) -> tuple[str, list[str]]:
    """Return (tier, reasons)."""
    reasons: list[str] = []
    if deps_drift:
        reasons.append("cross-skill dependency interface drift (check_skill_deps)")
        return "high", reasons

    old_fm, old_body = _split_frontmatter(old_text)
    new_fm, new_body = _split_frontmatter(new_text)

    if old_fm.get("allowed-tools") != new_fm.get("allowed-tools"):
        reasons.append("allowed-tools frontmatter changed")
        return "high", reasons

    added = [
        line for line in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), n=0)
        if line.startswith("+") and not line.startswith("+++")
    ]
    if any(DESTRUCTIVE.search(line) for line in added):
        reasons.append("added destructive shell command")
        return "high", reasons
    if any(SAFETY_MARKERS.search(line) for line in added):
        reasons.append("added safety/risk/permission-related text")
        return "high", reasons

    if old_fm.get("description") != new_fm.get("description"):
        reasons.append("description field (trigger surface) changed")
        return "medium", reasons
    if _headers(old_body) != _headers(new_body):
        reasons.append("phase/step headers changed")
        return "medium", reasons
    if any(line.startswith("+") and ("```" not in line) and any(c in line for c in "={}()[]") for line in added):
        reasons.append("script/code logic changed")
        return "medium", reasons

    reasons.append("prose/examples only")
    return "low", reasons


def _deps_drift_for(skill_id: str, old: str, new: str, roots: list[str] | None = None) -> bool:
    """Invoke check_skill_deps; return True if any dependent would see interface drift."""
    script = Path(__file__).with_name("check_skill_deps.py")
    if not script.is_file():
        return False
    cmd = [sys.executable, str(script), "--changed-skill", skill_id, "--old", old, "--new", new, "--json"]
    if roots:
        cmd.extend(["--roots", *roots])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode < 0 or not result.stdout:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("dependents")) and bool(payload.get("interface_drift"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="current SKILL.md path")
    ap.add_argument("--new", required=True, help="proposed SKILL.md path")
    ap.add_argument("--deps-drift", action="store_true", help="force-set; normally computed via --skill-id")
    ap.add_argument("--skill-id", help="auto-run check_skill_deps.py for this skill id and bump tier if dependents drift")
    ap.add_argument("--roots", nargs="+", help="skill roots passed through to check_skill_deps.py")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    deps_drift = args.deps_drift
    if args.skill_id and not deps_drift:
        deps_drift = _deps_drift_for(args.skill_id, args.old, args.new, roots=args.roots)

    tier, reasons = classify(
        Path(args.old).read_text(),
        Path(args.new).read_text(),
        deps_drift=deps_drift,
    )
    if args.json:
        print(json.dumps({"tier": tier, "reasons": reasons}))
    else:
        print(f"{tier}\t{'; '.join(reasons)}")
    sys.exit({"low": 0, "medium": 1, "high": 2}[tier])


if __name__ == "__main__":
    main()
