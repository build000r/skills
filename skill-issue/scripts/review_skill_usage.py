#!/usr/bin/env python3
"""
Review how a skill has actually been used in Claude/Codex transcripts.

Usage:
  review_skill_usage.py --skill skill-issue [--source both] [--since month] [--limit 50]

Outputs JSON with:
  - matched invocations from Claude/Codex session logs
  - last-invoked marker data
  - heuristic reliability signals and improvement opportunities
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from lib.skill_review import parse_date, scan_skill_invocations, write_marker


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
        default="month",
        help="Start date (YYYY-MM-DD or today/yesterday/week/month)",
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

    since = parse_date(args.since)
    until = parse_date(args.until) if args.until else datetime.now(timezone.utc)

    report = scan_skill_invocations(
        skill=args.skill,
        source=args.source,
        since=since,
        until=until,
        limit=args.limit,
    )

    if args.no_marker:
        report["marker_file"] = None
    else:
        report["marker_file"] = str(write_marker(report))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
