#!/usr/bin/env python3
"""
Display prompt review score trends from history.

Usage:
  show_trend.py [--weeks N] [--csv] [--project PATH] [--provider NAME]

Options:
  --weeks N         Number of weeks to show (default: 8)
  --csv             Output CSV instead of markdown
  --project PATH    Filter to reviews of a specific project
  --provider NAME   Filter to a specific provider (claude, codex, amp, opencode)

Reads from ~/.claude/prompt-review-history.jsonl
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

HISTORY_FILE = Path.home() / ".claude" / "prompt-review-history.jsonl"

AXES = [
    ("clarity", 3), ("context", 3), ("autonomy", 2), ("constraints", 2),
    ("checkpoints", 2), ("followup", 3), ("collaboration", 3),
    ("adaptability", 2), ("outcome", 3),
]

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def spark(values: list[float], max_val: float = 1.0) -> str:
    """Generate sparkline string from values."""
    if not values:
        return ""
    result = []
    for v in values:
        ratio = min(v / max_val, 1.0) if max_val > 0 else 0
        idx = int(ratio * (len(SPARK_CHARS) - 1))
        result.append(SPARK_CHARS[idx])
    return "".join(result)


def delta_str(current: float, previous: float) -> str:
    """Format delta with arrow."""
    diff = current - previous
    if abs(diff) < 0.005:
        return "  --"
    arrow = "+" if diff > 0 else ""
    return f"{arrow}{diff:.2f}"


def load_records(
    project_filter: str | None = None,
    provider_filter: str | None = None,
) -> list[dict]:
    """Load all records from history file."""
    if not HISTORY_FILE.exists():
        return []
    records = []
    with open(HISTORY_FILE, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if project_filter and rec.get("project") != project_filter:
                    continue
                if provider_filter and rec.get("provider") != provider_filter:
                    continue
                records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


def aggregate_by_week(records: list[dict]) -> dict[str, dict]:
    """Group records by ISO week and average scores."""
    weeks = defaultdict(list)
    for rec in records:
        week = rec.get("week", "unknown")
        weeks[week].append(rec)

    aggregated = {}
    for week, recs in sorted(weeks.items()):
        n = len(recs)
        avg_composite = sum(r["composite"] for r in recs) / n
        avg_axes = {}
        for axis, _ in AXES:
            vals = [r["axes"].get(axis, 0) for r in recs]
            avg_axes[axis] = sum(vals) / len(vals)
        total_sessions = sum(r.get("sessions", 0) for r in recs)
        total_prompts = sum(r.get("prompts", 0) for r in recs)
        aggregated[week] = {
            "composite": round(avg_composite, 3),
            "axes": {k: round(v, 1) for k, v in avg_axes.items()},
            "sessions": total_sessions,
            "prompts": total_prompts,
            "reviews": n,
        }
    return aggregated


def render_markdown(aggregated: dict[str, dict], num_weeks: int) -> str:
    """Render trend as markdown table with sparklines."""
    weeks = list(aggregated.keys())[-num_weeks:]

    if not weeks:
        return "No review history found. Run a prompt review first to start tracking.\n"

    lines = []

    # Header summary
    if len(weeks) >= 2:
        first = aggregated[weeks[0]]
        last = aggregated[weeks[-1]]
        d = delta_str(last["composite"], first["composite"])
        lines.append(f"## Prompt Score Trend ({weeks[0]} to {weeks[-1]})")
        lines.append("")
        composites = [aggregated[w]["composite"] for w in weeks]
        lines.append(f"**Composite:** {last['composite']:.2f} ({d}) {spark(composites)}")
        lines.append("")
    else:
        w = weeks[0]
        lines.append(f"## Prompt Score Trend ({w})")
        lines.append("")
        lines.append(f"**Composite:** {aggregated[w]['composite']:.2f} (first review)")
        lines.append("")

    # Main table
    lines.append("| Week | Composite | Sessions | Prompts | Trend |")
    lines.append("|------|-----------|----------|---------|-------|")

    composites_so_far = []
    prev_composite = None
    for w in weeks:
        data = aggregated[w]
        composites_so_far.append(data["composite"])
        d = delta_str(data["composite"], prev_composite) if prev_composite is not None else "  --"
        lines.append(
            f"| {w} | {data['composite']:.2f} | {data['sessions']} | "
            f"{data['prompts']} | {d} |"
        )
        prev_composite = data["composite"]

    lines.append("")

    # Per-axis breakdown
    lines.append("### Per-Axis Trends")
    lines.append("")
    lines.append("| Axis | Max | Current | Trend | Spark |")
    lines.append("|------|-----|---------|-------|-------|")

    last_week = weeks[-1]
    for axis, max_score in AXES:
        axis_vals = [aggregated[w]["axes"].get(axis, 0) for w in weeks]
        current = axis_vals[-1]
        d = delta_str(current, axis_vals[0]) if len(axis_vals) >= 2 else "  --"
        sp = spark(axis_vals, max_val=max_score)
        lines.append(f"| {axis.capitalize()} | {max_score} | {current:.1f} | {d} | {sp} |")

    lines.append("")

    # Biggest movers
    if len(weeks) >= 2:
        first_data = aggregated[weeks[0]]
        last_data = aggregated[weeks[-1]]
        deltas = []
        for axis, max_score in AXES:
            diff = last_data["axes"].get(axis, 0) - first_data["axes"].get(axis, 0)
            deltas.append((axis, diff, max_score))
        deltas.sort(key=lambda x: x[1], reverse=True)

        improved = [(a, d, m) for a, d, m in deltas if d > 0.05]
        declined = [(a, d, m) for a, d, m in deltas if d < -0.05]

        if improved or declined:
            lines.append("### Movers")
            lines.append("")
            if improved:
                top = improved[0]
                lines.append(f"- **Most improved:** {top[0].capitalize()} (+{top[1]:.1f}/{top[2]})")
            if declined:
                bot = declined[-1]
                lines.append(f"- **Needs attention:** {bot[0].capitalize()} ({bot[1]:.1f}/{bot[2]})")
            lines.append("")

    return "\n".join(lines)


def render_provider_breakdown(records: list[dict]) -> str:
    """Render composite score comparison across providers."""
    providers = defaultdict(list)
    for rec in records:
        p = rec.get("provider") or rec.get("source", "unknown")
        providers[p].append(rec["composite"])

    if len(providers) < 2:
        return ""

    lines = [
        "### By Provider",
        "",
        "| Provider | Reviews | Avg Score | Spark |",
        "|----------|---------|-----------|-------|",
    ]

    for provider in sorted(providers.keys()):
        scores = providers[provider]
        avg = sum(scores) / len(scores)
        sp = spark(scores)
        lines.append(f"| {provider} | {len(scores)} | {avg:.2f} | {sp} |")

    lines.append("")
    return "\n".join(lines)


def render_csv(aggregated: dict[str, dict], num_weeks: int) -> str:
    """Render trend as CSV."""
    weeks = list(aggregated.keys())[-num_weeks:]
    if not weeks:
        return ""

    output = StringIO()
    writer = csv.writer(output)

    headers = ["week", "composite", "sessions", "prompts", "reviews"]
    headers += [axis for axis, _ in AXES]
    writer.writerow(headers)

    for w in weeks:
        data = aggregated[w]
        row = [w, f"{data['composite']:.3f}", data["sessions"], data["prompts"], data["reviews"]]
        row += [f"{data['axes'].get(axis, 0):.1f}" for axis, _ in AXES]
        writer.writerow(row)

    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Show prompt review score trends")
    parser.add_argument("--weeks", type=int, default=8, help="Number of weeks to display")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("--project", default=None, help="Filter to project")
    parser.add_argument("--provider", default=None, help="Filter to provider")
    args = parser.parse_args()

    records = load_records(
        project_filter=args.project,
        provider_filter=args.provider,
    )

    if not records:
        if args.csv:
            print("")
        else:
            print("No review history found. Run a prompt review first to start tracking.")
        sys.exit(0)

    aggregated = aggregate_by_week(records)

    if args.csv:
        print(render_csv(aggregated, args.weeks))
    else:
        output = render_markdown(aggregated, args.weeks)
        # Append provider breakdown if not filtering to a single provider
        if not args.provider:
            provider_section = render_provider_breakdown(records)
            if provider_section:
                output += "\n" + provider_section
        print(output)


if __name__ == "__main__":
    main()
