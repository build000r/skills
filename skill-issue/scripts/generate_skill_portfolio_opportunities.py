#!/usr/bin/env python3
"""
Generate portfolio-level skill opportunities from Claude/Codex transcript data.

Usage:
  generate_skill_portfolio_opportunities.py [--skills-root /path/to/skills] [--source both] [--since month]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from lib.skill_portfolio import (
    generate_portfolio_opportunity_report,
    render_portfolio_opportunity_markdown,
    scan_skill_portfolio,
)
from lib.skill_review import parse_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate portfolio-level skill opportunities")
    parser.add_argument(
        "--skills-root",
        default=None,
        help="Root directory containing top-level skill folders; defaults to the installed/repo skills root",
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
    parser.add_argument("--limit", type=int, default=200, help="Max sessions to analyze")
    parser.add_argument("--min-cluster-runs", type=int, default=2, help="Minimum repeated runs for creation cards")
    parser.add_argument("--max-cards", type=int, default=12, help="Maximum cards to return")
    parser.add_argument("--max-evidence", type=int, default=3, help="Evidence examples per card")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args()

    since = parse_date(args.since)
    until = parse_date(args.until) if args.until else datetime.now(timezone.utc)
    portfolio_report = scan_skill_portfolio(
        source=args.source,
        since=since,
        until=until,
        limit=args.limit,
        skills_root=args.skills_root,
    )
    opportunity_report = generate_portfolio_opportunity_report(
        portfolio_report,
        min_cluster_runs=args.min_cluster_runs,
        max_cards=args.max_cards,
        max_evidence=args.max_evidence,
    )

    if args.json:
        print(json.dumps(opportunity_report, indent=2))
    else:
        print(render_portfolio_opportunity_markdown(opportunity_report), end="")


if __name__ == "__main__":
    main()
