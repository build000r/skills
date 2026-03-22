#!/usr/bin/env python3
"""
Log a shipped packet decision for later live-window observation.

Usage:
  generate_skill_evidence_packets.py --input /tmp/skill-review.json --json > /tmp/skill-packets.json
  log_skill_packet_decision.py --input /tmp/skill-packets.json --packet-id verification-gap-global
"""

from __future__ import annotations

import argparse
import json

from lib.skill_ship import SHIP_LEDGER_FILE, append_ship_record, build_ship_record, load_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a shipped operator-evidence packet decision")
    parser.add_argument("--input", required=True, help="Path to packet report JSON")
    parser.add_argument("--packet-id", required=True, help="Packet id to log")
    parser.add_argument(
        "--decision",
        choices=("ship", "revise", "discard"),
        default="ship",
        help="Decision taken for this packet",
    )
    parser.add_argument("--review", help="Optional baseline review JSON path")
    parser.add_argument("--skill-path", help="Optional path to the skill that was changed")
    parser.add_argument("--notes", help="Short note about the shipped change")
    args = parser.parse_args()

    packet_report = load_json(args.input)
    review_report = load_json(args.review) if args.review else None

    record = build_ship_record(
        packet_report=packet_report,
        packet_id=args.packet_id,
        decision=args.decision,
        notes=args.notes,
        skill_path=args.skill_path,
        review_report=review_report,
    )
    ledger_path = append_ship_record(record)

    print(json.dumps({"status": "saved", "ledger_file": str(ledger_path), "record": record}, indent=2))


if __name__ == "__main__":
    main()
