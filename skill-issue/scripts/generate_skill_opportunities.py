#!/usr/bin/env python3
"""
Generate ranked skill-improvement opportunities from post-invocation review data.

Usage:
  generate_skill_opportunities.py --skill skill-issue [--source both] [--since month]
  generate_skill_opportunities.py --input /tmp/skill-review.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.skill_opportunities import generate_opportunity_report, render_opportunity_markdown
from lib.skill_review import parse_date, scan_skill_invocations


def load_report(path: str) -> dict:
    """Load a review report from stdin or a file path."""
    if path == "-":
        return json.load(sys.stdin)
    with open(Path(path), "r") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ranked opportunities from skill reviews")
    parser.add_argument("--skill", help="Skill name to scan when --input is not provided")
    parser.add_argument("--input", help="Existing review JSON path, or - for stdin")
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
    parser.add_argument("--limit", type=int, default=50, help="Max invocations to analyze")
    parser.add_argument("--min-runs", type=int, default=3, help="Minimum runs for slice-specific cards")
    parser.add_argument("--max-cards", type=int, default=10, help="Maximum cards to return")
    parser.add_argument("--max-evidence", type=int, default=3, help="Evidence examples per card")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args()

    if args.input:
        review_report = load_report(args.input)
    else:
        if not args.skill:
            parser.error("--skill is required unless --input is provided")
        since = parse_date(args.since)
        until = parse_date(args.until) if args.until else None
        review_report = scan_skill_invocations(
            skill=args.skill,
            source=args.source,
            since=since,
            until=until,
            limit=args.limit,
        )

    opportunity_report = generate_opportunity_report(
        review_report,
        min_runs=args.min_runs,
        max_cards=args.max_cards,
        max_evidence=args.max_evidence,
    )

    if args.json:
        print(json.dumps(opportunity_report, indent=2))
    else:
        print(render_opportunity_markdown(opportunity_report), end="")


if __name__ == "__main__":
    main()
