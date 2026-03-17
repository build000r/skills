#!/usr/bin/env python3
"""
Persist a reviewed skill-usage report to JSONL history for trend tracking.

Usage:
  review_skill_usage.py --skill skill-issue > /tmp/skill-review.json
  save_skill_review.py --input /tmp/skill-review.json

Appends a compact record to ~/.claude/skill-review-history.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib.skill_review import REVIEW_HISTORY_FILE, iso_week


def load_input(path: str) -> dict:
    """Load review JSON from a file path or stdin."""
    if path == "-":
        return json.load(sys.stdin)
    with open(Path(path), "r") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a skill review report to history")
    parser.add_argument("--input", required=True, help="Path to review JSON, or - for stdin")
    args = parser.parse_args()

    report = load_input(args.input)
    now = datetime.now(timezone.utc)

    record = {
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
        "week": iso_week(now),
        "skill": report.get("skill"),
        "source": report.get("source"),
        "invocations": report.get("invocations_found", 0),
        "sessions_scanned": report.get("sessions_scanned", 0),
        "last_invoked_at": report.get("last_invoked_at"),
        "providers": report.get("summary", {}).get("providers", {}),
        "metrics": report.get("summary", {}).get("metrics", {}),
        "opportunities": report.get("opportunities", []),
        "evidence_packet_summary": report.get("evidence_packets", {}).get("summary", {}),
        "marker_file": report.get("marker_file"),
    }

    REVIEW_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_HISTORY_FILE, "a") as handle:
        handle.write(json.dumps(record) + "\n")

    print(json.dumps({"status": "saved", "record": record}, indent=2))


if __name__ == "__main__":
    main()
