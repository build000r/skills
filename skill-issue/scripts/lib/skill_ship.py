"""
Helpers for logging shipped packet decisions against future live skill traffic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHIP_LEDGER_FILE = Path.home() / ".claude" / "skill-packet-ledger.jsonl"


def load_json(path: str) -> dict[str, Any]:
    """Load JSON from a file path."""
    with open(Path(path), "r") as handle:
        return json.load(handle)


def select_packet(packet_report: dict[str, Any], packet_id: str) -> dict[str, Any]:
    """Return one packet by id from a packet report."""
    for packet in packet_report.get("packets", []):
        if packet.get("packet_id") == packet_id:
            return packet
    raise KeyError(f"Packet id not found: {packet_id}")


def build_ship_record(
    packet_report: dict[str, Any],
    packet_id: str,
    decision: str,
    notes: str | None = None,
    skill_path: str | None = None,
    review_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ledger record for a shipped or discarded packet decision."""
    packet = select_packet(packet_report, packet_id)
    now = datetime.now(timezone.utc)

    baseline_metrics = (review_report or {}).get("summary", {}).get("metrics", {})
    watch_metric = packet.get("watch_metric")

    return {
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
        "skill": packet_report.get("skill"),
        "packet_id": packet.get("packet_id"),
        "issue_type": packet.get("issue_type"),
        "decision": decision,
        "expected_contract": packet.get("expected_contract"),
        "watch_metric": watch_metric,
        "baseline_watch_metric_value": baseline_metrics.get(watch_metric),
        "baseline_metrics": baseline_metrics,
        "experiment_unit": packet.get("experiment_unit"),
        "historical_reference_slice": packet.get("historical_reference_slice", {}),
        "post_ship_window": packet.get("post_ship_window", {}),
        "affected_runs": packet.get("affected_runs"),
        "total_runs": packet.get("total_runs"),
        "packet_report_generated_at": packet_report.get("generated_at"),
        "review_generated_at": (review_report or {}).get("generated_at"),
        "skill_path": skill_path,
        "notes": notes or "",
    }


def append_ship_record(record: dict[str, Any], path: Path = SHIP_LEDGER_FILE) -> Path:
    """Append one packet decision record to the ship ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        handle.write(json.dumps(record) + "\n")
    return path
