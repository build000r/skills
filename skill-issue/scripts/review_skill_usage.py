#!/usr/bin/env python3
"""
Review how a skill has actually been used in Claude/Codex transcripts.

Usage:
  review_skill_usage.py --skill skill-issue [--source both] [--limit 50]
  review_skill_usage.py --skill skill-issue [--source both] [--since marker|month|2026-03-01] [--limit 50]

Outputs JSON with:
  - matched invocations from Claude/Codex session logs
  - last-invoked marker data
  - heuristic reliability signals and improvement opportunities
  - operator evidence packets for concrete patch planning
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from lib.skill_evidence import generate_evidence_report
from lib.skill_review import load_marker, parse_date, parse_timestamp, scan_skill_invocations, write_marker


def resolve_since(skill: str, since_arg: str | None) -> tuple[datetime, str]:
    """Resolve the review start timestamp from an explicit arg or the last marker."""
    month_fallback = parse_date("month")
    marker = load_marker(skill)

    if since_arg and since_arg != "marker":
        return parse_date(since_arg), "explicit"

    if marker:
        marker_timestamp = marker.get("reviewed_until") or marker.get("updated_at")
        if marker_timestamp:
            return parse_timestamp(marker_timestamp, month_fallback), "marker"

    if since_arg == "marker":
        return month_fallback, "marker-fallback-month"

    return month_fallback, "default-month"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review skill usage from Claude/Codex logs")
    parser.add_argument("--skill", required=True, help="Skill name to review")
    parser.add_argument(
        "--source",
        choices=("claude", "codex", "both", "all"),
        default="both",
        help="Which transcript source(s) to scan",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Start date (marker|YYYY-MM-DD|today|yesterday|week|month). Defaults to the last review marker for this skill, or month on first run.",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="End date (YYYY-MM-DD), defaults to now",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max invocations to return")
    parser.add_argument(
        "--no-marker",
        action="store_true",
        help="Do not update ~/.claude/skill-markers/<skill>.json",
    )
    args = parser.parse_args()

    since, since_source = resolve_since(args.skill, args.since)
    until = parse_date(args.until) if args.until else datetime.now(timezone.utc)

    report = scan_skill_invocations(
        skill=args.skill,
        source=args.source,
        since=since,
        until=until,
        limit=args.limit,
    )
    report["since_source"] = since_source
    report["evidence_packets"] = generate_evidence_report(report)

    if args.no_marker:
        report["marker_file"] = None
    else:
        report["marker_file"] = str(write_marker(report))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
