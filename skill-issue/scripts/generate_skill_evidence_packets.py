#!/usr/bin/env python3
"""
Generate operator-evidence packets from transcript-derived skill review data.

Usage:
  generate_skill_evidence_packets.py --skill skill-issue [--source both] [--since month]
  generate_skill_evidence_packets.py --input /tmp/skill-review.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.skill_evidence import generate_evidence_report, render_evidence_markdown
from lib.skill_review import parse_date, scan_skill_invocations


def load_report(path: str) -> dict:
    """Load a review report from stdin or a file path."""
    if path == "-":
        return json.load(sys.stdin)
    with open(Path(path), "r") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate operator evidence packets from skill reviews")
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
    parser.add_argument("--min-occurrences", type=int, default=2, help="Minimum repeated runs to create a packet")
    parser.add_argument("--max-packets", type=int, default=5, help="Maximum packets to return")
    parser.add_argument("--max-examples", type=int, default=3, help="Representative traces per packet")
    parser.add_argument("--max-controls", type=int, default=2, help="Holdout traces per packet")
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

    evidence_report = generate_evidence_report(
        review_report,
        min_occurrences=args.min_occurrences,
        max_packets=args.max_packets,
        max_examples=args.max_examples,
        max_controls=args.max_controls,
    )

    if args.json:
        print(json.dumps(evidence_report, indent=2))
    else:
        print(render_evidence_markdown(evidence_report), end="")


if __name__ == "__main__":
    main()
