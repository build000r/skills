#!/usr/bin/env python3
"""
Count raw Claude/Codex tool invocations over a date range.

Usage:
  count_tool_invocations.py [--source both] [--since month]
  count_tool_invocations.py --skill skill-issue [--source both] [--since month]
"""

from __future__ import annotations

import argparse
import json

from lib.skill_review import parse_date, scan_tool_invocations


def main() -> None:
    parser = argparse.ArgumentParser(description="Count transcript tool invocations")
    parser.add_argument(
        "--skill",
        help="Optional skill filter; only matched skill invocations are counted",
    )
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on matching sessions to count; defaults to no cap",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Optional cap on emitted tool rows; summary totals still use all matches",
    )
    args = parser.parse_args()

    since = parse_date(args.since)
    until = parse_date(args.until) if args.until else None

    report = scan_tool_invocations(
        source=args.source,
        since=since,
        until=until,
        limit=args.limit,
        skill=args.skill,
    )

    if args.top is not None:
        report["tool_counts"] = report["tool_counts"][: args.top]

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
