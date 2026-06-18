#!/usr/bin/env python3
"""
Persist prompt review scores to history file for trend tracking.

Usage:
  save_review.py --composite 0.74 --sessions 5 --prompts 32 \
    --clarity 2.5 --context 2.0 --autonomy 1.5 --constraints 1.0 \
    --checkpoints 1.5 --followup 2.0 --collaboration 2.5 \
    --adaptability 1.5 --outcome 2.5 \
    [--source both] [--provider claude] [--model opus] [--project /path/to/project] \
    [--improvements 'JSON'] [--strengths 'JSON'] \
    [--week 2025-W36]

For backfills, use --week to record the ORIGINAL week being reviewed (not today's week).

Improvements JSON format:
  [{"axis": "clarity", "score": 1.5, "tip": "Be specific", "example": "fix it"}]

Strengths JSON format:
  [{"axis": "collaboration", "score": 2.8, "observation": "Great redirects"}]

Appends a JSON record to ~/.claude/prompt-review-history.jsonl
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path.home() / ".claude" / "prompt-review-history.jsonl"

AXES = [
    "clarity", "context", "autonomy", "constraints",
    "checkpoints", "followup", "collaboration",
    "adaptability", "outcome",
]


def iso_week(dt: datetime) -> str:
    """Return ISO week string like '2025-W03'."""
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


def main():
    parser = argparse.ArgumentParser(description="Save prompt review scores to history")
    parser.add_argument("--composite", type=float, required=True, help="Composite score (0-1)")
    parser.add_argument("--sessions", type=int, required=True, help="Number of sessions reviewed")
    parser.add_argument("--prompts", type=int, required=True, help="Number of prompts reviewed")
    parser.add_argument("--source", default="both", help="Source: claude, codex, or both")
    parser.add_argument("--provider", default=None,
                        help="Provider/tool: claude, codex, amp, opencode, other")
    parser.add_argument("--model", default=None,
                        help="Model used: opus, sonnet, gpt-4o, etc.")
    parser.add_argument("--project", default=None, help="Project path if filtered")
    parser.add_argument("--improvements", default=None,
                        help="JSON array of top improvements: [{axis, score, tip, example}]")
    parser.add_argument("--strengths", default=None,
                        help="JSON array of strengths: [{axis, score, observation}]")
    parser.add_argument("--week", default=None,
                        help="Override week (e.g., 2025-W36) for backfills")

    for axis in AXES:
        parser.add_argument(f"--{axis}", type=float, required=True, help=f"{axis} score")

    args = parser.parse_args()
    now = datetime.now()

    # Parse JSON fields
    improvements = None
    if args.improvements:
        try:
            improvements = json.loads(args.improvements)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse --improvements as JSON", file=__import__('sys').stderr)

    strengths = None
    if args.strengths:
        try:
            strengths = json.loads(args.strengths)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse --strengths as JSON", file=__import__('sys').stderr)

    # Use provided week for backfills, otherwise today's week
    week = args.week if args.week else iso_week(now)

    record = {
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
        "week": week,
        "composite": round(args.composite, 3),
        "axes": {axis: round(getattr(args, axis), 1) for axis in AXES},
        "sessions": args.sessions,
        "prompts": args.prompts,
        "source": args.source,
        "provider": args.provider,
        "model": args.model,
        "project": args.project,
        "improvements": improvements,
        "strengths": strengths,
    }

    # Ensure directory exists
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(json.dumps({"status": "saved", "record": record}, indent=2))


if __name__ == "__main__":
    main()
