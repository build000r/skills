#!/usr/bin/env python3
"""
Display trend data from saved skill reviews.

Usage:
  show_skill_trend.py --skill skill-issue [--weeks 8]
"""

from __future__ import annotations

import argparse
import csv
from io import StringIO

from lib.skill_review import aggregate_history_by_week, load_history

SPARK_CHARS = "▁▂▃▄▅▆▇█"
METRIC_ORDER = (
    "ack_rate",
    "validation_rate",
    "checkpoint_rate",
    "risk_gating_rate",
    "correction_rate",
    "completion_rate",
)


def spark(values: list[float]) -> str:
    """Render a tiny sparkline for 0-1 values."""
    if not values:
        return ""
    chars = []
    for value in values:
        idx = int(max(0.0, min(value, 1.0)) * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars)


def delta_str(current: float, previous: float | None) -> str:
    """Format a delta between two metrics."""
    if previous is None:
        return "  --"
    diff = current - previous
    if abs(diff) < 0.005:
        return "  --"
    return f"{diff:+.2f}"


def render_markdown(skill: str, aggregated: dict[str, dict], weeks: int) -> str:
    """Render history as a markdown summary."""
    week_keys = list(aggregated.keys())[-weeks:]
    if not week_keys:
        return f"No review history found for {skill}.\n"

    lines = [f"## Skill Reliability Trend ({skill})", ""]
    ack_values = [aggregated[w]["metrics"]["ack_rate"] for w in week_keys]
    lines.append(f"**Ack Rate:** {ack_values[-1]:.2f} {spark(ack_values)}")
    lines.append("")
    lines.append("| Week | Reviews | Invocations | Ack | Validate | Checkpoints | Risk Gates | Corrections | Complete |")
    lines.append("|------|---------|-------------|-----|----------|-------------|------------|-------------|----------|")

    for week in week_keys:
        data = aggregated[week]
        metrics = data["metrics"]
        lines.append(
            f"| {week} | {data['reviews']} | {data['invocations']} | "
            f"{metrics['ack_rate']:.2f} | {metrics['validation_rate']:.2f} | "
            f"{metrics['checkpoint_rate']:.2f} | {metrics['risk_gating_rate']:.2f} | "
            f"{metrics['correction_rate']:.2f} | "
            f"{metrics['completion_rate']:.2f} |"
        )

    lines.append("")
    lines.append("### Metric Sparklines")
    lines.append("")
    lines.append("| Metric | Current | Trend |")
    lines.append("|--------|---------|-------|")
    for metric in METRIC_ORDER:
        values = [aggregated[w]["metrics"][metric] for w in week_keys]
        lines.append(f"| {metric} | {values[-1]:.2f} | {spark(values)} |")

    return "\n".join(lines) + "\n"


def render_csv(aggregated: dict[str, dict], weeks: int) -> str:
    """Render trend output as CSV."""
    week_keys = list(aggregated.keys())[-weeks:]
    if not week_keys:
        return ""

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["week", "reviews", "invocations", *METRIC_ORDER])
    for week in week_keys:
        data = aggregated[week]
        writer.writerow(
            [
                week,
                data["reviews"],
                data["invocations"],
                *[f"{data['metrics'][metric]:.3f}" for metric in METRIC_ORDER],
            ]
        )
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Show skill review trends")
    parser.add_argument("--skill", required=True, help="Skill name to chart")
    parser.add_argument("--weeks", type=int, default=8, help="Number of weeks to show")
    parser.add_argument("--csv", action="store_true", help="Output CSV instead of markdown")
    args = parser.parse_args()

    records = load_history(args.skill)
    aggregated = aggregate_history_by_week(records)

    if args.csv:
        print(render_csv(aggregated, args.weeks), end="")
    else:
        print(render_markdown(args.skill, aggregated, args.weeks), end="")


if __name__ == "__main__":
    main()
